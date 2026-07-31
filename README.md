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

See [docs/local-deploy.md](docs/local-deploy.md) for model selection, memory requirements,
and the optional vision-review mode.

## Verify

```bash
cd backend
uv run --locked --no-sync ruff check app scripts
uv run --locked --no-sync python scripts/check_local_extraction.py
uv run --locked --no-sync python scripts/evaluate_corpus.py

cd ../frontend
pnpm exec tsc -b --pretty false
pnpm lint
pnpm build
```

The corpus evaluator runs entirely locally, so it costs nothing and can be repeated as often
as you like.

## Accuracy note

A general-purpose local model structuring OCR text is less accurate than a purpose-trained
hosted invoice model. Confidence shown in the interface is derived, not model-reported: a
value found verbatim in the recovered text keeps the OCR confidence, and a value the model
reformatted or inferred is reduced. Run the corpus evaluator to measure the current setup
rather than assuming a figure.

By default the independent review reads the same OCR text as the primary extraction, so the
two are not fully independent; the review states when this is the case. Setting
`OLLAMA_VISION_MODEL` restores an independent read of the page image.

## Documentation

Start with [the client brief](docs/client-brief.md), then
[the architecture](docs/architecture.md) and [the API and pipeline](docs/api-and-pipeline.md).
