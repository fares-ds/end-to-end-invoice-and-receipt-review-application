# Invoice Review agent instructions

Read `docs/client-brief.md`, `docs/architecture.md`, and `docs/build-along.md` before changing the project.

## Stack

- Backend: Python 3.12+, uv, FastAPI, Pydantic v2, SQLAlchemy 2, SQLite.
- Extraction: local OCR (poppler `pdftotext`/`pdftoppm` plus `tesseract`) structured by a local model.
- Independent review and categorization: a local Ollama model through the OpenAI-compatible API with strict structured output.
- VAT checks: local EU structure/checksum validation with `python-stdnum`; no live VIES claim.
- The whole stack runs offline on a developer machine. No paid account, API key, or cloud service is required.
- Frontend: Vite, React, TypeScript strict, Tailwind CSS, pnpm.
- Verification: Ruff for backend; TypeScript, ESLint, production build, explicit live evaluators, and a manual browser walkthrough for the complete flow.

## Boundaries

- OCR binaries are invoked only from `backend/app/services/ocr_text_service.py`.
- OpenAI SDK types stop in the provider adapters under `backend/app/providers/`, including document review, GL suggestion, and correction-email drafting.
- The document reviewer returns classification plus provider-independent structured fields. Local OCR extraction remains primary; deterministic merging only fills its missing fields and exposes provenance. By default the reviewer reads the same OCR text as the primary extraction, so the two are not fully independent; setting `OLLAMA_VISION_MODEL` restores an independent image-based review.
- The GL categorizer receives normalized invoice fields only.
- The GL catalog and selection validation live in `backend/app/accounting/`; model output never becomes business policy.
- Business rules live in `backend/app/documents/validation.py` and must be pure.
- HTTP concerns live in `routes.py`; orchestration lives in `service.py`; SQLite access lives in `repository.py`.
- Settings are read only through `backend/app/config.py` and `frontend/src/lib/env.ts`.
- Do not add auth, queues, workers, deployment, batch processing, email ingestion/sending, or accounting integrations.
- Receipt processing uses the same normalized financial-document data and a separate deterministic policy. Live VIES registration lookup remains outside the build.

## Dependencies

- Never add a dependency without asking Dave first.
- Every dependency must earn its place. If only a small function is needed, propose implementing that function locally instead.
- Never run `uv add`, `pip install`, or `pnpm add` without explicit approval.
- When proposing a package, give the exact pinned version and one sentence explaining why it is better than local code.
- Pin direct dependencies exactly and commit `backend/uv.lock` and `frontend/pnpm-lock.yaml`.
- Keep `[tool.uv] add-bounds = "exact"` and `exclude-newer = "7 days"` in `backend/pyproject.toml`.
- Keep `savePrefix: ""`, `minimumReleaseAge: 10080`, and `minimumReleaseAgeStrict: true` in `frontend/pnpm-workspace.yaml`.
- Install with `uv sync --locked` and `pnpm install --frozen-lockfile`.
- Commands that must only run the existing backend environment use `uv run --locked --no-sync`.
- A cooldown exception requires explicit approval, a package/version-specific scope, and an adjacent explanation.

## Teaching guide

Update `docs/build-along.md` in the same commit as every working slice. Include the outcome, why, exact commands, observable result, and checkpoint.

## Verification policy

- Do not add automated test suites, `tests/` directories, or `*.test.*` files to this end-to-end teaching project.
- Keep verification proportional and demo-oriented: verify locked installs on the starter; as code is added, lint the backend, type-check/lint/build the frontend, exercise the fictional corpus evaluators, and manually walk through the user story in the browser.
- Keep deterministic business rules and provider boundaries explicit and easy to inspect even though they are not backed by a committed unit-test suite.
- Local OCR depends on `poppler-utils` and `tesseract-ocr` with the `eng`, `nld`, `deu`, and `fra` language packs. These are system binaries, not Python dependencies.

## Secrets and data

Never commit `.env`, uploaded invoices, private documents, or SQLite databases. Generated samples must contain only fictional data. The local stack needs no credentials, so nothing in `backend/.env.example` is a secret.
