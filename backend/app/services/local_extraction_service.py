"""Local replacement for the hosted prebuilt-invoice and prebuilt-receipt models.

Text is recovered by :mod:`app.services.ocr_text_service` and structured by a
local Ollama model under a strict JSON schema. The result is emitted in the same
``AnalyzeResult`` dictionary shape the hosted service returned, so
``app.schemas.invoice.mapping`` and ``app.schemas.receipt.mapping`` — and every
consumer downstream of them — remain unchanged.

Confidence is real rather than invented: it starts from the OCR confidence for
the document and is reduced for any value that does not appear verbatim in the
recovered text, which marks it as reformatted or inferred by the model.
"""

from __future__ import annotations

import json
import logging
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from app.config import Settings, get_settings
from app.providers.ollama_client import build_ollama_client
from app.providers.structured_output import build_request, parse_json_object
from app.services.ocr_text_service import OcrDocument, OcrError, OcrTextService

logger = logging.getLogger(__name__)

LOCAL_INVOICE_MODEL = "local-invoice"
LOCAL_RECEIPT_MODEL = "local-receipt"

# A value the model reformatted or inferred rather than copied is still usable,
# but it should not carry the same confidence as text read straight off the page.
INFERRED_VALUE_PENALTY = 0.75

INVOICE_INSTRUCTIONS = """
You extract fields from the OCR text of a European supplier invoice. Copy values exactly as
they appear; do not compute, correct, or infer values that are absent. Return dates as
YYYY-MM-DD. Return monetary values as plain decimal strings with a dot separator and no
currency symbol or thousands separator. Return the currency as a 3-letter ISO code. Use null
for any field that is not present in the text. Return only the fields defined by the schema
and no others. Do not decide whether the invoice is valid.
""".strip()

RECEIPT_INSTRUCTIONS = """
You extract fields from the OCR text of a European purchase receipt. Copy values exactly as
they appear; do not compute, correct, or infer values that are absent. Return dates as
YYYY-MM-DD. Return monetary values as plain decimal strings with a dot separator and no
currency symbol. Return the currency as a 3-letter ISO code. Set receipt_type to the expense
category: one of fuel, meals, travel, supplies, or other. Use null for any field not present
in the text. Return only the fields defined by the schema and no others.
""".strip()


class LocalExtractionError(RuntimeError):
    pass


class InvoiceFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vendor_name: str | None
    vendor_address: str | None
    vendor_vat_id: str | None
    customer_name: str | None
    customer_address: str | None
    customer_vat_id: str | None
    invoice_number: str | None
    purchase_order: str | None
    invoice_date: str | None
    due_date: str | None
    currency: str | None
    subtotal: str | None
    total_tax: str | None
    invoice_total: str | None
    amount_due: str | None


class ReceiptFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    merchant_name: str | None
    merchant_address: str | None
    transaction_date: str | None
    transaction_time: str | None
    receipt_type: str | None
    currency: str | None
    subtotal: str | None
    total_tax: str | None
    total: str | None


# Characters tesseract most often substitutes where a digit belongs.
LETTER_TO_DIGIT = {
    "O": "0", "Q": "0", "D": "0", "I": "1", "L": "1",
    "S": "5", "B": "8", "Z": "2", "G": "6",
}

# Countries whose VAT identifier is a country code followed only by digits.
NUMERIC_BODY_COUNTRIES = frozenset(
    {"DE", "BE", "IT", "LU", "PT", "DK", "FI", "GR", "SI", "CZ", "SK", "PL", "EE", "HR"}
)


def _digits_only(body: str) -> str:
    return "".join(LETTER_TO_DIGIT.get(character, character) for character in body)


def repair_vat_id(raw: str | None) -> str | None:
    """Undo common OCR letter/digit confusion inside a VAT identifier.

    Tesseract reads ``NL00449544B01`` as ``NLO0449544B01``. Repair is driven by each
    country's shape rather than a fixed length, because the corpus contains VAT IDs
    that are shorter than the official specification. Only positions that must hold a
    digit are rewritten, so the structural ``B`` in a Dutch VAT ID and the alphanumeric
    prefix of a French one survive.

    This only cleans up character recognition. ``python-stdnum`` still performs the
    real structure and checksum validation downstream.
    """
    if raw is None:
        return None
    cleaned = re.sub(r"[\s.\-/]", "", raw).upper()
    if len(cleaned) < 3 or not cleaned[:2].isalpha():
        return cleaned or None

    country, body = cleaned[:2], cleaned[2:]

    if country in NUMERIC_BODY_COUNTRIES:
        return country + _digits_only(body)
    if country == "NL":
        # Dutch VAT is digits, a literal B, then digits. Split on the final B so the
        # separator is preserved while both numeric runs are repaired.
        head, separator, tail = body.rpartition("B")
        if separator:
            return f"{country}{_digits_only(head)}B{_digits_only(tail)}"
        return country + _digits_only(body)
    if country == "FR":
        # Two alphanumeric check characters, then the SIREN digits.
        return country + body[:2] + _digits_only(body[2:])
    if country == "AT":
        # Always a literal U followed by digits.
        return country + body[:1] + _digits_only(body[1:])
    if country == "ES":
        # First and last positions may legitimately be letters.
        if len(body) >= 2:
            return country + body[0] + _digits_only(body[1:-1]) + body[-1]
        return cleaned
    return cleaned


def _decimal_or_none(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    cleaned = re.sub(r"[^\d.\-]", "", str(raw).strip().replace(",", "."))
    if not cleaned or cleaned in {"-", "."}:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _iso_date_or_none(raw: str | None) -> str | None:
    if not raw:
        return None
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(raw))
    return match.group(0) if match else None


class _FieldBuilder:
    """Build hosted-service-shaped field dictionaries with grounded confidence."""

    def __init__(self, ocr_text: str, base_confidence: float) -> None:
        self._haystack = re.sub(r"[\s]", "", ocr_text).upper()
        self._base = base_confidence

    def _confidence(self, raw: str | None) -> float:
        if not raw:
            return self._base
        needle = re.sub(r"[\s]", "", str(raw)).upper()
        if needle and needle in self._haystack:
            return round(self._base, 4)
        return round(self._base * INFERRED_VALUE_PENALTY, 4)

    def string(self, raw: str | None) -> dict[str, Any] | None:
        if not raw:
            return None
        return {
            "valueString": raw,
            "content": raw,
            "confidence": self._confidence(raw),
        }

    def date(self, raw: str | None) -> dict[str, Any] | None:
        iso = _iso_date_or_none(raw)
        if iso is None:
            return None
        return {"valueDate": iso, "content": raw, "confidence": self._confidence(raw)}

    def money(self, raw: str | None, currency: str | None) -> dict[str, Any] | None:
        amount = _decimal_or_none(raw)
        if amount is None:
            return None
        return {
            "valueCurrency": {
                "amount": float(amount),
                "currencyCode": (currency or "EUR").upper(),
            },
            "content": raw,
            "confidence": self._confidence(raw),
        }

    def address(self, raw: str | None) -> dict[str, Any] | None:
        if not raw:
            return None
        return {"content": raw, "confidence": self._confidence(raw)}


def _prune(fields: dict[str, Any | None]) -> dict[str, Any]:
    return {name: value for name, value in fields.items() if value is not None}


class LocalExtractionService:
    """Structure locally recovered document text into the hosted result shape."""

    def __init__(
        self,
        settings: Settings | None = None,
        ocr_service: OcrTextService | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._ocr = ocr_service or OcrTextService(self._settings)
        self._client = build_ollama_client(self._settings)

    def analyze_invoice(self, document_path: Path) -> dict[str, Any]:
        ocr = self._read(document_path)
        fields = self._structure(ocr.text, InvoiceFields, INVOICE_INSTRUCTIONS)
        return self._build_invoice_result(fields, ocr)

    def analyze_receipt(self, document_path: Path) -> dict[str, Any]:
        ocr = self._read(document_path)
        fields = self._structure(ocr.text, ReceiptFields, RECEIPT_INSTRUCTIONS)
        return self._build_receipt_result(fields, ocr)

    @staticmethod
    def to_dict(result: dict[str, Any]) -> dict[str, Any]:
        """Kept so callers written against the hosted service keep working."""
        return result

    def _read(self, document_path: Path) -> OcrDocument:
        content_type = _content_type_for(document_path)
        try:
            ocr = self._ocr.extract(document_path, content_type)
        except OcrError as error:
            raise LocalExtractionError(str(error)) from error
        if not ocr.text.strip():
            raise LocalExtractionError(
                "No text could be recovered from the document. "
                "The file may be blank or too low-resolution to read."
            )
        logger.info(
            "Recovered %d characters via %s (confidence=%.2f)",
            len(ocr.text),
            ocr.source,
            ocr.confidence,
        )
        return ocr

    def _structure[T: BaseModel](
        self, text: str, schema_model: type[T], instructions: str
    ) -> T:
        request = build_request(
            model=self._settings.ollama_model,
            system=instructions,
            user=text,
            schema=schema_model.model_json_schema(),
            schema_name=schema_model.__name__,
            prompted=self._settings.prompted_output(),
        )
        try:
            response = self._client.chat.completions.create(**request)
        except Exception as error:
            raise LocalExtractionError(
                f"The local model {self._settings.ollama_model!r} at "
                f"{self._settings.ollama_base_url} could not complete the request: {error}. "
                "Confirm Ollama is running, the model is pulled, and enough memory is free."
            ) from error

        content = response.choices[0].message.content or ""
        try:
            return schema_model.model_validate(parse_json_object(content))
        except (json.JSONDecodeError, ValidationError, TypeError) as error:
            raise LocalExtractionError(
                "The local model did not return valid structured extraction output."
            ) from error

    def _build_invoice_result(
        self, extracted: InvoiceFields, ocr: OcrDocument
    ) -> dict[str, Any]:
        build = _FieldBuilder(ocr.text, ocr.confidence)
        currency = extracted.currency
        fields = _prune(
            {
                "VendorName": build.string(extracted.vendor_name),
                "VendorAddress": build.address(extracted.vendor_address),
                "VendorTaxId": build.string(repair_vat_id(extracted.vendor_vat_id)),
                "CustomerName": build.string(extracted.customer_name),
                "CustomerAddress": build.address(extracted.customer_address),
                "CustomerTaxId": build.string(repair_vat_id(extracted.customer_vat_id)),
                "InvoiceId": build.string(extracted.invoice_number),
                "PurchaseOrder": build.string(extracted.purchase_order),
                "InvoiceDate": build.date(extracted.invoice_date),
                "DueDate": build.date(extracted.due_date),
                "SubTotal": build.money(extracted.subtotal, currency),
                "TotalTax": build.money(extracted.total_tax, currency),
                "InvoiceTotal": build.money(extracted.invoice_total, currency),
                "AmountDue": build.money(extracted.amount_due, currency),
            }
        )
        return {
            "modelId": LOCAL_INVOICE_MODEL,
            "documents": [{"docType": "invoice", "fields": fields}],
        }

    def _build_receipt_result(
        self, extracted: ReceiptFields, ocr: OcrDocument
    ) -> dict[str, Any]:
        build = _FieldBuilder(ocr.text, ocr.confidence)
        currency = extracted.currency
        fields = _prune(
            {
                "MerchantName": build.string(extracted.merchant_name),
                "MerchantAddress": build.address(extracted.merchant_address),
                "TransactionDate": build.date(extracted.transaction_date),
                "ReceiptType": build.string(extracted.receipt_type),
                "Subtotal": build.money(extracted.subtotal, currency),
                "TotalTax": build.money(extracted.total_tax, currency),
                "Total": build.money(extracted.total, currency),
            }
        )
        return {
            "modelId": LOCAL_RECEIPT_MODEL,
            "documents": [{"docType": "receipt", "fields": fields}],
        }


def _content_type_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "application/pdf"
    if suffix == ".png":
        return "image/png"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    raise LocalExtractionError(f"Unsupported document type {suffix!r}.")
