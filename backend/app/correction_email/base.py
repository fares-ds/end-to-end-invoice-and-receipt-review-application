from typing import Protocol

from app.correction_email.schemas import CorrectionEmailDraft
from app.documents.schemas import ReviewData, ValidationIssue


class CorrectionEmailDraftingError(RuntimeError):
    pass


class CorrectionEmailDrafter(Protocol):
    def draft(
        self, data: ReviewData, issues: list[ValidationIssue]
    ) -> CorrectionEmailDraft: ...
