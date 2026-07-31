from app.documents.schemas import ValidationIssue

SUPPLIER_FIXABLE_CODES = {
    "vendor_name_required",
    "vendor_vat_id_required",
    "vendor_vat_id_invalid",
    "customer_name_required",
    "customer_name_mismatch",
    "customer_vat_id_required",
    "customer_vat_id_mismatch",
    "invoice_number_required",
    "invoice_date_required",
    "invoice_total_required",
    "invoice_total_non_positive",
    "currency_required",
    "due_date_before_invoice_date",
    "invoice_total_mismatch",
    "purchase_order_missing",
    "merchant_name_required",
    "transaction_date_required",
    "receipt_currency_required",
    "receipt_total_required",
    "receipt_total_non_positive",
    "receipt_vat_required",
    "receipt_total_mismatch",
}


def supplier_fixable_issues(
    issues: list[ValidationIssue],
) -> list[ValidationIssue]:
    return [issue for issue in issues if issue.code in SUPPLIER_FIXABLE_CODES]
