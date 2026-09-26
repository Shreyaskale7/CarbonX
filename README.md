# CarbonX

A bitemporal carbon accounting ledger for India's Carbon Credit Trading Scheme,
where every reported emission figure is traceable to source evidence and every
historical report stays reproducible when emission factors are revised.

**V-semester group Experiential Learning project, RVCE.** SDG 13.
Courses: DBMS, AI/ML, Theory of Computation.

## Quick start

    docker compose up -d
    pip install -e ".[dev]"
    alembic upgrade head
    python scripts/fetch_cea.py          # download all CEA factor versions
    python scripts/seed_policies.py
    ./reproduce.sh                       # end-to-end on sample data

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
