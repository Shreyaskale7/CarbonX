"""Build the open CEA factor registry, and optionally load it into Postgres.

    python scripts/load_cea.py        # data/raw/cea -> data/cea/{versions,factors}.csv
    python scripts/load_cea.py --db   # data/cea/*.csv -> factor_source, emission_factor

The CSVs are committed: they are the Zenodo deliverable, and they let
reproduce.sh run without re-downloading from cea.nic.in. Every factor row
names the workbook cell it came from. Output is deterministic, so a re-run on
the same downloads yields byte-identical CSVs.
"""
import argparse
import csv
import json
import sys
import zipfile
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carbonx import db
from carbonx.ingest.cea import parse

MANIFEST = ROOT / "data" / "cea" / "manifest.json"
VERSIONS = ROOT / "data" / "cea" / "versions.csv"
FACTORS = ROOT / "data" / "cea" / "factors.csv"
WORKBOOK = (".xls", ".xlsx", ".xlsm")


def workbook(entry: dict) -> Path:
    """The version's workbook, extracting it from the zip if needed."""
    db = ROOT / entry["database"]["file"]
    if db.suffix == ".zip":
        with zipfile.ZipFile(db) as z:
            names = [n for n in z.namelist() if n.lower().endswith(WORKBOOK)]
            if len(names) != 1:
                raise ValueError(f"{db.name}: expected one workbook, got {names}")
            out = db.parent / "extracted"
            z.extract(names[0], out)
            return out / names[0]
    return db


def build() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))["versions"]
    versions, factors = [], []
    for entry in manifest:
        path = workbook(entry)
        wb = parse(path, entry["version_label"])
        versions.append({
            "version_label": wb.version_label,
            "version_ordinal": entry["version_ordinal"],
            "stated_date": wb.stated_date.isoformat() if wb.stated_date else "",
            "date_precision": wb.date_precision,
            "covers_fy": wb.covers_fy,
            "cea_outdated": entry["outdated"],
            "workbook": path.name,
            "database_url": entry["database"]["url"],
            "database_sha256": entry["database"]["sha256"],
            "user_guide_url": entry.get("user_guide", {}).get("url", ""),
            "user_guide_sha256": entry.get("user_guide", {}).get("sha256", ""),
        })
        factors += [{
            "version_label": f.version_label, "fy": f.fy,
            "factor_key": f.factor_key, "geography": f.geography,
            "value": repr(f.value), "unit": "tCO2/MWh",
            "cell": f.cell, "cea_label": f.label,
        } for f in wb.factors]
        print(f"{wb.version_label:6} {len(wb.factors):4} factors, covers {wb.covers_fy}")

    for path, rows in ((VERSIONS, versions), (FACTORS, factors)):
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
    print(f"{len(factors)} factors from {len(versions)} versions -> data/cea/")


def load_db() -> None:
    import psycopg

    from carbonx.factors.registry import insert_factor

    url = db.url()
    with VERSIONS.open(encoding="utf-8") as fh:
        versions = list(csv.DictReader(fh))
    with FACTORS.open(encoding="utf-8") as fh:
        factors = list(csv.DictReader(fh))

    with psycopg.connect(url) as conn:
        conn.execute("SET carbonx.actor = 'load_cea.py'")
        n = 0
        # Oldest version first, so each later version supersedes the one before.
        for v in sorted(versions, key=lambda v: int(v["version_ordinal"])):
            exists = conn.execute(
                "SELECT 1 FROM factor_source WHERE publisher = 'CEA'"
                " AND dataset_name = 'CO2 Baseline Database'"
                " AND version_ordinal = %s", (int(v["version_ordinal"]),)
            ).fetchone()
            if exists:
                continue  # already loaded: re-running is a no-op
            row = conn.execute(
                "INSERT INTO factor_source (publisher, dataset_name, version_label,"
                " version_ordinal, published_on, covers_fy, source_url, file_sha256)"
                " VALUES ('CEA', 'CO2 Baseline Database', %s, %s, %s, %s, %s, %s)"
                " RETURNING source_id",
                (v["version_label"], int(v["version_ordinal"]),
                 v["stated_date"] or None, v["covers_fy"], v["database_url"],
                 v["database_sha256"]),
            ).fetchone()
            assert row is not None
            for f in factors:
                if f["version_label"] == v["version_label"]:
                    numerator, denominator = f["unit"].split("/")
                    insert_factor(
                        conn, source_id=row[0], factor_key=f["factor_key"],
                        value=Decimal(f["value"]), numerator_unit=numerator,
                        denominator_unit=denominator, fy=f["fy"],
                        geography=f["geography"],
                    )
                    n += 1
            print(f"{v['version_label']:6} loaded")
    print(f"{n} factor rows inserted")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", action="store_true", help="load data/cea/*.csv into Postgres")
    (load_db if ap.parse_args().db else build)()
