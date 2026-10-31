# CarbonX

[![CI](https://github.com/Shreyaskale7/CarbonX/actions/workflows/ci.yml/badge.svg)](https://github.com/Shreyaskale7/CarbonX/actions/workflows/ci.yml)

A bitemporal carbon accounting ledger for India's Carbon Credit Trading Scheme,
where every reported emission figure is traceable to source evidence and every
historical report stays reproducible when emission factors are revised.

**V-semester group Experiential Learning project, RVCE.** SDG 13.
Courses: DBMS, AI/ML, Theory of Computation.

## What we found, in plain words

- **The rule for electricity emissions does not pin down one number.** The
  regulator (BEE) says to use "the latest average grid emission factor" from
  CEA's database. For the first compliance year:
  - that year's factor appeared only after reports were due (dated 1 Aug 2026,
    on CEA's site around 10 Sep 2026);
  - the two readings of "latest" (before or after it appeared) differ by 4.9%;
  - CEA publishes several "average" series, which differ by up to 22%.

  Same electricity use, different reported emissions. Quotes, evidence and
  open checks: `docs/RQ3_FINDINGS.md`.
- **The factor moves more year to year than the targets it is measured
  against.** Across all 23 published versions (2006–2026), every comparable
  year-on-year step in the all-India grid factor exceeded 1%. The latest was
  −4.93%. FY2025-26 targets ask for a 1–3% cut in intensity. This only moves
  the Scope 2 (purchased electricity) share of an entity's emissions:
  `docs/RQ2_RESULTS.md`.
- **A past report can be re-run and gives exactly the same bytes, even after
  the factor is revised.** Demo: `python scripts/demo_reproducibility.py
  --org 1`.

The sample facility and its figures (e.g. 11,055.5 vs 11,551.5 tCO2e under
different factor policies) are **synthetic illustrations**, not measurements of
any real entity.

## Where the project stands

Everything in scope is built and tested; what is missing is real data and
decisions only people can make. In short: CI is green on PostgreSQL 16; the
reproducibility property passed 10,000 generated sequences on Postgres 16 (and
three times on the development Postgres); bill extraction has only been tried on
invented bills, and the tooling to collect and score real ones is ready
(`docs/BILL_COLLECTION.md`, `scripts/eval_real_bills.py`). Each phase against its
own acceptance test, with what is missing: `docs/STATUS.md`.

## Quick start

    docker compose up -d                 # Postgres 16
    pip install -e ".[dev]"
    alembic upgrade head                 # applies db/schema.sql (migration 0001)
    python scripts/seed_policies.py      # the four resolution policies
    python scripts/load_cea.py --db      # CEA registry v1.0-v22.0 from data/cea/
    pytest                               # DB invariants, registry, engine, reports
    python -m carbonx.engine.report --org 1 --fy FY2025-26 --verify

**No Docker?** `pip install pixeltable-pgserver`, then
`python scripts/dev_pg.py reset` and `eval "$(python scripts/dev_pg.py env)"`
give a local Postgres with every migration applied. It is a stand-in
(Postgres 18, with two missing extensions emulated; the script explains how),
good for development. CI on Postgres 16 remains the authority.

Migrations run as the schema owner. Everything else (API, engine, scripts,
tests) connects as `carbonx_app`, a role that cannot delete, truncate, alter
schema or switch triggers off, so the database's rules hold against the
application (`src/carbonx/db.py`, migration 0005).

CI (`.github/workflows/ci.yml`) runs ruff, mypy --strict, the migrations, the
sample pipeline with report verification, and the full test suite against
Postgres 16 on every push.

The open CEA factor registry is committed in `data/cea/` (2,071 factors, 23
versions, each traced to a workbook cell and a SHA-256-hashed download).
Rebuild it from source with `python scripts/fetch_cea.py && python
scripts/load_cea.py`. RQ2 results: `docs/RQ2_RESULTS.md`.

`./reproduce.sh` runs end to end: migrate, load the registry, seed a synthetic
facility (electricity, gas and production), calculate, then generate a report
under each policy, with Scope 1 and 2 emissions and GEI (tCO2e per tonne),
verify each regenerates byte-identically, and print the uncertainty band. The API and the site:
`uvicorn carbonx.api.main:app` then http://127.0.0.1:8000.

The site is static HTML served by the API (no Node, no build step):

| Page | What it shows |
|---|---|
| `/` | Overview, with a live check that regenerates the newest stored report |
| `/findings` | RQ1, RQ2, RQ3, the nowcast backtest and the BEE vs IPCC comparison, with the generated figures |
| `/registry` | Every all-India CEA grid factor by year and version, with its history |
| `/method` | The type checker and the credit lifecycle, both runnable in the page |
| `/sampling` | Plan an audit sample of a stored report in proportion to tonnes, record what was found, and see the projection |
| `/ledger`, `/evidence`, `/reports` | The workbench: provenance, corrections, uploads, review queue, production records, reports with verify, the uncertainty band, materiality assessment, exceptions, and a one-click before/after demonstration of reproducibility |

Without Docker: `python scripts/dev_pg.py serve` starts a local Postgres and the site together.

**The console.** `/console` (or just double-click
`src/carbonx/api/static/console.html`; it needs no server and no network) is the
verifier's workbench in one file: overview, ledger with provenance, reports, the
factor registry, materiality, the factor nowcast backtest, sampling and the
audit trail, with the engine's arithmetic re-implemented in the browser and
tested against Python. It is a snapshot of the synthetic sample; see
`docs/FRONTEND.md`.

## Read these first

| File | What it is |
|---|---|
| `CLAUDE.md` | Project context, invariants, scope. **Read before writing code.** |
| `docs/BUILD_PLAN.md` | Ten phases with acceptance tests |
| `docs/STATUS.md` | Each phase against its acceptance test: what is met, partly met, missing |
| `db/schema.sql` | Full schema, commented |
| `docs/RQ3_FINDINGS.md` | Does BEE specify the factor vintage? (Phase 0) |
| `docs/RQ1_RESULTS.md` | When a grid-factor change alone crosses 5%, generated |
| `docs/RQ2_RESULTS.md` | Year-on-year CEA factor changes, generated |
| `docs/TYPE_SOUNDNESS.md` | Dimensional type system: rules, proof, limits |
| `docs/LIFECYCLE.md` | Credit lifecycle automaton, safety proofs, model checking |
| `docs/BEE_VS_IPCC.md` | BEE's default fuel factors against IPCC 2006, row by row, generated |
| `docs/UNCERTAINTY.md` | Correlated uncertainty: what is quantified and what is not |
| `docs/EXTRACTION.md` | Bill extraction: method, what development found, limits (synthetic data) |
| `docs/ADVERSARIAL_LOG.md` | Every attempt to break invariant 1, and what it found |
| `docs/BILL_COLLECTION.md` | How to collect, redact and score real bills (none collected yet) |
| `docs/paper/DATA_IN_BRIEF_ARTICLE.md` | The dataset paper, formatted for Data in Brief (a draft, not for submission yet) |
| `paper/` | The IEEE-format paper (`main.tex`): every number, table and graph generated from the registry by `scripts/paper_build.py` and checked by `tests/test_paper.py`; 16 open `[VERIFY]` items, not for submission yet |
| `docs/paper/POLICY_PAPER_DRAFT.md` | The policy paper draft: one rule, several numbers |
| `docs/FRONTEND.md` | The single-file console at `/console`: a snapshot of the synthetic sample, rebuilt by `scripts/build_console.py` |

## The invariant everything rests on

For any report R generated at transaction time T, re-executing R `AS OF T` at
any later time produces byte-identical output — regardless of intervening factor
supersessions, backdated corrections or data edits. Verified by property-based
testing in `tests/test_reproducibility.py` (10,000 generated sequences), not
asserted. What it took, and where it still stops: `docs/ADVERSARIAL_LOG.md`.

## The open registry, and licence

The CEA factor registry in `data/cea/` is meant to be released with a DOI. **No
licence has been chosen yet, for the code or the data**, and the terms under
which data derived from CEA's publications may be redistributed have not been
confirmed. CEA's current copyright policy allows free reproduction **only with prior
permission by email** (`docs/OUTREACH_DRAFTS.md` has the policy summary and a
draft request, not yet sent). Until that and the licence are settled, treat
everything here as all rights reserved
and ask before reusing it. Authors and licence go in `data/cea/release.json`.

## Not for production use

Research prototype. Not accredited. Does not issue assurance opinions.
Decision-support for accredited verifiers only.
