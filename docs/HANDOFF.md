# Handoff

State as of 2026-07-31. Everything described here is committed and pushed to
`main` at `github.com/fares-ds/end-to-end-invoice-and-receipt-review-application`.

This document lists what is *open*. What was already done is recorded in
[build-along.md](build-along.md) (nine slices, each with the reason and the
observable result) and in the commit messages, which are written to be read.

---

## Context you need before touching anything

**The project's spine.** The model reads evidence; deterministic Python decides what blocks
approval. [AGENTS.md](../AGENTS.md) states this as a boundary, and it is the thing not to
break: no model output may become policy.

**Two verification layers, and they catch different defects.** This is not redundancy and
was demonstrated, not assumed — reintroducing the OCR line-flattening bug left the corpus
evaluator at 169/169 on `gemma4:cloud` while `check_deterministic.py` failed six behaviours
immediately. A capable model reads flattened text fine; end-to-end scores are blind to
structural defects. Run both.

```bash
cd backend
uv run --locked --no-sync python scripts/check_deterministic.py          # 44 behaviours, no model
uv run --locked --no-sync python scripts/evaluate_corpus.py --merged \
    --baseline baselines/gemma4-cloud.json --min-accuracy 99
uv run --locked --no-sync python scripts/error_analysis.py               # per-field breakdown
```

**`--merged` matters.** Without it the evaluator scores primary extraction only and
understates real accuracy, because the merge fills gaps from the independent review.

---

## Open work, ranked

### 1. Column-aware segmentation — the highest-value item

[evaluation.md](evaluation.md) identifies that **5 of 11 errors on `gemma3:1b` are one
cause**: `pdftotext -layout` preserves two-column supplier/customer blocks, so both VAT
numbers land on one line and the model takes the first, dropping `customer_vat_id`.

Nothing has acted on that finding. Implementing segmentation, re-running, and reporting the
delta closes the full loop — measured, diagnosed, fixed, re-measured — against a baseline
that already exists (`baselines/gemma3-1b.json`: 93.5%, `customer_vat_id` 8/13).

A negative result is still worth committing. The point is the loop, not the win.

Touch `backend/app/services/ocr_text_service.py`. Extend `check_deterministic.py` with the
new behaviour before changing the extractor.

### 2. CI

No `.github/workflows`. The gates exist but nothing runs them, which is how the 93.5% → 91.7%
regression during this session went unnoticed until a manual re-run.

A runner has no Ollama and no subscription, so the workable job is: `ruff check app scripts`,
`check_deterministic.py` (44 checks, no network), and the frontend `tsc`/`lint`/`build`.
Corpus evaluation stays local. Roughly twenty minutes of work.

### 3. Confidence calibration

The README advertises this as a known gap: *the 0.80 threshold is a policy choice, not a
measured separation*. The labels needed to check it are in `samples/manifest.json`.

Question: does derived confidence actually predict correctness? Plot the separation, compute
where the threshold should sit. A result showing the threshold is wrong is more valuable than
one confirming it.

Confidence is built in `_FieldBuilder` in
`backend/app/services/local_extraction_service.py`; the semantics are documented in
[architecture.md](architecture.md#confidence).

### 4. Cost and latency

Unmeasured. `evaluate_corpus.py` reports p50/p95 but embeddings and model calls are cached or
variable, so the numbers are not meaningful. No token or cost tracking anywhere. This is a
gap worth closing if the project is used as evidence of production thinking.

---

## Deliberately not worth doing

- **Failure modes 3 and 4** in [evaluation.md](evaluation.md) — three errors, all already
  caught downstream by arithmetic or by `python-stdnum` rejecting a malformed VAT. Fixing
  them improves a metric, not reviewer safety.
- **Chasing `gemma3:1b` accuracy.** It is a capability ceiling, verified by falsifying the
  alternatives: not extraction, not prompt framing, not vocabulary. It misclassifies the
  fuel receipt as an invoice and no prompt work changed that.
- **Vision mode.** Removed as unexecutable and redundant; the dual-route OCR gives genuine
  independence without it. Do not reintroduce without a vision model that actually runs.

---

## Environment gotchas that cost time this session

| Gotcha | Detail |
| --- | --- |
| **Memory is tight** | ~3 GB free of 16 GB. Local models above ~2 GB refuse to load or are OOM-killed mid-request. `qwen3.5:4b` fails outright; `qwen3.5:2b` is unusably slow. |
| **Cloud models ignore `json_schema`** | Ollama grammar-constrains *local* models only. Cloud models are proxied without the sampler and reply in prose. `Settings.prompted_output()` handles this; `auto` keys off the `:cloud` suffix. |
| **Default model needs a subscription** | `gemma4:cloud`. `ollama signin` required. Credentials live in the signed-in host Ollama and cannot be reached from a containerised one — which is why `docker-compose.yml` points at `host.docker.internal`. |
| **pnpm version** | System has 9.x; the project pins 11.3.0 and pnpm 9 fails on the settings-only `pnpm-workspace.yaml`. Use `npx pnpm@11.3.0`. |
| **Spurious BLAS warnings** | Apple Accelerate raises divide-by-zero/overflow flags on finite matmuls. Verified correct to 6e-08 against float64. Suppressed with a comment where it occurs. |
| **Scripts need the path bootstrap** | `package = false` means `app` is never installed. Every script in `backend/scripts/` inserts the backend root into `sys.path`; keep that when adding one. |

---

## Loose ends on this machine

- Local-only branches `backup-before-rewrite` and `backup-with-dave` hold pre-rewrite
  history. They served their purpose and can be deleted.
- `backend/data/` holds ~32 KB of test uploads and the SQLite database. Gitignored.
- A container `e2e-invoice-review-app-1` may still be running and holding memory.
  `docker compose down`.
- The `ollama` container on port 11434 is **not** part of this project — it predates it and
  serves the host Ollama everything uses. Do not remove it.

---

## Suggested skills for the next session

- **`/tdd`** for the column-segmentation work. The pattern that worked here was: add the
  behaviour to `check_deterministic.py` first, watch it fail, then change the extractor.
  Verify each check can actually fail — two of the original 44 passed for the wrong reason
  until tested by reintroducing a real bug.
- **`/diagnose`** if a regression appears. The disciplined loop found the OCR flattening bug
  by printing the text the model actually received rather than reasoning about the model.
- **`/code-review`** before pushing anything that touches the confidence model or the
  Northstar rules — both decide what a reviewer sees.

## Related work

`../maghreb-retrieval-bench/` — a separate from-scratch repository started this session: a
retrieval ablation workbench on a multilingual Maghrebi corpus. Its own README carries the
findings. Its open items are native-speaker validation of 60 Arabic/Darija queries and a
cross-encoder reranking stage.
