"""Report whether the dependencies this application needs are actually usable.

The pipeline depends on two things it does not own: OCR binaries on PATH and a
reachable Ollama server holding the configured model. Neither is verified by
importing the application, so without an explicit probe the service starts
cleanly and only fails when a reviewer uploads their first document.

Binaries are treated differently from the model. A missing binary cannot appear
at runtime and every request needs it, so it is fatal at startup. A model server
can legitimately start after the application, so it is reported rather than
fatal.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field

from app.config import Settings
from app.providers.ollama_client import build_ollama_client

logger = logging.getLogger(__name__)

# A readiness probe must answer quickly enough to be polled.
PROBE_TIMEOUT_SECONDS = 5.0


class MissingDependencyError(RuntimeError):
    pass


@dataclass(frozen=True)
class DependencyReport:
    ocr_binaries_present: bool
    missing_binaries: list[str]
    model_server_reachable: bool
    model_available: bool
    configured_model: str
    detail: str | None = None
    available_models: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return (
            self.ocr_binaries_present
            and self.model_server_reachable
            and self.model_available
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "ocr": {
                "ok": self.ocr_binaries_present,
                "missing": self.missing_binaries,
            },
            "model": {
                "ok": self.model_server_reachable and self.model_available,
                "server_reachable": self.model_server_reachable,
                "model_available": self.model_available,
                "configured": self.configured_model,
            },
            "detail": self.detail,
        }


def missing_ocr_binaries(settings: Settings) -> list[str]:
    """Return the configured OCR binaries that are not on PATH."""
    required = (
        settings.tesseract_binary,
        settings.pdftoppm_binary,
        settings.pdftotext_binary,
    )
    return [name for name in required if shutil.which(name) is None]


def require_ocr_binaries(settings: Settings) -> None:
    """Fail startup when an OCR binary is absent, rather than at first upload."""
    missing = missing_ocr_binaries(settings)
    if not missing:
        return
    raise MissingDependencyError(
        f"Required OCR binaries are not installed: {', '.join(missing)}. "
        "Install poppler and tesseract, or set TESSERACT_BINARY, PDFTOPPM_BINARY "
        "and PDFTOTEXT_BINARY to their locations."
    )


def probe(settings: Settings) -> DependencyReport:
    """Check every external dependency without raising."""
    missing = missing_ocr_binaries(settings)

    reachable = False
    available = False
    names: list[str] = []
    detail: str | None = None

    try:
        client = build_ollama_client(settings).with_options(
            timeout=PROBE_TIMEOUT_SECONDS, max_retries=0
        )
        names = sorted(model.id for model in client.models.list().data)
        reachable = True
        # Ollama reports a cloud model both with and without its :cloud suffix.
        configured = settings.ollama_model
        available = configured in names or configured.split(":")[0] in names
        if not available:
            detail = f"Model {configured!r} is not pulled. Run: ollama pull {configured}"
    except Exception as error:  # noqa: BLE001 - a probe reports failures, never raises
        detail = f"Model server at {settings.ollama_base_url} is unreachable: {error}"

    if missing:
        binaries = ", ".join(missing)
        detail = f"Missing OCR binaries: {binaries}." + (f" {detail}" if detail else "")

    return DependencyReport(
        ocr_binaries_present=not missing,
        missing_binaries=missing,
        model_server_reachable=reachable,
        model_available=available,
        configured_model=settings.ollama_model,
        detail=detail,
        available_models=names,
    )
