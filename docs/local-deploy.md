# Deployment

Invoice Review runs on your own machine. Document extraction is entirely local; the model
calls go through Ollama, which by default uses a cloud-served model.

## What replaces the hosted services

| Concern | Local component |
| --- | --- |
| Document extraction | poppler (`pdftotext`, `pdftoppm`) and `tesseract` |
| Classification, independent review, GL suggestion, correction email | a model served by Ollama, cloud-served by default |
| Database | SQLite file under `backend/data/` |
| File storage | `backend/data/uploads/` |
| Hosting | uvicorn on your machine, or one Docker image |

## Option 1: run directly on the host

Install the OCR binaries once:

```bash
# macOS
brew install poppler tesseract tesseract-lang

# Debian/Ubuntu
sudo apt-get install -y poppler-utils tesseract-ocr \
  tesseract-ocr-eng tesseract-ocr-nld tesseract-ocr-deu tesseract-ocr-fra
```

Install and start Ollama from <https://ollama.com>. The default model is cloud-served, so
sign in rather than pulling weights:

```bash
ollama signin
```

To run fully offline instead, pull a local model and set `OLLAMA_MODEL`:

```bash
ollama pull gemma3:1b
```

Configure and start the application:

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
./scripts/dev.sh
```

## Option 2: docker

The image bundles poppler and tesseract and talks to the Ollama on your host. It
deliberately does not run its own Ollama: cloud credentials belong to the signed-in host
instance, and on Apple silicon a container cannot reach the Metal GPU.

```bash
docker compose up --build
open http://localhost:8000
```

The container health check polls `/ready`, which fails while OCR or the model server is
unusable — unlike `/health`, which only reports that the process is alive.

## Choosing a model

The default `gemma4:cloud` is chosen for accuracy. Small local models that fit in ordinary
memory are not good enough for this work.

| Model | Where it runs | Corpus field accuracy | Notes |
| --- | --- | ---: | --- |
| `gemma4:cloud` | Ollama cloud | 100% | Default. Needs a signed-in account with a subscription. |
| `gemma3:1b` | local, ~1.0 GB | 93.5% | Fully offline. Misclassifies receipts; misreads two-column layouts. |
| `qwen3.5:2b` | local, ~3.0 GB | not measured | Needs ~4 GB free. |
| `qwen3.5:4b` | local, ~5.4 GB | not measured | Needs ~6 GB free. |

Set the choice in `backend/.env`:

```bash
OLLAMA_MODEL=gemma3:1b
```

Ollama refuses to load a local model that does not fit in available memory, and an
oversized one is killed mid-request. Measure any change with
`scripts/evaluate_corpus.py` rather than assuming.

## How the independent review stays independent

The review is a second reading of the document, not a re-reading of the primary
extraction's text. A PDF is rasterized and OCRed for the review while the primary
extraction reads the embedded text layer, so the two can genuinely disagree. An image
has only one route, so its review shares a source and the result says so.

## Optional shared-password gate

If you expose the app beyond localhost, set both values:

```bash
APP_ACCESS_PASSWORD=some-demo-password
APP_SESSION_SECRET=some-long-random-string
```

The backend refuses to start with a password but no session secret.
