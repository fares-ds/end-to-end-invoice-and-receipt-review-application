"""Analyze a sample invoice with the local OCR + model extraction stack.

Run from this folder:

    uv run --project ../backend --locked --no-sync python analyze_sample_invoice.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.append(str((REPO_ROOT := Path(__file__).resolve().parents[1]) / "backend"))
SAMPLE_INVOICE = REPO_ROOT / "samples" / "generated" / "01-en-happy-classic.pdf"

from app.services.local_extraction_service import LocalExtractionService  # noqa: E402


def main() -> None:
    service = LocalExtractionService()
    result = service.analyze_invoice(SAMPLE_INVOICE)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
