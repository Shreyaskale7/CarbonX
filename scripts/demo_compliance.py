"""Demo of the compliance worksheets on the sample facility. Changes nothing permanently.

    python scripts/demo_compliance.py --org 1

1. Without boundary tags, the entitlement is withheld: an untagged activity is never assumed inside.
2. Tag every activity inside the boundary and record a FICTIONAL target 2% below the achieved intensity.
3. The entitlement is a shortfall; the Form I and Form A drafts show the same achieved intensity.
4. "Revise" the target to 2% above. A new report shows a surplus.
5. The entitlement of the earlier report, recomputed, is byte-identical: it keeps the target it read.

The targets are invented for the demonstration and marked 'assumed'. No notified target is loaded
anywhere in CarbonX. Everything runs in one transaction that is rolled back at the end.
"""
import argparse
import json
from decimal import Decimal

import psycopg

from carbonx import db
from carbonx.compliance import entitlement, form_a, form_i
from carbonx.compliance.boundary import tag_activity
from carbonx.engine.report import generate_report
from carbonx.factors.registry import Policy

SPECIFIC = "5.1(c)(iii) specific GHG emissions"


def run(conn: psycopg.Connection, org_id: int, fy: str) -> None:
    conn.execute("SELECT 1")   # open the outer transaction, so nothing below commits
    first = generate_report(conn, org_id, fy, Policy.VINTAGE_MATCHED)
    e = json.loads(entitlement.for_report(conn, first.report_id))["facilities"][0]
    print(f"1. report {first.report_id}, no boundary tags: withheld ({e['withheld_because']})")

    start = f"{fy[2:6]}-04-01"
    activities = conn.execute(
        "SELECT a.activity_id FROM activity a JOIN facility f USING (facility_id)"
        " WHERE f.org_id = %s AND upper_inf(a.system_time_range)"
        " AND a.period <@ daterange(%s::date, (%s::date + interval '1 year')::date)",
        (org_id, start, start)).fetchall()
    for (activity_id,) in activities:
        tag_activity(conn, activity_id=activity_id, boundary="inside",
                     basis="demo: all sample activities taken as inside the gate")
    tagged = generate_report(conn, org_id, fy, Policy.VINTAGE_MATCHED)
    shown = json.loads(entitlement.for_report(conn, tagged.report_id))["facilities"][0]
    facility_id, achieved = shown["facility_id"], shown["achieved"]
    if achieved is None:
        raise SystemExit("the sample facility has no achieved intensity; seed production first")

    def fictional_target(multiplier: str) -> None:
        entitlement.set_target(
            conn, facility_id=facility_id, fy=fy, unit=achieved["unit"], status="assumed",
            value=(Decimal(achieved["value"]) * Decimal(multiplier)).quantize(Decimal("0.000001")),
            source_citation=f"FICTIONAL demo target: achieved intensity x {multiplier}")

    fictional_target("0.98")
    print(f"2. {len(activities)} activities tagged inside; fictional target = achieved x 0.98")
    short = generate_report(conn, org_id, fy, Policy.VINTAGE_MATCHED)
    before = entitlement.for_report(conn, short.report_id)
    e = json.loads(before)["facilities"][0]
    i = json.loads(form_i.for_report(conn, short.report_id))["facilities"][0]
    a = json.loads(form_a.for_report(conn, short.report_id))["facilities"][0]
    print(f"3. report {short.report_id}: achieved {e['achieved']['value']} {e['achieved']['unit']},"
          f" {e['outcome']}: {e['entitlement_tco2e_equivalent']} tCO2e-equivalent")
    same = (abs(Decimal(i[SPECIFIC]["value"]) - Decimal(e["achieved"]["value"])) <= Decimal("0.000001")
            and a["7 achieved specific GHG emissions"] == e["achieved"])
    print(f"   Form I and Form A drafts show the same intensity: {same}")

    fictional_target("1.02")
    later = generate_report(conn, org_id, fy, Policy.VINTAGE_MATCHED)
    e2 = json.loads(entitlement.for_report(conn, later.report_id))["facilities"][0]
    print(f"4. target 'revised' to achieved x 1.02; report {later.report_id}: {e2['outcome']}:"
          f" {e2['entitlement_tco2e_equivalent']} tCO2e-equivalent")
    identical = entitlement.for_report(conn, short.report_id) == before
    print(f"5. report {short.report_id}'s entitlement recomputed: byte-identical: {identical}")
    if not (same and identical and e["outcome"].startswith("shortfall")
            and e2["outcome"].startswith("surplus")):
        raise SystemExit("COMPLIANCE DEMO FAILED")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--org", type=int, required=True)
    ap.add_argument("--fy", default="FY2025-26")
    args = ap.parse_args()
    with psycopg.connect(db.url()) as conn:
        try:
            run(conn, args.org, args.fy)
        finally:
            conn.rollback()
    print("(rolled back: the demo left no trace; the targets were fictional)")


if __name__ == "__main__":
    main()
