# Architecture: what is built, and the next two changes

Written 2026-11-10. A design note, not a commitment. **Nothing here is built.** Both
changes below are hardening of existing components (1 and 3 in `CLAUDE.md`), not new
scope. Anything that would add to the BUILD list goes through `docs/SCOPE_PROPOSAL.md`.

## What exists

```
 SOURCES                INGEST                 CORE (PostgreSQL, bitemporal)               OUTPUT
 CEA workbooks  ─►  factor loader     ─►  factor registry (versions, vintages)  ─┐
 DISCOM bills   ─►  redact + extract  ─►  evidence store (SHA-256, review gate)  ├─► calc engine ─► verifier workbench
 meter / ERP    ─►  CSV adapters      ─►  activity + production-basis versions   ─┘   (typed units)   materiality, uncertainty
                                          hash-chained audit trail (DB triggers)
```

Migrations 0001 to 0016 are in `db/migrations/versions/` (0015 intensity target and 0016 baseline record
were added after the first draft of this note). The next is **0017**.
Factor resolution is `carbonx.factors.registry.resolve()`, with `Policy` a per-call argument.

## Change 1: a regulatory profile for policy choice (RQ3 as data)

**Problem.** `Policy` is a parameter the caller passes. RQ3 (which version applies when the
BEE procedure is silent) is unresolved, and the answer may differ by scheme, sector and
compliance year. Hard-coding a default in code would hide an open question.

**Design.** A profile records which policy a scheme applies to a compliance year, and why.

| table | columns | notes |
|---|---|---|
| `regulatory_profile` | `profile_id`, `scheme` (e.g. CCTS), `compliance_fy`, `policy`, `source_citation`, `status` (`confirmed` / `assumed` / `disputed`), `note` | bitemporal, superseded and never edited, like factors |
| `report` | add `profile_id` | a report pins the profile it used |

**Rules.**
- Seed rows only for what a primary source supports. Until someone reads BEE's procedure
  (`docs/RQ3_FINDINGS.md`), the CCTS row is `assumed` or `disputed` and the console says so.
- The report records the profile and its status, so a reader sees an `assumed` policy as assumed.
- Reproducibility holds: the profile is read `AS OF` the report's transaction time, like a factor.

**Tests.** Hypothesis: a later profile supersession never changes an old report's bytes.
Unit: a report without a `confirmed` profile is labelled so in its output.

## Change 2: gate-to-gate boundary, so the grid factor touches only the Scope 2 part

**Problem.** GEI is tCO2e per unit of product, gate-to-gate, Scope 1 and 2. In cement, iron and steel
and refining, process emissions dominate and the grid factor does not touch them. The materiality
curve already shows this, but the data model does not separate the pieces.

**Design.** Tag each emission line with a boundary and a scope.

| field | values |
|---|---|
| `scope` | 1 (combustion), 1 (process), 2 (purchased electricity) |
| `boundary` | inside / outside the notified gate-to-gate boundary |

The engine already handles fuel activities (migration 0008). The change is a column on the
calculation lines and a materiality view that sums only the Scope 2 inside the boundary.

**Rules.**
- Every percentage derived from a grid-factor change keeps its Scope 2 qualifier (`CLAUDE.md`).
- A line without a boundary tag is rejected, not defaulted. Do not invent one.
- Process emission factors come from a cited source. If none is published, report a point
  estimate and say so (invariant 6).

**Tests.** Dimensional type check still holds. A facility with zero Scope 2 is unaffected by any
grid factor revision (property test).

## Smaller items, in order

| # | Item | Depends on |
|---|---|---|
| 3 | Evidence pack: one entity and one report, with a one-command re-run that compares hashes | change 1 (the pack names its profile) |
| 4 | Publish the audit chain head periodically (a dated signed file). Tamper-evidence, not blockchain | none |
| 5 | Per-utility extraction adapters; calibrated confidence | reviewed bills from at least 3 utilities |
| 6 | Registry release with checksum manifest | CEA's reply |

## Not proposed

Live registry or BEE portal integration, multi-tenant, role-based access, batch reports, Scope 3 and
regional grid factors are outside BUILD. An upload-ready export file is the safe substitute for
registry integration, and even that needs team agreement.

## Before building

- Confirm with the guide that these two changes are hardening and not new scope.
- Read BEE's procedure first, or change 1 can only ship with an `assumed` status.
- Keep to `mypy --strict` on `factors`, and write the Alembic migration as 0015. Never edit one that has run.
