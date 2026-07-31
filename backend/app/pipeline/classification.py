from __future__ import annotations

import logging
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.config import Settings, get_settings
from app.services.ocr_text_service import OcrError, OcrTextService

if TYPE_CHECKING:
    from app.pipeline.base import PipelineContext

logger = logging.getLogger(__name__)

CLASSIFICATION_PROMPT = (
    "Classify this financial document as invoice or receipt based on its layout and content."
)

CLASSIFICATION_INSTRUCTIONS = """\
You classify European financial documents for a finance team.

Choose invoice when the document is a supplier bill requesting payment. Invoices usually
include an invoice number, supplier and customer details, VAT IDs, line items, totals,
and often a due date or payment terms.

Choose receipt when the document records an expense that was already paid. Receipts usually
show a merchant, transaction date, payment total, and sometimes VAT, but not invoice
numbers, customer VAT IDs, purchase orders, or payment terms.

Return your best label, a confidence between 0 and 1, and a brief reason.
"""

MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


class DocumentKind(StrEnum):
    invoice = "invoice"
    receipt = "receipt"


class DocumentClassification(BaseModel):
    document_kind: DocumentKind
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


def build_local_agent[T](
    output_type: type[T], instructions: str, settings: Settings
) -> Agent[None, T]:
    """Build a pydantic-ai agent bound to the local Ollama server.

    Structured output is requested through the model's native JSON-schema support
    rather than the default tool-calling path, because the small local models this
    project targets serve a json_schema response format but do not support tools.
    """
    provider = OpenAIProvider(
        base_url=settings.ollama_base_url,
        api_key=settings.ollama_api_key,
    )
    model = OpenAIChatModel(model_name=settings.ollama_model, provider=provider)
    return Agent(
        model=model,
        output_type=NativeOutput(output_type),
        instructions=instructions,
    )


class DocumentClassifier:
    """Classify a document as invoice or receipt from its locally recovered text."""

    def __init__(
        self,
        settings: Settings | None = None,
        ocr_service: OcrTextService | None = None,
    ) -> None:
        resolved_settings = settings or get_settings()
        self._ocr = ocr_service or OcrTextService(resolved_settings)
        self._agent = build_local_agent(
            DocumentClassification, CLASSIFICATION_INSTRUCTIONS, resolved_settings
        )

    def run(self, document_path: Path) -> DocumentClassification:
        media_type = MEDIA_TYPES.get(document_path.suffix.lower())
        if media_type is None:
            supported = ", ".join(sorted(MEDIA_TYPES))
            raise ValueError(
                f"Unsupported document type {document_path.suffix!r}. Use one of: {supported}"
            )

        try:
            ocr = self._ocr.extract(document_path, media_type)
        except OcrError as error:
            raise ValueError(str(error)) from error

        result = self._agent.run_sync(
            user_prompt=[CLASSIFICATION_PROMPT, ocr.text],
        )
        return result.output


class ClassificationStep:
    """Pipeline step that classifies the document and writes ctx.classification."""

    name = "classification"

    def __init__(self, classifier: DocumentClassifier | None = None) -> None:
        self._classifier = classifier or DocumentClassifier()

    def run(self, ctx: PipelineContext) -> PipelineContext:
        logger.info("Classifying document with the local model")
        classification = self._classifier.run(ctx.document_path)
        logger.info(
            "Classified as %s (confidence=%.2f)",
            classification.document_kind,
            classification.confidence,
        )
        return ctx.model_copy(update={"classification": classification})
