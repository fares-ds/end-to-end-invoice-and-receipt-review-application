from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.pipeline.classification import DocumentKind
from app.schemas.invoice.mapping import map_invoice_result
from app.schemas.receipt.mapping import map_receipt_result
from app.services.local_extraction_service import (
    LOCAL_INVOICE_MODEL,
    LOCAL_RECEIPT_MODEL,
    LocalExtractionService,
)

if TYPE_CHECKING:
    from app.pipeline.base import PipelineContext

logger = logging.getLogger(__name__)


class ExtractionStep:
    """Route to the local invoice or receipt extractor and map into domain models."""

    name = "extraction"

    def __init__(self, service: LocalExtractionService | None = None) -> None:
        self._service = service or LocalExtractionService()

    def run(self, ctx: PipelineContext) -> PipelineContext:
        if ctx.classification is None:
            raise ValueError("ExtractionStep requires ctx.classification from ClassificationStep.")

        document_path = ctx.document_path
        if ctx.classification.document_kind == DocumentKind.invoice:
            logger.info("Extracting locally with %s", LOCAL_INVOICE_MODEL)
            result = self._service.analyze_invoice(document_path)
            extraction = map_invoice_result(result)
        else:
            logger.info("Extracting locally with %s", LOCAL_RECEIPT_MODEL)
            result = self._service.analyze_receipt(document_path)
            extraction = map_receipt_result(result)

        logger.info(
            "Mapped extraction (%s) with %d line item(s)",
            extraction.document_type,
            len(extraction.items),
        )
        return ctx.model_copy(update={"extraction": extraction})
