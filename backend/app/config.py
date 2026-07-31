from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[1]

# Local Ollama defaults. Ollama ignores the API key but the OpenAI SDK requires a
# non-empty value, so a placeholder is used rather than a real credential.
DEFAULT_MODEL = "gemma3:1b"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"
DEFAULT_OCR_LANGUAGES = "eng+nld+deu+fra"


@dataclass(frozen=True)
class AppConfig:
    expected_customer_name: str = "Northstar Facilities B.V."
    expected_customer_vat_id: str = "NL00449544B01"
    database_url: str = "sqlite:///./data/documents.db"
    upload_dir: Path = Path("./data/uploads")
    max_upload_bytes: int = 4 * 1024 * 1024
    min_field_confidence: float = 0.80
    # Pages rasterized per document, matching the previous two-page provider limit.
    max_ocr_pages: int = 2
    # Resolution used when rasterizing a PDF page before OCR.
    ocr_dpi: int = 200


APP_CONFIG = AppConfig()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL
    ollama_api_key: str = Field(default="ollama", min_length=1)
    ollama_model: str = DEFAULT_MODEL
    # Optional. When set, the document reviewer sends the original PDF/image to this
    # model instead of OCR text. Requires a vision-capable model and enough memory.
    ollama_vision_model: str | None = None

    # How structured output is requested. Ollama constrains locally-served models
    # with a grammar, so they honour a json_schema response format. Cloud-served
    # models are proxied without that constraint and must be prompted for JSON
    # instead. "auto" picks per model; set explicitly to override.
    ollama_output_mode: Literal["auto", "native", "prompted"] = "auto"

    ocr_languages: str = DEFAULT_OCR_LANGUAGES
    tesseract_binary: str = "tesseract"
    pdftoppm_binary: str = "pdftoppm"
    pdftotext_binary: str = "pdftotext"

    allowed_origin: str = "http://localhost:5173"
    app_access_password: str | None = None
    app_session_secret: str | None = None
    frontend_dist_dir: Path | None = None

    @model_validator(mode="after")
    def normalize_optional_settings(self) -> "Settings":
        # Assign in place and return self; returning a copy from a top-level
        # validator is unsupported and makes pydantic warn.
        self.app_access_password = (self.app_access_password or "").strip() or None
        self.app_session_secret = (self.app_session_secret or "").strip() or None
        self.ollama_vision_model = (self.ollama_vision_model or "").strip() or None
        if self.app_access_password and not self.app_session_secret:
            raise ValueError(
                "APP_SESSION_SECRET is required when APP_ACCESS_PASSWORD is set"
            )
        return self

    @property
    def auth_enabled(self) -> bool:
        return self.app_access_password is not None

    @property
    def vision_enabled(self) -> bool:
        return self.ollama_vision_model is not None

    def prompted_output(self, model_name: str | None = None) -> bool:
        """Whether this model needs JSON requested in the prompt rather than enforced."""
        if self.ollama_output_mode != "auto":
            return self.ollama_output_mode == "prompted"
        return (model_name or self.ollama_model).endswith(":cloud")

    def resolve_frontend_dist(self) -> Path | None:
        if self.frontend_dist_dir is not None:
            path = self.frontend_dist_dir
            return path if path.is_dir() else None
        for candidate in (
            BACKEND_ROOT.parent / "frontend" / "dist",
            Path("/app/frontend/dist"),
        ):
            if candidate.is_dir():
                return candidate
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
