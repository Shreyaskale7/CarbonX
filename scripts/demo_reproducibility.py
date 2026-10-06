"""Before/after demo of invariant 1, for the viva. Changes nothing permanently.

    python scripts/demo_reproducibility.py --org 1

1. Generate a report under VINTAGE_MATCHED and note its SHA-256.
2. CEA "publishes a revision": a new version revises the FY2025-26 factor.
3. Correct one month's meter reading (a backdated correction).
4. A new report now gives a different total: the world changed.
5. Regenerate the ORIGINAL report AS OF its own time: identical hash.

Everything runs in one transaction that is rolled back at the end, so the
revision is fictional (publisher DEMO) and never enters the real registry.
The same steps run from the Reports page of the site.
"""
import argparse

import psycopg

from carbonx import db
from carbonx.engine.demo import run


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--org", type=int, required=True)
    ap.add_argument("--fy", default="FY2025-26")
    args = ap.parse_args()

    with psycopg.connect(db.url()) as conn:
        try:
            d = run(conn, args.org, args.fy)
        finally:
            conn.rollback()
    b, a, r = d["before"], d["after"], d["regenerated"]
    print(f"1. report {b['report_id']}: {b['total_tco2e']} tCO2e   sha256 {b['sha256'][:16]}...")
    print(f"2. CEA 'revises' the {d['fy']} factor to {d['revision']['factor']} tCO2/MWh (fictional)")
    if c := d["correction"]:
        print(f"3. backdated correction: {c['month']} reading {c['from_kwh']} -> {c['to_kwh']} kWh")
    print(f"4. new report {a['report_id']}: {a['total_tco2e']} tCO2e"
          f"   sha256 {a['sha256'][:16]}...   (the world changed)")
    print(f"5. report {b['report_id']} regenerated AS OF its own time:"
          f" {r['total_tco2e']} tCO2e   sha256 {r['sha256'][:16]}...")
    print(f"   byte-identical to the original: {d['byte_identical']}")
    print("(rolled back: the demo left no trace)")
    if not d["byte_identical"]:
        raise SystemExit("INVARIANT 1 VIOLATED")


if __name__ == "__main__":
    main()
