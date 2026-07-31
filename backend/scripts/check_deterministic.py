"""Verify the deterministic parts of the pipeline.

These functions decide what a reviewer sees and what blocks approval, and none of
them call a model, so their behaviour must be exactly reproducible. This script
is the guard for that: it makes no network calls, needs no Ollama, runs in
milliseconds, and exits non-zero on the first behaviour that drifts.

Run it before and after touching OCR parsing, VAT repair, confidence scoring, or
the Northstar rules:

    uv run --locked --no-sync python scripts/check_deterministic.py
"""

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

# Running this file puts scripts/ on sys.path, not backend/. The project is not
# installed (package = false), so bootstrap the backend root before importing app.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import APP_CONFIG, get_settings  # noqa: E402
from app.documents.schemas import ReviewData  # noqa: E402
from app.documents.validation import validate_review_data  # noqa: E402
from app.services.local_extraction_service import _FieldBuilder, repair_vat_id  # noqa: E402
from app.services.ocr_text_service import OcrTextService  # noqa: E402

SAMPLES = Path(__file__).resolve().parents[2] / "samples" / "generated"

_failures: list[str] = []
_passed = 0


def check(name: str, actual: object, expected: object) -> None:
    global _passed
    if actual == expected:
        _passed += 1
        return
    _failures.append(f"{name}\n      expected: {expected!r}\n      actual:   {actual!r}")


def check_vat_repair() -> None:
    """OCR confusion is corrected, but only when the correction actually helps."""
    # Tesseract reads the digit zero as a letter O; the repair must recover a
    # valid identifier without disturbing the structural B of a Dutch VAT number.
    check("vat: repairs O/0 confusion", repair_vat_id("NLO0449544B01"), "NL00449544B01")
    check("vat: repairs G/6 confusion", repair_vat_id("DE13G695976"), "DE136695976")
    check("vat: strips separators", repair_vat_id("NL 0044 9544 B01"), "NL00449544B01")

    # A value that cannot be repaired is evidence the reviewer may have to quote
    # back to the supplier, so it must survive exactly as it was read.
    check("vat: leaves unrepairable value intact", repair_vat_id("DE-NOT-A-VAT"), "DE-NOT-A-VAT")

    # Already-valid identifiers must pass through untouched.
    check("vat: valid NL untouched", repair_vat_id("NL123456782B90"), "NL123456782B90")
    check("vat: valid FR untouched", repair_vat_id("FR61954506077"), "FR61954506077")

    check("vat: none stays none", repair_vat_id(None), None)
    check("vat: blank becomes none", repair_vat_id("   "), None)


def check_ocr_line_structure() -> None:
    """Recovered text keeps the page's lines, which bind a label to its amount.

    Flattening the page into one stream let a fuel grade ("EURO 95") be read as a
    subtotal and a litre count ("25.00 L") as VAT.
    """
    ocr = OcrTextService(get_settings())
    receipt = SAMPLES / "13-nl-fuel-receipt.png"
    lines = [line.strip() for line in ocr.extract(receipt, "image/png").text.splitlines()]

    check("ocr: document type stands alone", "KASSABON" in lines, True)
    check("ocr: label keeps its amount", "Subtotaal excl. BTW EUR 50.00" in lines, True)
    check("ocr: VAT line intact", "BTW 21% EUR 10.50" in lines, True)
    check("ocr: total line intact", "TOTAAL EUR 60.50" in lines, True)
    # The fuel grade must not be adjacent to the money column.
    check("ocr: fuel grade isolated", "EURO 95" in lines, True)
    check("ocr: page is not one flat line", len(lines) > 5, True)


def check_pdf_text_layer() -> None:
    """A PDF carrying a text layer is read exactly, not re-OCRed."""
    ocr = OcrTextService(get_settings())
    document = ocr.extract(SAMPLES / "01-en-happy-classic.pdf", "application/pdf")
    check("pdf: uses embedded text layer", document.source, "pdf_text_layer")
    check("pdf: exact text is full confidence", document.confidence, 1.0)
    check("pdf: recovers the invoice number", "EN-2026-1001" in document.text, True)


def check_confidence_scoring() -> None:
    """Confidence expresses how well the page was read, not how it was normalized.

    The extraction prompt requires ISO dates and the VAT repair rewrites OCR
    damage on purpose, so neither may be scored as an inference. A value that is
    genuinely absent from the page still must be.
    """
    # A date printed day-first still counts as read, because ISO output is mandated.
    day_first = _FieldBuilder("Datum: 19-07-2026 Tijd: 14:32", 0.95)
    check("confidence: day-first date is read", day_first.date("2026-07-19")["confidence"], 0.95)

    dotted = _FieldBuilder("Rechnungsdatum 1.7.2026", 0.95)
    check("confidence: dotted date is read", dotted.date("2026-07-01")["confidence"], 0.95)

    # A date nowhere on the page is an inference and must be penalised.
    absent = _FieldBuilder("no date printed anywhere", 0.95)
    check("confidence: absent date penalised", absent.date("2026-07-01")["confidence"], 0.7125)

    # A repaired VAT is scored against what was read, not the correction.
    repaired = _FieldBuilder("VAT number: NLO0449544B01", 0.9376)
    field = repaired.corrected_string("NLO0449544B01", "NL00449544B01")
    check("confidence: repaired VAT keeps score", field["confidence"], 0.9376)
    check("confidence: repaired VAT stores correction", field["valueString"], "NL00449544B01")
    check("confidence: repaired VAT keeps evidence", field["content"], "NLO0449544B01")

    # Verbatim text keeps full confidence; invented text does not.
    verbatim = _FieldBuilder("Bright Spark Europe S.A.S.", 1.0)
    read = verbatim.string("Bright Spark Europe S.A.S.")
    check("confidence: verbatim value", read["confidence"], 1.0)
    check("confidence: invented value penalised", verbatim.string("Acme Ltd")["confidence"], 0.75)


def _review(**overrides: object) -> ReviewData:
    """A valid invoice, so each check can change exactly one thing."""
    base = {
        "document_type": "invoice",
        "vendor_name": "Helder Schoonmaak B.V.",
        "vendor_vat_id": "NL123456782B90",
        "customer_name": APP_CONFIG.expected_customer_name,
        "customer_vat_id": APP_CONFIG.expected_customer_vat_id,
        "invoice_number": "NL-2026-2042",
        "invoice_date": date(2026, 7, 1),
        "due_date": date(2026, 7, 31),
        "purchase_order": "PO-4002",
        "currency": "EUR",
        "subtotal": Decimal("240.00"),
        "total_tax": Decimal("50.40"),
        "invoice_total": Decimal("290.40"),
    }
    base.update(overrides)
    return ReviewData(**base)


def _codes(data: ReviewData, *, is_duplicate: bool = False) -> list[str]:
    issues = validate_review_data(
        data,
        expected_customer_name=APP_CONFIG.expected_customer_name,
        expected_customer_vat_id=APP_CONFIG.expected_customer_vat_id,
        min_confidence=APP_CONFIG.min_field_confidence,
        is_duplicate=is_duplicate,
    )
    return sorted(issue.code for issue in issues)


def check_northstar_rules() -> None:
    """The Northstar rulebook decides what blocks approval. Nothing else may."""
    check("rules: a valid invoice raises nothing", _codes(_review()), [])

    check("rules: supplier VAT required", _codes(_review(vendor_vat_id=None)),
          ["vendor_vat_id_required"])
    check("rules: malformed supplier VAT", _codes(_review(vendor_vat_id="DE-NOT-A-VAT")),
          ["vendor_vat_id_invalid"])
    check("rules: customer VAT must be Northstar's",
          _codes(_review(customer_vat_id="FR40303265045")), ["customer_vat_id_mismatch"])
    check("rules: invoice number required", _codes(_review(invoice_number=None)),
          ["invoice_number_required"])

    # Totals must reconcile within one cent.
    check("rules: total mismatch blocks", _codes(_review(invoice_total=Decimal("125.00"))),
          ["invoice_total_mismatch"])
    check("rules: one cent is tolerated",
          _codes(_review(invoice_total=Decimal("290.41"))), [])

    check("rules: non-positive total blocks", _codes(_review(
        subtotal=Decimal("0.00"), total_tax=Decimal("0.00"), invoice_total=Decimal("0.00"))),
        ["invoice_total_non_positive"])
    check("rules: due date before invoice date blocks",
          _codes(_review(due_date=date(2026, 6, 1))), ["due_date_before_invoice_date"])

    # Missing PO is a warning, not a blocker.
    check("rules: missing PO warns only", _codes(_review(purchase_order=None)),
          ["purchase_order_missing"])
    check("rules: duplicate blocks", _codes(_review(), is_duplicate=True),
          ["duplicate_invoice"])


def check_independent_reading_route() -> None:
    """The review must be able to read a PDF by a different route than primary.

    Re-reading the same text layer made agreement between the two paths
    meaningless. Forcing OCR gives a second genuine reading of equal content.
    """
    ocr = OcrTextService(get_settings())
    pdf = SAMPLES / "01-en-happy-classic.pdf"

    primary = ocr.extract(pdf, "application/pdf")
    independent = ocr.extract(pdf, "application/pdf", prefer_text_layer=False)

    check("independence: primary uses text layer", primary.source, "pdf_text_layer")
    check("independence: review uses OCR", independent.source, "tesseract")
    check("independence: routes differ", primary.text != independent.text, True)

    # A different route is only useful if it recovers the same facts.
    for token in ("FR61954506077", "NL00449544B01", "EN-2026-1001", "121.00"):
        check(f"independence: OCR route recovers {token}", token in independent.text, True)

    # An image has only one route, so both paths necessarily share a source.
    receipt = SAMPLES / "13-nl-fuel-receipt.png"
    forced = ocr.extract(receipt, "image/png", prefer_text_layer=False)
    check("independence: image has one route only", forced.source, "tesseract")


CHECKS = [
    check_vat_repair,
    check_independent_reading_route,
    check_ocr_line_structure,
    check_pdf_text_layer,
    check_confidence_scoring,
    check_northstar_rules,
]


def main() -> int:
    for group in CHECKS:
        group()

    if _failures:
        print(f"FAIL  {len(_failures)} behaviour(s) drifted, {_passed} passed\n")
        for failure in _failures:
            print(f"  --> {failure}")
        return 1

    print(f"PASS  {_passed} deterministic behaviours verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
