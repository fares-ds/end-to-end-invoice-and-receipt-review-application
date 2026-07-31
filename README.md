# Invoice Review

An end-to-end invoice and receipt review application for Northstar Facilities B.V. It
combines local OCR extraction, deterministic finance rules, SQLite persistence, and a human
review interface.

Every stage runs on your own machine. There is no cloud account, no API key, and no metered
service anywhere in the stack.

## The stack

| Concern | Component |
| --- | --- |
| Document extraction | poppler (`pdftotext`, `pdftoppm`) and `tesseract` |
| Classification, independent review, GL suggestion, correction email | a local model served by [Ollama](https://ollama.com) |
| VAT validation | offline EU structure and checksum checks via `python-stdnum` |
| API | FastAPI, Pydantic v2, SQLAlchemy 2, SQLite |
| Interface | Vite, React, TypeScript, Tailwind CSS |

## Prerequisites

- Python 3.12 or newer, and [uv](https://docs.astral.sh/uv/)
- Node.js 22 or newer, and pnpm 11
- [Ollama](https://ollama.com), running locally
- poppler and tesseract with the English, Dutch, German, and French language data

```bash
# macOS
brew install poppler tesseract tesseract-lang

# Debian/Ubuntu
sudo apt-get install -y poppler-utils tesseract-ocr \
  tesseract-ocr-eng tesseract-ocr-nld tesseract-ocr-deu tesseract-ocr-fra
```

## Install

```bash
ollama pull gemma3:1b

cd backend
uv sync --locked

cd ../frontend
pnpm install --frozen-lockfile
```

Copy the environment templates. Neither file contains a secret — the backend file points at
your local Ollama server, and the frontend file sets `VITE_API_BASE_URL`.

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

## Run

```bash
./scripts/dev.sh
```

- API: <http://localhost:8000> (`GET /health` returns `{"status":"ok"}`)
- Interface: <http://localhost:5173>

Or run the whole thing, model included, in containers:

```bash
docker compose up --build
```

See [docs/local-deploy.md](docs/local-deploy.md) for model selection and memory requirements.

## Verify

```bash
cd backend
uv run --locked --no-sync ruff check app scripts

# Deterministic behaviour: no model or network needed, about a second
uv run --locked --no-sync python scripts/check_deterministic.py

# Corpus accuracy, with optional gating and regression detection
uv run --locked --no-sync python scripts/evaluate_corpus.py --merged
uv run --locked --no-sync python scripts/evaluate_corpus.py --min-accuracy 90
uv run --locked --no-sync python scripts/evaluate_corpus.py --baseline baselines/gemma3-1b.json

cd ../frontend
pnpm exec tsc -b --pretty false
pnpm lint
pnpm build
```

The corpus evaluator runs entirely locally, so it costs nothing and can be repeated as often
as you like.

## Accuracy note

Accuracy depends heavily on the model. Measured on the 13-document corpus:

| Model | Field accuracy | Exact documents | Policy matches |
| --- | ---: | ---: | ---: |
| `gemma3:1b` (default, local) | 93.5% | 3/13 | 4/13 |
| `gemma4:cloud` | 100% | 13/13 | 13/13 |

`gemma3:1b` is the default because it loads on a machine with very little free memory. It
misclassifies receipts as invoices and misreads some two-column layouts. If accuracy
matters more than staying offline, point `OLLAMA_MODEL` at a larger model and re-run the
evaluator to measure it yourself.

Confidence shown in the interface is derived, not model-reported: a value found in the
recovered text keeps the OCR confidence, and a value the model inferred is reduced.
Required normalization, such as ISO dates and repaired VAT identifiers, is not treated as
inference.

The independent review reads the document by a different route than the primary
extraction: a PDF is rasterized and OCRed while the primary extraction reads the embedded
text layer, so agreement between them carries real information. An image has only one
route, and the review says so when it shares a source.

## Documentation

Start with [the client brief](docs/client-brief.md), then
[the architecture](docs/architecture.md) and [the API and pipeline](docs/api-and-pipeline.md).
