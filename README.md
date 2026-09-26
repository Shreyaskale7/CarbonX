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
    pytest                               # DB invariants + factor registry

CI (`.github/workflows/ci.yml`) runs ruff, mypy --strict, the migration and the
full test suite against Postgres 16 on every push.

Not built yet (see `docs/BUILD_PLAN.md`): `scripts/fetch_cea.py`, CEA ingest,
the calculation engine, and therefore `./reproduce.sh`.

## Read these first

| File | What it is |
|---|---|
| `CLAUDE.md` | Project context, invariants, scope. **Read before writing code.** |
| `docs/BUILD_PLAN.md` | Ten phases with acceptance tests |
| `db/schema.sql` | Full schema, commented |
| `docs/RQ3_FINDINGS.md` | Does BEE specify the factor vintage? (Phase 0) |

## The invariant everything rests on

For any report R generated at transaction time T, re-executing R `AS OF T` at
any later time produces byte-identical output — regardless of intervening factor
supersessions, backdated corrections or data edits. Verified by property-based
testing in `tests/test_reproducibility.py`, not asserted.

## Not for production use

Research prototype. Not accredited. Does not issue assurance opinions.
Decision-support for accredited verifiers only.
