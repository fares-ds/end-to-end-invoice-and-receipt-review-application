
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

# Running this file puts scripts/ on sys.path, not backend/. The project is not
# installed (package = false), so bootstrap the backend root before importing app.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import APP_CONFIG, get_settings  # noqa: E402
from app.documents.schemas import ReviewData, ReviewLineItem  # noqa: E402
from app.pipeline.gl_categorization import GlCategorizer  # noqa: E402


def main() -> None:
    settings = get_settings()
    categorizer = GlCategorizer(settings)
    document = ReviewData(
        vendor_name="Cloud Tools Europe B.V.",
        customer_name=APP_CONFIG.expected_customer_name,
        customer_vat_id=APP_CONFIG.expected_customer_vat_id,
        invoice_number="SAAS-CHECK-001",
        invoice_date=date(2026, 7, 1),
        currency="EUR",
        invoice_total=Decimal("99.00"),
        line_items=[
            ReviewLineItem(
                description="Monthly workflow software subscription",
                quantity=Decimal("1"),
                amount=Decimal("99.00"),
            )
        ],
    )
    suggestion = categorizer.run(document)
    print(f"Model: {settings.ollama_model}")
    print(suggestion.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
