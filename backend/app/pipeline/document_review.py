from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.document_review.base import DocumentReviewer, DocumentReviewError
from app.document_review.reconciliation import merge_document_extractions
from app.document_review.schemas import DocumentReview
from app.documents.projection import project_extraction

if TYPE_CHECKING:
    from app.pipeline.base import PipelineContext

logger = logging.getLogger(__name__)


class UnsupportedDocumentError(RuntimeError):
    """Raised when the independent LLM review classifies the file as unsupported."""


class DocumentReviewStep:
    """Project DI extraction, run independent LLM review, and merge gaps."""

    name = "document_review"

    def __init__(
        self,
        *,
        reviewer: DocumentReviewer | None = None,
        content_type: str | None = None,
    ) -> None:
        self._reviewer = reviewer
        self._content_type = content_type

    def run(self, ctx: PipelineContext) -> PipelineContext:
        if ctx.extraction is None:
            raise ValueError("DocumentReviewStep requires ctx.extraction from ExtractionStep.")

        review_data = project_extraction(ctx.extraction)
        content_type = self._content_type or ctx.content_type
        if self._reviewer is None or content_type is None:
            logger.info("Skipping LLM document review; using Document Intelligence projection only")
            return ctx.model_copy(
                update={
                    "review_data": review_data,
                    "document_review": DocumentReview(
                        error_message="Independent LLM review was not configured."
                    ),
                }
            )

        try:
            llm_extraction = self._reviewer.review(ctx.document_path, content_type)
        except DocumentReviewError as error:
            logger.warning("LLM document review failed: %s", error)
            return ctx.model_copy(
                update={
                    "review_data": review_data,
                    "document_review": DocumentReview(error_message=str(error)),
                }
            )

        if llm_extraction.document_type == "unsupported":
            raise UnsupportedDocumentError(
                "The uploaded file is not a supported invoice or receipt."
            )

        merged, document_review = merge_document_extractions(review_data, llm_extraction)
        logger.info(
            "Merged DI and LLM extractions (%d fallback field(s))",
            len(document_review.fallback_fields),
        )
        return ctx.model_copy(
            update={"review_data": merged, "document_review": document_review}
        )
