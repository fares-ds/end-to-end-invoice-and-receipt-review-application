import sys
from pathlib import Path

# Running this file puts scripts/ on sys.path, not backend/. The project is not
# installed (package = false), so bootstrap the backend root before importing app.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.documents.projection import project_extraction  # noqa: E402
from app.schemas.invoice.mapping import map_invoice_result  # noqa: E402
from app.services.local_extraction_service import LocalExtractionService  # noqa: E402


def main() -> None:
    sample = Path(__file__).parents[2] / "samples" / "sample-invoice.pdf"
    if not sample.exists():
        sample = Path(__file__).parents[2] / "samples" / "generated" / "01-en-happy-classic.pdf"
    service = LocalExtractionService()
    result = service.analyze_invoice(sample)
    review_data = project_extraction(map_invoice_result(result))
    print(review_data.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
