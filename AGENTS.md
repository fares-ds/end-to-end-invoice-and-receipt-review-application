# Invoice Review agent instructions

Read `docs/client-brief.md`, `docs/architecture.md`, and `docs/build-along.md` before changing the project.

## Stack

- Backend: Python 3.12+, uv, FastAPI, Pydantic v2, SQLAlchemy 2, SQLite.
- Extraction: local OCR (poppler `pdftotext`/`pdftoppm` plus `tesseract`) structured by a local model.
- Independent review and categorization: an Ollama-served model through the OpenAI-compatible API with strict structured output. The default is cloud-served for accuracy; a local model is supported for offline use.
- VAT checks: local EU structure/checksum validation with `python-stdnum`; no live VIES claim.
- Document extraction (poppler, tesseract) is always local and free. Model calls default to a cloud-served Ollama model, which requires a signed-in account with a subscription. Setting `OLLAMA_MODEL` to a local model restores fully offline operation at measurably lower accuracy.
- Frontend: Vite, React, TypeScript strict, Tailwind CSS, pnpm.
- Verification: Ruff for backend; TypeScript, ESLint, production build, explicit live evaluators, and a manual browser walkthrough for the complete flow.

## Boundaries

- OCR binaries are invoked only from `backend/app/services/ocr_text_service.py`.
- OpenAI SDK types stop in the provider adapters under `backend/app/providers/`, including document review, GL suggestion, and correction-email drafting.
- The document reviewer returns classification plus provider-independent structured fields. Local OCR extraction remains primary; deterministic merging only fills its missing fields and exposes provenance. The reviewer reads the document by a different route than the primary extraction: a PDF is rasterized and OCRed while the primary extraction reads the embedded text layer. An image has only one route, and the review states when it shares a source.
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
- Keep deterministic business rules and provider boundaries explicit and easy to inspect.
- `backend/scripts/check_deterministic.py` locks the behaviour of the pure functions that decide what a reviewer sees and what blocks approval. It needs no model or network, runs in about a second, and exits non-zero on drift. Run it before and after touching OCR parsing, VAT repair, confidence scoring, or the Northstar rules. It is a check script, not a test suite: no `tests/` directory, no pytest, no `*.test.*`.
- `backend/scripts/evaluate_corpus.py` can gate (`--min-accuracy`) and detect regression (`--baseline`). A baseline records the model that produced it, because local and cloud accuracy are not comparable.
- Local OCR depends on `poppler-utils` and `tesseract-ocr` with the `eng`, `nld`, `deu`, and `fra` language packs. These are system binaries, not Python dependencies.

## Secrets and data

Never commit `.env`, uploaded invoices, private documents, or SQLite databases. Generated samples must contain only fictional data. The local stack needs no credentials, so nothing in `backend/.env.example` is a secret.
