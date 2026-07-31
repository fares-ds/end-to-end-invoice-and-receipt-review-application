"""Local text recovery for financial documents.

Replaces the hosted OCR stage with poppler and tesseract, which are invoked as
external binaries so the project keeps its Python dependency set unchanged.

A PDF produced by an accounting system already carries an exact text layer, so
``pdftotext`` is preferred and reported at full confidence. Scans, photos, and
images have no text layer and fall back to ``tesseract``, whose per-word
confidence is averaged into a document-level score that the Northstar
low-confidence warning can act on.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.config import APP_CONFIG, Settings, get_settings

logger = logging.getLogger(__name__)

SUPPORTED_CONTENT_TYPES = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
}

# Below this many characters a PDF text layer is treated as absent, which is the
# case for scanned pages wrapped in a PDF container.
MIN_TEXT_LAYER_CHARS = 120

TextSource = Literal["pdf_text_layer", "tesseract"]


class OcrError(RuntimeError):
    pass


@dataclass(frozen=True)
class OcrDocument:
    text: str
    confidence: float
    page_count: int
    source: TextSource


def _run(command: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
    except FileNotFoundError as error:
        raise OcrError(
            f"Required OCR binary {command[0]!r} is not installed. "
            "Install poppler and tesseract to run the local extraction stack."
        ) from error
    except subprocess.TimeoutExpired as error:
        raise OcrError(f"{command[0]} timed out after {timeout}s.") from error
    except subprocess.CalledProcessError as error:
        raise OcrError(f"{command[0]} failed: {error.stderr.strip()[:400]}") from error


def _parse_tesseract_tsv(tsv: str) -> tuple[str, list[float]]:
    """Return recovered text plus the per-word confidences tesseract reported.

    Line structure is reconstructed from the block/paragraph/line columns rather
    than joining every word into one stream. On a financial document the line is
    what binds a label to its amount: flattened, ``EURO 95`` sits directly beside
    the money column and gets read as a value. ``pdftotext -layout`` preserves
    this for PDFs, so the OCR path must preserve it too.
    """
    words_by_line: dict[tuple[str, str, str], list[str]] = {}
    order: list[tuple[str, str, str]] = []
    confidences: list[float] = []

    for row in tsv.splitlines()[1:]:
        columns = row.split("\t")
        if len(columns) < 12:
            continue
        text = columns[11].strip()
        if not text:
            continue

        # block_num, par_num, line_num identify the physical line of the page.
        key = (columns[2], columns[3], columns[4])
        if key not in words_by_line:
            words_by_line[key] = []
            order.append(key)
        words_by_line[key].append(text)

        try:
            confidence = float(columns[10])
        except ValueError:
            continue
        # Tesseract reports -1 for structural rows that carry no word.
        if confidence >= 0:
            confidences.append(confidence / 100.0)

    lines = [" ".join(words_by_line[key]) for key in order]
    return "\n".join(lines), confidences


class OcrTextService:
    """Recover document text locally, preferring an embedded PDF text layer."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def missing_binaries(self) -> list[str]:
        required = [
            self._settings.tesseract_binary,
            self._settings.pdftoppm_binary,
            self._settings.pdftotext_binary,
        ]
        return [name for name in required if shutil.which(name) is None]

    def extract(self, path: Path, content_type: str) -> OcrDocument:
        if content_type not in SUPPORTED_CONTENT_TYPES:
            raise OcrError(
                f"Unsupported content type {content_type!r}. "
                f"Use one of: {', '.join(sorted(SUPPORTED_CONTENT_TYPES))}."
            )

        if content_type == "application/pdf":
            layer = self._read_pdf_text_layer(path)
            if layer is not None:
                text, page_count = layer
                logger.info("Recovered PDF text layer (%d page(s))", page_count)
                return OcrDocument(
                    text=text,
                    confidence=1.0,
                    page_count=page_count,
                    source="pdf_text_layer",
                )
            return self._ocr_pdf(path)

        return self._ocr_image(path)

    def _read_pdf_text_layer(self, path: Path) -> tuple[str, int] | None:
        result = _run(
            [
                self._settings.pdftotext_binary,
                "-layout",
                "-f",
                "1",
                "-l",
                str(APP_CONFIG.max_ocr_pages),
                str(path),
                "-",
            ]
        )
        text = result.stdout.strip()
        if len(text) < MIN_TEXT_LAYER_CHARS:
            return None
        page_count = text.count("\f") + 1
        return text, min(page_count, APP_CONFIG.max_ocr_pages)

    def _ocr_pdf(self, path: Path) -> OcrDocument:
        with tempfile.TemporaryDirectory() as workspace:
            prefix = Path(workspace) / "page"
            _run(
                [
                    self._settings.pdftoppm_binary,
                    "-r",
                    str(APP_CONFIG.ocr_dpi),
                    "-png",
                    "-f",
                    "1",
                    "-l",
                    str(APP_CONFIG.max_ocr_pages),
                    str(path),
                    str(prefix),
                ],
                timeout=180,
            )
            pages = sorted(Path(workspace).glob("page*.png"))
            if not pages:
                raise OcrError("The PDF produced no rasterized pages to OCR.")

            texts: list[str] = []
            confidences: list[float] = []
            for page in pages:
                text, page_confidences = self._tesseract(page)
                texts.append(text)
                confidences.extend(page_confidences)

            return OcrDocument(
                text="\n\n".join(texts).strip(),
                confidence=_mean(confidences),
                page_count=len(pages),
                source="tesseract",
            )

    def _ocr_image(self, path: Path) -> OcrDocument:
        text, confidences = self._tesseract(path)
        return OcrDocument(
            text=text.strip(),
            confidence=_mean(confidences),
            page_count=1,
            source="tesseract",
        )

    def _tesseract(self, image_path: Path) -> tuple[str, list[float]]:
        result = _run(
            [
                self._settings.tesseract_binary,
                str(image_path),
                "stdout",
                "-l",
                self._settings.ocr_languages,
                "tsv",
            ],
            timeout=180,
        )
        return _parse_tesseract_tsv(result.stdout)


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)
