"""A draft of BEE's Form A, the Performance Assessment Document (Annexure VI, p. 42), from a stored report.

Form A is filled and signed by the obligated entity and verified by an accredited agency (Form B). This
is a worksheet for the two of them: it carries over the figures CarbonX computed for the entitlement
(same inputs, same boundary, so the two cannot disagree) and leaves everything else empty and named.

What it fills: field 7, the achieved specific GHG emissions. For field 8, "Production (baseline)", the
form's wording does not say whether it means the baseline year's output or the cycle's production, so
both are shown, labelled, and the choice is the entity's. For field 9, "Number of Carbon Credit
Certificates Issued/Purchased", it gives the signed tCO2e-equivalent and no number: the BEE file does not
say what one certificate equals or how a fraction rounds.

What it never does: fields 1 to 6 (identity, verifier, Form I status) and 10 to 11 (reduction measures)
are the entity's to state; the undertaking, signature and seal are the entity's alone. Nothing here is
signed, certified or a filing.
"""

from __future__ import annotations

import json
from typing import Any

import psycopg

from carbonx.compliance import entitlement

SCHEMA = "carbonx.form_a/1"
ENTITY_FIELDS = {
    "1 name of obligated entity": None,
    "2 registration number": None,
    "3 sector": None,
    "4 sub-sector": None,
    "5 accredited carbon verification agency": None,
    "6 Form I for the previous year submitted": None,
    "10-11 carbon emission reduction measures (measure, year, GHG before and after, investment)": None,
    "undertaking, signature, name, designation, seal": None,
}


def _facility(e: dict[str, Any]) -> dict[str, Any]:
    baseline = e["baseline"]
    return {
        "facility_id": e["facility_id"],
        "7 achieved specific GHG emissions": e["achieved"],
        "8 production (baseline)": {
            "baseline_year_output": None if baseline is None or baseline["output"] is None else {
                "quantity": baseline["output"], "unit": baseline["output_unit"],
                "baseline_fy": baseline["baseline_fy"], "status": baseline["status"]},
            "production_in_this_cycle": e["production"],
            "note": ("the form does not say which of the two is meant; both are shown and the "
                     "choice is the entity's"),
        },
        "9 number of carbon credit certificates issued or purchased": None,
        "9 basis": {"outcome": e["outcome"],
                    "entitlement_tco2e_equivalent": e["entitlement_tco2e_equivalent"],
                    "withheld_because": e["withheld_because"],
                    "target": e["target"], "note": e["note"]},
        "boundary": e["boundary"],
        "to_be_filled_by_the_entity": ENTITY_FIELDS,
    }


def form_a(entitlement_output: str) -> str:
    """Canonical JSON: one worksheet per facility, from the entitlement of the same report. Pure."""
    ent = json.loads(entitlement_output)
    return json.dumps({
        "schema": SCHEMA, "org_id": ent["org_id"], "compliance_year": ent["compliance_year"],
        "policy": ent["policy"], "report_as_of": ent["report_as_of"],
        "status": "worksheet for the entity and its verifier; not a filing, not signed or certified",
        "facilities": [_facility(e) for e in ent["facilities"]],
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def for_report(conn: psycopg.Connection, report_id: int) -> str:
    """Form A draft from a stored report: its entitlement, laid out as the form asks."""
    return form_a(entitlement.for_report(conn, report_id))
