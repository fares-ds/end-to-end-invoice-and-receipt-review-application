"""Per-field error analysis over the fictional corpus.

The corpus evaluator answers "how accurate is it". This answers "accurate at what,
and wrong in which way" - which is the question that tells you what to fix next.

Every extracted field is compared against the manifest and, when it disagrees, the
disagreement is classified rather than just counted. A field that is missing needs a
different fix from a field that picked up a neighbouring number, and an aggregate
percentage hides that distinction completely.

    uv run --locked --no-sync python scripts/error_analysis.py
    OLLAMA_MODEL=gemma3:1b uv run --locked --no-sync python scripts/error_analysis.py \
        --report ../docs/evaluation-gemma3-1b.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.services.local_extraction_service import LocalExtractionService  # noqa: E402
from scripts.evaluate_corpus import (  # noqa: E402
    MANIFEST_PATH,
    SAMPLES_PATH,
    _equal,
    extract_review_data,
)

# How a field can be wrong. Each class implies a different fix, which is the point of
# separating them.
MISSING = "missing"  # expected a value, extracted nothing
SPURIOUS = "spurious"  # expected nothing, invented something
TRUNCATED = "truncated"  # extracted a prefix or substring of the expected value
NEIGHBOUR = "neighbour_number"  # picked a different number that is present on the page
WRONG = "wrong_value"  # present, complete, and simply not right

CLASS_ORDER = [MISSING, SPURIOUS, TRUNCATED, NEIGHBOUR, WRONG]

CLASS_MEANING = {
    MISSING: "Expected a value, extracted nothing. Usually a recall problem.",
    SPURIOUS: "Expected nothing, produced a value. The model filled a gap it should not.",
    TRUNCATED: "Extracted a fragment of the right value. Usually OCR or a stop-token.",
    NEIGHBOUR: "Picked a different number that appears on the page. A grounding problem.",
    WRONG: "Complete, plausible, and incorrect. The hardest class to detect at runtime.",
}


@dataclass(frozen=True)
class FieldError:
    filename: str
    scenario: str
    field: str
    expected: Any
    actual: Any
    error_class: str


def _normalize_number(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def classify(field: str, expected: Any, actual: Any, page_text: str) -> str:
    if expected is not None and actual is None:
        return MISSING
    if expected is None and actual is not None:
        return SPURIOUS

    expected_text = str(expected).strip()
    actual_text = str(actual).strip()

    # A fragment of the right answer points at recognition, not reasoning.
    if actual_text and actual_text.casefold() in expected_text.casefold():
        if len(actual_text) < len(expected_text):
            return TRUNCATED

    # A number that is wrong but genuinely printed on the page is a grounding failure:
    # the value was read from the document, just from the wrong place.
    actual_number = _normalize_number(actual)
    if actual_number is not None and _normalize_number(expected) is not None:
        printed = {
            _normalize_number(token)
            for token in re.findall(r"\d+[.,]?\d*", page_text)
        }
        if actual_number in printed:
            return NEIGHBOUR

    return WRONG


def analyse(limit: int | None = None) -> tuple[list[FieldError], dict[str, dict[str, int]], int]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if limit:
        manifest = manifest[:limit]

    settings = get_settings()
    service = LocalExtractionService(settings)

    errors: list[FieldError] = []
    # field -> {"total": n, "correct": n}
    per_field: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "correct": 0})
    documents_evaluated = 0

    for entry in manifest:
        filename = entry["filename"]
        path = SAMPLES_PATH / filename
        document_type = entry.get("document_type", "invoice")
        try:
            actual = extract_review_data(service, path, document_type)
        except Exception as error:  # noqa: BLE001 - analysis continues past failures
            print(f"  skipped {filename}: {error}", file=sys.stderr)
            continue

        documents_evaluated += 1
        # The recovered page text is needed to tell a grounded wrong number from an
        # invented one.
        page_text = ""
        try:
            page_text = service._read(path).text  # noqa: SLF001 - analysis needs the source
        except Exception:  # noqa: BLE001
            pass

        for field, expected_value in entry["expected"].items():
            actual_value = getattr(actual, field, None)
            per_field[field]["total"] += 1
            if _equal(field, expected_value, actual_value):
                per_field[field]["correct"] += 1
                continue
            errors.append(
                FieldError(
                    filename=filename,
                    scenario=entry.get("scenario", "unknown"),
                    field=field,
                    expected=expected_value,
                    actual=actual_value,
                    error_class=classify(field, expected_value, actual_value, page_text),
                )
            )

    return errors, dict(per_field), documents_evaluated


def render(
    errors: list[FieldError],
    per_field: dict[str, dict[str, int]],
    documents: int,
    model: str,
) -> str:
    total = sum(stats["total"] for stats in per_field.values())
    correct = sum(stats["correct"] for stats in per_field.values())
    lines: list[str] = []
    add = lines.append

    add("# Per-field error analysis")
    add("")
    add(f"Model `{model}` · {documents} documents · {total} field comparisons · "
        f"{correct}/{total} correct ({correct / total * 100:.1f}%)")
    add("")
    add("Generated by `scripts/error_analysis.py`. Do not edit by hand.")
    add("")

    add("## Accuracy by field")
    add("")
    add("Sorted worst first. A field that is always right needs no attention; the "
        "aggregate number hides which ones are not.")
    add("")
    add("| Field | Correct | Total | Accuracy |")
    add("| --- | ---: | ---: | ---: |")
    for field, stats in sorted(
        per_field.items(), key=lambda item: (item[1]["correct"] / item[1]["total"], item[0])
    ):
        accuracy = stats["correct"] / stats["total"] * 100
        add(f"| `{field}` | {stats['correct']} | {stats['total']} | {accuracy:.0f}% |")
    add("")

    add("## Failure classes")
    add("")
    counts = Counter(error.error_class for error in errors)
    if not errors:
        add("No field errors on this run.")
        add("")
    else:
        add("| Class | Count | What it means |")
        add("| --- | ---: | --- |")
        for name in CLASS_ORDER:
            if counts.get(name):
                add(f"| `{name}` | {counts[name]} | {CLASS_MEANING[name]} |")
        add("")

        add("## Every failure")
        add("")
        add("| Document | Scenario | Field | Expected | Extracted | Class |")
        add("| --- | --- | --- | --- | --- | --- |")
        for error in sorted(errors, key=lambda e: (e.error_class, e.field, e.filename)):
            expected = "—" if error.expected is None else f"`{error.expected}`"
            actual = "—" if error.actual is None else f"`{error.actual}`"
            add(
                f"| {error.filename} | {error.scenario} | `{error.field}` | "
                f"{expected} | {actual} | `{error.error_class}` |"
            )
        add("")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Per-field error analysis over the corpus.")
    parser.add_argument("--report", type=Path, default=None, help="Write markdown here.")
    parser.add_argument("--limit", type=int, default=None, help="First N documents only.")
    args = parser.parse_args()

    model = get_settings().ollama_model
    errors, per_field, documents = analyse(args.limit)

    total = sum(stats["total"] for stats in per_field.values())
    correct = sum(stats["correct"] for stats in per_field.values())
    print(f"model {model} · {documents} documents · {correct}/{total} fields correct")

    counts = Counter(error.error_class for error in errors)
    for name in CLASS_ORDER:
        if counts.get(name):
            print(f"  {name:<16} {counts[name]}")

    worst = sorted(
        per_field.items(), key=lambda item: (item[1]["correct"] / item[1]["total"], item[0])
    )[:5]
    print("  worst fields:")
    for field, stats in worst:
        print(f"    {field:<20} {stats['correct']}/{stats['total']}")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(render(errors, per_field, documents, model), encoding="utf-8")
        print(f"report written to {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
