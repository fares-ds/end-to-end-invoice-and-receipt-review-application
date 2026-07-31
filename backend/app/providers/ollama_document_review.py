"""Independent second-opinion review of a financial document, run locally.

The hosted implementation sent the original file to a vision model. Independence
here comes from reading the document by a different route instead: a PDF is
rasterized and OCRed rather than read through the text layer the primary
extraction used, so the two readings can genuinely disagree.

An image offers only one route, so its review shares a source with the primary
extraction. The returned summary states which of the two situations applies
rather than leaving the reviewer to assume independence.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import ValidationError

from app.config import Settings, get_settings
from app.document_review.base import DocumentReviewer, DocumentReviewError
from app.document_review.schemas import LlmDocumentExtraction
from app.providers.ollama_client import build_ollama_client
from app.providers.structured_output import build_request, parse_json_object
from app.services.ocr_text_service import OcrError, OcrTextService

logger = logging.getLogger(__name__)

SUPPORTED_CONTENT_TYPES = {"application/pdf", "image/png", "image/jpeg"}

INSTRUCTIONS = """
You are an independent financial-document reviewer. First classify the source as invoice,
receipt, or unsupported. Then extract every requested value directly from the source without
using another model's output. For receipts, map the merchant to vendor_name, transaction date
to invoice_date, total to invoice_total and amount_due, and classify the expense as fuel,
meals, travel, supplies, or other. Return dates as YYYY-MM-DD and monetary values as plain
decimal strings without currency symbols. Use null when a value is absent or unreadable. The
summary must be one concise factual sentence. Do not decide whether the document should be
approved; deterministic application rules do that.
""".strip()

SHARED_SOURCE_NOTE = (
    "Reviewed from the same recovered text the primary extraction used, so the two "
    "readings are not independent."
)
INDEPENDENT_SOURCE_NOTE = (
    "Reviewed from an independent OCR pass over the page image, not the text layer "
    "the primary extraction read."
)


class OllamaDocumentReviewer(DocumentReviewer):
    def __init__(
        self,
        *,
        client=None,
        settings: Settings | None = None,
        ocr_service: OcrTextService | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self.client = client or build_ollama_client(self._settings)
        self._ocr = ocr_service or OcrTextService(self._settings)

    def review(self, path: Path, content_type: str) -> LlmDocumentExtraction:
        if content_type not in SUPPORTED_CONTENT_TYPES:
            raise DocumentReviewError(
                "The independent review supports PDF, PNG, or JPEG files. "
                "Local extraction and deterministic checks still completed."
            )

        message, shared_source = self._text_message(path, content_type)
        model = self._settings.ollama_model

        request = build_request(
            model=model,
            system=INSTRUCTIONS,
            user="",
            schema=LlmDocumentExtraction.model_json_schema(),
            schema_name="financial_document_review",
            prompted=self._settings.prompted_output(model),
        )
        # The user turn is built per input mode (OCR text or a page image).
        request["messages"] = [request["messages"][0], message]
        try:
            response = self.client.chat.completions.create(**request)
        except Exception as error:
            raise DocumentReviewError(
                "The local document review failed. The deterministic review can continue."
            ) from error

        content = response.choices[0].message.content or ""
        try:
            review = LlmDocumentExtraction.model_validate(parse_json_object(content))
        except (json.JSONDecodeError, ValidationError, TypeError) as error:
            raise DocumentReviewError(
                "The local model did not return valid structured document-review output."
            ) from error

        note = SHARED_SOURCE_NOTE if shared_source else INDEPENDENT_SOURCE_NOTE
        return review.model_copy(update={"summary": f"{review.summary} ({note})"})

    def _text_message(self, path: Path, content_type: str) -> tuple[dict[str, str], bool]:
        """Read the document by a different route than the primary extraction.

        A PDF is rasterized and OCRed rather than read through its text layer, so
        the review is a second genuine reading. An image has only one route, so
        the two necessarily share a source and the review says so.
        """
        try:
            ocr = self._ocr.extract(path, content_type, prefer_text_layer=False)
            primary_source = self._ocr.extract(path, content_type).source
        except OcrError as error:
            raise DocumentReviewError(str(error)) from error

        shared_source = ocr.source == primary_source
        logger.info(
            "Independent review read via %s (primary used %s)", ocr.source, primary_source
        )
        message = {
            "role": "user",
            "content": (
                "Classify, independently extract, and review this financial "
                f"document.\n\n{ocr.text}"
            ),
        }
        return message, shared_source
