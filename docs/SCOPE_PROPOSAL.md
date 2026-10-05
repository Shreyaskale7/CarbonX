# Scope proposal after the 26 Sep 2026 council review: NOT YET AGREED

`CLAUDE.md` says: *adding anything to the BUILD list requires whole-team
written agreement*. Removing things is just as much a scope decision. This
file proposes changes. **Nothing here takes effect until every member signs
below and the faculty guides confirm that each course's rubric is still met.**
Until then, `CLAUDE.md` and `docs/BUILD_PLAN.md` remain the scope.

Source: the LLM council verdict, `docs/council/council-report-20260926-2120.html`.

## Proposed cuts

| # | Component (CLAUDE.md BUILD list) | Proposal | Reason |
|---|---|---|---|
| 9 | Risk-weighted audit sampling (learning to rank) | **Cut** | Labels come from injected faults, which is circular (the build plan already admits this). All 5 advisors cut it. |
| 8 | Correlated uncertainty propagation | **Shrink** to IPCC fuel-factor ranges only | CEA publishes no uncertainty for grid factors, so the flagship grid example has no data. Invariant 6 forbids inventing it. |
| 11 | Verifier's workbench (Next.js) | **Shrink** to the existing FastAPI + static page | 4 of 5 advisors: the static page already walks the full provenance chain. As of 2026-10-05 the page also has reports with verify, a review queue for extractions and an exception log. |
| — | arXiv preprint | **Cut**; keep the Zenodo DOI | Zenodo is the deliverable; arXiv adds effort, not evidence. |

## Proposed to keep, reshaped

| # | Component | Proposal |
|---|---|---|
| 7 | Document extraction (AI/ML) | **Pipeline built 2026-10-04 on synthetic bills** (`docs/EXTRACTION.md`): rule baseline, candidate-scoring model, leave-one-layout-out calibration, frozen-model test. Test result: 33.3% on unseen layouts (baseline 0%); confidence ranks well but is not calibrated. Real bills are still needed. **Decision point at week 4:** fewer than about 30 real bills means staying on synthetic data and saying so. |
| 10 | Credit lifecycle automaton (ToC) | **Built 2026-09-26**: 5-state DFA, inductive proofs of P1–P3, explicit-state model checker with shortest counterexamples and mutation tests (`docs/LIFECYCLE.md`). DB-level enforcement of δ added 2026-10-05 (migration 0009; tests pass on the local development Postgres, CI not yet run). Optional: TLA+. |
| 2 | Denominator (production basis) versioning | **Built 2026-09-26** (migration 0006, `engine/production.py`). GEI is computed per facility; it is withheld with a reason for multi-product plants (equivalent-product conversion not built). This was already in scope, so no sign-off is needed. |
| 5 | Materiality engine + RQ1 curve | **Engine and sector-agnostic curve built 2026-09-26** (`materiality/assess.py`, `docs/RQ1_RESULTS.md`). Per-sector placement still needs cited Scope 2 shares *of the 2024-27 target basis* in `data/sector_scope2_shares.csv`. |

## Rejected by the council (recorded so nobody re-proposes them silently)

SEBI BRSR corpus, a CBAM extension and a policy paper. BRSR is company-level
disclosure, not plant-level gate-to-gate intensity, so it would not unblock
RQ1 or RQ3, and it is scope creep.

## Sign-off

| Member | Agree? | Date | Notes |
|---|---|---|---|
| ____ | | | |
| ____ | | | |
| ____ | | | |
| ____ | | | |
| Faculty guide(s): rubric still met for DBMS / AI/ML / ToC? | | | |
