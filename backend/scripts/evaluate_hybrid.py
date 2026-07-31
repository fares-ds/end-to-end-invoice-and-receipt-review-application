import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Running this file puts scripts/ on sys.path, not backend/. The project is not
# installed (package = false), so bootstrap the backend root before importing app.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import APP_CONFIG, get_settings  # noqa: E402
from app.document_review.reconciliation import FIELDS, merge_document_extractions  # noqa: E402
from app.document_review.schemas import DocumentReview  # noqa: E402
from app.documents.projection import project_extraction  # noqa: E402
from app.documents.schemas import ReviewData, ValidationIssue  # noqa: E402
from app.documents.validation import status_for_issues, validate_review_data  # noqa: E402
from app.providers.ollama_document_review import OllamaDocumentReviewer  # noqa: E402
from app.schemas.invoice.mapping import map_invoice_result  # noqa: E402
from app.schemas.receipt.mapping import map_receipt_result  # noqa: E402
from app.services.local_extraction_service import LocalExtractionService  # noqa: E402

ROOT = Path(__file__).parents[2]
SAMPLES = ROOT / "samples" / "generated"
DEFAULT_FILES = ("02-nl-happy-compact.pdf", "13-nl-fuel-receipt.png")
CONTENT_TYPES = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg"}


def build_result(
    filename: str,
    primary: ReviewData,
    merged: ReviewData,
    review: DocumentReview,
    issues: list[ValidationIssue],
) -> dict[str, Any]:
    primary_fields = [
        field for field, _label, _normalizer in FIELDS if getattr(primary, field) is not None
    ]
    conflict_fields = [
        item.field for item in review.comparisons if item.status == "different"
    ]
    return {
        "filename": filename,
        "document_type": merged.document_type,
        "expense_category": merged.expense_category,
        "extraction_model": (
            "local-receipt" if merged.document_type == "receipt" else "local-invoice"
        ),
        "primary_fields": primary_fields,
        "fallback_fields": [item.field for item in review.fallback_fields],
        "conflict_fields": conflict_fields,
        "final_status": status_for_issues(issues),
        "issue_codes": [issue.code for issue in issues],
        "model_calls": {
            "local_extraction": 1,
            "source_document_llm": 1,
        },
    }


def extract_primary(
    service: LocalExtractionService, path: Path, document_type: str
) -> ReviewData:
    if document_type == "receipt":
        result = service.analyze_receipt(path)
        return project_extraction(map_receipt_result(result))
    result = service.analyze_invoice(path)
    return project_extraction(map_invoice_result(result))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare primary local extraction with LLM fallback on selected samples."
    )
    parser.add_argument("filenames", nargs="*", default=list(DEFAULT_FILES))
    args = parser.parse_args()
    settings = get_settings()
    service = LocalExtractionService(settings)
    reviewer = OllamaDocumentReviewer(settings=settings)
    results: list[dict[str, Any]] = []

    for filename in args.filenames:
        path = SAMPLES / Path(filename).name
        content_type = CONTENT_TYPES.get(path.suffix.lower())
        if content_type is None:
            raise SystemExit(f"Unsupported evaluation file: {filename}")
        extraction = reviewer.review(path, content_type)
        if extraction.document_type == "unsupported":
            raise SystemExit(f"Model did not recognize {filename} as an invoice or receipt")
        primary = extract_primary(service, path, extraction.document_type)
        merged, review = merge_document_extractions(primary, extraction)
        issues = validate_review_data(
            merged,
            expected_customer_name=APP_CONFIG.expected_customer_name,
            expected_customer_vat_id=APP_CONFIG.expected_customer_vat_id,
            min_confidence=APP_CONFIG.min_field_confidence,
            is_duplicate=False,
        )
        results.append(build_result(filename, primary, merged, review, issues))

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
