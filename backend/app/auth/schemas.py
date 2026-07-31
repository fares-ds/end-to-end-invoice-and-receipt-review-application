from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    password: str = Field(min_length=1)


class SessionResponse(BaseModel):
    auth_enabled: bool
    authenticated: bool
