"""A draft of BEE's Form I (Annexure V, pp. 36-37, section 5.1) from a stored report.

Form I is the entity's own annual submission. This fills the rows CarbonX actually computes and says,
row by row, which it does not. It is a worksheet for the entity and its verifier, not a filing, and
nothing here is signed, sealed or certified.

What it fills: production, electricity purchased, direct and indirect energy-related emissions, and
specific emissions, counting only activities tagged inside the gate-to-gate boundary (migration 0017).
What it refuses to claim:
  * Total direct and indirect (row xiv) includes process emissions. CarbonX has no process-emission
    activity type, so row xiii is null and row xiv is not given, only a subtotal that excludes process.
    BEE p. 7 says 2024-27 targets count only combustion and purchased electricity, and the notified
    rules are reported to say otherwise (docs/RQ3_FINDINGS.md): which applies is open, so this decides
    nothing about it.
  * An untagged or unresolved line makes the figures incomplete, and specific emissions is withheld.
  * Fuel energy rows (million kcal), exported or generated electricity, TOE and the general details are
    not held, and are listed as not provided.
Figures come from compliance/figures.py, shared with the entitlement so the two agree: each line is
recomputed exactly from the inputs the report pinned, and rounded once when printed.

Tags are read AS OF the report's own time, so a Form I regenerated later is byte-identical.
"""

from __future__ import annotations

import json
from fractions import Fraction
from typing import Any

import psycopg

from carbonx.compliance.boundary import tags_as_of
from carbonx.compliance.figures import figures
from carbonx.engine.calculate import round6
from carbonx.units.core import parse_unit

SCHEMA = "carbonx.form_i/2"
NOT_PROVIDED = {
    "general_details": "name, registration number, address and energy manager are not held",
    "5.1(b)(ii) electricity generated": "not recorded",
    "5.1(b)(iii) electricity exported": "not recorded",
    "5.1(b)(v)-(viii) solid, liquid, gaseous and total thermal energy (million kcal)":
        "CarbonX prices fuel by NCV but does not total energy by fuel class",
    "5.1(b)(ix)-(x) total and normalised energy (TOE)": "not computed",
    "5.1(c)(i)-(ii) specific energy consumption (TOE/tonne)": "not computed",
    "5.2 thermal power stations and 5.3 refineries": "other sections of the form; not covered",
}


def _num(x: Fraction) -> str:
    return format(round6(x), "f")


def _facility(report: dict[str, Any], facility: dict[str, Any],
              tags: dict[int, dict[str, Any]]) -> dict[str, Any]:
    fig = figures(report, facility, tags)
    specific, why = None, fig.incomplete_because
    if why is None and (fig.production is None or fig.production == 0):
        why = facility["gei_withheld_because"] or "no production"
    elif why is None:
        assert fig.production is not None
        specific = {"value": _num(fig.emissions / fig.production),
                    "unit": parse_unit(f"tCO2e/{fig.production_unit}").name}
    return {
        "facility_id": facility["facility_id"],
        "complete": fig.complete,
        "production": facility["production"],
        "5.1(b)(i) electricity purchased (million kWh)": _num(fig.purchased_kwh / 10**6),
        "5.1(b)(xi) direct GHG, energy related (tCO2e)": _num(fig.direct),
        "5.1(b)(xii) indirect GHG, energy related (tCO2e)": _num(fig.indirect),
        "5.1(b)(xiii) direct GHG, process related (tCO2e)": None,
        "5.1(b)(xiv) total direct and indirect (tCO2e)": None,
        "subtotal_excluding_process_tco2e": _num(fig.emissions),
        "5.1(c)(iii) specific GHG emissions": specific,
        "specific_withheld_because": why,
        "process_note": ("process-related emissions are not recorded by CarbonX, so row xiii is "
                         "empty and row xiv is not given; the subtotal above excludes them"),
        "boundary": {"inside": fig.inside, "outside": fig.outside_count, "untagged": fig.untagged,
                     "unresolved": fig.unresolved, "outside_tco2e": _num(fig.outside)},
    }


def form_i(report_output: str, tags: dict[int, dict[str, Any]]) -> str:
    """Canonical JSON: one worksheet per facility in the report. Pure."""
    report = json.loads(report_output)
    return json.dumps({
        "schema": SCHEMA, "org_id": report["org_id"], "compliance_year": report["compliance_year"],
        "policy": report["policy"], "report_as_of": report["as_of"],
        "status": "worksheet for the entity and its verifier; not a filing, not signed or certified",
        "facilities": [_facility(report, f, tags) for f in report["facilities"]],
        "not_provided": NOT_PROVIDED,
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def for_report(conn: psycopg.Connection, report_id: int) -> str:
    """Form I draft from a stored report, with boundary tags read AS OF the report's own time."""
    row = conn.execute("SELECT as_of, output FROM report WHERE report_id = %s",
                       (report_id,)).fetchone()
    if row is None:
        raise LookupError(f"no report {report_id}")
    as_of, output = row
    ids = [ln["activity_id"] for ln in json.loads(output)["lines"]]
    return form_i(output, tags_as_of(conn, ids, as_of))
