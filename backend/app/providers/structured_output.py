"""Request and parse structured model output across differing Ollama backends.

Ollama enforces a JSON schema on locally-served models with a grammar sampler, so
a ``json_schema`` response format is honoured exactly. Cloud-served models are
proxied without that sampler and ignore the response format, replying in prose or
fenced markdown. These helpers make one call site work for both: the schema is
requested through the API *and* stated in the prompt, and the reply is parsed
leniently.
"""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def build_request(
    *,
    model: str,
    system: str,
    user: str,
    schema: dict[str, Any],
    schema_name: str,
    prompted: bool,
) -> dict[str, Any]:
    """Build chat-completion kwargs appropriate to the backend's capabilities."""
    instructions = system
    if prompted:
        instructions = (
            f"{system}\n\n"
            "Reply with a single JSON object and nothing else. No prose, no "
            "explanation, no markdown fences. Include only the fields this schema "
            "defines and no others. It must validate against this JSON "
            f"schema:\n{json.dumps(schema)}"
        )

    request: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": user},
        ],
        "temperature": 0,
    }
    if not prompted:
        request["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": schema},
        }
    return request


def parse_json_object(content: str) -> dict[str, Any]:
    """Extract one JSON object from a model reply.

    Raises ``json.JSONDecodeError`` when no object can be recovered, so callers
    keep their existing error handling.
    """
    text = (content or "").strip()
    if not text:
        raise json.JSONDecodeError("empty model response", text or "", 0)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fenced = _FENCE.search(text)
    if fenced:
        return json.loads(fenced.group(1))

    # Fall back to the outermost brace pair, which covers a reply wrapped in prose.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])

    raise json.JSONDecodeError("no JSON object in model response", text, 0)
