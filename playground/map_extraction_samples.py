"""Map Document Intelligence output into Pydantic extraction models.

Run from this folder:

    uv run --project ../backend --locked --no-sync python map_extraction_samples.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.append(str((REPO_ROOT := Path(__file__).resolve().parents[1]) / "backend"))
MANIFEST_PATH = REPO_ROOT / "samples" / "manifest.json"

from app.schemas.invoice.mapping import (  # noqa: E402
    invoice_to_manifest_view,
    map_invoice_result,
)
from app.schemas.receipt.mapping import (  # noqa: E402
    map_receipt_result,
    receipt_to_manifest_view,
)
from app.services.local_extraction_service import LocalExtractionService  # noqa: E402

CORE_MANIFEST_FIELDS = [
    "vendor_name",
    "vendor_vat_id",
    "customer_name",
    "customer_vat_id",
    "invoice_number",
    "invoice_date",
    "due_date",
    "purchase_order",
    "currency",
    "subtotal",
    "total_tax",
    "invoice_total",
]


def load_manifest() -> dict[str, dict[str, Any]]:
    entries = json.loads(MANIFEST_PATH.read_text())
    return {entry["filename"]: entry for entry in entries}


def compare_manifest(
    label: str,
    mapped: dict[str, str | None],
    expected: dict[str, Any] | None,
) -> None:
    print(f"\n--- Manifest comparison: {label} ---")
    if expected is None:
        print("No manifest entry for this sample.")
        return

    expected_view = expected.get("expected") or {}
    for field in CORE_MANIFEST_FIELDS:
        mapped_value = mapped.get(field)
        expected_value = expected_view.get(field)
        status = "match" if mapped_value == expected_value else "diff"
        print(
            f"  {field}: mapped={mapped_value!r} expected={expected_value!r} [{status}]"
        )


def summarize_core_fields(mapped: dict[str, str | None]) -> None:
    populated = [
        field for field in CORE_MANIFEST_FIELDS if mapped.get(field) is not None
    ]
    missing = [field for field in CORE_MANIFEST_FIELDS if mapped.get(field) is None]
    print(f"  populated ({len(populated)}): {', '.join(populated) or '-'}")
    print(f"  missing ({len(missing)}): {', '.join(missing) or '-'}")


def run_invoice_sample(
    service: LocalExtractionService,
    *,
    label: str,
    document_path: Path,
    manifest_entry: dict[str, Any] | None,
) -> None:
    print(f"\n{'=' * 72}\n{label}\n{'=' * 72}")
    result_dict = service.to_dict(service.analyze_invoice(document_path))
    extraction = map_invoice_result(result_dict)
    mapped = invoice_to_manifest_view(extraction)

    print(json.dumps(extraction.model_dump(mode="json"), indent=2, default=str))
    print("\n--- Core field summary ---")
    summarize_core_fields(mapped)
    compare_manifest(label, mapped, manifest_entry)


def run_receipt_sample(
    service: LocalExtractionService,
    *,
    label: str,
    document_path: Path,
    manifest_entry: dict[str, Any] | None,
) -> None:
    print(f"\n{'=' * 72}\n{label}\n{'=' * 72}")
    result_dict = service.to_dict(service.analyze_receipt(document_path))
    extraction = map_receipt_result(result_dict)
    mapped = receipt_to_manifest_view(extraction)

    print(json.dumps(extraction.model_dump(mode="json"), indent=2, default=str))
    print("\n--- Core field summary ---")
    summarize_core_fields(mapped)
    compare_manifest(label, mapped, manifest_entry)


def main() -> None:
    manifest = load_manifest()
    service = LocalExtractionService()

    run_invoice_sample(
        service,
        label="Microsoft sample invoice",
        document_path=REPO_ROOT / "samples" / "sample-invoice.pdf",
        manifest_entry=None,
    )
    run_invoice_sample(
        service,
        label="Corpus invoice 01-en-happy-classic.pdf",
        document_path=REPO_ROOT / "samples" / "generated" / "01-en-happy-classic.pdf",
        manifest_entry=manifest.get("01-en-happy-classic.pdf"),
    )
    run_receipt_sample(
        service,
        label="Corpus receipt 13-nl-fuel-receipt.png",
        document_path=REPO_ROOT / "samples" / "generated" / "13-nl-fuel-receipt.png",
        manifest_entry=manifest.get("13-nl-fuel-receipt.png"),
    )


if __name__ == "__main__":
    main()
