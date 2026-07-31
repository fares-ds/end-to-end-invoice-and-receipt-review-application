import hashlib
import hmac

from fastapi import Request, Response

from app.config import Settings

SESSION_COOKIE_NAME = "invoice_review_session"
_SESSION_PAYLOAD = "authenticated"


def build_session_token(secret: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        _SESSION_PAYLOAD.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest


def verify_session_token(token: str, secret: str) -> bool:
    expected = build_session_token(secret)
    return hmac.compare_digest(token, expected)


def is_authenticated(request: Request, settings: Settings) -> bool:
    if not settings.auth_enabled:
        return True
    assert settings.app_session_secret is not None
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return False
    return verify_session_token(token, settings.app_session_secret)


def _cookie_secure(request: Request) -> bool:
    forwarded = request.headers.get("x-forwarded-proto", "")
    if forwarded:
        return forwarded.split(",")[0].strip().lower() == "https"
    return request.url.scheme == "https"


def set_session_cookie(response: Response, request: Request, settings: Settings) -> None:
    assert settings.app_session_secret is not None
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=build_session_token(settings.app_session_secret),
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(request),
        max_age=60 * 60 * 24 * 7,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")


def passwords_match(provided: str, expected: str) -> bool:
    provided_digest = hashlib.sha256(provided.encode("utf-8")).digest()
    expected_digest = hashlib.sha256(expected.encode("utf-8")).digest()
    return hmac.compare_digest(provided_digest, expected_digest)
