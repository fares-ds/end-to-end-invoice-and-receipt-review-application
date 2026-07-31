import json
from typing import Any

from pydantic import ValidationError

from app.config import Settings, get_settings
from app.correction_email.base import CorrectionEmailDrafter, CorrectionEmailDraftingError
from app.correction_email.schemas import CorrectionEmailDraft
from app.documents.schemas import ReviewData, ValidationIssue
from app.providers.ollama_client import build_ollama_client

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
        try:
            response = self.client.chat.completions.create(
                model=self._settings.ollama_model,
                messages=[
                    {"role": "system", "content": INSTRUCTIONS},
                    {"role": "user", "content": payload},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "correction_email_draft",
                        "strict": True,
                        "schema": CorrectionEmailDraft.model_json_schema(),
                    },
                },
                temperature=0,
            )
        except Exception as error:
            raise CorrectionEmailDraftingError(
                "The local model could not draft the correction email."
            ) from error

        content = response.choices[0].message.content or ""
        try:
            return CorrectionEmailDraft.model_validate(json.loads(content))
        except (json.JSONDecodeError, ValidationError, TypeError) as error:
            raise CorrectionEmailDraftingError(
                "The local model returned an invalid correction-email draft."
            ) from error
