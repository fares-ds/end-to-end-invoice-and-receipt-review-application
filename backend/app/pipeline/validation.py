from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.config import APP_CONFIG
from app.documents.validation import validate_review_data
from app.pipeline.base import DuplicateChecker

if TYPE_CHECKING:
    from app.pipeline.base import PipelineContext

logger = logging.getLogger(__name__)


class ValidationStep:
    """Run Northstar policy against the flat review projection."""

    name = "validation"

    def __init__(
        self,
        *,
        expected_customer_name: str | None = None,
        expected_customer_vat_id: str | None = None,
        min_confidence: float | None = None,
        is_duplicate_checker: DuplicateChecker | None = None,
    ) -> None:
        self._expected_customer_name = (
            expected_customer_name or APP_CONFIG.expected_customer_name
        )
        self._expected_customer_vat_id = (
            expected_customer_vat_id or APP_CONFIG.expected_customer_vat_id
        )
        self._min_confidence = (
            min_confidence
            if min_confidence is not None
            else APP_CONFIG.min_field_confidence
        )
        self._is_duplicate_checker = is_duplicate_checker or (lambda _v, _n: False)

    def run(self, ctx: PipelineContext) -> PipelineContext:
        if ctx.review_data is None:
            raise ValueError(
                "ValidationStep requires ctx.review_data from DocumentReviewStep."
            )

        is_duplicate = self._is_duplicate_checker(
            ctx.review_data.vendor_name, ctx.review_data.invoice_number
        )
        issues = validate_review_data(
            ctx.review_data,
            expected_customer_name=self._expected_customer_name,
            expected_customer_vat_id=self._expected_customer_vat_id,
            min_confidence=self._min_confidence,
            is_duplicate=is_duplicate,
        )
        error_count = sum(1 for issue in issues if issue.severity == "error")
        logger.info(
            "Validation finished with %d finding(s) (%d error(s))",
            len(issues),
            error_count,
        )
        return ctx.model_copy(update={"issues": issues})
