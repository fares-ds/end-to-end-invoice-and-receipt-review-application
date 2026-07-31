from pydantic import BaseModel, ConfigDict


class CorrectionEmailDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipient_name: str
    subject: str
    body: str
