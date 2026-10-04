"""BEE's default (Type I) fuel emission factors, from Annexure IV of the
Detailed Procedure for Compliance Mechanism under CCTS.

    python scripts/load_bee_factors.py --pdf <procedure.pdf>   # -> data/bee/fuel_factors.csv
    python scripts/load_bee_factors.py --db                    # CSV -> emission_factor

The CSV is committed, with the PDF's SHA-256 and the page of every row, so the
factors are traceable without the PDF (which is not committed).

CO2e per fuel is DERIVED here, not printed by BEE:
    co2e = co2 + (ch4 * GWP_CH4 + n2o * GWP_N2O) / 1000        [t CO2e / TJ]
with the GWPs of Annexure I (IPCC AR2: CH4 21, N2O 310). Whether combustion
CH4 and N2O count towards GEI is our reading of sections 3.2 and Annexure IV
(the table gives all three gases); the CO2-only factor is loaded too.

Caveat carried from docs/RQ3_FINDINGS.md: the PDF read has internal metadata
dated 2023-11-08, before the reported July 2024 notification. Confirm the
table against the notified text before relying on it.
"""
import argparse
import csv
import hashlib
import re
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "data" / "bee" / "fuel_factors.csv"
URL = "https://beeindia.gov.in/WriteReadData/L45218/7772386525993811.pdf"
GWP = {"ch4": Decimal(21), "n2o": Decimal(310)}  # Annexure I, p. 25 (IPCC AR2)
PAGES = (34, 35)                                 # Annexure IV
ROW = re.compile(r"^(?:(\d{1,2}) )?(.+?) (\d+\.\d+) (\d+\.\d+) (\d+\.\d+)$")
# Applies "for the first trajectory period" (procedure p. 8, clause (6)).
VALID = (date(2024, 4, 1), date(2027, 4, 1))


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def parse(pdf_path: Path) -> list[dict]:
    import pdfplumber
    sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    rows, pending = [], ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in PAGES:
            for line in (pdf.pages[page - 1].extract_text() or "").splitlines():
                line = line.strip()
                m = ROW.match(line)
                if not m:
                    # A fuel name wrapped onto its own line, e.g. "Municipal Waste
                    # (Non Biomass" / "39 Fraction) 91.70 30.00 4.00".
                    # A wrapped name leaves a bracket open; a page header does not.
                    pending = line if line.count("(") > line.count(")") else ""
                    continue
                number, name, co2, ch4, n2o = m.groups()
                if number is None:
                    continue  # not a numbered fuel row
                name = f"{pending} {name}".strip() if pending else name
                pending = ""
                co2, ch4, n2o = Decimal(co2), Decimal(ch4), Decimal(n2o)
                co2e = co2 + (ch4 * GWP["ch4"] + n2o * GWP["n2o"]) / 1000
                rows.append({
                    "sr_no": int(number), "fuel": name, "slug": slug(name),
                    "co2_t_per_tj": f"{co2}", "ch4_kg_per_tj": f"{ch4}",
                    "n2o_kg_per_tj": f"{n2o}", "co2e_t_per_tj": f"{co2e}",
                    "page": page, "source_sha256": sha,
                })
    numbers = [r["sr_no"] for r in rows]
    if numbers != list(range(1, 54)):
        raise ValueError(f"expected fuels 1..53 in order, got {numbers}")
    if any(len(r["fuel"]) > 45 for r in rows):
        raise ValueError("a fuel name swallowed a neighbouring line")
    if len({r["slug"] for r in rows}) != len(rows):
        raise ValueError("two fuels map to the same slug")
    return rows


def build(pdf_path: Path) -> None:
    rows = parse(pdf_path)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} fuels -> {OUT.relative_to(ROOT)}")


def load_db() -> None:
    import psycopg

    from carbonx import db
    from carbonx.factors.registry import insert_factor

    with OUT.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    with psycopg.connect(db.url()) as conn:
        conn.execute("SELECT set_config('carbonx.actor', 'load_bee_factors.py', false)")
        if conn.execute("SELECT 1 FROM factor_source WHERE publisher = 'BEE'").fetchone():
            print("BEE fuel factors already loaded")
            return
        (source_id,) = conn.execute(
            "INSERT INTO factor_source (publisher, dataset_name, version_label,"
            " version_ordinal, source_url, file_sha256) VALUES ('BEE',"
            " 'CCTS Compliance Procedure, Annexure IV', 'v1.0', 10, %s, %s)"
            " RETURNING source_id", (URL, rows[0]["source_sha256"])).fetchone()
        ranged = 0
        for r, (low, high) in zip(rows, ipcc_ranges(rows), strict=True):
            co2, co2e = Decimal(r["co2_t_per_tj"]), Decimal(r["co2e_t_per_tj"])
            other = co2e - co2   # the CH4 + N2O part, carried without a range
            for gas, value, unit in (("co2", co2, "tCO2"), ("co2e", co2e, "tCO2e")):
                shift = other if gas == "co2e" else Decimal(0)
                insert_factor(
                    conn, source_id=source_id, factor_key=f"fuel.{r['slug']}.{gas}",
                    value=value, numerator_unit=unit, denominator_unit="TJ", valid=VALID,
                    uncertainty_low=None if low is None else low + shift,
                    uncertainty_high=None if high is None else high + shift,
                    uncertainty_basis=None if low is None else BASIS)
            ranged += low is not None
    print(f"{2 * len(rows)} fuel factor rows inserted; {ranged} fuels carry IPCC's "
          f"range, {len(rows) - ranged} are point estimates")


BASIS = ("IPCC 2006 Guidelines, Vol. 2, Ch. 2, Table 2.2: 95% confidence limits of the "
         "CO2 default; CH4 and N2O carried without a range")


def ipcc_ranges(rows: list[dict]) -> list[tuple[Decimal | None, Decimal | None]]:
    """IPCC's lower and upper CO2 limits (t/TJ) for each BEE row, or (None, None).

    Invariant 6: a range is attached only where BEE's CO2 value equals IPCC's
    default. Where they differ (docs/BEE_VS_IPCC.md), IPCC's range describes a
    different central value, so the factor stays a point estimate.
    """
    path = ROOT / "data" / "ipcc" / "table_2_2_co2.csv"
    if not path.exists():
        return [(None, None)] * len(rows)
    with path.open(encoding="utf-8") as fh:
        ipcc = list(csv.DictReader(fh))
    out: list[tuple[Decimal | None, Decimal | None]] = []
    for r, i in zip(rows, ipcc, strict=True):
        same = Decimal(r["co2_t_per_tj"]) == Decimal(i["co2_default_kg_per_tj"]) / 1000
        out.append((Decimal(i["co2_lower_kg_per_tj"]) / 1000,
                    Decimal(i["co2_upper_kg_per_tj"]) / 1000) if same else (None, None))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", type=Path, help="the BEE procedure PDF; rebuilds the CSV")
    ap.add_argument("--db", action="store_true", help="load the CSV into Postgres")
    args = ap.parse_args()
    if args.pdf:
        build(args.pdf)
    if args.db:
        load_db()
    if not args.pdf and not args.db:
        ap.error("give --pdf and/or --db")
