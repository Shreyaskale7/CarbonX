# Team and ownership

Every phase needs a named owner. Unowned work does not happen.

| Role | Owner | Owns | Gate |
|---|---|---|---|
| Data / DB | ____ | Schema, migrations, factor registry, CEA ingest, audit triggers | G2 |
| ML | ____ | Extraction, calibration, uncertainty, audit sampling | G3 |
| Formal | ____ | Dimensional type system, lifecycle automaton, Hypothesis suite | — |
| Product | ____ | API, verifier workbench, frontend | — |
| Writing | ____ | RQ3 document read, paper, Zenodo, viva deck | G1 |

Roles are ownership, not silos.

## Standing rules
- Scope is `CLAUDE.md`. Additions need whole-team written agreement.
- No raw utility bills in the repo, ever. Redact before storage.
- Never edit a migration that has already run.
- Commit format: `[P3] add dimensional composition rules`
