# CarbonX build plan

Ten phases over 14 weeks. Each has an **acceptance test** — a thing that must
work before the next phase starts. Do not skip ahead. Phase 4 is the hinge: if
it slips, cut a component, don't extend the deadline.

---

## Phase 0 — Gates  (Week 1, before any code)

Three questions. Two of them can change the project.

**G1. Does BEE specify the factor vintage?**
Read *Detailed Procedure for Compliance Mechanism under CCTS v1.0* (BEE,
July 2024) and the GHG Emission calculation pro forma. Record verbatim
quotes in `docs/RQ3_FINDINGS.md`.
- **Silent** → RQ3 is live; it becomes the headline finding.
- **Specified** → we validate against the spec; emphasis shifts to RQ1.
Either way the project proceeds. Knowing which is worth one afternoon.

**G2. Is the CEA archive complete?**
Download every version of the CO2 Baseline Database from cea.nic.in — Excel
files, not just PDFs. Record which version ordinals actually exist.
- **>=8 versions** → full time series, RQ2 is strong.
- **<8** → narrower series; state the limitation, RQ1 carries more weight.

**G3. Bill collection started?**
Messages sent to >=5 people. This has the longest lead time of anything in
the project and decides whether Phase 6 has training data.

**Acceptance:** `docs/RQ3_FINDINGS.md` exists with quotes.
`data/raw/cea/` contains >=4 version files. Team roles assigned in
`docs/TEAM.md` with a named owner per phase.

---

## Phase 1 — Schema and migrations  (Week 1–2)

Apply `db/schema.sql` via Alembic. Seed `resolution_policy` with the four
codes. Docker Compose up with Postgres 16 + btree_gist.

Write `src/carbonx/factors/registry.py`:
- `insert_factor(...)` — never updates; sets `supersedes` and closes the prior
  row's `system_time_range`.
- `resolve(factor_key, compliance_year, as_of, policy) -> EmissionFactor`
- `as_of_query(table, ts)` helper used everywhere.

**Acceptance:**
- Inserting an overlapping factor raises an exclusion-constraint violation.
- `resolve()` returns different factors for different policies on the same
  inputs. Test this explicitly — it is RQ3 in code form.

---

## Phase 2 — CEA ingest and the open registry  (Week 2)

`scripts/fetch_cea.py` — download all versions, hash each file, record in
`factor_source`. URL pattern:
`cea.nic.in/wp-content/uploads/baseline/{year}/{month}/User_Guide_V_{n}.0.pdf`
with variants (`User_Guide__Version_19.0`, `user_guide_ver5`). Fall back to
scraping the baseline landing page for links.

`src/carbonx/ingest/cea.py` — parse the Excel databases into `emission_factor`
rows. Expect layout drift across versions; write a per-version adapter rather
than one brittle parser.

**Then compute RQ2 immediately.** `notebooks/01_rq2_factor_deltas.ipynb`:
year-on-year percentage change for every factor_key across all versions.

**Acceptance:**
- `emission_factor` holds every CEA version retrieved, each linked to a
  `factor_source` with a file hash and source URL.
- A table of year-on-year deltas exists. **You now have a finding, in week 2.**
- Known checkpoints: v19 = 0.716, v20 = 0.727 (weighted avg with RE).

---

## Phase 3 — Dimensional type system  (Week 3)   [ToC]

`src/carbonx/units/` — this is a ToC contribution, not a utility wrapper.
Do NOT just import `pint`.

- `Dimension` — a mapping from base dimension to exponent
  (`energy`, `mass`, `volume`, `co2e`, `currency`, `time`).
- `Quantity(value, Unit)` where `Unit` carries a `Dimension`.
- Typed `__mul__` / `__truediv__` that compose dimensions.
- `EmissionFactorType = Unit[co2e] / Unit[X]`; multiplying by `Quantity[X]`
  yields `Quantity[co2e]`. Any other pairing raises `DimensionError`
  **at composition time, not at runtime on the value**.

Write `docs/TYPE_SOUNDNESS.md`: the typing rules, what soundness means here
(*a well-typed calculation cannot produce a dimensional error*), the argument,
and — importantly — **where it does not hold** (empirical conversion factors,
mass↔volume for fuels needing density). The escape hatches are the interesting
part; name them.

**Acceptance:**
- `kWh * (tCO2e/MWh)` type-checks after unit normalisation; result is tCO2e.
- `kWh * (tCO2e/litre)` raises `DimensionError`.
- Hypothesis test: for random well-typed expression trees, the result dimension
  always equals the algebraically predicted dimension.
- `mypy --strict src/carbonx/units` passes.

---

## Phase 4 — Vertical slice  (Week 4)   **HINGE — non-negotiable**

Thin end-to-end path. Ugly UI is fine.

1. Upload a PDF → `source_document` row with SHA-256.
2. Manual entry of consumption (extraction comes later).
3. `src/carbonx/engine/calculate.py` resolves a factor under a policy,
   multiplies via the typed engine, writes `calculation` + `ledger_entry`.
4. Frontend: click the emissions number → provenance chain showing activity,
   factor value + version + source URL, document filename + hash, actor,
   timestamp.
5. Edit the activity value → audit trigger fires → recalculation → the old
   `calculation` row remains retrievable.

**Acceptance:** a person who has never seen the repo can run `./reproduce.sh`,
open a browser, upload a bill and walk the full provenance chain.
**If this is not working by end of week 4, cut a Phase 7–9 component.**

---

## Phase 5 — Reproducibility invariant  (Week 5)   **the core result**

`src/carbonx/engine/report.py` — generate a report as canonical JSON
(sorted keys, fixed float formatting), hash it, store in `report.output_sha256`.

`regenerate(report_id)` re-executes using `report.as_of` and must produce the
identical hash.

`tests/test_reproducibility.py` with **Hypothesis**:

```python
@given(op_sequence())   # random legal sequences of:
                        #   factor supersession
                        #   backdated correction
                        #   activity edit
                        #   out-of-order arrival
                        #   correction to an already-superseded factor
def test_report_reproducible(ops):
    r = generate_report(org, fy, policy)
    apply_all(ops)
    assert regenerate(r.report_id).output_sha256 == r.output_sha256
```

Then hunt: **try to construct a legal sequence that breaks it.** Finding a
violation and fixing it is a better result than never having looked. Record
attempts in `docs/ADVERSARIAL_LOG.md`.

**Acceptance:** >=10,000 generated sequences pass. Any failure found is
documented, root-caused and fixed.

---

## Phase 6 — Document extraction  (Week 6–8)   [AI/ML]

**Week 6 — data.** Redact (names, addresses, account numbers) → annotate five
fields: `consumption_kwh`, `period_start`, `period_end`, `meter_id`, `issuer`.
Split **by DISCOM**, not by document. Rule-based per-layout baseline first —
you must know the floor you're beating.

**Week 7 — model.** Fine-tune LayoutLMv3. Pretrain/benchmark on public KIE sets
first (DocILE 6,206 train / 1,000 test / 37 fields; SROIE; CORD) so ~200 Indian
bills is enough.

**Week 8 — calibration. Do not skip this.** Raw softmax is badly calibrated.
Apply temperature scaling; report reliability diagrams and expected calibration
error. An uncalibrated confidence feeding Phase 7 produces uncertainty bands
that are confidently wrong.

**Acceptance:**
- Field accuracy reported per DISCOM, **seen vs unseen layouts** — the headline
  is generalisation, not in-distribution accuracy.
- Beats the rule-based baseline on unseen layouts.
- ECE reported before and after temperature scaling.
- `extraction_result.confidence` stores the **calibrated** value.

---

## Phase 7 — Uncertainty propagation  (Week 9)   [AI/ML]

`src/carbonx/uncertainty/` — two sources, both empirical:
- factor uncertainty from published IPCC 2006 Vol 2 ranges
- extraction uncertainty from calibrated confidence

**Correlation matters and is the hard part.** Three facilities on one grid share
one factor — their uncertainties are perfectly correlated. Treating them as
independent understates the aggregate band. Build the dependency graph, then
propagate with the correlation structure.

Then answer: **is a reported 2% GEI improvement statistically distinguishable
from zero?** Given FY2025-26 targets are 1–3%, possibly not.

**Acceptance:**
- Aggregate band under correlated propagation is demonstrably wider than naive
  independent propagation; the difference is quantified.
- Every variance traces to IPCC or to calibrated model confidence. Nothing invented.

---

## Phase 8 — Materiality engine + RQ1  (Week 10)

`src/carbonx/materiality/` — on any change, recompute baseline-year emissions,
compare, flag `requires_recalc` when `pct_change >= 5.0`, auto-draft the
disclosure text GHG Protocol requires.

**Then RQ1**, the headline: sweep Scope 2 share from 0 to 100% and, for each CEA
version step, compute the resulting change in total GEI. Output: **the Scope 2
share at which factor revision alone crosses 5%**, plotted per CCTS sector using
representative Scope 1/2 splits.

Chlor-alkali and aluminium sit at one end; cement and refining at the other
because process CO2 from calcination is Scope 1. **That contrast is the paper.**

**Acceptance:** `notebooks/02_rq1_materiality_curve.ipynb` produces the
per-sector sensitivity curve with sector Scope 1/2 splits cited to source.

---

## Phase 9 — Automaton + audit sampling  (Week 11)   [ToC + AI/ML]

**Lifecycle automaton** — `src/carbonx/lifecycle/`. States ISSUED, HELD,
SURRENDERED, RETIRED. Enumerate the reachable state space and **prove**:
- P1 no reachable path re-surrenders a RETIRED credit
- P2 no credit is simultaneously held by two orgs
- P3 conservation holds
Enforce the same constraints at the DB layer too — belt and braces, and say why.

**Audit sampling** — `src/carbonx/audit/sampling.py`. Learning to rank by
expected error magnitude. Features: calibrated extraction confidence, value vs
facility history, consumption-to-production ratio deviation, evidence
completeness, days between activity and entry, corrected-after-period-close flag.

Evaluate as **detection rate at k% budget** against random and value-weighted
baselines. Labels come from injected faults — **say so, it's circular** — and
mitigate by also testing on real consumption anomalies (UCI household power,
open smart-meter sets) where the anomalies aren't yours.

**Acceptance:** properties proved by enumeration, not just tested. Learned
ranker beats both baselines at 5% and 10% budgets, reported on both fault
sources separately.

---

## Phase 10 — Verifier's workbench and release  (Week 12–14)

**Workbench** (`src/carbonx/api` + frontend). Built around the ACVA workflow:
- risk-ranked sampling queue (Phase 9)
- traceability check per sampled figure
- **audit coverage metric** — % of reported tCO2e whose lineage reaches a hashed
  document (`mv_audit_coverage`)
- exception log — missing evidence, hash mismatches, post-close corrections,
  dimension errors
- **factor version attestation** — which version applied, why, and what the
  figure would be under each alternative policy. **This is RQ3 rendered as a
  product feature.**

**Release:** CEA factor registry to Zenodo with a DOI. Code to GitHub with
pinned environment and `reproduce.sh`. Preprint to arXiv before the viva.

**Acceptance:** demo runs without a developer touching a terminal. DOI minted.

---

## The demo (rehearse until it's muscle memory)

1. Upload a real, unseen electricity bill → model extracts values with confidence
2. Dashboard updates; emissions shown with an uncertainty band
3. Click the number → drill: org → facility → Scope 2 → electricity → month
4. Click the calculation → factor value, version, CEA source URL, document
   SHA-256, actor, timestamp
5. Edit a value → audit event fires, recalculation runs, old calculation still
   retrievable
6. **Switch resolution policy from VINTAGE_MATCHED to LATEST_AVAILABLE** →
   the reported GEI changes → show whether the change crosses the compliance
   target → then regenerate the original report and show it reproduces its
   original hash exactly

Step 6 is the moment. It is the thing commercial tools get wrong.

---

## Definition of done, by grade

| Level | Looks like |
|---|---|
| Pass | Phases 1–4. Working provenance chain, demo, report |
| Good | + Phase 5 (reproducibility invariant proved) and Phase 2 (RQ2 table) |
| A | + Phase 6 (calibrated extraction, unseen-layout results) and Phase 8 (RQ1 curve) |
| A+ | + Phase 7 correlated uncertainty, Phase 9 proved properties, Zenodo DOI, arXiv preprint, and a documented answer to RQ3 |
