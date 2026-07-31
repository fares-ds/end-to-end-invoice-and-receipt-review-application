from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from app.accounting.catalog import GlAccountCode, format_catalog_for_prompt
from app.config import Settings, get_settings
from app.documents.schemas import ReviewData
from app.pipeline.classification import build_local_agent
from app.schemas.invoice.mapping import invoice_to_manifest_view
from app.schemas.invoice.model import InvoiceExtraction
from app.schemas.receipt.mapping import receipt_to_manifest_view
from app.schemas.receipt.model import ReceiptExtraction

if TYPE_CHECKING:
    from app.pipeline.base import PipelineContext

logger = logging.getLogger(__name__)

GL_CATEGORIZATION_PROMPT = (
    "Suggest the best Northstar GL account for this extracted financial document."
)

GL_CATEGORIZATION_INSTRUCTIONS = f"""\
You categorize extracted invoice and receipt fields for Northstar Facilities B.V.,
a facilities-management company in Amsterdam.

Use the vendor or merchant name, line-item descriptions, totals, and document type
to pick the single best GL account from the fixed catalog below. Invoices usually
reflect supplier services; receipts usually reflect paid employee or field expenses.

{format_catalog_for_prompt()}

Return exactly one catalog code, a confidence between 0 and 1, and a brief reason.
"""


class GlSuggestion(BaseModel):
    account_code: GlAccountCode
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


def build_gl_categorization_input(
    extraction: InvoiceExtraction | ReceiptExtraction | ReviewData,
) -> dict[str, Any]:
    if isinstance(extraction, ReviewData):
        payload = extraction.model_dump(mode="json")
        payload["line_items"] = [
            item.description for item in extraction.line_items
        ]
        return payload

    if isinstance(extraction, InvoiceExtraction):
        payload = dict(invoice_to_manifest_view(extraction))
        payload["line_items"] = [
            item.description.value if item.description else None for item in extraction.items
        ]
        return payload

    payload = dict(receipt_to_manifest_view(extraction))
    payload["receipt_type"] = (
        extraction.receipt_type.value if extraction.receipt_type else None
    )
    payload["line_items"] = [
        item.description.value if item.description else None for item in extraction.items
    ]
    return payload


class GlCategorizer:
    """Suggest a Northstar GL account from normalized extraction fields."""

    def __init__(self, settings: Settings | None = None) -> None:
        resolved_settings = settings or get_settings()
        self._agent: Agent[None, GlSuggestion] = build_local_agent(
            GlSuggestion, GL_CATEGORIZATION_INSTRUCTIONS, resolved_settings
        )

    def run(
        self, extraction: InvoiceExtraction | ReceiptExtraction | ReviewData
    ) -> GlSuggestion:
        payload = build_gl_categorization_input(extraction)
        result = self._agent.run_sync(
            user_prompt=[
                GL_CATEGORIZATION_PROMPT,
                json.dumps(payload, indent=2, default=str),
            ]
        )
        return result.output


class GlCategorizationStep:
    """Pipeline step that suggests a GL account and writes ctx.gl_suggestion."""

    name = "gl_categorization"

    def __init__(self, categorizer: GlCategorizer | None = None) -> None:
        self._categorizer = categorizer or GlCategorizer()

    def run(self, ctx: PipelineContext) -> PipelineContext:
        source = ctx.review_data if ctx.review_data is not None else ctx.extraction
        if source is None:
            raise ValueError(
                "GlCategorizationStep requires ctx.review_data or ctx.extraction."
            )

        logger.info("Suggesting Northstar GL account with the local model")
        suggestion = self._categorizer.run(source)
        logger.info(
            "Suggested GL account %s (confidence=%.2f)",
            suggestion.account_code.value,
            suggestion.confidence,
        )
        return ctx.model_copy(update={"gl_suggestion": suggestion})
