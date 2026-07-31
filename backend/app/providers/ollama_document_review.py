"""Independent second-opinion review of a financial document, run locally.

The hosted implementation sent the original PDF or image to a vision model. A
local vision model needs memory this project does not assume, so the default
path reviews the OCR text instead. Setting ``OLLAMA_VISION_MODEL`` restores the
original behaviour by rasterizing the first page and sending it as an image.

Because the default path reads the same OCR text the primary extraction reads,
the two results are not fully independent. That limitation is surfaced in the
returned summary rather than hidden, so a reviewer can weigh the agreement
between the two accordingly.
"""

from __future__ import annotations

import base64
import json
import logging
import subprocess
import tempfile
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
    "Reviewed from locally recovered document text, which the primary extraction also used."
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

        if self._settings.vision_enabled:
            message = self._vision_message(path, content_type)
            model = self._settings.ollama_vision_model or self._settings.ollama_model
            shared_source = False
        else:
            message = self._text_message(path, content_type)
            model = self._settings.ollama_model
            shared_source = True

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

        if shared_source:
            review = review.model_copy(
                update={"summary": f"{review.summary} ({SHARED_SOURCE_NOTE})"}
            )
        return review

    def _text_message(self, path: Path, content_type: str) -> dict[str, str]:
        try:
            ocr = self._ocr.extract(path, content_type)
        except OcrError as error:
            raise DocumentReviewError(str(error)) from error
        return {
            "role": "user",
            "content": (
                "Classify, independently extract, and review this financial "
                f"document.\n\n{ocr.text}"
            ),
        }

    def _vision_message(self, path: Path, content_type: str) -> dict:
        if content_type == "application/pdf":
            image_bytes = _rasterize_first_page(path, self._settings)
            media_type = "image/png"
        else:
            image_bytes = path.read_bytes()
            media_type = content_type

        encoded = base64.b64encode(image_bytes).decode("ascii")
        return {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Classify, independently extract, and review this document.",
                },
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{media_type};base64,{encoded}"},
                },
            ],
        }


def _rasterize_first_page(path: Path, settings: Settings) -> bytes:
    with tempfile.TemporaryDirectory() as workspace:
        prefix = Path(workspace) / "page"
        try:
            subprocess.run(
                [
                    settings.pdftoppm_binary,
                    "-r",
                    "150",
                    "-png",
                    "-f",
                    "1",
                    "-l",
                    "1",
                    str(path),
                    str(prefix),
                ],
                capture_output=True,
                check=True,
                timeout=120,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise DocumentReviewError(
                "The PDF could not be rasterized for the vision review."
            ) from error

        pages = sorted(Path(workspace).glob("page*.png"))
        if not pages:
            raise DocumentReviewError("The PDF produced no page image to review.")
        return pages[0].read_bytes()
