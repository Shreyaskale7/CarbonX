# CarbonX

A bitemporal carbon accounting ledger for India's Carbon Credit Trading Scheme,
where every reported emission figure is traceable to source evidence and every
historical report stays reproducible when emission factors are revised.

**V-semester group Experiential Learning project, RVCE.** SDG 13.
Courses: DBMS, AI/ML, Theory of Computation.

## Quick start

    docker compose up -d                 # Postgres 16
    pip install -e ".[dev]"
    alembic upgrade head                 # applies db/schema.sql (migration 0001)
    python scripts/seed_policies.py      # the four resolution policies
    python scripts/load_cea.py --db      # CEA registry v1.0-v22.0 from data/cea/
    pytest                               # DB invariants + factor registry

CI (`.github/workflows/ci.yml`) runs ruff, mypy --strict, the migration and the
full test suite against Postgres 16 on every push.

The open CEA factor registry is committed in `data/cea/` (2,071 factors, 23
versions, each traced to a workbook cell and a SHA-256-hashed download).
Rebuild it from source with `python scripts/fetch_cea.py && python
scripts/load_cea.py`. RQ2 results: `docs/RQ2_RESULTS.md`.

Not built yet (see `docs/BUILD_PLAN.md`): the calculation engine, and
therefore `./reproduce.sh` past step 3.

## Read these first

| File | What it is |
|---|---|
| `CLAUDE.md` | Project context, invariants, scope. **Read before writing code.** |
| `docs/BUILD_PLAN.md` | Ten phases with acceptance tests |
| `db/schema.sql` | Full schema, commented |
| `docs/RQ3_FINDINGS.md` | Does BEE specify the factor vintage? (Phase 0) |
| `docs/RQ2_RESULTS.md` | Year-on-year CEA factor changes, generated |
| `docs/TYPE_SOUNDNESS.md` | Dimensional type system: rules, proof, limits |

## The invariant everything rests on

For any report R generated at transaction time T, re-executing R `AS OF T` at
any later time produces byte-identical output — regardless of intervening factor
supersessions, backdated corrections or data edits. Verified by property-based
testing in `tests/test_reproducibility.py`, not asserted.

## Not for production use

Research prototype. Not accredited. Does not issue assurance opinions.
Decision-support for accredited verifiers only.
