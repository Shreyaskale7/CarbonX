"""Entitlement under BEE's compliance procedure, from a stored report and a cited target.

BEE (pp. 4 and 22): the entitlement is
    (specific GHG emission notified for the cycle - specific GHG emission achieved) x production.
Positive: the entity exceeded its target and is entitled to certificates. Negative: it fell short and
must purchase them.

What this does not do. The BEE file does not say what one certificate equals or how a fraction is
rounded, so no certificate count is given: the result is the signed tCO2e-equivalent, unrounded to a
whole number. The target is an input that must carry its source; a target we have not seen in a
primary source is 'assumed' and the result says so. Only activities tagged inside the gate-to-gate
boundary count, and an untagged or unresolved line withholds the result (compliance/figures.py, shared
with the Form I draft, so the two agree). Process emissions are not recorded by CarbonX; whether targets
cover them is open (docs/RQ3_FINDINGS.md) and nothing here decides it. This is decision support for an accredited verifier, not an
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

from carbonx.compliance.baseline import baselines_as_of
from carbonx.compliance.boundary import tags_as_of
from carbonx.compliance.figures import Figures, figures
from carbonx.engine.calculate import round6, set_audit_context, system_now
from carbonx.factors.registry import fy_start
from carbonx.units.core import parse_unit

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
    if status == "notified" and not (source_url or "").strip():
        raise ValueError("a 'notified' target needs the url of the notification it was read in; "
                         "without one, record it as 'assumed'")
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


def _exact9(x: Fraction) -> str:
    return format(Decimal(round(x * 10**9)).scaleb(-9), "f")


def entitlement_for_facility(facility_id: int, fig: Figures, target: dict[str, Any] | None,
                             baseline: dict[str, Any] | None = None,
                             no_production_because: str | None = None) -> dict[str, Any]:
    """One facility's entitlement from its exact gate-to-gate figures, its target and (optionally)
    its baseline, or null with the reason. Pure: no database, no clock.

    Computed as target x production - emissions, which is BEE's (target - achieved) x production
    without dividing first, in exact fractions, rounded once when printed."""
    out: dict[str, Any] = {
        "facility_id": facility_id, "outcome": None,
        "entitlement_tco2e_equivalent": None, "withheld_because": None,
        "target": target, "baseline": baseline, "achieved": None, "production": None,
        "reduction_vs_baseline_pct": None, "baseline_notes": [],
        "boundary": {"inside": fig.inside, "outside": fig.outside_count,
                     "untagged": fig.untagged, "unresolved": fig.unresolved},
        "note": ("Signed tCO2e-equivalent, from activities tagged inside the gate-to-gate boundary "
                 "only, under the factor policy of this report: a report under another policy gives "
                 "another figure. BEE's file does not say what one certificate equals or how a "
                 "fraction rounds, so no certificate count is given."),
    }
    if not fig.complete:
        out["withheld_because"] = fig.incomplete_because
        return out
    if fig.production is None or fig.production == 0:
        out["withheld_because"] = "no achieved intensity: " + (no_production_because
                                                               or "no production")
        return out
    unit = parse_unit(f"tCO2e/{fig.production_unit}").name
    achieved = fig.emissions / fig.production
    out["achieved"] = {"value": _exact9(achieved), "unit": unit}
    out["production"] = {"quantity": format(round6(fig.production), "f"),
                         "unit": fig.production_unit}
    if target is None:
        out["withheld_because"] = "no target recorded for this facility and year"
        return out
    if target["unit"] != unit:
        out["withheld_because"] = (f"target is in {target['unit']} but the achieved intensity is "
                                   f"in {unit}; they are not comparable")
        return out
    _baseline_view(out, achieved, unit, target, baseline)
    delta = Fraction(target["value"]) * fig.production - fig.emissions
    out["entitlement_tco2e_equivalent"] = format(round6(delta), "f")
    out["outcome"] = ("surplus: entitled to certificates" if delta > 0
                      else "shortfall: must purchase certificates" if delta < 0
                      else "on target")
    if target["status"] != "notified":
        out["note"] += (" The target is 'assumed', not read from a notification: do not rely on "
                        "this figure until it is replaced by the notified one.")
    return out


def _baseline_view(out: dict[str, Any], achieved: Fraction, unit: str, target: dict[str, Any],
                   baseline: dict[str, Any] | None) -> None:
    """Reduction achieved against the stated baseline, and what to doubt about it. Informational:
    the entitlement itself uses only target, emissions and production."""
    notes: list[str] = out["baseline_notes"]
    if baseline is None:
        notes.append("no baseline recorded: the reduction against the baseline year is not shown")
        return
    if baseline["status"] == "assumed":
        notes.append("the baseline is 'assumed', not read from a notification or a verified "
                     "submission")
    if target.get("baseline_fy") and target["baseline_fy"] != baseline["baseline_fy"]:
        notes.append(f"the target was derived from {target['baseline_fy']} but the baseline "
                     f"recorded is {baseline['baseline_fy']}")
    if baseline["unit"] != unit:
        notes.append(f"the baseline is in {baseline['unit']} but the achieved intensity is in "
                     f"{unit}; no reduction is shown")
        return
    base = Fraction(baseline["intensity"])
    if base == 0:
        notes.append("the baseline intensity is zero; no reduction is shown")
        return
    out["reduction_vs_baseline_pct"] = format(round6((base - achieved) / base * 100), "f")


def entitlements(report_output: str, targets: dict[int, dict[str, Any]],
                 baselines: dict[int, dict[str, Any]] | None = None,
                 tags: dict[int, dict[str, Any]] | None = None) -> str:
    """Canonical JSON: one entry per facility in the report."""
    baselines, tags = baselines or {}, tags or {}
    report = json.loads(report_output)
    return json.dumps({
        "schema": "carbonx.entitlement/3", "org_id": report["org_id"],
        "compliance_year": report["compliance_year"], "policy": report["policy"],
        "report_as_of": report["as_of"],
        "facilities": [entitlement_for_facility(
            f["facility_id"], figures(report, f, tags), targets.get(f["facility_id"]),
            baselines.get(f["facility_id"]), f["gei_withheld_because"])
            for f in report["facilities"]],
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def for_report(conn: psycopg.Connection, report_id: int) -> str:
    """Entitlement from a stored report, with targets, baselines and boundary tags read AS OF the
    report's own time."""
    row = conn.execute("SELECT org_id, compliance_year, as_of, output FROM report"
                       " WHERE report_id = %s", (report_id,)).fetchone()
    if row is None:
        raise LookupError(f"no report {report_id}")
    org_id, fy, as_of, output = row
    ids = [ln["activity_id"] for ln in json.loads(output)["lines"]]
    return entitlements(output, targets_as_of(conn, org_id, fy, as_of),
                        baselines_as_of(conn, org_id, as_of), tags_as_of(conn, ids, as_of))
