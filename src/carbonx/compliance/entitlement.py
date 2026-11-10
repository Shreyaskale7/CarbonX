"""Entitlement under BEE's compliance procedure, from a stored report and a cited target.

BEE (pp. 4 and 22): the entitlement is
    (specific GHG emission notified for the cycle - specific GHG emission achieved) x production.
Positive: the entity exceeded its target and is entitled to certificates. Negative: it fell short and
must purchase them.

What this does not do. The BEE file does not say what one certificate equals or how a fraction is
rounded, so no certificate count is given: the result is the signed tCO2e-equivalent, unrounded to a
whole number. The target is an input that must carry its source; a target we have not seen in a
primary source is 'assumed' and the result says so. Whether the entity's achieved intensity covers
process emissions is not settled here (docs/RQ3_FINDINGS.md): the result repeats the report's own
boundary and decides nothing about it. This is decision support for an accredited verifier, not an
assurance opinion, and it is not Form B.

Reproducibility: targets are read AS OF the report's own time, so an entitlement recomputed later
from the same report gives the same bytes, whatever targets are superseded afterwards.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from fractions import Fraction
from typing import Any

import psycopg

from carbonx.engine.calculate import round6, set_audit_context, system_now
from carbonx.factors.registry import fy_start

STATUSES = {"notified", "assumed"}


def set_target(conn: psycopg.Connection, *, facility_id: int, fy: str, value: Decimal,
               unit: str, status: str, source_citation: str, source_url: str | None = None,
               baseline_fy: str | None = None, actor: str | None = None,
               reason: str | None = None) -> int:
    """Record the target for one facility and financial year. A new one supersedes the current
    one; an entitlement computed earlier keeps the target it read."""
    if status not in STATUSES:
        raise ValueError(f"status must be one of {sorted(STATUSES)}")
    if not source_citation.strip():
        raise ValueError("state where the target comes from (notification, page); a verifier must "
                         "be able to check it")
    if not unit.startswith("tCO2e/") or len(unit) == len("tCO2e/"):
        raise ValueError("a target is tCO2e per unit of product, e.g. 'tCO2e/t'")
    if value < 0:
        raise ValueError("a target cannot be negative")
    start = fy_start(fy)
    with conn.transaction():
        set_audit_context(conn, actor, reason or source_citation)
        t = system_now(conn)
        old = conn.execute(
            "SELECT target_id FROM intensity_target WHERE facility_id = %s"
            " AND valid_time @> %s::date AND upper_inf(system_time_range) FOR UPDATE",
            (facility_id, start)).fetchone()
        if old:
            conn.execute("UPDATE intensity_target SET system_time_range ="
                         " tstzrange(lower(system_time_range), %s) WHERE target_id = %s",
                         (t, old[0]))
        row = conn.execute(
            "INSERT INTO intensity_target (facility_id, valid_time, value, unit, status,"
            " source_citation, source_url, baseline_fy, supersedes, system_time_range)"
            " VALUES (%s, daterange(%s, %s), %s, %s, %s, %s, %s, %s, %s, tstzrange(%s, NULL))"
            " RETURNING target_id",
            (facility_id, start, date(start.year + 1, 4, 1), value, unit, status,
             source_citation.strip(), source_url, baseline_fy, old[0] if old else None,
             t)).fetchone()
    assert row is not None
    return int(row[0])


def targets_as_of(conn: psycopg.Connection, org_id: int, fy: str,
                  as_of: datetime) -> dict[int, dict[str, Any]]:
    """The targets known at `as_of` for every facility of an organisation, keyed by facility."""
    rows = conn.execute(
        "SELECT t.facility_id, t.target_id, t.value, t.unit, t.status, t.source_citation,"
        " t.source_url, t.baseline_fy FROM intensity_target t"
        " JOIN facility f USING (facility_id)"
        " WHERE f.org_id = %s AND t.valid_time @> %s::date"
        " AND t.system_time_range @> %s::timestamptz", (org_id, fy_start(fy), as_of)).fetchall()
    return {fid: {"target_id": tid, "value": format(value, "f"), "unit": unit, "status": status,
                  "source_citation": cite, "source_url": url, "baseline_fy": base}
            for fid, tid, value, unit, status, cite, url, base in rows}


def entitlement_for_facility(facility: dict[str, Any],
                             target: dict[str, Any] | None) -> dict[str, Any]:
    """One facility's entitlement from its entry in a report and its target, or null with the
    reason. Pure: no database, no clock."""
    out: dict[str, Any] = {
        "facility_id": facility["facility_id"], "outcome": None,
        "entitlement_tco2e_equivalent": None, "withheld_because": None,
        "target": target, "achieved": None, "production": None,
        "note": ("Signed tCO2e-equivalent. BEE's file does not say what one certificate equals "
                 "or how a fraction rounds, so no certificate count is given."),
    }
    if facility["gei"] is None:
        out["withheld_because"] = ("no achieved intensity: " + (facility["gei_withheld_because"]
                                                                or "not computed"))
        return out
    out["achieved"] = {"value": facility["gei"], "unit": facility["gei_unit"]}
    out["production"] = facility["production"]
    if target is None:
        out["withheld_because"] = "no target recorded for this facility and year"
        return out
    if target["unit"] != facility["gei_unit"]:
        out["withheld_because"] = (f"target is in {target['unit']} but the achieved intensity is "
                                   f"in {facility['gei_unit']}; they are not comparable")
        return out
    delta = ((Fraction(target["value"]) - Fraction(facility["gei"]))
             * Fraction(facility["production"]["quantity"]))
    out["entitlement_tco2e_equivalent"] = format(round6(delta), "f")
    out["outcome"] = ("surplus: entitled to certificates" if delta > 0
                      else "shortfall: must purchase certificates" if delta < 0
                      else "on target")
    if target["status"] != "notified":
        out["note"] += (" The target is 'assumed', not read from a notification: do not rely on "
                        "this figure until it is replaced by the notified one.")
    return out


def entitlements(report_output: str, targets: dict[int, dict[str, Any]]) -> str:
    """Canonical JSON: one entry per facility in the report."""
    report = json.loads(report_output)
    return json.dumps({
        "schema": "carbonx.entitlement/1", "org_id": report["org_id"],
        "compliance_year": report["compliance_year"], "policy": report["policy"],
        "report_as_of": report["as_of"],
        "facilities": [entitlement_for_facility(f, targets.get(f["facility_id"]))
                       for f in report["facilities"]],
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def for_report(conn: psycopg.Connection, report_id: int) -> str:
    """Entitlement from a stored report, with targets read AS OF the report's own time."""
    row = conn.execute("SELECT org_id, compliance_year, as_of, output FROM report"
                       " WHERE report_id = %s", (report_id,)).fetchone()
    if row is None:
        raise LookupError(f"no report {report_id}")
    org_id, fy, as_of, output = row
    return entitlements(output, targets_as_of(conn, org_id, fy, as_of))
