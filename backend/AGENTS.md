# Backend agent instructions

Read [../AGENTS.md](../AGENTS.md) first. The root file contains the project-wide product boundaries, dependency policy, teaching rules, and verification policy. This file adds backend-specific conventions.

## Stack

- Python 3.12 or newer.
- `uv` for dependency and project management.
- FastAPI and uvicorn for the HTTP service.
- Pydantic v2 and pydantic-settings for typed boundaries and provider settings.
- SQLAlchemy 2 with local SQLite persistence.
- Local OCR binaries (poppler, tesseract) and a local Ollama model behind provider adapters.
- Ruff for linting and import/style checks.

The stack is locked unless Dave explicitly approves a change.

## Layout

The implementation uses these boundaries:

```text
backend/
├── app/
│   ├── main.py              # FastAPI construction and dependency wiring
│   ├── config.py            # Provider settings and fixed application config
│   ├── invoices/            # HTTP, orchestration, persistence, and policy by module
│   ├── accounting/          # Fixed GL catalog and validated selections
│   ├── document_review/     # Provider-independent review and reconciliation
│   ├── correction_email/    # Eligibility and provider-independent draft models
│   ├── services/            # Local OCR and local structured extraction
│   └── providers/           # Ollama adapters; SDK types stop here
├── scripts/                 # Explicit provider checks and corpus evaluations
├── pyproject.toml
└── uv.lock
```

Do not create empty architectural layers before the tutorial reaches them.

## Boundaries and code style

- Routes own HTTP parsing, response models, and status-code translation.
- Services orchestrate the user workflow and depend on explicit interfaces.
- Repositories own SQLAlchemy and SQLite access.
- Provider adapters are the only modules allowed to expose third-party SDK types.
- Deterministic validation and reconciliation remain separate from AI extraction or generation.
- Keep public functions typed and modules focused. Prefer dataclasses, enums, `pathlib`, and other standard-library capabilities over helper packages.
- Validate files, HTTP input, provider output, and database writes at their boundaries. Do not repeatedly validate trusted internal calls.
- The OCR subprocesses, Ollama client, and SQLite clients are all synchronous. Use normal FastAPI `def` handlers for synchronous request paths instead of blocking an async event loop.
- Do not add auth, queues, workers, caching, analytics, deployment code, or accounting integrations unless the user story changes.

## Configuration

- `app/config.py` is the only backend configuration boundary.
- The Ollama base URL, model names, and OCR binary/language settings are read through its Pydantic `Settings` model.
- Fixed tutorial policy belongs in its immutable application configuration, not environment variables.
- Never call `os.getenv`, read `os.environ`, or call `load_dotenv` in application modules or scripts.
- Fail clearly when Ollama is unreachable or an OCR binary is missing. Do not hide these failures behind silent fallbacks.
- Never commit `.env`, uploaded documents, SQLite databases, or generated runtime data.

## Dependencies

- Never add a dependency without Dave's explicit approval.
- Use exact direct versions and commit `uv.lock` with every approved dependency change.
- Keep `add-bounds = "exact"` and `exclude-newer = "7 days"` under `[tool.uv]`.
- Install with `uv sync --locked`.
- Commands that must use the existing environment run through `uv run --locked --no-sync`.
- Prefer a small local function when a dependency would only replace a few clear standard-library lines.

## Verification

Verify a locked install with:

```bash
uv sync --locked
```

As implementation is added, keep the documented backend check green:

```bash
uv run --locked --no-sync ruff check app scripts
```

Provider checks and corpus evaluations run entirely against local OCR and a local model, so they cost nothing and can be re-run freely. They do need Ollama running with the configured model pulled, plus `poppler-utils` and `tesseract-ocr` on PATH. Complete verification also includes startup readiness and the manual end-to-end workflow.

Do not add `tests/`, `pytest`, or committed automated test files. This weekly teaching project uses linting, explicit provider/corpus checks, and manual workflow verification as defined by the root instructions.
