# CarbonX

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
verify each regenerates byte-identically, and print the uncertainty band. The API and provenance page:
`uvicorn carbonx.api.main:app` then http://127.0.0.1:8000.

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

## The invariant everything rests on

For any report R generated at transaction time T, re-executing R `AS OF T` at
any later time produces byte-identical output — regardless of intervening factor
supersessions, backdated corrections or data edits. Verified by property-based
testing in `tests/test_reproducibility.py` (10,000 generated sequences), not
asserted. What it took, and where it still stops: `docs/ADVERSARIAL_LOG.md`.

## Not for production use

Research prototype. Not accredited. Does not issue assurance opinions.
Decision-support for accredited verifiers only.
