# API endpoints and pipeline

This document describes the Invoice Review HTTP API and how `POST /api/documents` runs the document pipeline.

Base URL (local): `http://localhost:8000`

Interactive docs while the API is running:

- Swagger UI: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

CORS allows the Vite app at `http://localhost:5173`.

---

## Endpoint summary

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Liveness check |
| `GET` | `/api/accounting/gl-accounts` | Fixed Northstar GL catalog |
| `POST` | `/api/documents` | Upload a document and run the full pipeline |
| `GET` | `/api/documents` | List saved reviews (newest first) |
| `GET` | `/api/documents/{document_id}` | Fetch one review |
| `GET` | `/api/documents/{document_id}/file` | Serve the stored upload bytes |
| `PUT` | `/api/documents/{document_id}` | Apply field corrections and revalidate |
| `PUT` | `/api/documents/{document_id}/accounting` | Override / confirm selected GL account |
| `POST` | `/api/documents/{document_id}/decision` | Approve or reject |
| `POST` | `/api/documents/{document_id}/correction-email` | Draft a supplier correction email |
| `DELETE` | `/api/documents/{document_id}` | Delete a saved review and its upload file |

---

## Shared response shape

Document endpoints return `DocumentResponse`:

| Field | Type | Meaning |
|-------|------|---------|
| `id` | string (UUID) | Stable review id |
| `original_filename` | string | Filename from the upload |
| `content_type` | string | `application/pdf`, `image/jpeg`, or `image/png` |
| `status` | string | `processing`, `ready`, `needs_review`, `approved`, `rejected`, or `failed` |
| `classification` | object \| null | Invoice vs receipt label from the local model |
| `extraction` | object \| null | Mapped Document Intelligence fields (evidence) |
| `validation` | object \| null | Compact findings summary for the teaching UI |
| `gl_suggestion` | object \| null | Raw pipeline GL suggestion |
| `review_data` | object \| null | Flat editable projection used for policy and Maya edits |
| `document_review` | object \| null | LLM cross-check comparisons and fallbacks |
| `accounting_coding` | object \| null | Suggestion + selected GL + override flag |
| `issues` | array | Northstar `ValidationIssue` list |
| `supplier_action_required` | bool | True when supplier-fixable issues exist |
| `error_message` | string \| null | Set when status is `failed` |
| `created_at` / `updated_at` | ISO datetime | Persistence timestamps |

Status after a successful pipeline run:

- `needs_review` — validation reported at least one **error**
- `ready` — pipeline finished without validation errors (warnings allowed)

Decided records use `approved` or `rejected` and become immutable. A pipeline exception is persisted as `failed`, then the HTTP handler returns **502**. Unsupported documents from the LLM review return **422**.

---

## Pipeline steps

`build_default_pipeline()` runs:

1. **Classification** — the local model labels invoice vs receipt from recovered text.
2. **Extraction** — local OCR structured by the `local-invoice` or `local-receipt` extractor.
3. **Document review** — project DI → `ReviewData`, run independent LLM extraction, merge gaps only (DI wins on conflict).
4. **Validation** — pure Northstar invoice/receipt policy + duplicate detection.
5. **GL categorization** — suggest one catalog code from `6100`–`6190`.

---

## Review actions

- `PUT /api/documents/{id}` — body is `DocumentCorrectionRequest` (scalar fields only). Changed fields are marked `human` in `field_sources`, then policy re-runs.
- `PUT /api/documents/{id}/accounting` — `{ "gl_account_code": "6170" }` must exist in the catalog.
- `POST /api/documents/{id}/decision` — `{ "decision": "approved" | "rejected" }`. Approval requires no error issues and a valid selected GL.
- `POST /api/documents/{id}/correction-email` — drafts only; the app never sends mail. Requires supplier-fixable issues.

---

## Corpus evaluation

```bash
cd backend
uv run --locked --no-sync python scripts/evaluate_corpus.py
uv run --locked --no-sync python scripts/evaluate_hybrid.py
```

`evaluate_corpus.py` checks Document Intelligence field accuracy against `samples/manifest.json` and reports whether policy issue codes match `expected_issue_codes` (duplicate detection still needs a peer row in SQLite for sample `10`).
