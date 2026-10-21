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

from figure_theme import write as write_figure

ROOT = Path(__file__).resolve().parents[1]
FACTORS = ROOT / "data" / "cea" / "factors.csv"
VERSIONS = ROOT / "data" / "cea" / "versions.csv"
SHARES = ROOT / "data" / "sector_scope2_shares.csv"
OUT = ROOT / "docs" / "RQ1_RESULTS.md"
FIG = ROOT / "docs" / "figures" / "rq1_sensitivity.svg"
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


# Figure: light surface only, palette checked with the dataviz validator.
INK, INK2, MUTED, GRIDLINE, AXIS, SURFACE = (
    "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb")
COLOURS = ["#2a78d6", "#eb6834", "#1baf7a"]  # fixed order: series, latest, revision


def figure(lines: list[tuple[str, float]]) -> str:
    """SVG of total change = share x |d|, one straight line per (label, |d| %)."""
    x0, x1, y0, y1, ymax = 56, 560, 380, 96, 25.0

    def px(share: float) -> float:
        return x0 + (x1 - x0) * share / 100

    def py(v: float) -> float:
        return y0 - (y0 - y1) * v / ymax

    def text(x: float, y: float, s: str, fill: str = INK2, anchor: str = "start",
             size: int = 12, weight: str = "400") -> str:
        return (f'<text x="{x:.1f}" y="{y:.1f}" fill="{fill}" text-anchor="{anchor}"'
                f' font-size="{size}" font-weight="{weight}">{s}</text>')

    out = [
        ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 440" role="img"'
         ' font-family="system-ui, -apple-system, Segoe UI, sans-serif"'
         ' aria-labelledby="t d">'),
        ('<title id="t">Change in total emissions from a grid-factor change alone,'
         ' by Scope 2 share</title>'),
        '<desc id="d">' + "; ".join(f"{n}: {d:.2f}% at a 100% share" for n, d in lines)
        + f". Threshold {THRESHOLD:.0f}%.</desc>",
        f'<rect width="760" height="440" fill="{SURFACE}"/>',
        text(x0, 28, "Change in total emissions from a grid-factor change alone",
             INK, size=15, weight="600"),
        text(x0, 46, "All-India grid factor, CEA CO2 Baseline Database v22.0;"
             " share is of the GEI target basis"),
    ]
    lx = x0
    for (name, _), colour in zip(lines, COLOURS, strict=True):  # legend
        out.append(f'<line x1="{lx}" x2="{lx + 18}" y1="68" y2="68" stroke="{colour}"'
                   ' stroke-width="2" stroke-linecap="round"/>')
        out.append(text(lx + 24, 72, name))
        lx += 24 + 7 * len(name) + 20
    for v in range(0, int(ymax) + 1, 5):
        out.append(f'<line x1="{x0}" x2="{x1}" y1="{py(v):.1f}" y2="{py(v):.1f}"'
                   f' stroke="{AXIS if v == 0 else GRIDLINE}" stroke-width="1"/>')
        out.append(text(x0 - 8, py(v) + 4, f"{v}%", MUTED, "end"))
    for s in range(0, 101, 20):
        out.append(text(px(s), y0 + 18, f"{s}%", MUTED, "middle"))
    out.append(text((x0 + x1) / 2, y0 + 40, "Scope 2 share of the GEI basis", INK2, "middle"))
    out.append(f'<line x1="{x0}" x2="{x1}" y1="{py(THRESHOLD):.1f}" y2="{py(THRESHOLD):.1f}"'
               f' stroke="{INK2}" stroke-width="1" stroke-dasharray="4 4"/>')
    out.append(text(x1 - 4, py(THRESHOLD) - 6,
                    f"{THRESHOLD:.0f}% materiality threshold (SBTi)", INK2, "end"))
    for (name, d), colour in zip(lines, COLOURS, strict=True):
        out.append(f'<line x1="{px(0):.1f}" y1="{py(0):.1f}" x2="{px(100):.1f}"'
                   f' y2="{py(d):.1f}" stroke="{colour}" stroke-width="2"'
                   f' stroke-linecap="round"><title>{name}: {d:.2f}% at a 100% share'
                   '</title></line>')
        out.append(f'<circle cx="{px(100):.1f}" cy="{py(d):.1f}" r="4" fill="{colour}"'
                   f' stroke="{SURFACE}" stroke-width="2"/>')
        out.append(text(px(100) + 10, py(d) + 4, f"{name.split(' (')[0]}: {d:.2f}%", INK))
        if d > THRESHOLD:  # mark where this line crosses the threshold
            s = 100 * THRESHOLD / d
            out.append(f'<circle cx="{px(s):.1f}" cy="{py(THRESHOLD):.1f}" r="4"'
                       f' fill="{SURFACE}" stroke="{INK}" stroke-width="2"/>')
            out.append(text(px(s) + 10, py(THRESHOLD) + 17, f"crosses at {s:.0f}%", INK))
    return "\n".join(out + ["</svg>"]) + "\n"


def effects() -> list[list[str]]:
    """The four kinds of factor change: [kind, what changes, d as '+x.xx%', share needed]."""
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

    rows = [
        ["revision", f"largest restatement of one FY ({rev_fy}), first vs latest version",
         f"{revisions[rev_fy]:+.2f}%"],
        ["step", "FY2025-26 (v22) vs FY2024-25 (v22)", f"{pct(v22_2526, v22_2425):+.2f}%"],
        ["latest", "BEE 'latest' before v22 (v21, FY2024-25) vs after (v22, FY2025-26)",
         f"{pct(v22_2526, v21_2425):+.2f}%"],
        ["series", "spread of CEA's four average series, v22 FY2025-26",
         f"{spread[('v22.0', 'FY2025-26')]:.2f}%"],
    ]
    for row in rows:
        row.append(share_needed(float(row[2].rstrip("%"))))
    return rows


def main() -> None:
    effects_ = effects()

    shares = [10, 20, 30, 40, 50, 60, 80, 100]
    curve = []
    for name, _, d, _ in effects_:
        dv = abs(float(d.rstrip("%")))
        curve.append([name] + [("**" if s * dv / 100 >= THRESHOLD else "")
                               + f"{s * dv / 100:.2f}%"
                               + ("**" if s * dv / 100 >= THRESHOLD else "")
                               for s in shares])

    d = {name: abs(float(v.rstrip("%"))) for name, _, v, _ in effects_}
    # ponytail: "latest" and "step" differ by 0.06 points and would overprint,
    # so the figure draws "latest" only; the table below it has both.
    write_figure(FIG, figure([("Series choice", d["series"]),
                              ("Reading of 'latest' (year step is within 0.1)", d["latest"]),
                              ("Revision of a past year", d["revision"])]))

    sectors = "_No sector rows yet: `data/sector_scope2_shares.csv` needs cited shares._"
    if SHARES.exists():
        with SHARES.open(encoding="utf-8") as fh:
            rows = [r for r in csv.DictReader(fh) if r.get("scope2_share_pct")]
        if rows:
            sectors = table(
                ["sector", "Scope 2 share of target basis", "source"] +
                [e[0] for e in effects_],
                [[r["sector"], f"{r['scope2_share_pct']}%", r["source"]] +
                 [f"{float(r['scope2_share_pct']) * abs(float(e[2].rstrip('%'))) / 100:.2f}%"
                  for e in effects_] for r in rows])

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
        table(["kind", "what changes", "d", "Scope 2 share needed to cross 5%"], effects_),
        "## Sensitivity curve: change in total emissions by Scope 2 share",
        ("![Three straight lines from the origin: series choice reaches 21.85% and "
         "crosses the 5% threshold at a 23% share; the reading of 'latest' reaches "
         "4.87% and revision 0.78%, neither crossing](figures/rq1_sensitivity.svg)"),
        "The same numbers as a table (`step` is not drawn: it overprints `latest`):",
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
