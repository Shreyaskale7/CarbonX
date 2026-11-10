"""Load intensity targets and baselines for facilities from a CSV, with their sources.

    python scripts/load_targets.py data/targets/template.csv --dry-run
    python scripts/load_targets.py my_targets.csv

Nothing is pre-filled. The notified Schedule (MoEFCC, October 2025 and its January 2026 amendment) gives,
per obligated entity, a baseline output and intensity for FY2023-24 and targets for 2025-26 and 2026-27,
in tCO2e per tonne of equivalent product. Those figures belong to named entities: read them from the
gazette (not from a news summary) and enter them against the facility that is that entity.

Columns (one row per facility and compliance year):
  facility_id, compliance_fy, target, unit, status, citation, url,
  baseline_fy, baseline_intensity, baseline_status, baseline_output, baseline_output_unit

`status` is 'notified' only if you read the value in the notification: then `citation` (gazette number,
schedule, row) and `url` are required. Otherwise 'assumed'. A row is refused whole, never half-loaded.
"""
import argparse
import csv
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import psycopg

from carbonx import db
from carbonx.compliance.baseline import STATUSES as BASELINE_STATUSES
from carbonx.compliance.baseline import set_baseline
from carbonx.compliance.entitlement import STATUSES, set_target
from carbonx.factors.registry import fy_start

REQUIRED = ["facility_id", "compliance_fy", "target", "unit", "status", "citation"]


def problems(row: dict[str, str]) -> list[str]:
    bad = [f"missing {c}" for c in REQUIRED if not (row.get(c) or "").strip()]
    if (row.get("status") or "").strip() not in STATUSES:
        bad.append(f"status must be one of {sorted(STATUSES)}")
    if (row.get("status") or "").strip() == "notified" and not (row.get("url") or "").strip():
        bad.append("a 'notified' value needs the url of the notification you read it in")
    for c in ("facility_id", "target", "baseline_intensity", "baseline_output"):
        if (row.get(c) or "").strip():
            try:
                Decimal(row[c]) if c != "facility_id" else int(row[c])
            except (InvalidOperation, ValueError):
                bad.append(f"{c} is not a number: {row[c]!r}")
    if (row.get("baseline_intensity") or "").strip() and not (row.get("baseline_fy") or "").strip():
        bad.append("a baseline intensity needs its baseline_fy")
    for c in ("compliance_fy", "baseline_fy"):
        if (row.get(c) or "").strip():
            try:
                fy_start(row[c].strip())
            except ValueError:
                bad.append(f"{c} is not a financial year like FY2025-26: {row[c]!r}")
    unit = (row.get("unit") or "").strip()
    if unit and (not unit.startswith("tCO2e/") or unit == "tCO2e/"):
        bad.append("unit must be tCO2e per unit of product, e.g. tCO2e/t")
    base_status = (row.get("baseline_status") or "").strip()
    if base_status and base_status not in BASELINE_STATUSES:
        bad.append(f"baseline_status must be one of {sorted(BASELINE_STATUSES)}")
    if base_status == "notified" and not (row.get("url") or "").strip():
        bad.append("a 'notified' baseline needs the url of the notification you read it in")
    if bool((row.get("baseline_output") or "").strip()) != bool(
            (row.get("baseline_output_unit") or "").strip()):
        bad.append("give baseline_output and baseline_output_unit together, or neither")
    return bad


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("csv", type=Path)
    ap.add_argument("--dry-run", action="store_true", help="check every row, write nothing")
    ap.add_argument("--actor", default="load_targets")
    args = ap.parse_args()
    with args.csv.open(encoding="utf-8", newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if any((v or "").strip() for v in r.values())]
    refused = {i: p for i, r in enumerate(rows, start=2) if (p := problems(r))}
    for line, why in refused.items():
        print(f"line {line}: refused: {'; '.join(why)}")
    if refused or args.dry_run:
        print(f"{len(rows) - len(refused)} of {len(rows)} rows are valid"
              + ("; nothing written (dry run)" if args.dry_run else "; nothing written"))
        raise SystemExit(1 if refused else 0)
    with psycopg.connect(db.url()) as conn:
        wanted = sorted({int(r["facility_id"]) for r in rows})
        known = {f for (f,) in conn.execute(
            "SELECT facility_id FROM facility WHERE facility_id = ANY(%s)", (wanted,))}
        if missing := [f for f in wanted if f not in known]:
            sys.exit(f"no such facility: {missing}; nothing written")
        for r in rows:
            fid, status = int(r["facility_id"]), r["status"].strip()
            tid = set_target(
                conn, facility_id=fid, fy=r["compliance_fy"].strip(), value=Decimal(r["target"]),
                unit=r["unit"].strip(), status=status, source_citation=r["citation"],
                source_url=(r.get("url") or "").strip() or None,
                baseline_fy=(r.get("baseline_fy") or "").strip() or None, actor=args.actor)
            line = f"facility {fid} {r['compliance_fy']}: target {tid}"
            if (r.get("baseline_intensity") or "").strip():
                out = (r.get("baseline_output") or "").strip()
                bid = set_baseline(
                    conn, facility_id=fid, baseline_fy=r["baseline_fy"].strip(),
                    intensity=Decimal(r["baseline_intensity"]), intensity_unit=r["unit"].strip(),
                    status=(r.get("baseline_status") or status).strip(), source_citation=r["citation"],
                    output=Decimal(out) if out else None,
                    output_unit=(r.get("baseline_output_unit") or "").strip() or None if out else None,
                    source_url=(r.get("url") or "").strip() or None, actor=args.actor)
                line += f", baseline {bid}"
            print(line)
        conn.commit()


if __name__ == "__main__":
    main()
