# Multi-stage: build the React SPA, then run FastAPI + static files in one image.

FROM node:22-bookworm-slim AS frontend-build
WORKDIR /frontend
RUN corepack enable && corepack prepare pnpm@11.3.0 --activate
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
ENV VITE_API_BASE_URL=/
RUN pnpm build

FROM python:3.12-slim-bookworm AS runtime
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    FRONTEND_DIST_DIR=/app/frontend/dist \
    OLLAMA_BASE_URL=http://ollama:11434/v1

# poppler supplies pdftotext/pdftoppm and tesseract performs OCR. Both replace the
# hosted document-extraction service, so they are part of the runtime, not a build tool.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        poppler-utils \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-nld \
        tesseract-ocr-deu \
        tesseract-ocr-fra \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /usr/local/bin/uv

COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY backend/app ./app
COPY --from=frontend-build /frontend/dist /app/frontend/dist

RUN mkdir -p /app/data/uploads

EXPOSE 8000

CMD ["uv", "run", "--locked", "--no-sync", "uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
