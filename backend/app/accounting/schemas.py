from pydantic import BaseModel, ConfigDict, Field


class AccountingSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gl_account_code: str
    category: str
    rationale: str = Field(min_length=1, max_length=480)
    confidence: float = Field(ge=0, le=1)


class AccountingCoding(BaseModel):
    suggestion: AccountingSuggestion | None = None
    selected_gl_account_code: str | None = None
    overridden: bool = False
    error_message: str | None = None


class AccountingSelectionRequest(BaseModel):
    gl_account_code: str
