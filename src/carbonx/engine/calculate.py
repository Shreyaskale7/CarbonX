"""Carbon calculation engine: activity x resolved factor, through the typed
calculation language, pinned forever.

Every calculation is written as a units/lang.py program, type-checked before
it is evaluated, and stored verbatim in calculation.program. It pins the
factor row it used (invariant 2) and resolves that factor AS OF its own
transaction time, so re-running it later gives the same factor.

Corrections never overwrite (invariant 1): edit_activity closes the old
activity, calculation and ledger rows and inserts new ones. The DB guard
rejects anything else, and the audit trigger records it all (invariant 3).

    python -m carbonx.engine.calculate --org 1 --policy VINTAGE_MATCHED
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from importlib.metadata import version

import psycopg

from carbonx.factors.registry import EmissionFactor, Policy, resolve
from carbonx.units.lang import run

ENGINE_VERSION = version("carbonx")

# activity_type -> (scope, factor_key, geography). Which CEA factor applies to
# Scope 2 electricity is a methodological choice, not a fact: this is the
# all-India weighted average incl. RE, captive and imports (the series behind
# the v19 = 0.716 checkpoint). Change it here, and nowhere else.
ACTIVITY_TYPES: dict[str, tuple[int, str, str]] = {
    "grid_electricity": (2, "grid.weighted_avg_incl_re_captive.incl_imports", "IN"),
}


@dataclass(frozen=True)
class Calculation:
    calculation_id: int
    activity_id: int
    tco2e: Decimal          # as stored: NUMERIC(18,6), rounded half-even
    exact: Fraction         # what the typed program actually computed
    factor: EmissionFactor
    policy: Policy
    program: str


def fy_of(d: date) -> str:
    start = d.year if d.month >= 4 else d.year - 1
    return f"FY{start}-{(start + 1) % 100:02d}"


def _now(conn: psycopg.Connection) -> datetime:
    row = conn.execute("SELECT clock_timestamp()").fetchone()
    assert row is not None
    return row[0]


def set_audit_context(conn: psycopg.Connection, actor: str | None, reason: str | None) -> None:
    """Read by fn_audit; transaction-local, so it cannot leak to a later write."""
    conn.execute("SELECT set_config('carbonx.actor', %s, true),"
                 " set_config('carbonx.reason', %s, true)", (actor or "", reason or ""))


def _round6(x: Fraction) -> Decimal:
    return Decimal(round(x * 10**6)).scaleb(-6)  # round() on Fraction: exact half-even


def record_activity(
    conn: psycopg.Connection, *, facility_id: int, activity_type: str,
    period_start: date, period_end: date, quantity: Decimal, unit: str,
    document_id: int | None = None, actor: str | None = None,
    reason: str | None = None, supersedes: int | None = None,
    t: datetime | None = None,
) -> int:
    """Insert an activity. `period_end` is exclusive, like every DATERANGE here."""
    if activity_type not in ACTIVITY_TYPES:
        raise ValueError(f"unknown activity_type {activity_type!r}; "
                         f"known: {sorted(ACTIVITY_TYPES)}")
    if quantity < 0:
        raise ValueError("quantity must be >= 0")
    if period_end <= period_start:
        raise ValueError("period_end must be after period_start (it is exclusive)")
    if fy_of(period_start) != fy_of(period_end - timedelta(days=1)):
        raise ValueError("an activity period must lie within one financial year")
    with conn.transaction():
        set_audit_context(conn, actor, reason)
        t = t or _now(conn)
        row = conn.execute(
            "INSERT INTO activity (facility_id, activity_type, scope, period, quantity,"
            " unit, document_id, supersedes, system_time_range)"
            " VALUES (%s, %s, %s, daterange(%s, %s), %s, %s, %s, %s, tstzrange(%s, NULL))"
            " RETURNING activity_id",
            (facility_id, activity_type, ACTIVITY_TYPES[activity_type][0],
             period_start, period_end, quantity, unit, document_id, supersedes, t),
        ).fetchone()
    assert row is not None
    return int(row[0])


def calculate(
    conn: psycopg.Connection, activity_id: int, policy: Policy, *,
    baseline_year: str | None = None, t: datetime | None = None,
) -> Calculation:
    with conn.transaction():
        t = t or _now(conn)
        row = conn.execute(
            "SELECT activity_type, lower(period), quantity, unit"
            " FROM activity WHERE activity_id = %s AND upper_inf(system_time_range)",
            (activity_id,)).fetchone()
        if row is None:
            raise LookupError(f"activity {activity_id} does not exist or was superseded")
        activity_type, start, quantity, unit = row
        _, factor_key, geography = ACTIVITY_TYPES[activity_type]

        factor = resolve(conn, factor_key, fy_of(start), t, policy,
                         geography=geography, baseline_year=baseline_year)
        factor_unit = f"{factor.numerator_unit}/{factor.denominator_unit}"
        program = (
            f"let activity  : [{unit}] = {quantity:f} [{unit}]\n"
            f"let factor    : [{factor_unit}] = {factor.value:f} [{factor_unit}]"
            f"  # {factor.factor_key} {factor.version_label}\n"
            f"let emissions : [tCO2e] = activity * factor\n"
        )
        exact = run(program)["emissions"].value  # type-checked, then evaluated
        tco2e = _round6(exact)

        (policy_id,) = conn.execute(
            "SELECT policy_id FROM resolution_policy WHERE code = %s",
            (policy.value,)).fetchone() or (None,)
        if policy_id is None:
            raise LookupError(f"policy {policy} not seeded; run scripts/seed_policies.py")
        calc_row = conn.execute(
            "INSERT INTO calculation (activity_id, factor_id, policy_id, engine_version,"
            " result_value, result_unit, program, system_time_range)"
            " VALUES (%s, %s, %s, %s, %s, 'tCO2e', %s, tstzrange(%s, NULL))"
            " RETURNING calculation_id",
            (activity_id, factor.factor_id, policy_id, ENGINE_VERSION, tco2e, program, t),
        ).fetchone()
        assert calc_row is not None
        conn.execute(
            "INSERT INTO ledger_entry (calculation_id, facility_id, scope, period, tco2e,"
            " system_time_range)"
            " SELECT %s, facility_id, scope, period, %s, tstzrange(%s, NULL)"
            " FROM activity WHERE activity_id = %s",
            (calc_row[0], tco2e, t, activity_id))
    return Calculation(int(calc_row[0]), activity_id, tco2e, exact, factor, policy, program)


def edit_activity(
    conn: psycopg.Connection, activity_id: int, *, quantity: Decimal, reason: str,
    actor: str | None = None, baseline_year: str | None = None,
) -> tuple[int, list[Calculation]]:
    """Correct an activity's quantity. Returns the new activity_id and its
    recalculations (one per policy the old activity was calculated under).

    The old activity, calculations and ledger entries are closed, never
    changed: they stay retrievable AS OF any earlier time.
    """
    if not reason.strip():
        raise ValueError("a correction needs a reason; it goes in the audit trail")
    with conn.transaction():
        set_audit_context(conn, actor, reason)
        t = _now(conn)
        old = conn.execute(
            "SELECT facility_id, activity_type, lower(period), upper(period), unit,"
            " document_id FROM activity"
            " WHERE activity_id = %s AND upper_inf(system_time_range) FOR UPDATE",
            (activity_id,)).fetchone()
        if old is None:
            raise LookupError(f"activity {activity_id} does not exist or was superseded")
        policies = [Policy(code) for (code,) in conn.execute(
            "SELECT p.code FROM calculation c JOIN resolution_policy p USING (policy_id)"
            " WHERE c.activity_id = %s AND upper_inf(c.system_time_range)"
            " ORDER BY p.code", (activity_id,)).fetchall()]
        close = "SET system_time_range = tstzrange(lower(system_time_range), %s)"
        conn.execute(f"UPDATE ledger_entry {close} WHERE upper_inf(system_time_range)"
                     " AND calculation_id IN (SELECT calculation_id FROM calculation"
                     " WHERE activity_id = %s)", (t, activity_id))
        conn.execute(f"UPDATE calculation {close} WHERE activity_id = %s"
                     " AND upper_inf(system_time_range)", (t, activity_id))
        conn.execute(f"UPDATE activity {close} WHERE activity_id = %s", (t, activity_id))

        facility_id, activity_type, start, end, unit, document_id = old
        new_id = record_activity(
            conn, facility_id=facility_id, activity_type=activity_type,
            period_start=start, period_end=end, quantity=quantity, unit=unit,
            document_id=document_id, actor=actor, reason=reason,
            supersedes=activity_id, t=t)
        calcs = [calculate(conn, new_id, p, baseline_year=baseline_year, t=t)
                 for p in policies]
    return new_id, calcs


def main() -> None:
    ap = argparse.ArgumentParser(description="Calculate every uncalculated current "
                                 "activity of an organisation under one policy.")
    ap.add_argument("--org", type=int, required=True)
    ap.add_argument("--policy", type=Policy, default=Policy.VINTAGE_MATCHED)
    ap.add_argument("--baseline-year")
    args = ap.parse_args()
    url = os.environ.get(
        "DATABASE_URL", "postgresql://carbonx:carbonx@localhost:5432/carbonx"
    ).replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(url) as conn:
        set_audit_context(conn, "carbonx.engine.calculate", None)
        pending = conn.execute(
            "SELECT a.activity_id FROM activity a JOIN facility f USING (facility_id)"
            " WHERE f.org_id = %s AND upper_inf(a.system_time_range)"
            " AND NOT EXISTS (SELECT 1 FROM calculation c JOIN resolution_policy p"
            "   USING (policy_id) WHERE c.activity_id = a.activity_id"
            "   AND p.code = %s AND upper_inf(c.system_time_range))"
            " ORDER BY a.activity_id", (args.org, args.policy.value)).fetchall()
        for (activity_id,) in pending:
            c = calculate(conn, activity_id, args.policy, baseline_year=args.baseline_year)
            print(f"activity {activity_id}: {c.tco2e} tCO2e  (factor {c.factor.value} "
                  f"{c.factor.numerator_unit}/{c.factor.denominator_unit}, CEA "
                  f"{c.factor.version_label} {c.factor.valid_from:%Y}, {args.policy})")
        print(f"{len(pending)} activities calculated under {args.policy}")


if __name__ == "__main__":
    main()
