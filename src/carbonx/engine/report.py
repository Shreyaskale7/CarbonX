"""Reproducible compliance reports (invariant 1).

A report is canonical JSON computed AS OF a transaction time T, hashed with
SHA-256 and stored immutably. regenerate(report_id) recomputes it AS OF the
same T and must produce the identical bytes, whatever has happened since:
factor supersessions, late-published versions, backdated corrections, new
activities for old periods, renamed facilities.

It recomputes from activities and factors known at T, rather than summing
stored calculation rows, so it does not depend on when calculations happened
to be run, and one dataset can be reported under every resolution policy.

Why it reproduces:
  * every read is AS OF T: rows whose system time began after T are invisible,
    and closing a row later does not hide it (factors/registry.py);
  * T is chosen under the global write lock (migration 0003), so every row
    stamped before T was committed before the report read;
  * the output holds ids, never mutable names; the tables it does read are
    immutable or bitemporal;
  * all arithmetic is exact (units/core.py); decimals appear only in the
    canonical rendering, rounded half-even to 6 places;
  * JSON is canonical: sorted keys, no whitespace, numbers as strings, lines
    in a total order;
  * the engine version is recorded, and regenerate() refuses to run under a
    different one rather than silently produce different bytes.

Must run under READ COMMITTED (the default): the reads after the lock need
fresh snapshots.

    python -m carbonx.engine.report --org 1 --fy FY2025-26 --verify
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction
from typing import Any

import psycopg

from carbonx import db
from carbonx.engine.calculate import (
    ACTIVITY_TYPES,
    ENGINE_VERSION,
    emissions,
    fy_of,
    round6,
)
from carbonx.factors.registry import FactorNotFound, Policy, fy_start, resolve
from carbonx.units.core import Quantity, parse_unit

SCHEMA = "carbonx.report/2"  # /2: per-facility production and GEI


class EngineVersionMismatch(RuntimeError):
    """The report was produced by different code; regenerating it would not be
    a reproduction. Check out that version instead."""


@dataclass(frozen=True)
class Report:
    report_id: int
    output: str
    sha256: str


def _num(x: Fraction) -> str:
    return format(round6(x), "f")


def build(conn: psycopg.Connection, org_id: int, compliance_year: str,
          policy: Policy, as_of: datetime, baseline_year: str | None = None) -> str:
    """The canonical JSON for one report. Pure function of (args, DB AS OF as_of)."""
    start = fy_start(compliance_year)
    end = date(start.year + 1, 4, 1)
    activities = conn.execute("""
        SELECT a.activity_id, a.facility_id, a.activity_type, a.scope,
               lower(a.period), upper(a.period), a.quantity, a.unit, d.sha256
        FROM activity a
        JOIN facility f USING (facility_id)
        LEFT JOIN source_document d USING (document_id)
        WHERE f.org_id = %s
          AND a.system_time_range @> %s::timestamptz
          AND a.period <@ daterange(%s, %s)
        ORDER BY a.facility_id, lower(a.period), a.activity_type, a.activity_id""",
        (org_id, as_of, start, end)).fetchall()

    lines, unresolved = [], []
    totals: dict[int, Fraction] = {1: Fraction(0), 2: Fraction(0)}
    by_facility: dict[int, Fraction] = {}
    for (activity_id, facility_id, activity_type, scope, p_start, p_end,
         quantity, unit, doc_sha) in activities:
        _, factor_key, geography = ACTIVITY_TYPES[activity_type]
        line: dict[str, Any] = {
            "activity_id": activity_id, "facility_id": facility_id,
            "activity_type": activity_type, "scope": scope,
            "period": [p_start.isoformat(), p_end.isoformat()],
            "quantity": format(quantity, "f"), "unit": unit,
            "document_sha256": doc_sha,
        }
        try:
            factor = resolve(conn, factor_key, fy_of(p_start), as_of, policy,
                             geography=geography, baseline_year=baseline_year)
        except FactorNotFound:
            unresolved.append(line | {"reason": f"no {factor_key} factor under {policy}"})
            continue
        _, exact = emissions(quantity, unit, factor)
        totals[scope] += exact
        by_facility[facility_id] = by_facility.get(facility_id, Fraction(0)) + exact
        lines.append(line | {
            "factor": {
                "factor_id": factor.factor_id, "factor_key": factor.factor_key,
                "geography": factor.geography, "value": format(factor.value, "f"),
                "unit": f"{factor.numerator_unit}/{factor.denominator_unit}",
                "valid_from": factor.valid_from.isoformat(),
                "source_version": factor.version_label,
            },
            "tco2e": _num(exact),
        })

    production = conn.execute("""
        SELECT pb.facility_id, pb.product_code, pr.unit, pr.production_id,
               pr.quantity, lower(pr.period), upper(pr.period), d.sha256
        FROM production_record pr
        JOIN production_basis pb USING (basis_id)
        JOIN facility f ON f.facility_id = pb.facility_id
        LEFT JOIN source_document d ON d.document_id = pr.document_id
        WHERE f.org_id = %s
          AND pr.system_time_range @> %s::timestamptz
          AND pb.system_time_range @> %s::timestamptz
          AND pr.period <@ daterange(%s, %s)
        ORDER BY pb.facility_id, pb.product_code, lower(pr.period), pr.production_id""",
        (org_id, as_of, as_of, start, end)).fetchall()

    records = [{"production_id": pid, "facility_id": fid, "product_code": code,
                "period": [p_s.isoformat(), p_e.isoformat()],
                "quantity": format(qty, "f"), "unit": unit, "document_sha256": sha}
               for fid, code, unit, pid, qty, p_s, p_e, sha in production]
    unresolved_at = {line["facility_id"] for line in unresolved}
    facility_ids = sorted({line["facility_id"] for line in lines + unresolved}
                          | {r["facility_id"] for r in records})
    facilities = [_facility_gei(fid, by_facility.get(fid, Fraction(0)),
                                [r for r in records if r["facility_id"] == fid],
                                fid in unresolved_at)
                  for fid in facility_ids]

    return json.dumps({
        "schema": SCHEMA,
        "org_id": org_id,
        "compliance_year": compliance_year,
        "policy": policy.value,
        "baseline_year": baseline_year,
        "as_of": as_of.astimezone(UTC).isoformat(),
        "engine_version": ENGINE_VERSION,
        "lines": lines,
        "unresolved": unresolved,
        # Totals are the exact sum, rounded once, not a sum of rounded lines.
        "totals": {"scope1_tco2e": _num(totals[1]), "scope2_tco2e": _num(totals[2]),
                   "total_tco2e": _num(totals[1] + totals[2])},
        "production_records": records,
        # GEI is per facility (gate-to-gate). The top level repeats it only
        # when the report covers exactly one facility.
        "facilities": facilities,
        "gei": facilities[0]["gei"] if len(facilities) == 1 else None,
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _facility_gei(facility_id: int, tco2e: Fraction, records: list[dict[str, Any]],
                  has_unresolved: bool) -> dict[str, Any]:
    """GEI = emissions / production for one facility, or null with the reason.

    Null rather than a wrong number: an unresolved emission line would
    understate the numerator; several products need an equivalent-product
    conversion that is not implemented.
    """
    out: dict[str, Any] = {"facility_id": facility_id, "tco2e": _num(tco2e),
                           "production": None, "gei": None, "gei_unit": None,
                           "gei_withheld_because": None}
    products = sorted({(r["product_code"], r["unit"]) for r in records})
    if not products:
        out["gei_withheld_because"] = "no production recorded"
        return out
    if len(products) > 1:
        out["gei_withheld_because"] = ("more than one product or unit: equivalent-product "
                                       "conversion is not implemented")
        return out
    (code, unit), = products
    quantity = sum((Fraction(r["quantity"]) for r in records), Fraction(0))
    out["production"] = {"product_code": code, "quantity": _num(quantity), "unit": unit}
    if has_unresolved:
        out["gei_withheld_because"] = "some emission lines are unresolved under this policy"
    elif quantity == 0:
        out["gei_withheld_because"] = "zero production"
    else:
        gei_unit = parse_unit(f"tCO2e/{unit}")
        gei = (Quantity(tco2e, parse_unit("tCO2e")) / Quantity(quantity, parse_unit(unit))
               ).to(gei_unit)  # dimension-checked: DimensionError, not a wrong number
        out["gei"] = format(Decimal(round(gei.value * 10**9)).scaleb(-9), "f")
        out["gei_unit"] = gei_unit.name
    return out


def _sha(output: str) -> str:
    return hashlib.sha256(output.encode("utf-8")).hexdigest()


def generate_report(conn: psycopg.Connection, org_id: int, compliance_year: str,
                    policy: Policy, baseline_year: str | None = None) -> Report:
    with conn.transaction():
        row = conn.execute("SELECT fn_system_now()").fetchone()  # takes the lock
        assert row is not None
        as_of: datetime = row[0]
        output = build(conn, org_id, compliance_year, policy, as_of, baseline_year)
        parsed = json.loads(output)
        single = parsed["facilities"][0] if len(parsed["facilities"]) == 1 else None
        production_qty = (single["production"] or {}).get("quantity") if single else None
        rid = conn.execute(
            "INSERT INTO report (org_id, compliance_year, policy_id, as_of, total_tco2e,"
            " production_qty, gei, output_sha256, baseline_year, engine_version, output)"
            " SELECT %s, %s, policy_id, %s, %s, %s, %s, %s, %s, %s, %s"
            " FROM resolution_policy WHERE code = %s RETURNING report_id",
            (org_id, compliance_year, as_of, parsed["totals"]["total_tco2e"],
             production_qty, parsed["gei"], _sha(output), baseline_year,
             ENGINE_VERSION, output, policy.value)).fetchone()
        if rid is None:
            raise LookupError(f"policy {policy} not seeded; run scripts/seed_policies.py")
    return Report(int(rid[0]), output, _sha(output))


def regenerate(conn: psycopg.Connection, report_id: int) -> Report:
    """Recompute a stored report AS OF its own time. Does not store anything."""
    row = conn.execute(
        "SELECT r.org_id, r.compliance_year, p.code, r.as_of, r.baseline_year,"
        " r.engine_version FROM report r JOIN resolution_policy p USING (policy_id)"
        " WHERE r.report_id = %s", (report_id,)).fetchone()
    if row is None:
        raise LookupError(f"no report {report_id}")
    org_id, fy, code, as_of, baseline_year, engine_version = row
    if engine_version != ENGINE_VERSION:
        raise EngineVersionMismatch(
            f"report {report_id} was produced by engine {engine_version}; this is "
            f"{ENGINE_VERSION}. Regenerate it with that version.")
    output = build(conn, org_id, fy, Policy(code), as_of, baseline_year)
    return Report(report_id, output, _sha(output))


def verify(conn: psycopg.Connection, report_id: int) -> bool:
    stored = conn.execute("SELECT output_sha256 FROM report WHERE report_id = %s",
                          (report_id,)).fetchone()
    if stored is None:
        raise LookupError(f"no report {report_id}")
    return bool(regenerate(conn, report_id).sha256 == stored[0])


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate a report under every policy "
                                 "and optionally verify each reproduces.")
    ap.add_argument("--org", type=int, required=True)
    ap.add_argument("--fy", required=True)
    ap.add_argument("--baseline-year", help="needed for BASELINE_FROZEN; skipped without")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    url = db.url()
    with psycopg.connect(url) as conn:
        conn.execute("SELECT set_config('carbonx.actor', 'carbonx.engine.report', false)")
        failures = 0
        for policy in Policy:
            if policy is Policy.BASELINE_FROZEN and not args.baseline_year:
                continue
            r = generate_report(conn, args.org, args.fy, policy, args.baseline_year)
            conn.commit()
            out = json.loads(r.output)
            note = f", {len(out['unresolved'])} unresolved" if out["unresolved"] else ""
            ok = ""
            if args.verify:
                good = verify(conn, r.report_id)
                failures += not good
                ok = "  reproduces" if good else "  DOES NOT REPRODUCE"
            gei = f"GEI {out['gei']} {out['facilities'][0]['gei_unit']}" if out["gei"] else ""
            print(f"report {r.report_id} {policy.value:17} "
                  f"{out['totals']['total_tco2e']:>16} tCO2e  {gei}{note}  "
                  f"sha256 {r.sha256[:16]}{ok}")
    if failures:
        raise SystemExit(f"{failures} report(s) failed to reproduce")


if __name__ == "__main__":
    main()
