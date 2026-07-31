from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.documents.schemas import FieldSource, ReviewData, ReviewLineItem
from app.schemas.common import ExtractedDate, ExtractedMoney, ExtractedNumber, ExtractedString
from app.schemas.invoice.model import InvoiceExtraction
from app.schemas.receipt.model import ReceiptExtraction


def _string(extracted: ExtractedString | None) -> str | None:
    return extracted.value if extracted is not None else None


def _date(extracted: ExtractedDate | None) -> date | None:
    return extracted.value if extracted is not None else None


def _money(extracted: ExtractedMoney | None) -> Decimal | None:
    return extracted.amount if extracted is not None else None


def _confidence(
    field_confidence: dict[str, float],
    field: str,
    extracted: ExtractedString | ExtractedDate | ExtractedMoney | ExtractedNumber | None,
) -> None:
    if extracted is not None and extracted.confidence is not None:
        field_confidence[field] = extracted.confidence


def _source(
    field_sources: dict[str, FieldSource],
    field: str,
    value: object | None,
) -> None:
    if value is not None:
        field_sources[field] = "document_intelligence"


def project_invoice_extraction(extraction: InvoiceExtraction) -> ReviewData:
    field_confidence: dict[str, float] = {}
    field_sources: dict[str, FieldSource] = {}

    vendor_name = _string(extraction.vendor_name)
    vendor_vat_id = _string(extraction.vendor_tax_id)
    customer_name = _string(extraction.customer_name)
    customer_vat_id = _string(extraction.customer_tax_id)
    invoice_number = _string(extraction.invoice_id)
    purchase_order = _string(extraction.purchase_order)
    invoice_date = _date(extraction.invoice_date)
    due_date = _date(extraction.due_date)
    subtotal = _money(extraction.subtotal)
    total_tax = _money(extraction.total_tax)
    invoice_total = _money(extraction.invoice_total)
    amount_due = _money(extraction.amount_due)

    currency = None
    if extraction.invoice_total and extraction.invoice_total.currency_code:
        currency = extraction.invoice_total.currency_code
    elif extraction.subtotal and extraction.subtotal.currency_code:
        currency = extraction.subtotal.currency_code

    _confidence(field_confidence, "vendor_name", extraction.vendor_name)
    _confidence(field_confidence, "vendor_vat_id", extraction.vendor_tax_id)
    _confidence(field_confidence, "customer_name", extraction.customer_name)
    _confidence(field_confidence, "customer_vat_id", extraction.customer_tax_id)
    _confidence(field_confidence, "invoice_number", extraction.invoice_id)
    _confidence(field_confidence, "purchase_order", extraction.purchase_order)
    _confidence(field_confidence, "invoice_date", extraction.invoice_date)
    _confidence(field_confidence, "due_date", extraction.due_date)
    _confidence(field_confidence, "subtotal", extraction.subtotal)
    _confidence(field_confidence, "total_tax", extraction.total_tax)
    _confidence(field_confidence, "invoice_total", extraction.invoice_total)
    _confidence(field_confidence, "amount_due", extraction.amount_due)

    for field, value in (
        ("vendor_name", vendor_name),
        ("vendor_vat_id", vendor_vat_id),
        ("customer_name", customer_name),
        ("customer_vat_id", customer_vat_id),
        ("invoice_number", invoice_number),
        ("purchase_order", purchase_order),
        ("invoice_date", invoice_date),
        ("due_date", due_date),
        ("currency", currency),
        ("subtotal", subtotal),
        ("total_tax", total_tax),
        ("invoice_total", invoice_total),
        ("amount_due", amount_due),
    ):
        _source(field_sources, field, value)

    line_items = [
        ReviewLineItem(
            description=_string(item.description),
            quantity=item.quantity.value if item.quantity else None,
            unit_price=_money(item.unit_price),
            amount=_money(item.amount),
        )
        for item in extraction.items
    ]

    return ReviewData(
        document_type="invoice",
        vendor_name=vendor_name,
        vendor_vat_id=vendor_vat_id,
        customer_name=customer_name,
        customer_vat_id=customer_vat_id,
        invoice_number=invoice_number,
        purchase_order=purchase_order,
        invoice_date=invoice_date,
        due_date=due_date,
        currency=currency,
        subtotal=subtotal,
        total_tax=total_tax,
        invoice_total=invoice_total,
        amount_due=amount_due,
        line_items=line_items,
        field_confidence=field_confidence,
        field_sources=field_sources,
    )


def project_receipt_extraction(extraction: ReceiptExtraction) -> ReviewData:
    field_confidence: dict[str, float] = {}
    field_sources: dict[str, FieldSource] = {}

    vendor_name = _string(extraction.merchant_name)
    invoice_date = _date(extraction.transaction_date)
    subtotal = _money(extraction.subtotal)
    total_tax = _money(extraction.total_tax)
    invoice_total = _money(extraction.total)

    currency = None
    if extraction.total and extraction.total.currency_code:
        currency = extraction.total.currency_code
    elif extraction.subtotal and extraction.subtotal.currency_code:
        currency = extraction.subtotal.currency_code

    _confidence(field_confidence, "vendor_name", extraction.merchant_name)
    _confidence(field_confidence, "invoice_date", extraction.transaction_date)
    _confidence(field_confidence, "subtotal", extraction.subtotal)
    _confidence(field_confidence, "total_tax", extraction.total_tax)
    _confidence(field_confidence, "invoice_total", extraction.total)

    for field, value in (
        ("vendor_name", vendor_name),
        ("invoice_date", invoice_date),
        ("currency", currency),
        ("subtotal", subtotal),
        ("total_tax", total_tax),
        ("invoice_total", invoice_total),
        ("amount_due", invoice_total),
    ):
        _source(field_sources, field, value)

    line_items = [
        ReviewLineItem(
            description=_string(item.description),
            quantity=item.quantity.value if item.quantity else None,
            unit_price=_money(item.price),
            amount=_money(item.total_price),
        )
        for item in extraction.items
    ]

    return ReviewData(
        document_type="receipt",
        vendor_name=vendor_name,
        invoice_date=invoice_date,
        currency=currency,
        subtotal=subtotal,
        total_tax=total_tax,
        invoice_total=invoice_total,
        amount_due=invoice_total,
        line_items=line_items,
        field_confidence=field_confidence,
        field_sources=field_sources,
    )


def project_extraction(extraction: InvoiceExtraction | ReceiptExtraction) -> ReviewData:
    if isinstance(extraction, InvoiceExtraction):
        return project_invoice_extraction(extraction)
    return project_receipt_extraction(extraction)
