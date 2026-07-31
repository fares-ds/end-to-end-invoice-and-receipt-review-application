from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ComparisonStatus = Literal[
    "match",
    "different",
    "missing_in_llm",
    "missing_in_document_intelligence",
    "missing_in_both",
]


class LlmDocumentExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: Literal["invoice", "receipt", "unsupported"]
    expense_category: Literal["fuel", "meals", "travel", "supplies", "other"] | None
    vendor_name: str | None
    vendor_vat_id: str | None
    customer_name: str | None
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
    summary: str


class FieldComparison(BaseModel):
    field: str
    label: str
    status: ComparisonStatus
    document_intelligence_value: str | None
    llm_value: str | None


class DocumentReview(BaseModel):
    extraction: LlmDocumentExtraction | None = None
    comparisons: list[FieldComparison] = Field(default_factory=list)
    fallback_fields: list[FieldComparison] = Field(default_factory=list)
    error_message: str | None = None
