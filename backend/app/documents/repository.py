from __future__ import annotations

from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.accounting.schemas import AccountingCoding
from app.document_review.schemas import DocumentReview
from app.documents.models import DocumentRecord
from app.documents.schemas import DocumentStatus, ReviewData, ValidationIssue
from app.documents.validation import normalize_invoice_number, normalize_name


class DocumentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_processing(
        self,
        *,
        record_id: str,
        original_filename: str,
        stored_filename: str,
        content_type: str,
    ) -> DocumentRecord:
        record = DocumentRecord(
            id=record_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            content_type=content_type,
            status="processing",
            issues=[],
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def get(self, record_id: str) -> DocumentRecord | None:
        return self.session.get(DocumentRecord, record_id)

    def list(self) -> list[DocumentRecord]:
        statement = select(DocumentRecord).order_by(
            DocumentRecord.created_at.desc(), DocumentRecord.id.desc()
        )
        return list(self.session.scalars(statement))

    def save_result(
        self,
        record_id: str,
        *,
        status: DocumentStatus,
        classification: dict[str, Any] | None,
        extraction: dict[str, Any] | None,
        validation: dict[str, Any] | None,
        gl_suggestion: dict[str, Any] | None,
        review_data: ReviewData | None,
        document_review: DocumentReview | None,
        accounting_coding: AccountingCoding | None,
        issues: list[ValidationIssue],
    ) -> DocumentRecord:
        record = self._require(record_id)
        record.status = status
        record.classification = classification
        record.extraction = extraction
        record.validation = validation
        record.gl_suggestion = gl_suggestion
        record.review_data = (
            review_data.model_dump(mode="json") if review_data is not None else None
        )
        record.document_review = (
            document_review.model_dump(mode="json") if document_review is not None else None
        )
        record.accounting_coding = (
            accounting_coding.model_dump(mode="json")
            if accounting_coding is not None
            else None
        )
        record.issues = [issue.model_dump(mode="json") for issue in issues]
        record.error_message = None
        if review_data is not None:
            record.normalized_vendor_name = (
                normalize_name(review_data.vendor_name) if review_data.vendor_name else None
            )
            record.normalized_invoice_number = (
                normalize_invoice_number(review_data.invoice_number)
                if review_data.invoice_number
                else None
            )
        self._commit(record)
        return record

    def save_review(
        self,
        record_id: str,
        *,
        review_data: ReviewData,
        issues: list[ValidationIssue],
        status: DocumentStatus,
        document_review: DocumentReview | None = None,
        accounting_coding: AccountingCoding | None = None,
    ) -> DocumentRecord:
        record = self._require(record_id)
        record.review_data = review_data.model_dump(mode="json")
        record.issues = [issue.model_dump(mode="json") for issue in issues]
        record.status = status
        record.validation = {
            "findings": [issue.model_dump(mode="json") for issue in issues],
            "has_errors": any(issue.severity == "error" for issue in issues),
        }
        if document_review is not None:
            record.document_review = document_review.model_dump(mode="json")
        if accounting_coding is not None:
            record.accounting_coding = accounting_coding.model_dump(mode="json")
        record.error_message = None
        record.normalized_vendor_name = (
            normalize_name(review_data.vendor_name) if review_data.vendor_name else None
        )
        record.normalized_invoice_number = (
            normalize_invoice_number(review_data.invoice_number)
            if review_data.invoice_number
            else None
        )
        self._commit(record)
        return record

    def select_gl_account(self, record_id: str, gl_account_code: str) -> DocumentRecord:
        record = self._require(record_id)
        coding = AccountingCoding.model_validate(record.accounting_coding or {})
        coding.selected_gl_account_code = gl_account_code
        coding.overridden = bool(
            coding.suggestion and coding.suggestion.gl_account_code != gl_account_code
        )
        record.accounting_coding = coding.model_dump(mode="json")
        self._commit(record)
        return record

    def save_failure(self, record_id: str, message: str) -> DocumentRecord:
        record = self._require(record_id)
        record.status = "failed"
        record.error_message = message
        self._commit(record)
        return record

    def set_status(self, record_id: str, status: DocumentStatus) -> DocumentRecord:
        record = self._require(record_id)
        record.status = status
        self._commit(record)
        return record

    def delete(self, record_id: str) -> None:
        record = self._require(record_id)
        self.session.delete(record)
        self.session.commit()

    def duplicate_exists(
        self,
        vendor_name: str,
        invoice_number: str,
        *,
        exclude_id: str | None = None,
    ) -> bool:
        statement: Select[tuple[DocumentRecord]] = select(DocumentRecord).where(
            DocumentRecord.normalized_vendor_name == normalize_name(vendor_name),
            DocumentRecord.normalized_invoice_number
            == normalize_invoice_number(invoice_number),
            DocumentRecord.status != "rejected",
        )
        if exclude_id is not None:
            statement = statement.where(DocumentRecord.id != exclude_id)
        return self.session.scalar(statement.limit(1)) is not None

    def _require(self, record_id: str) -> DocumentRecord:
        record = self.get(record_id)
        if record is None:
            raise KeyError(record_id)
        return record

    def _commit(self, record: DocumentRecord) -> None:
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
