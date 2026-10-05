"""RQ2: how large are year-on-year CEA factor changes, and how often do they
exceed the FY2025-26 CCTS GEI reduction target (1-3%)?

    python scripts/rq2_deltas.py   # data/cea/factors.csv -> docs/RQ2_RESULTS.md

All-India factors only. Two views of the same history:
  first-published: the step a reporter saw when each new FY first appeared
                   (FY t from the version that introduced it, vs FY t-1 in
                   that same version)
  revision:        how far a FY's value moved between the version that first
                   published it and the newest version
"""
import csv
from collections import defaultdict
from itertools import pairwise
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
FACTORS = ROOT / "data" / "cea" / "factors.csv"
VERSIONS = ROOT / "data" / "cea" / "versions.csv"
OUT = ROOT / "docs" / "RQ2_RESULTS.md"
FIG = ROOT / "docs" / "figures" / "rq2_steps.svg"
FIG_KEY = "grid.weighted_avg.incl_imports"  # the longest comparable series

# v20's own note: BM and CM for FY2023-24 onward include renewables, so the
# FY2022-23 -> FY2023-24 step for these keys is a method change, not physics.
METHOD_BREAK = {("grid.build_margin", "FY2023-24"), ("grid.combined_margin", "FY2023-24")}


def pct(new: float, old: float) -> float:
    return 100 * (new - old) / old


def table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return "\n".join(lines + ["| " + " | ".join(r) + " |" for r in rows])


# Figure: light surface only; one series, so one colour and no legend.
INK, INK2, MUTED, GRIDLINE, AXIS, SURFACE, BLUE = (
    "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb", "#2a78d6")


def figure(key: str, steps: list[tuple[str, float]]) -> str:
    """SVG bars of |step| per FY for one factor, over the 1-3% GEI target band."""
    x0, x1, y0, y1 = 56, 700, 380, 108
    ymax = int(max(abs(s) for _, s in steps)) + 1
    slot = (x1 - x0) / len(steps)
    w = min(16.0, slot - 2)  # at least a 2px surface gap between bars

    def py(v: float) -> float:
        return y0 - (y0 - y1) * v / ymax

    def text(x: float, y: float, s: str, fill: str = INK2, anchor: str = "start",
             size: int = 12, weight: str = "400") -> str:
        return (f'<text x="{x:.1f}" y="{y:.1f}" fill="{fill}" text-anchor="{anchor}"'
                f' font-size="{size}" font-weight="{weight}">{s}</text>')

    over1 = sum(abs(s) > 1 for _, s in steps)
    out = [
        ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 440" role="img"'
         ' font-family="system-ui, -apple-system, Segoe UI, sans-serif"'
         ' aria-labelledby="t d">'),
        '<title id="t">Size of each year-on-year change in the all-India grid factor</title>',
        (f'<desc id="d">{over1} of {len(steps)} steps exceed 1%; the largest is'
         f' {max(abs(s) for _, s in steps):.2f}%. Shaded band: 1 to 3%.</desc>'),
        f'<rect width="760" height="440" fill="{SURFACE}"/>',
        text(x0, 28, "Size of each year-on-year change in the all-India grid factor",
             INK, size=15, weight="600"),
        text(x0, 46, f"|change| as first published by CEA, {key}"),
        text(x0, 64, "Comparable to the GEI target only for an entity whose basis"
             " is entirely Scope 2 (see RQ1)"),
        (f'<rect x="{x0}" y="{py(3):.1f}" width="{x1 - x0}" height="{py(1) - py(3):.1f}"'
         f' fill="{GRIDLINE}" opacity="0.6"/>'),
    ]
    for v in range(ymax + 1):
        out.append(f'<line x1="{x0}" x2="{x1}" y1="{py(v):.1f}" y2="{py(v):.1f}"'
                   f' stroke="{AXIS if v == 0 else GRIDLINE}" stroke-width="1"/>')
        out.append(text(x0 - 8, py(v) + 4, f"{v}%", MUTED, "end"))
    out.append(f'<rect x="{x0}" y="76" width="18" height="10" fill="{GRIDLINE}"/>')
    out.append(text(x0 + 24, 86, "FY2025-26 GEI reduction target: 1–3%", INK2))
    top = max(steps, key=lambda fs: abs(fs[1]))
    for i, (fy, step) in enumerate(steps):
        x, h = x0 + slot * i + (slot - w) / 2, y0 - py(abs(step))
        r = min(4.0, h)  # rounded data end, square at the baseline
        out.append(
            f'<path d="M{x:.1f},{y0} v{-(h - r):.1f} q0,{-r:.1f} {r:.1f},{-r:.1f}'
            f' h{w - 2 * r:.1f} q{r:.1f},0 {r:.1f},{r:.1f} v{h - r:.1f} z" fill="{BLUE}">'
            f'<title>{fy}: {step:+.2f}%</title></path>')
        if (fy, step) in (top, steps[-1]):  # selective labels: largest and latest
            out.append(text(x + w / 2, py(abs(step)) - 6, f"{step:+.2f}%", INK, "middle"))
        if i % 4 == 0 or i == len(steps) - 1:
            out.append(text(x + w / 2, y0 + 18, fy[2:], MUTED, "middle", 11))
    out.append(text((x0 + x1) / 2, y0 + 40, "Financial year the change arrived in",
                    INK2, "middle"))
    return "\n".join(out + ["</svg>"]) + "\n"


def main() -> None:
    with VERSIONS.open(encoding="utf-8") as fh:
        ordinal = {v["version_label"]: int(v["version_ordinal"]) for v in csv.DictReader(fh)}
    # series[key][fy] = [(ordinal, version, value), ...] oldest first
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

    summary, detail, drawn = [], [], []
    for key in sorted(series):
        by_fy = series[key]
        fys = sorted(by_fy)
        steps: list[float] = []
        for prev, fy in pairwise(fys):
            _, first_v, value = by_fy[fy][0]
            same = [x for x in by_fy[prev] if x[1] == first_v]
            if not same:
                continue  # introducing version did not restate the prior FY
            step = pct(value, same[0][2])
            broken = any(key.startswith(k) and fy == b for k, b in METHOD_BREAK)
            detail.append([key, f"{prev} → {fy}", first_v, f"{step:+.2f}%",
                           "method change" if broken else ""])
            if not broken:
                steps.append(step)
                if key == FIG_KEY:
                    drawn.append((fy, step))
        revisions = [abs(pct(obs[-1][2], obs[0][2])) for obs in by_fy.values()
                     if len(obs) > 1]
        if not steps:
            continue
        mags = [abs(s) for s in steps]
        summary.append([
            key, f"{fys[0]}–{fys[-1]}", str(len(steps)),
            f"{median(mags):.2f}%", f"{max(mags):.2f}%",
            f"{sum(m > 1 for m in mags)}/{len(mags)}",
            f"{sum(m > 3 for m in mags)}/{len(mags)}",
            f"{median(revisions):.2f}%" if revisions else "–",
            f"{max(revisions):.2f}%" if revisions else "–",
        ])

    FIG.parent.mkdir(exist_ok=True)
    FIG.write_text(figure(FIG_KEY, drawn), encoding="utf-8", newline="\n")

    OUT.write_text("\n\n".join([
        "# RQ2 results: CEA year-on-year factor changes",
        ("_Generated by `scripts/rq2_deltas.py` from `data/cea/factors.csv`. "
         "Do not edit by hand._"),
        ("All-India factors, CEA CO2 Baseline Database v1.0–v22.0. "
        "**Step** = first-published year-on-year change (the change a reporter "
        "saw when a new FY first appeared). **Revision** = movement of one FY's "
        "value between the version that first published it and the newest one. "
        "Steps flagged as method changes are excluded from the summary. "
         "They are not noise to discard: if FY2023-24 is the CCTS baseline year "
         "(unverified; see docs/RQ3_FINDINGS.md), this break lands on it."),
        ("**Scope 2 qualifier.** CCTS GEI targets cover Scope 1 and Scope 2. A "
        "grid factor change moves total GEI only in proportion to the Scope 2 "
        "share, so comparing these steps directly to the 1–3% target holds only "
        "for an entity whose emissions are entirely Scope 2. The per-sector "
        "answer is RQ1."),
        (f"![Bars of the size of each year-on-year change in `{FIG_KEY}`, against a "
         "shaded 1 to 3% band](figures/rq2_steps.svg)"),
        "## Summary",
        table(["factor", "FYs", "steps", "median \\|step\\|", "max \\|step\\|",
               "\\|step\\| > 1%", "\\|step\\| > 3%", "median revision",
               "max revision"], summary),
        "## Every step",
        table(["factor", "step", "first published in", "change", "note"], detail),
    ]) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(detail)} steps over {len(summary)} factors -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
