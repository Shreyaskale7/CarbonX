# Document extraction: method, what development found, and limits

Code: `src/carbonx/extraction/` (`synthetic.py`, `extract.py`). Results,
generated: `docs/EXTRACTION_RESULTS.md`. Tests: `tests/test_extraction.py`.
This is component 7 of CLAUDE.md (AI/ML), in the reduced form the council
proposed on 26 Sep 2026: *a rule baseline plus a small model with calibrated
confidence and an honest held-out split.*

> **Everything here runs on synthetic bills.** No real bill has been collected.
> The numbers describe the pipeline, not real-world accuracy. Do not quote
> them as accuracy on Indian electricity bills.

## 1. What is built

- **Task.** Find `consumption_kwh` in a bill's text. This is the one value that
  feeds emissions. Period, meter id and issuer are not extracted yet.
- **Input.** The text pdfplumber extracts from a digital PDF
  (`text_from_pdf`). Scanned bills (OCR) are not handled.
- **Rule baseline** (`baseline`). Regular expressions written from the
  training layouts only. It is the floor the model has to beat. It returns no
  confidence, because rules have none.
- **Model** (`ConsumptionModel`). Every number in the document is a candidate.
  A logistic regression scores each candidate from:
  - the words near it (left, right, table header above, lines around a lone
    number), both with their position and position-free;
  - simple numeric cues: magnitude, decimals, position in the line and page;
  - whether the number equals the difference of two others (present reading
    minus previous reading).

  The highest-scoring candidate is the answer. Its confidence is the softmax
  over that document's candidates.
- **Calibration.** Temperature scaling, fitted by leave-one-layout-out (§3).

## 2. Data and splits

Synthetic bills from 11 fictional issuers (`SYNTH-DISCOM-1` … `11`), 300 each.
Layouts differ in label wording, inline versus table structure, number and date
formats, distractors (readings, kVAh, demand, amounts) and multiplying
factors.

| Split | Layouts | Role |
|---|---|---|
| Train | 1–5 (80% of each) | fit the model; leave-one-layout-out calibration |
| Seen test | 1–5 (20% of each) | in-distribution check |
| Development | 6–8 | unseen in training, **but used for error analysis** |
| **Test** | **9–11** | **written after the model was frozen; evaluated once** |

Splitting by layout, not by document, is the point. A document-level split of
the same layouts measures memorisation of a template. The plan's "held-out by
DISCOM" is this, with synthetic layouts standing in for DISCOMs.

## 3. What development found (kept, because it is the lesson)

**First version** (position-specific features; temperature fitted on a
validation split of the *training* layouts):

- seen layouts 100%, unseen layouts 66.7%;
- layout 6 was **0% correct at 99.6% mean confidence**;
- calibration made unseen-layout ECE *worse*, 0.265 → 0.332.

Two causes, both instructive:

1. **Features did not transfer.** "kWh" beside a number and "kWh" in a column
   header were different features, so a new table layout looked unfamiliar.
   Fix: every context word is also added position-free.
2. **In-distribution calibration teaches over-confidence.** On validation
   documents from layouts it trained on, the model is nearly always right, so
   the fitted temperature *sharpened* it (T = 0.16). It was then confidently
   wrong on a new layout. Fix: fit the temperature on **leave-one-layout-out**
   predictions (train on four layouts, score the fifth), which are
   out-of-layout by construction.

A third problem appeared with that fix. Leave-one-layout-out accuracy on the
five training layouts was 100%, so there were no errors to learn from, and the
likelihood was maximised by T → 0 (certainty). "Never observed failing" is not
evidence of certainty. **Rule adopted before the test was run: calibration may
soften confidence, never sharpen it (T ≥ 1).**

Because layouts 6–8 drove these changes, they are no longer a fair test. Three
new layouts (9–11) were then written with the model frozen, chosen as hard,
realistic cases: a tariff table where consumption is just "Qty"; time-of-day
slabs where several numbers are kWh; and consumption history printed beside
the current figure.

## 4. Result (see `EXTRACTION_RESULTS.md` for the generated tables)

| Evaluated on | Rule baseline | Model | ECE (calibrated) | Mean confidence |
|---|---|---|---|---|
| Seen layouts | 100% | 100% | 0.000 | 100% |
| Development layouts (6–8) | 0% | 100% | 0.255 | 74.5% |
| **Test layouts (9–11)** | **0%** | **33.3%** | **0.347** | 42.0% |

Reading it honestly:

- **The model beats the rule baseline on unseen layouts**, which is the bar
  the plan set. The rules get 0% on every layout they were not written for.
- **It does not generalise reliably.** On the test it gets the
  consumption-history layout right (100%) and fails the tariff table and the
  time-of-day slabs completely (0%).
- **Development accuracy overstated test accuracy** (100% versus 33.3%). So
  did leave-one-layout-out accuracy on five similar training layouts (100%).
  Neither is a trustworthy estimate of performance on a new layout.
- **The confidence ranks well but is not calibrated.** On the test layouts
  every wrong answer has confidence below 0.4 and every right answer above
  it, so low confidence does flag the failures. But ECE is 0.347: the model
  is under-confident when right, and still gives about 30% to answers that
  are always wrong.
- **As a review queue.** Across all 1,800 unseen-layout bills (development and
  test), accepting only extractions with confidence ≥ 0.5 would auto-accept
  47.9% of them with no errors among them. That threshold was read off this
  data after the fact, so it is an observation, not a validated rule.

## 5. Consequences for the rest of CarbonX

- **Invariant 6 is not yet met for extraction.** It requires extraction
  uncertainty to come from *calibrated* confidence. On unseen layouts this
  confidence is not calibrated. So Phase 7 (uncertainty propagation) must not
  consume it as a probability until calibration is shown on real bills. Until
  then an extracted value is a point estimate that a human confirms
  (`extraction_result.human_verified`).
- **The intended use is triage**, which is what a verifier's sampling queue
  needs: send low-confidence extractions to a person.
- **Storing results.** `extraction/review.py` records each extraction in
  `extraction_result` with the model version, and queues it for a person to
  confirm, least confident first. Only the confirmation can change afterwards
  (migration 0010). Not yet run against a database.

## 6. Limits

- **Synthetic data, designed by the same people who built the model.** Real
  bills will differ in ways these layouts do not anticipate. Layouts 9–11 are
  an honest hard test, but they are still our guess at what is hard.
- **Eleven layouts, five for training.** That is too few to estimate
  generalisation, as §4 shows.
- **Digital text only.** No OCR, so no scanned or photographed bills.
- **One field.** `consumption_kwh` only.
- **Which bills matter.** The council's First Principles advisor argued that
  CCTS plants take their electricity data from HT meters and SCADA, not
  scanned DISCOM bills. That question is still open. This pipeline does not
  answer it.

## 7. When real bills arrive

1. Redact them (names, addresses, account numbers) before they are stored;
   never commit a raw bill.
2. Annotate `consumption_kwh` (and the DISCOM).
3. Replace `synthetic.corpus` in `scripts/eval_extraction.py` with the real
   corpus, split **by DISCOM**, and run it unchanged.
4. Decision point from the scope proposal: fewer than about 30 real bills by
   week 4 means staying on synthetic data and saying so.
