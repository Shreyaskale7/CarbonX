# Status: each phase against its own acceptance test

As of 2026-10-05, commit history `be78e97..HEAD`. The acceptance tests are the
ones in `docs/BUILD_PLAN.md`, quoted or paraphrased. "Met" means the stated test
passes; anything short of that says what is missing.

**How far to trust "passes".** All database tests pass on the local development
Postgres (`scripts/dev_pg.py`: Postgres 18, with `btree_gist` and `pgcrypto`
emulated). The last run on the target (Postgres 16 in Docker) was at commit
`5f518b1` and covered phases 1–5. **CI has never run**, because the repository
has not been pushed.

| Phase | Acceptance test | Status | Evidence | Missing |
|---|---|---|---|---|
| 0 Gates | RQ3 findings with quotes; ≥4 CEA versions; named owner per phase | **Partly** | `RQ3_FINDINGS.md` has verbatim quotes; 23 CEA versions | **No named owners** (`TEAM.md` blank). BEE PDF not confirmed as the notified text. No bills collected |
| 1 Schema, registry | overlapping factor rejected; `resolve()` differs by policy | **Met** | `test_factor_registry.py` | — |
| 2 CEA ingest, RQ2 | every version loaded with hash and URL; year-on-year table; checkpoints | **Met** | `data/cea/`, `RQ2_RESULTS.md`, `test_cea_registry.py` | Plan named a notebook; a script generates the table instead |
| 3 Type system | `kWh × tCO2e/MWh` → tCO2e; wrong unit rejected; property test; `mypy --strict` | **Met**, with one correction | `test_units.py`, `TYPE_SOUNDNESS.md` | The plan's "`kWh × tCO2e/litre` raises" is wrong as stated: the error is in *declaring* the result tCO2e. Documented |
| 4 Vertical slice | a newcomer runs `reproduce.sh`, uploads a bill, walks the chain | **Met** | walked in a browser at `5728e7c`, and again on 2026-10-05 with every panel (provenance, policy attestation, reports with verify, coverage, review queue, exceptions, fuel entry) against the development Postgres; `test_engine.py`, `test_workbench.py` | The second walk-through used the development Postgres, not Docker |
| 5 Reproducibility | ≥10,000 generated sequences pass; failures documented and fixed | **Met on the development Postgres** | 10,000 generated sequences passed, 0 failed (2026-10-05, commit `8ebc6a1`, 1 h 35 min); `ADVERSARIAL_LOG.md` documents 13 attempts | Not yet repeated on Postgres 16; CI runs the 100-sequence profile |
| 6 Extraction | accuracy per DISCOM, seen vs unseen; beats baseline on unseen; ECE before/after; calibrated confidence stored | **Partly, on synthetic data** | `EXTRACTION_RESULTS.md`: unseen test layouts 33.3% vs baseline 0% | **No real bills.** One modelled field; period and meter id by rules only. Confidence is *not* calibrated on unseen layouts (ECE 0.347), so the stored confidence does not meet invariant 6 |
| 7 Uncertainty | correlated band wider than naive, quantified; every variance traced, nothing invented | **Met, in reduced scope** | `test_uncertainty.py` (wider by √3); `UNCERTAINTY.md` | Fuel factors only. Grid factor, activity data and extraction carry no uncertainty, by invariant 6 |
| 8 Materiality, RQ1 | per-sector curve with cited Scope 1/2 splits | **Partly** | engine: `test_materiality.py`; `RQ1_RESULTS.md` (sector-agnostic curve) | **No sector rows**: `data/sector_scope2_shares.csv` needs cited shares |
| 9 Automaton | properties proved by enumeration | **Met** | `LIFECYCLE.md`: proofs, model checker, mutation tests; enforced in the DB (migration 0009) | Proof is by hand, not mechanised |
| (proposed) Nowcast | leakage-safe rolling backtest against a naive baseline; bands with out-of-sample coverage; revision analysis | **Built, not in agreed scope** | `NOWCAST.md`, `NOWCAST_RESULTS.md`, `test_nowcast.py` (7 tests, no database) | Team sign-off in `SCOPE_PROPOSAL.md`. About 20 yearly values, so it can only show that nothing simple beats the naive forecast |
| 9 Audit sampling | learned ranker beats two baselines at 5% and 10% | **Built with a different method** (proposed, unsigned) | `SAMPLING.md`, `test_sampling.py`, migration 0012, the `/sampling` page: a statistical sample in proportion to tonnes, re-derivable from the report, with a projection and upper limits | No learned ranker, so the plan's test as written is not met. Needs sign-off in `SCOPE_PROPOSAL.md`. The tolerable misstatement for CCTS is not verified |
| 10 Workbench, release | demo with no developer at a terminal; DOI minted | **Partly** | a seven-page static site served by the API (overview, findings, factor registry, method, and a three-page workbench: ledger with provenance and corrections, evidence with the review queue and production records, reports with verify, uncertainty, materiality, exceptions and a rolled-back reproducibility demonstration); every page exercised in a browser on 2026-10-05 and 06 | **No DOI.** Licence and authors undecided. Not pushed to GitHub |

## Against the grade ladder in the build plan

| Level | Needs | Where it stands |
|---|---|---|
| Pass | Phases 1–4 | Met |
| Good | + Phase 5 and Phase 2 | Phase 2 met. Phase 5 met on the development Postgres; repeat on Postgres 16 once CI runs |
| A | + Phase 6 (calibrated, unseen-layout results) and Phase 8 (RQ1 curve) | Both partly: Phase 6 needs real bills; Phase 8 needs cited sector shares |
| A+ | + Phase 7, Phase 9 proofs, DOI, preprint, documented RQ3 answer | Phase 7 met in reduced scope; Phase 9 proofs met; RQ3 answered provisionally. No DOI, no preprint |

## The invariants

| # | Invariant | Holds? |
|---|---|---|
| 1 | Reports reproduce byte-identically | Yes against the application; `ADVERSARIAL_LOG.md` lists what it took. 10,000 generated sequences pass on the development Postgres |
| 2 | No in-place factor updates | Yes: trigger-enforced |
| 3 | Audit trail enforced at the database layer | Yes against the application, which runs as a non-owner role. Not against the database owner or a superuser; a rewrite by them before an anchor is detectable if the anchor file is kept elsewhere (`anchors/README.md`) |
| 4 | Dimensional soundness | Yes for the calculation language; eight documented escape hatches |
| 5 | Evidence hashed; audit log hash-chained | Yes. Tamper-evidence, not a blockchain |
| 6 | Uncertainty never invented | Yes for factors. **Not yet for extraction**: its confidence is not calibrated on unseen layouts, so it must not be used as a probability |

## Findings so far (each with its caveat in the linked file)

- **RQ3** (`RQ3_FINDINGS.md`): BEE's rule, "the latest average grid emission
  factor", does not determine one number. Readings of "latest" differ by 4.87%
  for FY2025-26; CEA's candidate "average" series by 17–22%. The FY2025-26
  factor is dated 1 Aug 2026 and reached CEA's server about 10 Sep 2026.
- **RQ3 as a compliance outcome** (`RQ3_COMPLIANCE.md`): with no physical
  change, the three readings show a GEI change of 0%, −2.45% or −7.20% times
  the Scope 2 share. The baseline year (FY2023-24) is assumed, not verified.
- **Nowcast** (`NOWCAST_RESULTS.md`; proposed addition, unsigned): predicting a
  year's factor by the previous year's value missed by 1.99% on average over 20
  years; none of four simple alternatives beat it. A band built from earlier
  errors contained 10 of 12 (80%) and 11 of 12 (90%) later values. The FY2025-26
  value fell outside the 90% band. CEA's later restatements of a year are far
  smaller (median 0.07%).
- **RQ2** (`RQ2_RESULTS.md`): every comparable year-on-year step in the
  all-India grid factor exceeded 1%; the latest was −4.93%.
- **RQ1** (`RQ1_RESULTS.md`): CEA's restatements of a past year are too small
  to cross 5% at any Scope 2 share. The choice of series crosses it above a
  23% share.
- **BEE vs IPCC** (`BEE_VS_IPCC.md`): 50 of BEE's 53 default CO2 factors equal
  IPCC 2006's. Three coal factors do not, by +1.6%, +5.1% and +5.9%.
- **The denominator is under-determined too** (`RQ3_FINDINGS.md`): for plants
  with more than one product BEE says "the main product or an equivalent
  product ... per standard practice prevalent in the obligated entity's sector"
  and gives no conversion. The procedure also never names the baseline year.
  CarbonX therefore takes the conversion as a declared, versioned input
  (migration 0011) and withholds intensity until every product has one.
- **2024-27 targets exclude process emissions** (BEE p. 7 note), which raises
  the Scope 2 share of the target basis in cement, steel and refining.

All of these rest on one BEE PDF whose internal date (2023-11-08) precedes the
reported notification. Confirm it before any of them is cited.

## Environment note (2026-10-06)

For part of 2026-10-06, a Windows Application Control policy on the development
laptop blocked one compiled file of scikit-learn (`_target_encoder_fast`), so
the bill reader and its tests could not run. It cleared later the same day with
no change on our side, and the full suite passes again (148 passed, 1 skipped).
It may recur, for example before a demo. If it does, the site still starts:
the reader is loaded on demand and returns a clear error. Nothing in the
repository works around the policy.

**2026-10-12: the development database no longer starts on this laptop.** The
same Windows policy now blocks the bundled `postgres.exe` ("blocked by your
organization's Device Guard policy") and another scikit-learn file. Until that
changes, nothing that needs a database can be run or verified here: the site
with data, `reproduce.sh`, and the database tests. The 40 tests that need
neither still pass. Work committed up to `c741d55` was verified before the
block. The way forward is a PostgreSQL the policy allows: version 16 installed
from postgresql.org, Docker, or CI on GitHub. Each of those is also the real
target, with the real `btree_gist` and `pgcrypto`.

**2026-10-13: the block lifted.** `postgres.exe` runs again on the laptop, with
no change on our side. Everything built while it was blocked was then verified
on the database: the full suite (170 passed, 1 skipped), `reproduce.sh` on a
fresh database, and the site with data. The block may return, so the advice
above stands: have a PostgreSQL 16 or CI available before the viva.

## What only the team can do

1. Put names in `docs/TEAM.md`; each owner learns their component well enough
   to defend it.
2. Push to GitHub, so CI runs on Postgres 16.
3. Sign or reject `docs/SCOPE_PROPOSAL.md`.
4. Confirm the BEE PDF against the notified text; archive the CEA v22 evidence.
5. Collect and redact real bills (decision point: week 4).
6. Cite per-sector Scope 2 shares of the 2024-27 target basis.
7. Check RVCE's AI-use policy and complete `docs/AI_USE.md`.
8. Choose a licence and authors for the registry and put them in
   `data/cea/release.json`; `python scripts/build_registry_release.py` then
   builds the bundle to upload. Mint the DOI.
