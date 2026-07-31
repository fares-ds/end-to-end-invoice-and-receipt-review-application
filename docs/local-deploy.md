# Local deployment

Invoice Review runs entirely on your own machine. There is no cloud account, API key, or
metered service anywhere in the stack.

## What replaces the hosted services

| Concern | Local component |
| --- | --- |
| Document extraction | poppler (`pdftotext`, `pdftoppm`) and `tesseract` |
| Classification, independent review, GL suggestion, correction email | a local model served by Ollama |
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

Install and start Ollama from <https://ollama.com>, then pull the model:

```bash
ollama pull gemma3:1b
```

Configure and start the application:

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
./scripts/dev.sh
```

## Option 2: docker compose

This builds the application image, starts Ollama in a second container, and pulls the model
into a named volume on first run:

```bash
docker compose up --build
open http://localhost:8000
```

On Apple silicon a container cannot reach the Metal GPU, so a container-hosted model is
noticeably slower than a native one. To keep Docker for the app but use a native Ollama,
comment out the `ollama` and `model-pull` services and set:

```yaml
OLLAMA_BASE_URL: http://host.docker.internal:11434/v1
```

## Choosing a model

`gemma3:1b` is the default because it is small enough to load on a machine with very little
free memory. Larger models extract more accurately. Check what your machine can hold before
switching — Ollama refuses to load a model that does not fit, and the container is killed if
it runs out of memory mid-request.

| Model | Approx. resident size | Notes |
| --- | ---: | --- |
| `gemma3:1b` | ~1.0 GB | Default. Fastest, adequate on text-layer PDFs. |
| `qwen3.5:2b` | ~3.0 GB | Better field recall; needs real headroom. |
| `qwen3.5:4b` | ~5.4 GB | Best of the small text models. |

Set the choice in `backend/.env`:

```bash
OLLAMA_MODEL=qwen3.5:4b
```

## Optional: independent vision review

By default the independent review reads the same OCR text as the primary extraction, so the
two results are not fully independent. Pointing the reviewer at a vision-capable model
restores an independent read of the page image:

```bash
ollama pull qwen2.5vl:3b
# backend/.env
OLLAMA_VISION_MODEL=qwen2.5vl:3b
```

Leave it unset on machines without spare memory. The application works either way and states
which mode produced a review.

## Optional shared-password gate

If you expose the app beyond localhost, set both values:

```bash
APP_ACCESS_PASSWORD=some-demo-password
APP_SESSION_SECRET=some-long-random-string
```

The backend refuses to start with a password but no session secret.
