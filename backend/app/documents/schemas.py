from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.accounting.schemas import AccountingCoding
from app.document_review.schemas import DocumentReview

DocumentStatus = Literal[
    "processing",
    "ready",
    "needs_review",
    "approved",
    "rejected",
    "failed",
]
IssueSeverity = Literal["error", "warning"]
DocumentType = Literal["invoice", "receipt"]
ExpenseCategory = Literal["fuel", "meals", "travel", "supplies", "other"]
FieldSource = Literal["document_intelligence", "llm_fallback", "human"]


class ReviewLineItem(BaseModel):
    description: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None


class ReviewData(BaseModel):
    """Flat review projection used for policy, Maya edits, and approval."""

    document_type: DocumentType = "invoice"
    expense_category: ExpenseCategory | None = None
    vendor_name: str | None = None
    vendor_vat_id: str | None = None
    customer_name: str | None = None
    customer_vat_id: str | None = None
    invoice_number: str | None = None
    purchase_order: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    currency: str | None = None
    subtotal: Decimal | None = None
    total_tax: Decimal | None = None
    invoice_total: Decimal | None = None
    amount_due: Decimal | None = None
    line_items: list[ReviewLineItem] = Field(default_factory=list)
    field_confidence: dict[str, float] = Field(default_factory=dict)
    field_sources: dict[str, FieldSource] = Field(default_factory=dict)


class ValidationIssue(BaseModel):
    code: str
    field: str | None
    severity: IssueSeverity
    message: str


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_filename: str
    content_type: str
    status: DocumentStatus
    classification: dict[str, Any] | None = None
    extraction: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None
    gl_suggestion: dict[str, Any] | None = None
    review_data: ReviewData | None = None
    document_review: DocumentReview | None = None
    accounting_coding: AccountingCoding | None = None
    issues: list[ValidationIssue] = Field(default_factory=list)
    supplier_action_required: bool = False
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class DocumentCorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vendor_name: str | None = None
    vendor_vat_id: str | None = None
    customer_name: str | None = None
    customer_vat_id: str | None = None
    invoice_number: str | None = None
    purchase_order: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    currency: str | None = None
    subtotal: Decimal | None = None
    total_tax: Decimal | None = None
    invoice_total: Decimal | None = None
    amount_due: Decimal | None = None


class DecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
