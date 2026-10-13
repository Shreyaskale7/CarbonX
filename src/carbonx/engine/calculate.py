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
import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from importlib.metadata import version
from pathlib import Path

import psycopg

from carbonx import db
from carbonx.factors.registry import EmissionFactor, Policy, resolve
from carbonx.units.core import parse_unit
from carbonx.units.lang import run

# Everything that decides a report's bytes. Hashing the source (not trusting a
# manually bumped version) means any edit makes regenerate() refuse old reports
# instead of silently producing different output.
_ENGINE_SOURCES = ["units/core.py", "units/lang.py", "factors/registry.py",
                   "engine/calculate.py", "engine/report.py"]


def _engine_version() -> str:
    root, h = Path(__file__).resolve().parents[1], hashlib.sha256()
    for rel in _ENGINE_SOURCES:
        # Normalise CRLF so a Windows checkout hashes like a Linux one.
        source = (root / rel).read_bytes().replace(bytes([13, 10]), bytes([10]))
        for part in (rel.encode(), source):  # length-prefixed: unambiguous
            h.update(len(part).to_bytes(8, "big") + part)
    return f"{version('carbonx')}+{h.hexdigest()[:12]}"


ENGINE_VERSION = _engine_version()

# activity_type -> (scope, factor_key, geography). Which CEA factor applies to
# Scope 2 electricity is a methodological choice, not a fact: this is the
# all-India weighted average incl. RE, captive and imports (the series behind
# the v19 = 0.716 checkpoint). Change it here, and nowhere else.
ACTIVITY_TYPES: dict[str, tuple[int, str, str]] = {
    "grid_electricity": (2, "grid.weighted_avg_incl_re_captive.incl_imports", "IN"),
}
_FUEL = re.compile(r"fuel\.([a-z0-9_]+)")


@dataclass(frozen=True)
class ActivitySpec:
    scope: int
    factor_key: str
    geography: str
    is_fuel: bool   # needs an NCV; its factor does not depend on the policy


def activity_spec(activity_type: str) -> ActivitySpec:
    """What an activity type means. Fuels are 'fuel.<slug>', with <slug> as in
    data/bee/fuel_factors.csv (BEE's Annexure IV), e.g. 'fuel.other_bituminous_coal'.

    Fuel combustion uses the CO2e factor (CO2 plus CH4 and N2O at Annexure I
    GWPs). That is our reading of the procedure; the CO2-only factor is in the
    registry as 'fuel.<slug>.co2'.
    """
    if activity_type in ACTIVITY_TYPES:
        return ActivitySpec(*ACTIVITY_TYPES[activity_type], is_fuel=False)
    if m := _FUEL.fullmatch(activity_type):
        return ActivitySpec(1, f"fuel.{m[1]}.co2e", "IN", is_fuel=True)
    raise ValueError(f"unknown activity_type {activity_type!r}; known: "
                     f"{sorted(ACTIVITY_TYPES)} and 'fuel.<slug>'")


def resolve_for(conn: psycopg.Connection, spec: ActivitySpec, fy: str, as_of: datetime,
                policy: Policy, baseline_year: str | None = None) -> EmissionFactor:
    """The factor for an activity. The resolution policy applies to grid
    factors only: it is about which CEA vintage to use. BEE's default fuel
    factors are not versioned by year ("the emission factor shall be
    consistently applied for baseline and assessment year"), so a fuel factor
    is simply the one valid for the activity's year, as known at as_of."""
    if spec.is_fuel:
        return resolve(conn, spec.factor_key, fy, as_of, Policy.VINTAGE_MATCHED,
                       geography=spec.geography)
    return resolve(conn, spec.factor_key, fy, as_of, policy,
                   geography=spec.geography, baseline_year=baseline_year)


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


def system_now(conn: psycopg.Connection) -> datetime:
    """Transaction time, taken under the global write lock (migration 0003)."""
    row = conn.execute("SELECT fn_system_now()").fetchone()
    assert row is not None
    return row[0]


def set_audit_context(conn: psycopg.Connection, actor: str | None, reason: str | None) -> None:
    """Read by fn_audit; transaction-local, so it cannot leak to a later write."""
    conn.execute("SELECT set_config('carbonx.actor', %s, true),"
                 " set_config('carbonx.reason', %s, true)", (actor or "", reason or ""))


def round6(x: Fraction) -> Decimal:
    """To NUMERIC(18,6). round() on a Fraction is exact, half-even."""
    return Decimal(round(x * 10**6)).scaleb(-6)


def emissions(quantity: Decimal, unit: str, factor: EmissionFactor,
              ncv: Decimal | None = None, ncv_unit: str | None = None,
              oxidation: Decimal = Decimal(1)) -> tuple[str, Fraction]:
    """The typed program for an activity, and its exact tCO2e result.

    Electricity:  activity x factor.
    Fuel (ncv given), BEE Annexure II eq. III-IV:
                  fuel x NCV x factor x oxidation factor.

    The program is type-checked before it is evaluated (units/lang.py): a wrong
    unit raises DimensionError here, before any number exists.
    """
    factor_unit = f"{factor.numerator_unit}/{factor.denominator_unit}"
    factor_line = (f"let factor    : [{factor_unit}] = {factor.value:f} [{factor_unit}]"
                   f"  # {factor.factor_key} {factor.version_label}\n")
    if ncv is None:
        program = (
            f"let activity  : [{unit}] = {quantity:f} [{unit}]\n"
            + factor_line +
            "let emissions : [tCO2e] = activity * factor\n"
        )
    else:
        program = (
            f"let fuel      : [{unit}] = {quantity:f} [{unit}]\n"
            f"let ncv       : [{ncv_unit}] = {ncv:f} [{ncv_unit}]\n"
            + factor_line +
            f"let oxidation : [1] = {oxidation:f}\n"
            "let emissions : [tCO2e] = fuel * ncv * factor * oxidation\n"
        )
    return program, run(program)["emissions"].value


def record_activity(
    conn: psycopg.Connection, *, facility_id: int, activity_type: str,
    period_start: date, period_end: date, quantity: Decimal, unit: str,
    document_id: int | None = None, actor: str | None = None,
    reason: str | None = None, supersedes: int | None = None,
    t: datetime | None = None, ncv: Decimal | None = None,
    ncv_unit: str | None = None, oxidation_factor: Decimal = Decimal(1),
    meter_id: int | None = None,
) -> int:
    """Insert an activity. `period_end` is exclusive, like every DATERANGE here.

    `meter_id` names the meter row the reading came from (migration 0013). It
    must belong to this facility and measure this activity type.

    A fuel activity ('fuel.<slug>') must carry its net calorific value, e.g.
    ncv=4000, ncv_unit='kcal/kg'.
    """
    spec = activity_spec(activity_type)
    if spec.is_fuel and (ncv is None or ncv_unit is None):
        raise ValueError("a fuel activity needs ncv and ncv_unit (net calorific value)")
    if not spec.is_fuel and (ncv is not None or ncv_unit is not None):
        raise ValueError(f"{activity_type} takes no ncv")
    if ncv is not None and ncv <= 0:
        raise ValueError("ncv must be > 0")
    if not 0 < oxidation_factor <= 1:
        raise ValueError("oxidation_factor must be in (0, 1]")
    for u in (unit, ncv_unit):
        if u is not None:
            parse_unit(u)   # unknown units fail here, not inside a calculation
    if quantity < 0:
        raise ValueError("quantity must be >= 0")
    if period_end <= period_start:
        raise ValueError("period_end must be after period_start (it is exclusive)")
    if fy_of(period_start) != fy_of(period_end - timedelta(days=1)):
        raise ValueError("an activity period must lie within one financial year")
    with conn.transaction():
        set_audit_context(conn, actor, reason)
        t = t or system_now(conn)
        if meter_id is not None:
            meter = conn.execute("SELECT facility_id, measures, meter_code FROM meter"
                                 " WHERE meter_id = %s", (meter_id,)).fetchone()
            if meter is None:
                raise LookupError(f"no meter {meter_id}")
            if (meter[0], meter[1]) != (facility_id, activity_type):
                raise ValueError(f"meter {meter[2]} measures {meter[1]} at facility "
                                 f"{meter[0]}; it cannot be the source of this reading")
        row = conn.execute(
            "INSERT INTO activity (facility_id, activity_type, scope, period, quantity,"
            " unit, document_id, supersedes, ncv, ncv_unit, oxidation_factor, meter_id,"
            " system_time_range)"
            " VALUES (%s, %s, %s, daterange(%s, %s), %s, %s, %s, %s, %s, %s, %s, %s,"
            " tstzrange(%s, NULL)) RETURNING activity_id",
            (facility_id, activity_type, spec.scope, period_start, period_end, quantity,
             unit, document_id, supersedes, ncv, ncv_unit, oxidation_factor, meter_id, t),
        ).fetchone()
    assert row is not None
    return int(row[0])


def calculate(
    conn: psycopg.Connection, activity_id: int, policy: Policy, *,
    baseline_year: str | None = None, t: datetime | None = None,
) -> Calculation:
    with conn.transaction():
        t = t or system_now(conn)
        row = conn.execute(
            "SELECT activity_type, lower(period), quantity, unit, ncv, ncv_unit,"
            " oxidation_factor"
            " FROM activity WHERE activity_id = %s AND upper_inf(system_time_range)",
            (activity_id,)).fetchone()
        if row is None:
            raise LookupError(f"activity {activity_id} does not exist or was superseded")
        activity_type, start, quantity, unit, ncv, ncv_unit, oxidation = row
        factor = resolve_for(conn, activity_spec(activity_type), fy_of(start), t,
                             policy, baseline_year)
        program, exact = emissions(quantity, unit, factor, ncv, ncv_unit, oxidation)
        tco2e = round6(exact)

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
    ncv: Decimal | None = None,
) -> tuple[int, list[Calculation]]:
    """Correct an activity's quantity (and, for a fuel, optionally its NCV).
    Returns the new activity_id and its recalculations (one per policy the old
    activity was calculated under).

    The old activity, calculations and ledger entries are closed, never
    changed: they stay retrievable AS OF any earlier time.
    """
    if not reason.strip():
        raise ValueError("a correction needs a reason; it goes in the audit trail")
    with conn.transaction():
        set_audit_context(conn, actor, reason)
        t = system_now(conn)
        old = conn.execute(
            "SELECT facility_id, activity_type, lower(period), upper(period), unit,"
            " document_id, ncv, ncv_unit, oxidation_factor, meter_id FROM activity"
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

        (facility_id, activity_type, start, end, unit, document_id, old_ncv, ncv_unit,
         oxidation, meter_id) = old   # a correction is still a reading of the same meter
        new_id = record_activity(
            conn, facility_id=facility_id, activity_type=activity_type,
            period_start=start, period_end=end, quantity=quantity, unit=unit,
            document_id=document_id, actor=actor, reason=reason,
            supersedes=activity_id, t=t, ncv=old_ncv if ncv is None else ncv,
            ncv_unit=ncv_unit, oxidation_factor=oxidation, meter_id=meter_id)
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
    url = db.url()
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
                  f"{c.factor.numerator_unit}/{c.factor.denominator_unit}, "
                  f"{c.factor.factor_key} {c.factor.version_label}, {args.policy})")
        print(f"{len(pending)} activities calculated under {args.policy}")


if __name__ == "__main__":
    main()
