"""RQ1: at what Scope 2 share does a grid-factor change ALONE cross the 5%
materiality threshold (SBTi's >=5% change in base-year emissions)?

    python scripts/rq1_materiality.py   # data/cea/factors.csv -> docs/RQ1_RESULTS.md

If grid electricity is a share s of the emissions in the GEI basis, a change
d in the grid factor moves the total by s*d. It crosses 5% when s >= 5%/|d|.
The registry supplies four kinds of d, which are the real question here:

  revision     the same FY's factor, restated by a later CEA version
  step         this FY's factor vs last FY's (the vintage moves on)
  latest       BEE's "latest" read before vs after the new version appears
  series       CEA's "average" series disagree (BEE does not name one)

Sector placement needs each sector's Scope 2 share OF THE TARGET BASIS, cited
to a source; it is not in this script. data/sector_scope2_shares.csv holds
those rows once someone has a citation for them.
"""
import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FACTORS = ROOT / "data" / "cea" / "factors.csv"
VERSIONS = ROOT / "data" / "cea" / "versions.csv"
SHARES = ROOT / "data" / "sector_scope2_shares.csv"
OUT = ROOT / "docs" / "RQ1_RESULTS.md"
THRESHOLD = 5.0  # percent
GRID = "grid.weighted_avg_incl_re_captive.incl_imports"  # engine/calculate.py
SERIES = ["grid.weighted_avg.excl_imports", "grid.weighted_avg.incl_imports",
          "grid.weighted_avg_incl_re_captive.excl_imports", GRID]


def pct(new: float, old: float) -> float:
    return 100 * (new - old) / old


def share_needed(d: float) -> str:
    """Scope 2 share of the basis at which |d| alone reaches the threshold."""
    if d == 0:
        return "never"
    s = THRESHOLD / abs(d)
    return "never (would need >100%)" if s > 1 else f"{100 * s:.0f}%"


def table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return "\n".join(lines + ["| " + " | ".join(r) + " |" for r in rows])


def main() -> None:
    with VERSIONS.open(encoding="utf-8") as fh:
        ordinal = {v["version_label"]: int(v["version_ordinal"]) for v in csv.DictReader(fh)}
    series: dict[str, dict[str, list[tuple[int, str, float]]]] = defaultdict(
        lambda: defaultdict(list))
    with FACTORS.open(encoding="utf-8") as fh:
        for f in csv.DictReader(fh):
            if f["geography"] == "IN":
                series[f["factor_key"]][f["fy"]].append(
                    (ordinal[f["version_label"]], f["version_label"], float(f["value"])))
    for by_fy in series.values():
        for obs in by_fy.values():
            obs.sort()

    grid = series[GRID]
    # revision: largest restatement of any FY between its first and latest version
    revisions = {fy: pct(o[-1][2], o[0][2]) for fy, o in grid.items() if len(o) > 1}
    rev_fy = max(revisions, key=lambda fy: abs(revisions[fy]))
    # step and latest: FY2025-26 in v22 vs FY2024-25 (as v21 published it)
    v22_2526 = next(x for x in grid["FY2025-26"] if x[1] == "v22.0")[2]
    v21_2425 = next(x for x in grid["FY2024-25"] if x[1] == "v21.0")[2]
    v22_2425 = next(x for x in grid["FY2024-25"] if x[1] == "v22.0")[2]
    # series: spread of the four all-India average series, same version and FY
    spread = {}
    for version, fy in (("v21.0", "FY2024-25"), ("v22.0", "FY2025-26")):
        vals = [x[2] for k in SERIES for x in series[k].get(fy, []) if x[1] == version]
        spread[(version, fy)] = pct(max(vals), min(vals))

    effects = [
        ["revision", f"largest restatement of one FY ({rev_fy}), first vs latest version",
         f"{revisions[rev_fy]:+.2f}%"],
        ["step", "FY2025-26 (v22) vs FY2024-25 (v22)", f"{pct(v22_2526, v22_2425):+.2f}%"],
        ["latest", "BEE 'latest' before v22 (v21, FY2024-25) vs after (v22, FY2025-26)",
         f"{pct(v22_2526, v21_2425):+.2f}%"],
        ["series", "spread of CEA's four average series, v22 FY2025-26",
         f"{spread[('v22.0', 'FY2025-26')]:.2f}%"],
    ]
    for row in effects:
        row.append(share_needed(float(row[2].rstrip("%"))))

    shares = [10, 20, 30, 40, 50, 60, 80, 100]
    curve = []
    for name, _, d, _ in effects:
        dv = abs(float(d.rstrip("%")))
        curve.append([name] + [("**" if s * dv / 100 >= THRESHOLD else "")
                               + f"{s * dv / 100:.2f}%"
                               + ("**" if s * dv / 100 >= THRESHOLD else "")
                               for s in shares])

    sectors = "_No sector rows yet: `data/sector_scope2_shares.csv` needs cited shares._"
    if SHARES.exists():
        with SHARES.open(encoding="utf-8") as fh:
            rows = [r for r in csv.DictReader(fh) if r.get("scope2_share_pct")]
        if rows:
            sectors = table(
                ["sector", "Scope 2 share of target basis", "source"] +
                [e[0] for e in effects],
                [[r["sector"], f"{r['scope2_share_pct']}%", r["source"]] +
                 [f"{float(r['scope2_share_pct']) * abs(float(e[2].rstrip('%'))) / 100:.2f}%"
                  for e in effects] for r in rows])

    OUT.write_text("\n\n".join([
        "# RQ1 results: when does a grid-factor change alone cross 5%?",
        ("_Generated by `scripts/rq1_materiality.py` from `data/cea/factors.csv`. "
         "Do not edit by hand._"),
        (f"Factor: `{GRID}` (all-India, the series CarbonX uses). If grid electricity "
         "is a share *s* of the emissions in the GEI basis, a factor change *d* moves "
         f"the total by *s·d*, crossing the {THRESHOLD:.0f}% materiality threshold "
         f"(SBTi) when *s* ≥ {THRESHOLD:.0f}% / |*d*|."),
        ("**Basis, not inventory.** Per BEE's procedure (p. 7 note, to be confirmed "
         "against the notified text), 2024-27 targets count only combustion and "
         "indirect (electricity) emissions, not process emissions. So *s* is the Scope 2 "
         "share of *that* basis, which is larger than the share of a full Scope 1+2 "
         "inventory for cement, steel and refining. See `docs/RQ3_FINDINGS.md`."),
        "## Four kinds of factor change",
        table(["kind", "what changes", "d", "Scope 2 share needed to cross 5%"], effects),
        "## Sensitivity curve: change in total emissions by Scope 2 share",
        table(["kind"] + [f"s = {s}%" for s in shares], curve),
        "**Bold** = at or above the 5% threshold.",
        "## Reading it",
        ("- **CEA's restatements of a past year are small**: revision alone does not "
         "cross 5% at any Scope 2 share for this series. Base-year recalculation "
         "triggered purely by CEA revising the base year's own factor is immaterial "
         "here.\n"
         "- **Which reading of 'latest', and the year-on-year step, are both just under "
         "5%**: alone, they cross only at Scope 2 shares near 100%. But they are the same "
         "size as the 1–3% GEI targets, which is RQ2's point, not RQ1's.\n"
         "- **The choice of series is the material one**: CEA's average series disagree "
         "by about 22%, so an entity whose basis is more than about a quarter grid "
         "electricity crosses 5% from the series choice alone. BEE's procedure does "
         "not name the series (RQ3)."),
        "## By sector",
        sectors,
    ]) + "\n", encoding="utf-8", newline="\n")
    print(f"RQ1 -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
