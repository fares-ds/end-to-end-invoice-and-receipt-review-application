# Evaluation

An aggregate accuracy number tells you whether to ship. It does not tell you what to fix.
This document is the second question: **accurate at what, and wrong in which way.**

Regenerate everything here with:

```bash
cd backend
uv run --locked --no-sync python scripts/error_analysis.py --report ../docs/evaluation-gemma4-cloud.md
OLLAMA_MODEL=gemma3:1b uv run --locked --no-sync python scripts/error_analysis.py \
    --report ../docs/evaluation-gemma3-1b.md
```

---

## Method

**Corpus.** 13 fictional documents — 12 invoices and one Dutch fuel receipt — across
English, Dutch, German and French, in PDF and PNG. Nine scenarios: happy path, missing
vendor VAT, invalid vendor VAT, wrong customer VAT, total mismatch, missing PO, duplicate,
degraded scan, and a receipt. `samples/manifest.json` holds the expected value of every
field plus the policy issue codes each document should raise.

**Unit of measurement.** 13 fields per document, 169 comparisons per run. Comparison is
type-aware so formatting differences are not counted as errors: `Decimal` equality for
money, so `121.0 == 121.00`; ISO comparison for dates; case- and whitespace-normalised for
text.

**Two things are scored separately.** Field accuracy asks whether extraction was right.
Policy match asks whether the deterministic rules raised exactly the expected issue codes.
A run can extract well and still apply the wrong rulebook — which is precisely what happens
below.

---

## Model comparison

| | `gemma4:cloud` | `gemma3:1b` |
| --- | ---: | ---: |
| Field accuracy | **169/169 (100%)** | 158/169 (93.5%) |
| Exact documents | **13/13** | 3/13 |
| Policy matches | **13/13** | 4/13 |
| Field errors | **0** | 11 |

The 6.5-point gap in field accuracy understates the difference. **Exact documents fall from
13 to 3** — because a document needs every field right, and errors cluster into different
documents rather than piling into the same one.

The policy column is the one that matters operationally. 4/13 means nine documents got the
wrong set of findings, which is a worse failure than a wrong field: it changes what the
reviewer is asked to do.

---

## Where the local model fails

Per-field accuracy, worst first. Eight of thirteen fields are perfect; the aggregate hides
that the damage is concentrated.

| Field | Correct | Accuracy |
| --- | ---: | ---: |
| `customer_vat_id` | 8/13 | **62%** |
| `vendor_vat_id` | 10/13 | **77%** |
| `customer_name` | 12/13 | 92% |
| `subtotal` | 12/13 | 92% |
| `total_tax` | 12/13 | 92% |
| `currency`, `document_type`, `due_date`, `invoice_date`, `invoice_number`, `invoice_total`, `purchase_order`, `vendor_name` | 13/13 | 100% |

### Failure classes

Each class implies a different fix, which is the reason for separating them rather than
counting errors.

| Class | Count | Meaning |
| --- | ---: | --- |
| `missing` | 6 | Expected a value, extracted nothing. A recall problem. |
| `wrong_value` | 3 | Complete, plausible, incorrect. Hardest to detect at runtime. |
| `neighbour_number` | 2 | Picked a different number **that is printed on the page**. A grounding problem. |

The `neighbour_number` class is worth the extra code. It separates a model inventing a
figure from a model reading the wrong figure off the document — the second is a grounding
failure with a different fix, and counting both as "wrong" would hide it.

---

## Four failure modes

The eleven errors are not eleven problems. They are four.

### 1. Two-column layouts lose the second VAT ID — 5 of 11 errors

Every `missing` `customer_vat_id` is the same value, `NL00449544B01`, on five different
documents. The cause is visible in the recovered text:

```
Supplier                          Customer
Bright Spark Europe S.A.S.        Northstar Facilities B.V.
VAT number: FR61954506077         VAT number: NL00449544B01
```

`pdftotext -layout` preserves the columns, so both VAT numbers land on one line. The model
takes the first and drops the second. **The fix is not a better model — it is column-aware
segmentation before extraction.** `gemma4:cloud` gets all five right, which shows a stronger
model can compensate, but the structural fix would help both.

### 2. The invoice number is mistaken for the VAT ID — 2 errors

| Document | Expected | Extracted |
| --- | --- | --- |
| `02-nl-happy-compact.pdf` | `NL123456782B90` | `NL-2026-2042` |
| `06-de-invalid-vendor-vat.pdf` | `DE-NOT-A-VAT` | `DE-2026-6006` |

Both extractions returned the **invoice number**. Both share the country-code-like prefix
that makes a VAT ID recognisable — `NL-`, `DE-`. The model is pattern-matching the prefix
rather than the label.

This one is partly caught downstream: `python-stdnum` rejects `NL-2026-2042`, so the
document is flagged rather than silently approved. Deterministic validation converts an
extraction error into a visible finding, which is the whole argument for keeping policy out
of the model.

### 3. Money fields grab an adjacent amount — 2 errors

| Document | Field | Expected | Extracted | Also on the page as |
| --- | --- | --- | --- | --- |
| `13-nl-fuel-receipt.png` | `subtotal` | `50.00` | `60.5` | the total |
| `04-fr-happy-classic.pdf` | `total_tax` | `37.80` | `217.8` | the invoice total |

Both values are printed on the document. The model located the money column and picked the
wrong row. Arithmetic catches both — subtotal plus VAT will not reconcile — so they surface
as `invoice_total_mismatch` rather than passing silently.

### 4. A label is extracted instead of its value — 1 error

`07-fr-wrong-customer-vat.pdf` returned `Client` as the `customer_name`. The model returned
the field label rather than the value beside it.

---

## What this says to do next

Ranked by errors removed per unit of work, not by interest:

1. **Column-aware segmentation.** Five of eleven errors, one cause, and it is a
   preprocessing fix rather than a model change. Split detected columns before extraction
   instead of feeding the model interleaved text.
2. **Constrain the VAT field.** A VAT ID has a checkable shape. Rejecting a candidate that
   fails `python-stdnum` *at extraction time* and retrying would remove failure mode 2
   before it reaches the reviewer.
3. **Leave modes 3 and 4 alone for now.** Three errors, both already caught downstream by
   arithmetic or by the customer-name policy check. Fixing them buys accuracy on a metric,
   not safety for the reviewer.

---

## Limitations

- **n = 13.** With 13 observations per field, `customer_vat_id` at 8/13 (62%) has a 95%
  Wilson score interval of **36%–82%**. The *direction* is reliable and the cause is
  identified from the failures themselves rather than inferred from the rate; the point
  estimate is not precise. Treat the ranking as sound and the percentages as indicative.
- **Single run per model.** Temperature is pinned at 0, and `--runs N` measures variance, but
  the numbers here come from one pass.
- **Primary extraction only.** This analysis scores the extractor, not the merged result the
  application shows. The merge fills gaps from the independent review, so real end-to-end
  accuracy is higher — doc 01's `customer_vat_id` fails here but succeeds through the API.
- **The corpus is fictional and small**, generated for a tutorial. It exercises nine
  scenarios deliberately; it is not a sample of real supplier invoices.
