from __future__ import annotations

from app.document_review.base import DocumentReviewer
from app.pipeline.base import DuplicateChecker, Pipeline, PipelineContext, PipelineStep
from app.pipeline.classification import (
    ClassificationStep,
    DocumentClassification,
    DocumentClassifier,
    DocumentKind,
)
from app.pipeline.document_review import DocumentReviewStep, UnsupportedDocumentError
from app.pipeline.extraction import ExtractionStep
from app.pipeline.gl_categorization import (
    GlCategorizationStep,
    GlCategorizer,
    GlSuggestion,
)
from app.pipeline.validation import ValidationStep


def build_default_pipeline(
    *,
    document_reviewer: DocumentReviewer | None = None,
    content_type: str | None = None,
    expected_customer_name: str | None = None,
    expected_customer_vat_id: str | None = None,
    min_confidence: float | None = None,
    is_duplicate_checker: DuplicateChecker | None = None,
) -> Pipeline:
    """Classify → extract → LLM review/merge → validate → suggest GL."""
    return Pipeline(
        [
            ClassificationStep(),
            ExtractionStep(),
            DocumentReviewStep(reviewer=document_reviewer, content_type=content_type),
            ValidationStep(
                expected_customer_name=expected_customer_name,
                expected_customer_vat_id=expected_customer_vat_id,
                min_confidence=min_confidence,
                is_duplicate_checker=is_duplicate_checker,
            ),
            GlCategorizationStep(),
        ]
    )


__all__ = [
    "ClassificationStep",
    "DocumentClassification",
    "DocumentClassifier",
    "DocumentKind",
    "DocumentReviewStep",
    "ExtractionStep",
    "GlCategorizationStep",
    "GlCategorizer",
    "GlSuggestion",
    "Pipeline",
    "PipelineContext",
    "PipelineStep",
    "UnsupportedDocumentError",
    "ValidationStep",
    "build_default_pipeline",
]
