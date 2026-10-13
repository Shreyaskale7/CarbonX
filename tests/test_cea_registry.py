"""The open CEA registry (data/cea/*.csv) and the parser that builds it.

CSV checks run everywhere, CI included. Re-parse checks need the raw
downloads (python scripts/fetch_cea.py) and skip without them.
"""
import csv
import json
from datetime import date, timedelta
from itertools import pairwise
from pathlib import Path

import pytest

from carbonx.factors.registry import FactorNotFound, Policy, resolve
from carbonx.ingest.cea import imports, metric, parse

ROOT = Path(__file__).resolve().parents[1]
GRID = "grid.weighted_avg_incl_re_captive.incl_imports"


def _csv(name):
    with (ROOT / "data" / "cea" / name).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


VERSIONS = _csv("versions.csv")
FACTORS = _csv("factors.csv")


def _value(version, fy, key=GRID, geo="IN"):
    (row,) = [f for f in FACTORS if (f["version_label"], f["fy"], f["factor_key"],
                                     f["geography"]) == (version, fy, key, geo)]
    return float(row["value"])


def test_every_published_version_is_present_and_ordered():
    assert [v["version_label"] for v in VERSIONS][:2] == ["v1.0", "v1.1"]
    assert VERSIONS[-1]["version_label"] == "v22.0"
    assert len(VERSIONS) == 23
    for a, b in pairwise(VERSIONS):
        assert int(a["version_ordinal"]) < int(b["version_ordinal"])
        assert a["stated_date"] <= b["stated_date"]


def test_known_checkpoints():
    """CLAUDE.md: v19 = 0.716 (FY2022-23), v20 = 0.727 (FY2023-24)."""
    assert _value("v19.0", "FY2022-23") == 0.716
    assert round(_value("v20.0", "FY2023-24"), 3) == 0.727


def test_v22_covers_fy2025_26_and_is_dated_after_the_deadline():
    """The RQ3 fact: the compliance year's own factor post-dates 31 July 2026."""
    (v22,) = [v for v in VERSIONS if v["version_label"] == "v22.0"]
    assert v22["covers_fy"] == "FY2025-26"
    assert date.fromisoformat(v22["stated_date"]) > date(2026, 7, 31)


def test_every_row_is_traceable_and_unique():
    keys = [(f["version_label"], f["fy"], f["factor_key"], f["geography"])
            for f in FACTORS]
    assert len(keys) == len(set(keys))
    assert all(f["cell"].startswith("Result") for f in FACTORS)
    manifest = json.loads((ROOT / "data/cea/manifest.json").read_text())["versions"]
    assert {v["database_sha256"] for v in VERSIONS} == {
        m["database"]["sha256"] for m in manifest}


def test_labels_map_explicitly():
    assert metric("Grid Emission Factor (for net effective injection into grid)") \
        == metric("Weighted Average Grid Emission Rate (Incl. RES,Captive) (2)") \
        == "weighted_avg_incl_re_captive"
    assert metric("Weighted Average Emission Rate Incl. RES (2)") == "weighted_avg_incl_re"
    assert imports("x", "Build Margin (not adjusted for imports)") == "excl_imports"
    with pytest.raises(ValueError):
        metric("Gross Generation Total (GWh)")


@pytest.mark.parametrize("version", [v["version_label"] for v in VERSIONS])
def test_reparse_matches_committed_csv(version):
    """Every version: the committed CSV is exactly what the parser reads from
    the workbook. (Until 2026-10-13 only one version per layout was checked.)"""
    (v,) = [x for x in VERSIONS if x["version_label"] == version]
    found = list((ROOT / "data" / "raw" / "cea" / version).rglob(v["workbook"]))
    if not found:
        pytest.skip("raw CEA files not downloaded; run scripts/fetch_cea.py")
    parsed = {(f.fy, f.factor_key, f.geography, repr(f.value), f.cell)
              for f in parse(found[0], version).factors}
    committed = {(f["fy"], f["factor_key"], f["geography"], f["value"], f["cell"])
                 for f in FACTORS if f["version_label"] == version}
    assert parsed == committed


def test_policies_on_real_cea_data(conn):
    """RQ3 on the real registry. Needs `load_cea.py --db` (CI does this)."""
    if not conn.execute("SELECT 1 FROM factor_source WHERE publisher = 'CEA'"
                        " AND version_label = 'v22.0'").fetchone():
        pytest.skip("CEA registry not loaded; run scripts/load_cea.py --db")
    now = conn.execute("SELECT clock_timestamp()").fetchone()[0]

    def pick(policy, **kw):
        f = resolve(conn, GRID, "FY2025-26", now, policy, **kw)
        return f.version_label, f.valid_from, round(float(f.value), 6)

    v22 = round(_value("v22.0", "FY2025-26"), 6)
    v21 = round(_value("v21.0", "FY2024-25"), 6)
    assert pick(Policy.VINTAGE_MATCHED) == ("v22.0", date(2025, 4, 1), v22)
    assert pick(Policy.LATEST_AVAILABLE) == ("v22.0", date(2025, 4, 1), v22)
    # Published by the 31 July 2026 deadline: only up to v21, i.e. FY2024-25.
    assert pick(Policy.AS_OF_REPORT) == ("v21.0", date(2024, 4, 1), v21)
    assert pick(Policy.BASELINE_FROZEN, baseline_year="FY2023-24")[0] == "v20.0"

    # Before v22 was loaded, the vintage-matched factor did not exist at all.
    first = conn.execute(
        "SELECT min(lower(system_time_range)) FROM emission_factor ef"
        " JOIN factor_source fs USING (source_id) WHERE fs.version_label = 'v22.0'"
    ).fetchone()[0]
    with pytest.raises(FactorNotFound):
        resolve(conn, GRID, "FY2025-26", first - timedelta(microseconds=1),
                Policy.VINTAGE_MATCHED)
