
from datetime import date
from decimal import Decimal

from app.config import APP_CONFIG, get_settings
from app.documents.schemas import ReviewData, ReviewLineItem
from app.pipeline.gl_categorization import GlCategorizer


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
