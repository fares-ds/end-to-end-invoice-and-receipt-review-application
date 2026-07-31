from openai import OpenAI

from app.config import Settings, get_settings


def build_ollama_client(settings: Settings | None = None) -> OpenAI:
    """Build an OpenAI-SDK client pointed at a local Ollama server.

    Ollama exposes an OpenAI-compatible surface, so the official SDK is reused
    unchanged. The API key is a placeholder that Ollama ignores; it exists only
    because the SDK refuses to construct without one.
    """
    resolved = settings or get_settings()
    return OpenAI(
        base_url=resolved.ollama_base_url,
        api_key=resolved.ollama_api_key,
    )
