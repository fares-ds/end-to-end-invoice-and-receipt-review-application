"""Send a prompt to the local Ollama model through the shared client.

Run from this folder:

    uv run --project ../backend --locked --no-sync python create_local_response.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import get_settings  # noqa: E402
from app.providers.ollama_client import build_ollama_client  # noqa: E402


def main() -> None:
    prompt = sys.argv[1] if len(sys.argv) > 1 else "What is the capital of France?"
    settings = get_settings()
    client = build_ollama_client(settings)
    response = client.chat.completions.create(
        model=settings.ollama_model,
        messages=[{"role": "user", "content": prompt}],
    )
    print(response.choices[0].message.content)


if __name__ == "__main__":
    main()
