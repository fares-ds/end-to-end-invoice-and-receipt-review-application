import argparse
import json
import sys
from collections.abc import Mapping
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

# Running this file puts scripts/ on sys.path, not backend/. The project is not
# installed (package = false), so bootstrap the backend root before importing app.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import APP_CONFIG, get_settings  # noqa: E402
from app.document_review.reconciliation import merge_document_extractions  # noqa: E402
from app.documents.projection import project_extraction  # noqa: E402
from app.documents.schemas import ReviewData  # noqa: E402
from app.documents.validation import validate_review_data  # noqa: E402
from app.providers.ollama_document_review import OllamaDocumentReviewer  # noqa: E402
from app.schemas.invoice.mapping import map_invoice_result  # noqa: E402
from app.schemas.receipt.mapping import map_receipt_result  # noqa: E402
from app.services.local_extraction_service import LocalExtractionService  # noqa: E402

ROOT = Path(__file__).parents[2]
MANIFEST_PATH = ROOT / "samples" / "manifest.json"
SAMPLES_PATH = ROOT / "samples" / "generated"
CONTENT_TYPES = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg"}

DECIMAL_FIELDS = {"subtotal", "total_tax", "invoice_total", "amount_due"}
DATE_FIELDS = {"invoice_date", "due_date"}


def _normalized_text(value: Any) -> str:
    return " ".join(str(value).casefold().split())


def _equal(field: str, expected: Any, actual: Any) -> bool:
    if expected is None:
        return actual is None
    if actual is None:
        return False
    if field in DECIMAL_FIELDS:
        try:
            return Decimal(str(expected)) == Decimal(str(actual))
        except InvalidOperation:
            return False
    if field in DATE_FIELDS:
        actual_value = actual.isoformat() if isinstance(actual, date) else str(actual)
        return str(expected) == actual_value
    return _normalized_text(expected) == _normalized_text(actual)


def compare_review(expected: Mapping[str, Any], actual: ReviewData) -> dict[str, bool]:
    """Compare manifest fields while ignoring harmless display differences."""
    return {
        field: _equal(field, expected_value, getattr(actual, field, None))
        for field, expected_value in expected.items()
    }


def extract_review_data(
    service: LocalExtractionService, path: Path, document_type: str
) -> ReviewData:
    if document_type == "receipt":
        result = service.analyze_receipt(path)
        extraction = map_receipt_result(result)
    else:
        result = service.analyze_invoice(path)
        extraction = map_invoice_result(result)
    return project_extraction(extraction)


def evaluate_document(
    entry: Mapping[str, Any],
    service: LocalExtractionService,
    reviewer: OllamaDocumentReviewer | None,
) -> tuple[list[str], list[str], list[str]]:
    """Return (mismatched fields, issue codes, expected codes) for one document.

    When a reviewer is supplied the merged result is scored, which is what the
    application actually shows. Without one, only the primary extraction is
    scored, which understates real accuracy because the merge fills gaps.
    """
    filename = entry["filename"]
    path = SAMPLES_PATH / filename
    document_type = entry.get("document_type", "invoice")
    actual = extract_review_data(service, path, document_type)

    if reviewer is not None:
        content_type = CONTENT_TYPES[path.suffix.lower()]
        llm = reviewer.review(path, content_type)
        actual, _ = merge_document_extractions(actual, llm)

    comparison = compare_review(entry["expected"], actual)
    mismatches = [field for field, is_match in comparison.items() if not is_match]

    issues = validate_review_data(
        actual,
        expected_customer_name=APP_CONFIG.expected_customer_name,
        expected_customer_vat_id=APP_CONFIG.expected_customer_vat_id,
        min_confidence=APP_CONFIG.min_field_confidence,
        # The duplicate sample needs a peer row that this offline check cannot
        # create, so the scenario is simulated rather than skipped.
        is_duplicate=entry.get("scenario") == "duplicate",
    )
    issue_codes = sorted(issue.code for issue in issues)
    expected_codes = sorted(entry.get("expected_issue_codes", []))
    return mismatches, issue_codes, expected_codes


def run_once(
    manifest: list[Mapping[str, Any]],
    service: LocalExtractionService,
    reviewer: OllamaDocumentReviewer | None,
    *,
    quiet: bool,
) -> dict[str, Any]:
    matched_fields = total_fields = exact_documents = policy_matches = failures = 0
    per_document: dict[str, bool] = {}

    for entry in manifest:
        filename = entry["filename"]
        try:
            mismatches, issue_codes, expected_codes = evaluate_document(
                entry, service, reviewer
            )
        except Exception as error:  # noqa: BLE001 - evaluator continues through its corpus
            failures += 1
            per_document[filename] = False
            if not quiet:
                print(f"FAIL  {filename:<36} provider error: {error}")
            continue

        total = len(entry["expected"])
        matched = total - len(mismatches)
        policy_ok = issue_codes == expected_codes

        matched_fields += matched
        total_fields += total
        exact_documents += not mismatches
        policy_matches += policy_ok
        per_document[filename] = not mismatches and policy_ok

        if not quiet:
            detail = "all fields" if not mismatches else f"mismatch: {', '.join(mismatches)}"
            outcome = "PASS" if not mismatches else "PART"
            policy = (
                "policy-ok" if policy_ok
                else f"policy={issue_codes} expected={expected_codes}"
            )
            print(f"{outcome}  {filename:<36} {matched:>2}/{total}  {detail}  {policy}")

    accuracy = (matched_fields / total_fields * 100) if total_fields else 0.0
    return {
        "field_accuracy": round(accuracy, 2),
        "matched_fields": matched_fields,
        "total_fields": total_fields,
        "exact_documents": exact_documents,
        "policy_matches": policy_matches,
        "provider_failures": failures,
        "documents": len(manifest),
        "per_document": per_document,
    }


def _variance_report(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarise how far results move between identical runs."""
    accuracies = [run["field_accuracy"] for run in runs]
    unstable = sorted(
        {
            filename
            for filename in runs[0]["per_document"]
            if len({run["per_document"].get(filename) for run in runs}) > 1
        }
    )
    return {
        "runs": len(runs),
        "min": min(accuracies),
        "max": max(accuracies),
        "spread": round(max(accuracies) - min(accuracies), 2),
        "unstable_documents": unstable,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Score the fictional corpus and optionally gate on the result."
    )
    parser.add_argument(
        "--min-accuracy", type=float, default=None,
        help="Exit non-zero when field accuracy falls below this percentage.",
    )
    parser.add_argument(
        "--baseline", type=Path, default=None,
        help="Compare against a stored baseline JSON file and fail on regression.",
    )
    parser.add_argument(
        "--write-baseline", action="store_true",
        help="Write this run to --baseline instead of comparing against it.",
    )
    parser.add_argument(
        "--merged", action="store_true",
        help="Score the merged result the application shows, not primary extraction alone.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Evaluate only the first N documents, for fast iteration.",
    )
    parser.add_argument(
        "--runs", type=int, default=1,
        help="Repeat the corpus N times and report variance between runs.",
    )
    args = parser.parse_args()

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if args.limit:
        manifest = manifest[: args.limit]
    settings = get_settings()
    service = LocalExtractionService(settings)
    reviewer = OllamaDocumentReviewer(settings=settings) if args.merged else None

    scope = "merged result" if args.merged else "primary extraction"
    print(f"Evaluating {len(manifest)} fictional financial documents ({scope})\n")

    runs = [
        run_once(manifest, service, reviewer, quiet=index > 0)
        for index in range(max(1, args.runs))
    ]
    result = runs[0]

    print("\nSummary")
    print(f"  Field accuracy:     {result['matched_fields']}/{result['total_fields']}"
          f" ({result['field_accuracy']:.1f}%)")
    print(f"  Exact documents:   {result['exact_documents']}/{result['documents']}")
    print(f"  Policy matches:    {result['policy_matches']}/{result['documents']}")
    print(f"  Provider failures: {result['provider_failures']}/{result['documents']}")

    exit_code = 0

    if len(runs) > 1:
        variance = _variance_report(runs)
        print(f"\nVariance over {variance['runs']} runs")
        print(f"  Accuracy range:    {variance['min']:.1f}% - {variance['max']:.1f}%"
              f" (spread {variance['spread']:.1f})")
        print(f"  Unstable documents: {variance['unstable_documents'] or 'none'}")
        result["variance"] = variance

    if args.baseline and args.write_baseline:
        payload = {key: value for key, value in result.items() if key != "per_document"}
        payload["model"] = settings.ollama_model
        args.baseline.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"\nBaseline written to {args.baseline}")
    elif args.baseline:
        exit_code |= _compare_baseline(args.baseline, result, settings.ollama_model)

    if args.min_accuracy is not None and result["field_accuracy"] < args.min_accuracy:
        print(f"\nFAIL  field accuracy {result['field_accuracy']:.1f}% is below the "
              f"required {args.min_accuracy:.1f}%")
        exit_code |= 1

    return exit_code


def _compare_baseline(path: Path, result: dict[str, Any], model: str) -> int:
    if not path.exists():
        print(f"\nNo baseline at {path}. Create one with --write-baseline.")
        return 1

    baseline = json.loads(path.read_text(encoding="utf-8"))
    recorded_model = baseline.get("model")
    if recorded_model and recorded_model != model:
        print(f"\nBaseline was recorded with model {recorded_model!r} but this run used "
              f"{model!r}. Comparison skipped; write a baseline per model.")
        return 0

    regressions: list[str] = []
    for metric in ("field_accuracy", "exact_documents", "policy_matches"):
        before, after = baseline.get(metric), result[metric]
        if before is not None and after < before:
            regressions.append(f"{metric}: {before} -> {after}")
    if result["provider_failures"] > baseline.get("provider_failures", 0):
        regressions.append(
            f"provider_failures: {baseline.get('provider_failures')} -> "
            f"{result['provider_failures']}"
        )

    if regressions:
        print("\nFAIL  regression against baseline")
        for line in regressions:
            print(f"  --> {line}")
        return 1

    print(f"\nNo regression against baseline ({path})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
