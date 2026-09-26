"""Before/after demo of invariant 1, for the viva. Changes nothing permanently.

    python scripts/demo_reproducibility.py --org 1

1. Generate a report under VINTAGE_MATCHED and note its SHA-256.
2. CEA "publishes a revision": a new version revises the FY2025-26 factor.
3. Correct one month's meter reading (a backdated correction).
4. A new report now gives a different total: the world changed.
5. Regenerate the ORIGINAL report AS OF its own time: identical hash.

Everything runs in one transaction that is rolled back at the end, so the
revision is fictional (publisher DEMO) and never enters the real registry.
"""
import argparse
import json
from decimal import Decimal

import psycopg

from carbonx import db
from carbonx.engine.calculate import edit_activity, fy_of
from carbonx.engine.report import generate_report, regenerate
from carbonx.factors.registry import Policy, insert_factor

GRID = "grid.weighted_avg_incl_re_captive.incl_imports"


def total(report) -> str:
    return json.loads(report.output)["totals"]["total_tco2e"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--org", type=int, required=True)
    ap.add_argument("--fy", default="FY2025-26")
    args = ap.parse_args()
    url = db.url()

    with psycopg.connect(url) as conn:
        try:
            # Open the outer transaction first: with none open, the
            # conn.transaction() inside generate_report would COMMIT, and a
            # committed report can never be removed (reports are append-only).
            conn.execute("SELECT 1")
            before = generate_report(conn, args.org, args.fy, Policy.VINTAGE_MATCHED)
            print(f"1. report {before.report_id}: {total(before)} tCO2e"
                  f"   sha256 {before.sha256[:16]}...")

            (source_id,) = conn.execute(
                "INSERT INTO factor_source (publisher, dataset_name, version_label,"
                " version_ordinal, published_on, source_url) VALUES ('DEMO',"
                " 'fictional revision', 'v22.1-demo', 221, current_date,"
                " 'https://example.test') RETURNING source_id").fetchone()
            insert_factor(conn, source_id=source_id, factor_key=GRID,
                          value=Decimal("0.700000000"), numerator_unit="tCO2",
                          denominator_unit="MWh", fy=args.fy)
            print(f"2. CEA 'revises' the {args.fy} factor to 0.700 tCO2/MWh (fictional)")

            row = conn.execute(
                "SELECT a.activity_id, a.quantity, lower(a.period) FROM activity a"
                " JOIN facility f USING (facility_id) WHERE f.org_id = %s"
                " AND upper_inf(a.system_time_range) ORDER BY lower(a.period) LIMIT 1",
                (args.org,)).fetchone()
            if row and fy_of(row[2]) == args.fy:
                edit_activity(conn, row[0], quantity=row[1] + 50_000,
                              reason="demo: backdated meter correction")
                print(f"3. backdated correction: {row[2]:%b %Y} reading"
                      f" {row[1]:,.0f} -> {row[1] + 50_000:,.0f} kWh")

            after = generate_report(conn, args.org, args.fy, Policy.VINTAGE_MATCHED)
            print(f"4. new report {after.report_id}: {total(after)} tCO2e"
                  f"   sha256 {after.sha256[:16]}...   (the world changed)")

            again = regenerate(conn, before.report_id)
            same = again.output == before.output
            print(f"5. report {before.report_id} regenerated AS OF its own time:"
                  f" {total(again)} tCO2e   sha256 {again.sha256[:16]}...")
            print(f"   byte-identical to the original: {same}")
            if not same:
                raise SystemExit("INVARIANT 1 VIOLATED")
        finally:
            conn.rollback()
            print("(rolled back: the demo left no trace)")


if __name__ == "__main__":
    main()
