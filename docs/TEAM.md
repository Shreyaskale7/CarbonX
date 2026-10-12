# Team and ownership

Every phase needs a named owner. Unowned work does not happen.

**Viva rule (council, 26 Sep 2026):** RVCE grades each member individually.
Each owner must be able to explain their component without notes and defend
its design choices. Before the viva, every member also presents *another*
member's component once (cross-defence rehearsal).

| Role | Owner | Owns | Must be able to defend |
|---|---|---|---|
| Data / DB | ____ | Schema, migrations 0001–0004, factor registry, CEA ingest, audit triggers | Bitemporal model; exclusion constraints; why a report reproduces (`docs/ADVERSARIAL_LOG.md`) |
| ML | ____ | Document extraction, calibration, (fuel-factor) uncertainty | Held-out split design; calibration (ECE before/after); why confidence is calibrated |
| Formal (ToC) | ____ | Units language and type checker, credit automaton, Hypothesis suite | Grammar is LL(1); soundness proof (`docs/TYPE_SOUNDNESS.md`); automaton safety properties |
| Research / writing | ____ | RQ3 reading (BEE procedure), RQ1/RQ2 write-up, Zenodo, viva deck | `docs/RQ3_FINDINGS.md`, `docs/RQ2_RESULTS.md`; what the project does NOT claim (`CLAUDE.md`) |

Roles are ownership, not silos.

## Handover: already built, now needs an owner who understands it

| Built | Code | Proposed owner |
|---|---|---|
| Factor registry, 4 resolution policies | `src/carbonx/factors/registry.py` | Data / DB |
| CEA registry (23 versions) + RQ2 | `src/carbonx/ingest/cea.py`, `scripts/*cea*`, `scripts/rq2_deltas.py` | Data / DB + Research |
| Units language, checker, soundness | `src/carbonx/units/`, `docs/TYPE_SOUNDNESS.md` | Formal |
| Engine, evidence store, provenance, API | `src/carbonx/engine/`, `src/carbonx/evidence/`, `src/carbonx/api/` | Data / DB |
| Production and GEI (denominator) | `src/carbonx/engine/production.py`, migration 0006 | Data / DB |
| Least-privilege app role | `src/carbonx/db.py`, migration 0005 | Data / DB |
| Materiality engine (5% base-year recalculation) | `src/carbonx/materiality/assess.py`, migration 0007 | Data / DB + Research |
| Grid-factor nowcast and revision analysis (proposed, unsigned) | `src/carbonx/forecast/nowcast.py`, `scripts/nowcast.py`, `docs/NOWCAST.md` | ML + Research |
| RQ1 sensitivity curve | `scripts/rq1_materiality.py`, `docs/RQ1_RESULTS.md`, `data/sector_scope2_shares.csv` | Research |
| Scope 1 fuel combustion (BEE Annexure IV) | `scripts/load_bee_factors.py`, `data/bee/`, engine `fuel.<slug>` | Data / DB |
| BEE vs IPCC comparison; uncertainty propagation | `scripts/compare_bee_ipcc.py`, `src/carbonx/uncertainty/`, `docs/UNCERTAINTY.md` | ML + Research |
| Bill extraction: baseline, model, calibration, evaluation | `src/carbonx/extraction/`, `scripts/eval_extraction.py`, `docs/EXTRACTION.md` | ML |
| Credit lifecycle automaton, model checker, DB enforcement | `src/carbonx/lifecycle/`, migration 0009, `docs/LIFECYCLE.md` | Formal |
| Review queue and exception log | `src/carbonx/extraction/review.py`, `src/carbonx/engine/exceptions.py`, migration 0010 | ML + Data / DB |
| Reproducible reports + adversarial log | `src/carbonx/engine/report.py`, `tests/test_reproducibility.py` | Data / DB + Formal |

Suggested way in for each owner: pick one test in your area, break the code it
guards on purpose, watch the test fail, and explain why. Then fix it.

## Standing rules
- Scope is `CLAUDE.md`. Changes need whole-team written agreement (see
  `docs/SCOPE_PROPOSAL.md` for the pending proposal).
- No raw utility bills in the repo, ever. Redact before storage.
- Never edit a migration that has already run.
- AI assistance is recorded in `docs/AI_USE.md`.
- Commit format: `[P3] add dimensional composition rules`
