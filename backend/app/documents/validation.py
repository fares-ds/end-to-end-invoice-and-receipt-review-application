from decimal import Decimal

from stdnum.eu import vat

from app.documents.schemas import DocumentStatus, ReviewData, ValidationIssue

CORE_CONFIDENCE_FIELDS = {
    "vendor_name",
    "vendor_vat_id",
    "customer_name",
    "customer_vat_id",
    "invoice_number",
    "invoice_date",
    "invoice_total",
}
RECEIPT_CONFIDENCE_FIELDS = {
    "vendor_name",
    "invoice_date",
    "total_tax",
    "invoice_total",
}


def normalize_name(value: str) -> str:
    return " ".join(value.casefold().split())


def normalize_vat_id(value: str) -> str:
    return vat.compact(value)


def normalize_invoice_number(value: str) -> str:
    return " ".join(value.casefold().split())


def _issue(
    code: str,
    field: str | None,
    message: str,
    *,
    severity: str = "error",
) -> ValidationIssue:
    return ValidationIssue.model_validate(
        {"code": code, "field": field, "severity": severity, "message": message}
    )


def _validate_receipt(
    receipt: ReviewData, *, min_confidence: float
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not receipt.vendor_name:
        issues.append(
            _issue("merchant_name_required", "vendor_name", "Merchant name is required.")
        )
    if receipt.invoice_date is None:
        issues.append(
            _issue(
                "transaction_date_required",
                "invoice_date",
                "Transaction date is required.",
            )
        )
    if not receipt.currency:
        issues.append(
            _issue("receipt_currency_required", "currency", "Receipt currency is required.")
        )
    if receipt.invoice_total is None:
        issues.append(
            _issue("receipt_total_required", "invoice_total", "Receipt total is required.")
        )
    elif receipt.invoice_total <= 0:
        issues.append(
            _issue(
                "receipt_total_non_positive",
                "invoice_total",
                "Receipt total must be greater than zero.",
            )
        )
    if receipt.total_tax is None:
        issues.append(
            _issue("receipt_vat_required", "total_tax", "Receipt VAT total is required.")
        )
    if (
        receipt.subtotal is not None
        and receipt.total_tax is not None
        and receipt.invoice_total is not None
        and abs(receipt.subtotal + receipt.total_tax - receipt.invoice_total)
        > Decimal("0.01")
    ):
        issues.append(
            _issue(
                "receipt_total_mismatch",
                "invoice_total",
                "Receipt subtotal plus VAT does not match the total.",
            )
        )
    for field, confidence in receipt.field_confidence.items():
        if (
            field in RECEIPT_CONFIDENCE_FIELDS
            and receipt.field_sources.get(field) != "human"
            and confidence < min_confidence
        ):
            issues.append(
                _issue(
                    "low_confidence",
                    field,
                    (
                        f"Extraction confidence for {field.replace('_', ' ')} "
                        f"is below {min_confidence:.0%}."
                    ),
                    severity="warning",
                )
            )
    return issues


def validate_review_data(
    data: ReviewData,
    *,
    expected_customer_name: str,
    expected_customer_vat_id: str,
    min_confidence: float,
    is_duplicate: bool,
) -> list[ValidationIssue]:
    if data.document_type == "receipt":
        return _validate_receipt(data, min_confidence=min_confidence)

    issues: list[ValidationIssue] = []

    if not data.vendor_name:
        issues.append(_issue("vendor_name_required", "vendor_name", "Supplier name is required."))

    if not data.vendor_vat_id:
        issues.append(
            _issue("vendor_vat_id_required", "vendor_vat_id", "Supplier VAT number is required.")
        )
    elif not vat.is_valid(data.vendor_vat_id):
        issues.append(
            _issue(
                "vendor_vat_id_invalid",
                "vendor_vat_id",
                "Supplier VAT number has an invalid EU format or checksum.",
            )
        )

    if not data.customer_name:
        issues.append(
            _issue("customer_name_required", "customer_name", "Customer name is required.")
        )
    elif normalize_name(data.customer_name) != normalize_name(expected_customer_name):
        issues.append(
            _issue(
                "customer_name_mismatch",
                "customer_name",
                f"Customer must be {expected_customer_name}.",
            )
        )

    if not data.customer_vat_id:
        issues.append(
            _issue(
                "customer_vat_id_required",
                "customer_vat_id",
                "Customer VAT number is required.",
            )
        )
    elif normalize_vat_id(data.customer_vat_id) != normalize_vat_id(expected_customer_vat_id):
        issues.append(
            _issue(
                "customer_vat_id_mismatch",
                "customer_vat_id",
                "Customer VAT number does not match Northstar's configured VAT number.",
            )
        )

    if not data.invoice_number:
        issues.append(
            _issue("invoice_number_required", "invoice_number", "Invoice number is required.")
        )
    if data.invoice_date is None:
        issues.append(_issue("invoice_date_required", "invoice_date", "Invoice date is required."))
    if data.invoice_total is None:
        issues.append(
            _issue("invoice_total_required", "invoice_total", "Invoice total is required.")
        )
    elif data.invoice_total <= 0:
        issues.append(
            _issue(
                "invoice_total_non_positive",
                "invoice_total",
                "Invoice total must be greater than zero.",
            )
        )
    if not data.currency:
        issues.append(_issue("currency_required", "currency", "Currency is required."))

    if (
        data.invoice_date is not None
        and data.due_date is not None
        and data.due_date < data.invoice_date
    ):
        issues.append(
            _issue(
                "due_date_before_invoice_date",
                "due_date",
                "Due date cannot be before the invoice date.",
            )
        )

    if (
        data.subtotal is not None
        and data.total_tax is not None
        and data.invoice_total is not None
        and abs(data.subtotal + data.total_tax - data.invoice_total) > Decimal("0.01")
    ):
        issues.append(
            _issue(
                "invoice_total_mismatch",
                "invoice_total",
                "Subtotal plus VAT does not match the invoice total.",
            )
        )

    if is_duplicate:
        issues.append(
            _issue(
                "duplicate_invoice",
                "invoice_number",
                "A non-rejected invoice with this supplier and invoice number already exists.",
            )
        )

    if not data.purchase_order:
        issues.append(
            _issue(
                "purchase_order_missing",
                "purchase_order",
                "Purchase-order reference is missing.",
                severity="warning",
            )
        )

    for field, confidence in data.field_confidence.items():
        if (
            field in CORE_CONFIDENCE_FIELDS
            and data.field_sources.get(field) != "human"
            and confidence < min_confidence
        ):
            issues.append(
                _issue(
                    "low_confidence",
                    field,
                    (
                        f"Extraction confidence for {field.replace('_', ' ')} "
                        f"is below {min_confidence:.0%}."
                    ),
                    severity="warning",
                )
            )

    return issues


def status_for_issues(issues: list[ValidationIssue]) -> DocumentStatus:
    return "needs_review" if any(issue.severity == "error" for issue in issues) else "ready"


def issues_have_errors(issues: list[ValidationIssue]) -> bool:
    return any(issue.severity == "error" for issue in issues)
