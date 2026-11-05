# Reviewing redacted bills before they enter the repository

A real bill reaches `data/redacted_bills/` only after a **named person** has read its redacted text.
The scripts cannot do this for you: `residual()` and the promotion gate catch only what their patterns
know about. A name or address printed without a label can slip through.

## Steps

1. `python scripts/review_pack.py` builds `data/bills/work/REVIEW.html` (local, git-ignored).
2. Open it. For each bill read the **whole redacted text** and the highlighted label.
3. Reject the bill (leave it unticked) if you see any of:
   - a person's, company's, plant's, street's or village's name, or a part of one;
   - a phone number, email, tax or bank identifier, account, bill or meter number;
   - a signature, stamp text or logo text that names the consumer.
4. Check the label: the highlighted number is the monthly consumption in kWh and is the meter-table KWH row
   (`present - last = difference`, `difference x multiplying factor = consumption`). Reject if it is a
   different row or is wrongly read.
5. Tick the accepted bills, type your **own name** as reviewer, and press **Download review.json**.
6. `python scripts/promote_reviewed.py --review review.json` copies the accepted bills to
   `data/redacted_bills/` with your name and date. The gate still refuses any bill without recorded consent,
   without a label, with a leftover personal pattern, or with an identifier-shaped number.
7. `python scripts/eval_real_bills.py --by consumer` runs the official evaluation.
8. Only after step 6, delete `data/bills/work/` (page images, OCR) if it is no longer needed.

## Rules

- Raw bills and page images never go into the repository. Only the redacted text and sidecar do.
- Consent is recorded per sidecar (`consent`, `consent_basis`). It is a statement by a project member and
  has not been independently verified; say so wherever the results are quoted.
- Nobody reviews on behalf of someone else. `reviewed_by` is the person who read the text.
- Results from fewer than three utilities are **not** held-out-by-utility results, and must not be described as such.
