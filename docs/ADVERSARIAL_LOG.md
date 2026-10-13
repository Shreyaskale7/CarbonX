# Adversarial log: attempts to break invariant 1

> For any report R generated at transaction time T, re-executing R `AS OF T`
> at any later time T' produces byte-identical output, regardless of
> intervening factor supersessions, backdated corrections or data edits.

This is the record of trying to break that. Each entry says what was tried,
whether it **actually broke** reproduction (and how that was shown), the fix,
and the test that now guards it. Finding and fixing a break is a better result
than never having looked.

Code: `src/carbonx/engine/report.py`. Tests: `tests/test_reproducibility.py`.
Migrations: `db/migrations/versions/0003_*`, `0004_*`.

## Summary

| # | Attempt | Broke it? | Fixed by | Guarded by |
|---|---|---|---|---|
| 1 | Commit-time race: a writer stamps before T, commits after the report reads | **Yes**, demonstrated | 0003 | `test_report_waits_for_an_in_flight_writer` |
| 2 | Edit `factor_source.published_on` after the fact | Yes, by construction | 0003 | property test, `tamper_factor_source` op |
| 3 | Edit a document's recorded SHA-256 | Yes, by construction | 0003 | `tg_document_immutable` |
| 4 | Move a facility to another organisation / rename things | Moving: yes. Renaming: no | 0003 | property test, `move_facility` and `rename` ops |
| 5 | Insert a row with a backdated transaction time | **Yes**, demonstrated | 0004 | `test_backdated_transaction_time_is_rejected` |
| 6 | Close a row with an end time in the past | **Yes**, demonstrated | 0004 | `test_closing_a_row_in_the_past_is_rejected` |
| 7 | `TRUNCATE` a history table | Yes, by construction | 0004 | `test_history_cannot_be_truncated` |
| 8 | Rename a resolution policy code | Yes, by construction | 0004 | `test_policy_codes_are_immutable` |
| 9 | Change calculation code without bumping the version | Yes, by construction | engine version = source hash | `test_regenerate_refuses_under_another_engine_version` |
| 10 | Insert and supersede a factor in one transaction | Crashed, not silent | clock-based stamps (Phase 1) | `test_resolve_is_reproducible_under_any_later_inserts` |
| 11 | Random interleavings of everything legal | No | — | 10,000 Hypothesis sequences (below) |
| 12 | Disable the triggers as a database superuser | **Yes**, demonstrated | 0005: the app runs as non-owner `carbonx_app`; the owner remains trusted | `test_app_role_cannot_bypass_the_database_rules` |
| 13 | Two current production records for the same month (double denominator, half the GEI) | Yes, by construction | 0006 | `test_overlapping_production_is_rejected` |

"Demonstrated" means the break was reproduced against Postgres 16 on
2026-09-26 with the protection removed, and the report's regenerated SHA-256
differed from the stored one. "By construction" means the break follows
directly from the data model and was closed without staging it.

## The attempts

### 1. Commit-time race (demonstrated)

A row's transaction time was taken while its transaction ran, but the row only
became visible at commit. Nothing ordered that against a report choosing T.
Sequence: writer stamps its row `t`, has not committed. Report picks
`T > t` and reads without the row. Writer commits. Regenerating `AS OF T`
now sees the row (`t ≤ T`): different output.

Demonstrated by swapping `fn_system_now()` for a lock-free version and racing
two connections:

```
pre-0003 (lock-free):  reproduces=False  lines at generation=0, at regeneration=1
0003 (locking):        reproduces=True   lines at generation=1, at regeneration=1
```

The report *did* block in the broken version, but only at its own audited
`INSERT`, after it had already read. Blocking alone proves nothing, so the
test checks content and reproduction instead.

**Fix (0003):** transaction time comes only from `fn_system_now()`, which
first takes the global lock the audit chain already uses, held to commit. A
report takes the same lock before choosing T. So every row stamped before T
belongs to a transaction that committed before the report read.

### 2–4. Mutable reference data

- **`factor_source.published_on`** decides which versions `AS_OF_REPORT`
  may use. Editing it re-decides old reports. Now immutable.
- **`source_document`**: reports carry the document's SHA-256. Now immutable.
- **`facility.org_id`**: moving a facility would move its activities into
  another organisation's past reports. Now rejected.
- **Names** of organisations and facilities stay editable. Reports carry only
  ids, never names; the property test renames things mid-sequence to check
  this.

### 5–6. Backdated transaction time (demonstrated)

0003 made the *default* transaction time safe, but a writer could still supply
its own value.

- **Backdated insert:** `system_time_range = tstzrange('2020-01-01', NULL)`
  makes a row retroactively visible to every report `AS OF` a time after 2020.
- **Backdated close:** setting a row's end time before a report's T removes it
  from that report. Reports read activities with `@>`. Factor resolution was
  already immune, because it ignores closure.

Demonstrated by switching triggers off for one session (possible only as a
superuser, see 12):

```
backdated close   triggers on : REJECTED by trigger  report reproduces: True
backdated close   triggers OFF: accepted             report reproduces: False
backdated insert  triggers on : REJECTED by trigger  report reproduces: True
backdated insert  triggers OFF: accepted             report reproduces: False
```

**Fix (0004):** a transaction's *floor* is the clock time at which it first
took the global lock. Every system time it writes (a new row's start, a closed
row's end) must be at or after its floor. Any report taken before this
transaction took the lock has `T` < floor, so no write from this transaction
can change what that report sees.

### 7–8. TRUNCATE and policy renames

- **`TRUNCATE`** does not fire row triggers, so the delete guards never ran.
  Statement-level `BEFORE TRUNCATE` triggers now reject it on every history
  and reference table.
- **`resolution_policy.code`:** a stored report references its policy by id.
  Renaming the code changes what `regenerate` computes. Codes are now
  immutable.

### 9. Code drift

`regenerate` runs today's code. A changed rounding rule or factor mapping
would reproduce *different bytes* while claiming to be the same report.
`engine_version` is now the package version **plus a hash of every source file
that decides a report's bytes**. This covers the units language, the factor
registry, the calculation engine and the report builder. `regenerate` refuses
under any other version (`EngineVersionMismatch`). To regenerate an old
report, check out the commit that made it; this is by design.

### 10. Same-transaction supersession (Phase 1)

A factor inserted and superseded in the same transaction got an empty `[t, t)`
range, which the guard rejects. That was a crash, not a silent wrong answer.
Stamps come from a clock, not `now()`, so ranges within one transaction are
never empty.

### 11. Random interleavings: 10,000 sequences

`test_reports_reproduce_after_any_sequence` generates a starting set of
activities, then 1–8 operations drawn from:

- **new factor version:** a new source supersedes the current factor, for any
  FY in 2023-24 to 2025-26;
- **late older version:** a version with a *lower* ordinal arrives after newer
  ones;
- **activity arrives:** possibly for an earlier month (out-of-order arrival);
- **backdated correction:** `edit_activity` on a past month;
- **rename:** the organisation and facility, with arbitrary Unicode;
- **tamper factor source** and **move facility:** must be rejected;
- **production arrives** and **production correction:** the GEI
  denominator changes after the report was taken;
- **second product arrives** and **conversion declared** (added 2026-10-13,
  migration 0011): the plant gains a second product, and conversions into the
  equivalent product are declared and revised, so the intensity's denominator
  changes meaning after reports were taken;
- **new fuel factor**, **fuel arrives** and **fuel correction** (added
  2026-10-05): a default fuel factor is superseded; natural gas is recorded
  with an NCV; its quantity and NCV are corrected later. If any fuel was
  recorded, the test also asserts that the last report contains a fuel
  line, so these operations cannot pass by doing nothing.

After the initial state and after **every** operation, it generates a report
under **all four** policies. At the end it regenerates every one of them and
compares output and SHA-256 byte for byte.

**Result (2026-10-05, commit `8ebc6a1`): 10,000 sequences passed, 0 failed.**
Hypothesis also reports 811 generated cases as invalid (discarded by the
generator, not run). The run took 1 h 35 min
(`HYPOTHESIS_PROFILE=thorough pytest tests/test_reproducibility.py -k any_sequence`)
and included the fuel operations.

What this run does not show: it ran on the local development Postgres (18.4,
with `btree_gist` and `pgcrypto` emulated by `scripts/dev_pg.py`), not on the
target Postgres 16, and in one transaction (see the limits below). An earlier
run without the fuel operations was stopped by a time limit and gives no result.

The only failure Hypothesis found during development was in the test data,
not the invariant: it generated a name containing a NUL byte, which
PostgreSQL cannot store. The generator now excludes NUL.

### 12. Superuser (fixed for the application, 0005)

Every guarantee above is enforced by triggers. A database superuser, or the
table owner using DDL, can disable them (`SET session_replication_role =
replica`), and attempts 5–6 then break reproduction again. With triggers off,
the audit trail records nothing either, so this would not even be
tamper-evident.

Until migration 0005, the prototype connected as the `carbonx` role, which the
Postgres image creates as a superuser. So every guarantee here held only
while the application chose not to break it. This was flagged by the project
council (`docs/council/`) as the cheapest credibility hole.

**Fix (0005):** the API, engine, scripts and tests now connect as
`carbonx_app`. It is not a superuser and owns no tables, and it has only the
privileges the application needs: SELECT everywhere; INSERT on ledger tables;
UPDATE only where rows may be closed or renamed. It has no DELETE, TRUNCATE
or DDL, and cannot set `session_replication_role`. It cannot write
`audit_event` directly: `fn_audit` runs as its owner (`SECURITY DEFINER`), so
audit rows can only come from the trigger. Only Alembic uses the owner
(`MIGRATION_DATABASE_URL`). `test_app_role_cannot_bypass_the_database_rules`
checks each refusal.

**Still a limit:** the owner and any superuser can do all of this, so they
must be trusted. Invariant 3 ("enforced at the database layer") now holds
against the application, not against the DBA.

**Narrowed, not closed (2026-10-13): anchors.** An owner who rewrites an event
can also recompute the hash chain, so `fn_verify_audit_chain()` passes on the
falsified history. `carbonx.evidence.anchor` records the chain's latest hash in
a file outside the database; after such a rewrite the hash at the anchored event
no longer matches. `tests/test_anchor.py` performs the rewrite, shows the
chain's own check passing, and shows the anchor failing. This is detection after
the fact, only for history before an anchor, and only as trustworthy as the
place the anchor file is kept (`anchors/README.md`). The DBA can still disable
the triggers; they can no longer do it and leave no trace before an anchor.

## Limits of the evidence

- **The property test runs all 10,000 sequences in one database
  transaction.** It tests the `AS OF` logic, not concurrency. Behaviour across
  transactions (attempts 1, 5, 6) is covered by targeted two-connection tests,
  which commit real rows under uniquely named organisations; the ledger is
  append-only, so those rows cannot be removed.
- **Reports cover grid electricity (Scope 2) and fuel combustion (Scope 1),
  not process emissions.** Production and GEI (component 2, migration 0006)
  are covered, and the property test corrects production and fuel
  mid-sequence. For a plant with more than one product, GEI needs a
  declared conversion for every product (migration 0011); until then it is
  withheld with the reason. The property test adds a second product and
  declares and revises conversions mid-sequence.
- **Reports block writers briefly.** Report generation holds the global write
  lock for its duration. That is fine for a prototype; partitioning the lock by
  organisation is the upgrade path.
