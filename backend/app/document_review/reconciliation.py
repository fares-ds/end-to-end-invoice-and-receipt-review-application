import re
from collections.abc import Callable
from datetime import date
from decimal import Decimal, InvalidOperation

from app.document_review.schemas import DocumentReview, FieldComparison, LlmDocumentExtraction
from app.documents.schemas import ReviewData

FIELDS = (
    ("vendor_name", "Supplier", "text"),
    ("vendor_vat_id", "Supplier VAT number", "identifier"),
    ("customer_name", "Customer", "text"),
    ("customer_vat_id", "Customer VAT number", "identifier"),
    ("invoice_number", "Invoice number", "identifier"),
    ("purchase_order", "Purchase order", "identifier"),
    ("invoice_date", "Invoice date", "date"),
    ("due_date", "Due date", "date"),
    ("currency", "Currency", "identifier"),
    ("subtotal", "Subtotal", "amount"),
    ("total_tax", "Tax", "amount"),
    ("invoice_total", "Invoice total", "amount"),
    ("amount_due", "Amount due", "amount"),
)


def _shown(value: object | None) -> str | None:
    if value is None:
        return None
    return str(value).strip() or None


def _text(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _identifier(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return value.strip().casefold()


def _amount(value: str) -> str:
    try:
        return str(Decimal(value.replace(",", ".")).normalize())
    except InvalidOperation:
        return value.strip().casefold()


NORMALIZERS: dict[str, Callable[[str], str]] = {
    "text": _text,
    "identifier": _identifier,
    "date": _date,
    "amount": _amount,
}


def reconcile_document_extractions(
    review_data: ReviewData,
    extraction: LlmDocumentExtraction,
) -> DocumentReview:
    comparisons: list[FieldComparison] = []
    for field, label, normalizer_name in FIELDS:
        document_intelligence_value = _shown(getattr(review_data, field))
        llm_value = _shown(getattr(extraction, field))
        if document_intelligence_value is None and llm_value is None:
            comparison_status = "missing_in_both"
        elif llm_value is None:
            comparison_status = "missing_in_llm"
        elif document_intelligence_value is None:
            comparison_status = "missing_in_document_intelligence"
        else:
            normalizer = NORMALIZERS[normalizer_name]
            comparison_status = (
                "match"
                if normalizer(document_intelligence_value) == normalizer(llm_value)
                else "different"
            )
        comparisons.append(
            FieldComparison(
                field=field,
                label=label,
                status=comparison_status,
                document_intelligence_value=document_intelligence_value,
                llm_value=llm_value,
            )
        )

    return DocumentReview(
        extraction=extraction,
        comparisons=comparisons,
    )


def _fallback_value(field: str, value: str) -> object | None:
    if field in {"invoice_date", "due_date"}:
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    if field in {"subtotal", "total_tax", "invoice_total", "amount_due"}:
        try:
            return Decimal(value.replace(",", "."))
        except InvalidOperation:
            return None
    return value.strip() or None


def merge_document_extractions(
    primary: ReviewData,
    extraction: LlmDocumentExtraction,
) -> tuple[ReviewData, DocumentReview]:
    review = reconcile_document_extractions(primary, extraction)
    merged_values = primary.model_dump()
    field_sources = dict(primary.field_sources)
    fallback_fields: list[FieldComparison] = []

    for field, _label, _normalizer_name in FIELDS:
        primary_value = getattr(primary, field)
        if _shown(primary_value) is not None:
            field_sources.setdefault(field, "document_intelligence")
            continue

        llm_value = _shown(getattr(extraction, field))
        if llm_value is None:
            continue
        parsed_value = _fallback_value(field, llm_value)
        if parsed_value is None:
            continue
        merged_values[field] = parsed_value
        field_sources[field] = "llm_fallback"
        fallback_fields.append(
            next(item for item in review.comparisons if item.field == field)
        )

    merged_values["document_type"] = primary.document_type
    merged_values["expense_category"] = (
        extraction.expense_category if primary.document_type == "receipt" else None
    )
    merged_values["field_sources"] = field_sources
    review.fallback_fields = fallback_fields
    return ReviewData.model_validate(merged_values), review
