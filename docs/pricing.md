# Cost and resource use

Invoice Review has no metered component. Every stage that once called a hosted service now
runs on the developer machine, so the monetary cost of any workload is **€0.00**, including
reprocessing the same document repeatedly.

## Cost of this setup

| Component | Where it runs | Standing cost | Usage cost |
| --- | --- | ---: | ---: |
| Document extraction (poppler + tesseract) | Developer machine | €0 | €0 |
| Classification, review, GL suggestion, correction email (Ollama) | Developer machine | €0 | €0 |
| FastAPI, React, SQLite, uploaded files | Developer machine | €0 | €0 |
| Hosting, managed database, object storage | Not deployed | €0 | €0 |

There is no request quota, no page allowance, no token meter, and no per-document limit. The
4 MB upload cap is an application policy, not a provider constraint.

## What it costs instead: memory and time

The real budget is local resources. Ollama refuses to load a model that does not fit in
available memory, and an oversized model is killed mid-request, so plan for headroom.

| Model | Approx. resident size | Suitable when |
| --- | ---: | --- |
| `gemma3:1b` | ~1.0 GB | Default. Works on a machine with ~2 GB free. |
| `qwen3.5:2b` | ~3.0 GB | ~4 GB free. |
| `qwen3.5:4b` | ~5.4 GB | ~6 GB free. Best small-model accuracy. |
| `qwen2.5vl:3b` | ~3.2 GB | Optional independent vision review. |

Per-document wall-clock time depends on the model and whether OCR is needed:

- A PDF with a text layer skips OCR entirely — `pdftotext` returns in milliseconds.
- A scan or photo is rasterized at 200 DPI and passed through tesseract, which costs roughly
  one to three seconds per page.
- Each document then makes three local model calls: classification, structured extraction,
  and GL suggestion. A correction-email draft adds a fourth, only when requested.

## Extraction accuracy is the real trade-off

The hosted `prebuilt-invoice` model was trained on invoices and returned per-field
confidence. The local stack recovers text and asks a general-purpose model to structure it,
which is measurably less accurate on the same corpus. Confidence is derived rather than
model-reported: a value found verbatim in the recovered text keeps the OCR confidence, and a
value the model reformatted or inferred is reduced by 25%.

Measure it yourself rather than trusting an estimate — the evaluator is free to run as often
as you like:

```bash
cd backend
uv run --locked --no-sync python scripts/evaluate_corpus.py
```

## Recheck the corpus

```bash
jq '{documents: length, pages: ([.[].pages] | add)}' samples/manifest.json
```

Expected:

```json
{
  "documents": 13,
  "pages": 14
}
```
