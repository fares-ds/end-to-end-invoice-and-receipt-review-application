import json
import sys
from collections.abc import Mapping
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

# Running this file puts scripts/ on sys.path, not backend/. The project is not
# installed (package = false), so bootstrap the backend root before importing app.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import APP_CONFIG  # noqa: E402
from app.documents.projection import project_extraction  # noqa: E402
from app.documents.schemas import ReviewData  # noqa: E402
from app.documents.validation import validate_review_data  # noqa: E402
from app.schemas.invoice.mapping import map_invoice_result  # noqa: E402
from app.schemas.receipt.mapping import map_receipt_result  # noqa: E402
from app.services.local_extraction_service import LocalExtractionService  # noqa: E402

ROOT = Path(__file__).parents[2]
MANIFEST_PATH = ROOT / "samples" / "manifest.json"
SAMPLES_PATH = ROOT / "samples" / "generated"

DECIMAL_FIELDS = {"subtotal", "total_tax", "invoice_total", "amount_due"}
DATE_FIELDS = {"invoice_date", "due_date"}


def _normalized_text(value: Any) -> str:
    return " ".join(str(value).casefold().split())


def _equal(field: str, expected: Any, actual: Any) -> bool:
    if expected is None:
        return actual is None
    if actual is None:
        return False
    if field in DECIMAL_FIELDS:
        try:
            return Decimal(str(expected)) == Decimal(str(actual))
        except InvalidOperation:
            return False
    if field in DATE_FIELDS:
        actual_value = actual.isoformat() if isinstance(actual, date) else str(actual)
        return str(expected) == actual_value
    return _normalized_text(expected) == _normalized_text(actual)


def compare_review(expected: Mapping[str, Any], actual: ReviewData) -> dict[str, bool]:
    """Compare manifest fields while ignoring harmless display differences."""
    return {
        field: _equal(field, expected_value, getattr(actual, field, None))
        for field, expected_value in expected.items()
    }


def extract_review_data(
    service: LocalExtractionService, path: Path, document_type: str
) -> ReviewData:
    if document_type == "receipt":
        result = service.analyze_receipt(path)
        extraction = map_receipt_result(result)
    else:
        result = service.analyze_invoice(path)
        extraction = map_invoice_result(result)
    return project_extraction(extraction)


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    service = LocalExtractionService()

    matched_fields = 0
    total_fields = 0
    exact_documents = 0
    failures = 0
    policy_matches = 0

    print(f"Evaluating {len(manifest)} fictional financial documents\n")
    for entry in manifest:
        filename = entry["filename"]
        try:
            document_type = entry.get("document_type", "invoice")
            actual = extract_review_data(
                service, SAMPLES_PATH / filename, document_type
            )
            comparison = compare_review(entry["expected"], actual)
            issues = validate_review_data(
                actual,
                expected_customer_name=APP_CONFIG.expected_customer_name,
                expected_customer_vat_id=APP_CONFIG.expected_customer_vat_id,
                min_confidence=APP_CONFIG.min_field_confidence,
                is_duplicate=False,
            )
            # Duplicate sample needs a peer in the DB; evaluator reports codes without it.
            issue_codes = sorted(issue.code for issue in issues)
            expected_codes = sorted(entry.get("expected_issue_codes", []))
            # When duplicate is the only expected code, allow empty from this offline check.
            if expected_codes == ["duplicate_invoice"]:
                policy_ok = issue_codes == [] or issue_codes == expected_codes
            else:
                policy_ok = issue_codes == expected_codes
        except Exception as error:  # noqa: BLE001 - evaluator must continue through its corpus
            failures += 1
            print(f"FAIL  {filename:<36} provider error: {error}")
            continue

        matched = sum(comparison.values())
        total = len(comparison)
        mismatches = [field for field, is_match in comparison.items() if not is_match]
        matched_fields += matched
        total_fields += total
        exact_documents += not mismatches
        policy_matches += policy_ok
        detail = "all fields" if not mismatches else f"mismatch: {', '.join(mismatches)}"
        result = "PASS" if not mismatches else "PART"
        policy = "policy-ok" if policy_ok else f"policy={issue_codes} expected={expected_codes}"
        print(f"{result}  {filename:<36} {matched:>2}/{total}  {detail}  {policy}")

    accuracy = (matched_fields / total_fields * 100) if total_fields else 0
    print("\nSummary")
    print(f"  Field accuracy:     {matched_fields}/{total_fields} ({accuracy:.1f}%)")
    print(f"  Exact documents:   {exact_documents}/{len(manifest)}")
    print(f"  Policy matches:    {policy_matches}/{len(manifest)}")
    print(f"  Provider failures: {failures}/{len(manifest)}")


if __name__ == "__main__":
    main()
