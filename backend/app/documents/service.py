from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.accounting.catalog import get_gl_account
from app.accounting.schemas import AccountingCoding, AccountingSuggestion
from app.config import AppConfig
from app.correction_email.base import CorrectionEmailDrafter
from app.correction_email.eligibility import supplier_fixable_issues
from app.correction_email.schemas import CorrectionEmailDraft
from app.document_review.base import DocumentReviewer
from app.document_review.schemas import DocumentReview
from app.documents.models import DocumentRecord
from app.documents.repository import DocumentRepository
from app.documents.schemas import (
    DocumentCorrectionRequest,
    ReviewData,
    ValidationIssue,
)
from app.documents.validation import status_for_issues, validate_review_data
from app.pipeline import UnsupportedDocumentError, build_default_pipeline
from app.pipeline.gl_categorization import GlSuggestion


class DocumentNotFoundError(RuntimeError):
    pass


class DocumentProcessingError(RuntimeError):
    pass


class DocumentContentError(RuntimeError):
    pass


class DocumentReviewConflictError(RuntimeError):
    pass


class DocumentService:
    def __init__(
        self,
        *,
        repository: DocumentRepository,
        upload_dir: Path,
        expected_customer_name: str,
        expected_customer_vat_id: str,
        min_confidence: float,
        document_reviewer: DocumentReviewer | None = None,
        correction_email_drafter: CorrectionEmailDrafter | None = None,
        content_type: str | None = None,
    ) -> None:
        self.repository = repository
        self.upload_dir = upload_dir
        self.expected_customer_name = expected_customer_name
        self.expected_customer_vat_id = expected_customer_vat_id
        self.min_confidence = min_confidence
        self.document_reviewer = document_reviewer
        self.correction_email_drafter = correction_email_drafter
        self._content_type = content_type

    def process(
        self,
        *,
        original_filename: str,
        content_type: str,
        content: bytes,
        suffix: str,
    ) -> DocumentRecord:
        record_id = str(uuid4())
        stored_filename = f"{record_id}{suffix}"
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        stored_path = self.upload_dir / stored_filename
        stored_path.write_bytes(content)
        self.repository.create_processing(
            record_id=record_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            content_type=content_type,
        )

        try:
            context = build_default_pipeline(
                document_reviewer=self.document_reviewer,
                content_type=content_type,
                expected_customer_name=self.expected_customer_name,
                expected_customer_vat_id=self.expected_customer_vat_id,
                min_confidence=self.min_confidence,
                is_duplicate_checker=lambda vendor, number: bool(
                    vendor
                    and number
                    and self.repository.duplicate_exists(vendor, number)
                ),
            ).run(stored_path)
        except UnsupportedDocumentError as error:
            self.repository.save_failure(record_id, str(error))
            raise DocumentContentError(str(error)) from error
        except Exception as error:
            message = str(error) or error.__class__.__name__
            self.repository.save_failure(record_id, message)
            raise DocumentProcessingError(message) from error

        accounting_coding = _accounting_from_suggestion(context.gl_suggestion)
        issues = context.issues or []
        return self.repository.save_result(
            record_id,
            status=status_for_issues(issues),
            classification=(
                context.classification.model_dump(mode="json")
                if context.classification
                else None
            ),
            extraction=(
                context.extraction.model_dump(mode="json") if context.extraction else None
            ),
            validation={
                "findings": [issue.model_dump(mode="json") for issue in issues],
                "has_errors": any(issue.severity == "error" for issue in issues),
            },
            gl_suggestion=(
                context.gl_suggestion.model_dump(mode="json")
                if context.gl_suggestion
                else None
            ),
            review_data=context.review_data,
            document_review=context.document_review,
            accounting_coding=accounting_coding,
            issues=issues,
        )

    def get(self, record_id: str) -> DocumentRecord:
        record = self.repository.get(record_id)
        if record is None:
            raise DocumentNotFoundError("Document not found")
        return record

    def revalidate(
        self, record_id: str, corrections: DocumentCorrectionRequest
    ) -> DocumentRecord:
        record = self.repository.get(record_id)
        if record is None:
            raise DocumentNotFoundError("Document not found")
        if record.status in {"approved", "rejected"}:
            raise DocumentReviewConflictError("A decided document cannot be edited.")

        saved_data = ReviewData.model_validate(record.review_data or {})
        corrected_fields = corrections.model_dump(exclude_unset=True)
        data = saved_data.model_copy(update=corrected_fields)
        field_sources = dict(saved_data.field_sources)
        for field, value in corrected_fields.items():
            if value != getattr(saved_data, field):
                field_sources[field] = "human"
        data = data.model_copy(update={"field_sources": field_sources})

        is_duplicate = bool(
            data.vendor_name
            and data.invoice_number
            and self.repository.duplicate_exists(
                data.vendor_name, data.invoice_number, exclude_id=record_id
            )
        )
        issues = validate_review_data(
            data,
            expected_customer_name=self.expected_customer_name,
            expected_customer_vat_id=self.expected_customer_vat_id,
            min_confidence=self.min_confidence,
            is_duplicate=is_duplicate,
        )
        document_review = DocumentReview.model_validate(record.document_review or {})
        return self.repository.save_review(
            record_id,
            review_data=data,
            issues=issues,
            status=status_for_issues(issues),
            document_review=document_review,
        )

    def select_gl_account(self, record_id: str, gl_account_code: str) -> DocumentRecord:
        record = self.repository.get(record_id)
        if record is None:
            raise DocumentNotFoundError("Document not found")
        if record.status in {"approved", "rejected"}:
            raise DocumentReviewConflictError("A decided document cannot be edited.")
        if get_gl_account(gl_account_code) is None:
            raise ValueError(f"Unknown GL account: {gl_account_code}")
        return self.repository.select_gl_account(record_id, gl_account_code)

    def decide(self, record_id: str, decision: str) -> DocumentRecord:
        record = self.repository.get(record_id)
        if record is None:
            raise DocumentNotFoundError("Document not found")
        if record.status in {"approved", "rejected"}:
            raise DocumentReviewConflictError("This document already has a decision.")
        if record.status in {"processing", "failed"}:
            raise DocumentReviewConflictError(
                "Only a completed review can receive a decision."
            )
        if decision == "approved" and any(
            issue.get("severity") == "error" for issue in (record.issues or [])
        ):
            raise DocumentReviewConflictError(
                "Resolve all validation errors before approval."
            )
        coding = AccountingCoding.model_validate(record.accounting_coding or {})
        if decision == "approved" and get_gl_account(coding.selected_gl_account_code or "") is None:
            raise DocumentReviewConflictError(
                "Select a valid GL account before approval."
            )
        if decision not in {"approved", "rejected"}:
            raise ValueError(f"Unsupported decision: {decision}")
        return self.repository.set_status(record_id, decision)  # type: ignore[arg-type]

    def draft_correction_email(self, record_id: str) -> CorrectionEmailDraft:
        if self.correction_email_drafter is None:
            raise DocumentReviewConflictError(
                "Correction-email drafting is not configured."
            )
        record = self.repository.get(record_id)
        if record is None:
            raise DocumentNotFoundError("Document not found")
        if record.status in {"processing", "failed"} or record.review_data is None:
            raise DocumentReviewConflictError(
                "Only a completed review can generate a correction email."
            )
        data = ReviewData.model_validate(record.review_data)
        issues = [ValidationIssue.model_validate(item) for item in (record.issues or [])]
        eligible_issues = supplier_fixable_issues(issues)
        if not eligible_issues:
            raise DocumentReviewConflictError(
                "This review has no supplier-fixable business issues."
            )
        return self.correction_email_drafter.draft(data, eligible_issues)

    def delete(self, record_id: str) -> None:
        record = self.repository.get(record_id)
        if record is None:
            raise DocumentNotFoundError(f"Document {record_id} was not found.")
        stored_path = self.upload_dir / Path(record.stored_filename).name
        self.repository.delete(record_id)
        stored_path.unlink(missing_ok=True)


def build_service_from_config(
    repository: DocumentRepository,
    config: AppConfig,
    *,
    document_reviewer: DocumentReviewer | None = None,
    correction_email_drafter: CorrectionEmailDrafter | None = None,
) -> DocumentService:
    return DocumentService(
        repository=repository,
        upload_dir=config.upload_dir,
        expected_customer_name=config.expected_customer_name,
        expected_customer_vat_id=config.expected_customer_vat_id,
        min_confidence=config.min_field_confidence,
        document_reviewer=document_reviewer,
        correction_email_drafter=correction_email_drafter,
    )


def _accounting_from_suggestion(
    suggestion: GlSuggestion | None,
) -> AccountingCoding:
    if suggestion is None:
        return AccountingCoding(error_message="No GL suggestion was produced.")
    account = get_gl_account(suggestion.account_code)
    if account is None:
        return AccountingCoding(error_message="Suggested GL account is not in the catalog.")
    coded = AccountingSuggestion(
        gl_account_code=suggestion.account_code.value,
        category=account.name,
        rationale=suggestion.reasoning,
        confidence=suggestion.confidence,
    )
    return AccountingCoding(
        suggestion=coded,
        selected_gl_account_code=coded.gl_account_code,
        overridden=False,
    )
