from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.auth.schemas import LoginRequest, SessionResponse
from app.auth.session import (
    clear_session_cookie,
    is_authenticated,
    passwords_match,
    set_session_cookie,
)
from app.config import Settings, get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _settings() -> Settings:
    return get_settings()


@router.get("/session", response_model=SessionResponse)
def read_session(
    request: Request,
    settings: Annotated[Settings, Depends(_settings)],
) -> SessionResponse:
    return SessionResponse(
        auth_enabled=settings.auth_enabled,
        authenticated=is_authenticated(request, settings),
    )


@router.post("/login", response_model=SessionResponse)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(_settings)],
) -> SessionResponse:
    if not settings.auth_enabled:
        return SessionResponse(auth_enabled=False, authenticated=True)
    assert settings.app_access_password is not None
    if not passwords_match(body.password, settings.app_access_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
        )
    set_session_cookie(response, request, settings)
    return SessionResponse(auth_enabled=True, authenticated=True)


@router.post("/logout", response_model=SessionResponse)
def logout(
    response: Response,
    settings: Annotated[Settings, Depends(_settings)],
) -> SessionResponse:
    clear_session_cookie(response)
    return SessionResponse(
        auth_enabled=settings.auth_enabled,
        authenticated=not settings.auth_enabled,
    )
