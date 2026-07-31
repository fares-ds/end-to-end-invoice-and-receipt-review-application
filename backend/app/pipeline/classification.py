from __future__ import annotations

import logging
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field
from pydantic_ai import Agent, NativeOutput, PromptedOutput
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

Documents may be written in English, Dutch, German, or French. Judge by these words rather
than by how detailed the document looks:

- Invoice: "invoice", "factuur", "Rechnung", "facture".
- Receipt: "receipt", "kassabon", "bon", "Kassenbon", "Quittung", "Beleg", "ticket",
  "reçu", "ticket de caisse".

Evidence that a document was already paid — a payment method such as PIN, card, or cash, a
till or terminal number, a pump number — means receipt, even when VAT is broken out and the
line detail looks invoice-like. A VAT breakdown alone never makes a document an invoice.
The absence of an invoice number and a customer is strong evidence for receipt.

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
    """Build a pydantic-ai agent bound to the configured Ollama server.

    Tool-calling, pydantic-ai's default output path, is unavailable: the small
    local models this project targets do not support tools. The replacement
    depends on where the model runs. Locally served models are grammar-constrained
    by Ollama and take NativeOutput; cloud-served models are proxied without that
    constraint, ignore a json_schema response format, and must be asked for JSON
    in the prompt instead.
    """
    provider = OpenAIProvider(
        base_url=settings.ollama_base_url,
        api_key=settings.ollama_api_key,
    )
    model = OpenAIChatModel(model_name=settings.ollama_model, provider=provider)
    output = (
        PromptedOutput(output_type)
        if settings.prompted_output()
        else NativeOutput(output_type)
    )
    return Agent(
        model=model,
        output_type=output,
        instructions=instructions,
        # Pinned so the same document yields the same classification and GL
        # suggestion across runs, matching the extraction call.
        model_settings={"temperature": 0.0},
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
