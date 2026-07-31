import json
import logging
import sys
from pathlib import Path

import nest_asyncio

sys.path.append(str((REPO_ROOT := Path(__file__).resolve().parents[1]) / "backend"))

from app.pipeline import build_default_pipeline  # noqa: E402
from app.schemas.invoice.mapping import invoice_to_manifest_view  # noqa: E402
from app.schemas.invoice.model import InvoiceExtraction  # noqa: E402
from app.schemas.receipt.mapping import receipt_to_manifest_view  # noqa: E402
from app.schemas.receipt.model import ReceiptExtraction  # noqa: E402

nest_asyncio.apply()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)


def _extraction_summary(extraction: InvoiceExtraction | ReceiptExtraction) -> dict:
    if isinstance(extraction, InvoiceExtraction):
        view = invoice_to_manifest_view(extraction)
        view["line_item_count"] = str(len(extraction.items))
        return view
    view = receipt_to_manifest_view(extraction)
    view["line_item_count"] = str(len(extraction.items))
    return view


def main() -> None:
    document_path = REPO_ROOT / "samples" / "generated" / "05-nl-missing-vendor-vat.pdf"

    result = build_default_pipeline().run(document_path)

    payload = {
        "document_path": str(document_path),
        "classification": (
            result.classification.model_dump(mode="json")
            if result.classification
            else None
        ),
        "extraction_summary": (
            _extraction_summary(result.extraction) if result.extraction else None
        ),
        "review_data": (
            result.review_data.model_dump(mode="json") if result.review_data else None
        ),
        "document_review": (
            result.document_review.model_dump(mode="json")
            if result.document_review
            else None
        ),
        "issues": (
            [issue.model_dump(mode="json") for issue in result.issues]
            if result.issues
            else None
        ),
        "gl_suggestion": (
            result.gl_suggestion.model_dump(mode="json")
            if result.gl_suggestion
            else None
        ),
    }
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
