from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from app.document_review.schemas import DocumentReview
from app.documents.schemas import ReviewData, ValidationIssue
from app.pipeline.classification import DocumentClassification
from app.pipeline.gl_categorization import GlSuggestion
from app.schemas.invoice.model import InvoiceExtraction
from app.schemas.receipt.model import ReceiptExtraction

logger = logging.getLogger(__name__)


class PipelineContext(BaseModel):
    """Shared state passed through each pipeline step."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    document_path: Path
    content_type: str | None = None
    classification: DocumentClassification | None = None
    extraction: InvoiceExtraction | ReceiptExtraction | None = None
    review_data: ReviewData | None = None
    document_review: DocumentReview | None = None
    issues: list[ValidationIssue] | None = None
    gl_suggestion: GlSuggestion | None = None


class PipelineStep(Protocol):
    name: str

    def run(self, ctx: PipelineContext) -> PipelineContext: ...


class Pipeline:
    """Run an ordered sequence of pipeline steps against a document path."""

    def __init__(self, steps: Sequence[PipelineStep]) -> None:
        self.steps = list(steps)

    def run(self, document_path: Path) -> PipelineContext:
        logger.info("Pipeline started for %s (%d steps)", document_path.name, len(self.steps))
        ctx = PipelineContext(document_path=document_path)
        for index, step in enumerate(self.steps, start=1):
            logger.info("[%d/%d] Starting step: %s", index, len(self.steps), step.name)
            ctx = step.run(ctx)
            logger.info("[%d/%d] Finished step: %s", index, len(self.steps), step.name)
        logger.info("Pipeline completed for %s", document_path.name)
        return ctx


DuplicateChecker = Callable[[str | None, str | None], bool]
