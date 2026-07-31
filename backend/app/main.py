from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.accounting.routes import router as accounting_router
from app.auth.routes import router as auth_router
from app.auth.session import is_authenticated
from app.config import APP_CONFIG, get_settings
from app.database import build_database
from app.documents.models import DocumentRecord
from app.documents.routes import router as document_router
from app.providers.ollama_correction_email import OllamaCorrectionEmailDrafter
from app.providers.ollama_document_review import OllamaDocumentReviewer
from app.readiness import probe, require_ocr_binaries


class AccessPasswordMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        settings = get_settings()
        if not settings.auth_enabled:
            return await call_next(request)

        path = request.url.path
        if (
            path == "/health"
            or path.startswith("/api/auth/")
            or not path.startswith("/api/")
        ):
            return await call_next(request)

        if not is_authenticated(request, settings):
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
            )
        return await call_next(request)


def create_app() -> FastAPI:
    config = APP_CONFIG
    require_ocr_binaries(get_settings())
    config.upload_dir.mkdir(parents=True, exist_ok=True)
    database_path = config.database_url.removeprefix("sqlite:///")
    if config.database_url.startswith("sqlite:///"):
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)

    engine, session_factory = build_database(config.database_url)
    DocumentRecord.metadata.create_all(engine)

    settings = get_settings()

    app = FastAPI(title="Invoice Review API", version="0.1.0")
    app.state.config = config
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.document_reviewer = OllamaDocumentReviewer(settings=settings)
    app.state.correction_email_drafter = OllamaCorrectionEmailDrafter(settings=settings)
    app.add_middleware(AccessPasswordMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.allowed_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth_router)
    app.include_router(document_router)
    app.include_router(accounting_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        """Liveness only: the process is up. See /ready for dependency state."""
        return {"status": "ok"}

    @app.get("/ready")
    def ready(response: Response) -> dict[str, object]:
        """Readiness: whether OCR and the model server can actually serve a review."""
        report = probe(get_settings())
        if not report.ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return report.as_dict()

    frontend_dist = settings.resolve_frontend_dist()
    if frontend_dist is not None:
        assets_dir = frontend_dist / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/{full_path:path}")
        def spa_fallback(full_path: str) -> FileResponse:
            candidate = frontend_dist / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(frontend_dist / "index.html")

    return app
