import json
from typing import Any

from pydantic import ValidationError

from app.config import Settings, get_settings
from app.correction_email.base import CorrectionEmailDrafter, CorrectionEmailDraftingError
from app.correction_email.schemas import CorrectionEmailDraft
from app.documents.schemas import ReviewData, ValidationIssue
from app.providers.ollama_client import build_ollama_client
from app.providers.structured_output import build_request, parse_json_object

INSTRUCTIONS = """
Draft a concise, professional correction-request email from a finance administrator to the
supplier or merchant. Mention only the supplied business issues and document facts. Do not
mention AI, extraction confidence, internal systems, or invent an email address. Ask for a
corrected document or clarification. Use a neutral greeting and sign off as Maya, Finance
Administration, Northstar Facilities B.V.
""".strip()


class OllamaCorrectionEmailDrafter(CorrectionEmailDrafter):
    def __init__(
        self,
        *,
        client: Any | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self.client = client or build_ollama_client(self._settings)

    def draft(
        self, data: ReviewData, issues: list[ValidationIssue]
    ) -> CorrectionEmailDraft:
        payload = json.dumps(
            {
                "document": data.model_dump(mode="json"),
                "issues": [issue.model_dump(mode="json") for issue in issues],
            }
        )
        request = build_request(
            model=self._settings.ollama_model,
            system=INSTRUCTIONS,
            user=payload,
            schema=CorrectionEmailDraft.model_json_schema(),
            schema_name="correction_email_draft",
            prompted=self._settings.prompted_output(),
        )
        try:
            response = self.client.chat.completions.create(**request)
        except Exception as error:
            raise CorrectionEmailDraftingError(
                "The local model could not draft the correction email."
            ) from error

        content = response.choices[0].message.content or ""
        try:
            return CorrectionEmailDraft.model_validate(parse_json_object(content))
        except (json.JSONDecodeError, ValidationError, TypeError) as error:
            raise CorrectionEmailDraftingError(
                "The local model returned an invalid correction-email draft."
            ) from error
