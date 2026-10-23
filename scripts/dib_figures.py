"""The two figures for the Data in Brief article (docs/paper/DATA_IN_BRIEF_ARTICLE.md).

    python scripts/dib_figures.py          # data/cea/*.csv -> docs/figures/dib_*.svg (+ _dark)
    python scripts/dib_figures.py --png    # also PNGs at 4x, for the journal's Word template
                                           # (needs playwright with Chromium; not a project dependency)

  Figure 1  The 23 versions: the date written in each workbook against the newest
            financial year it covers.
  Figure 2  One all-India series, every financial year: the spread of its values
            across the versions that published it.

No title is drawn inside the figures: the article's captions carry that. Only the
colours in figure_theme.DARK are used, so each figure has a checked dark twin.
Marker shape and fill, not colour alone, carry the distinctions.
"""
import csv
import sys
from datetime import date
from pathlib import Path
from statistics import median

from figure_theme import write as write_figure

ROOT = Path(__file__).resolve().parents[1]
FACTORS = ROOT / "data" / "cea" / "factors.csv"
VERSIONS = ROOT / "data" / "cea" / "versions.csv"
FIGS = ROOT / "docs" / "figures"
SERIES = "grid.weighted_avg.incl_imports"      # the longest all-India series
INK, INK2, MUTED, GRIDLINE, AXIS, SURFACE, BLUE, ORANGE = (
    "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb", "#2a78d6", "#eb6834")
HEAD = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 {h}" role="img"'
        ' font-family="system-ui, -apple-system, Segoe UI, sans-serif" aria-labelledby="t d">')


def text(x, y, s, fill=INK2, anchor="start", size=12, weight="400"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" fill="{fill}" text-anchor="{anchor}"'
            f' font-size="{size}" font-weight="{weight}">{s}</text>')


def load_versions():
    with VERSIONS.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def fy_index(fy):                       # "FY2004-05" -> 2004
    return int(fy[2:6])


def series_points():
    """{fy: [(ordinal, version, value), ...]} for SERIES, all-India, oldest first."""
    ordinal = {v["version_label"]: int(v["version_ordinal"]) for v in load_versions()}
    by_fy = {}
    with FACTORS.open(encoding="utf-8") as fh:
        for f in csv.DictReader(fh):
            if f["geography"] == "IN" and f["factor_key"] == SERIES:
                by_fy.setdefault(f["fy"], []).append(
                    (ordinal[f["version_label"]], f["version_label"], float(f["value"])))
    return {fy: sorted(v) for fy, v in sorted(by_fy.items())}


def outlier(by_fy):
    """The (fy, version, value, others' median) whose value is furthest from the median of the
    other versions of the same year, among years with at least three versions."""
    best = None
    for fy, obs in by_fy.items():
        if len(obs) < 3:
            continue
        for i, (_, ver, val) in enumerate(obs):
            rest = median(v for j, (_, _, v) in enumerate(obs) if j != i)
            dev = abs(val / rest - 1)
            if best is None or dev > best[0]:
                best = (dev, fy, ver, val, rest)
    return best[1:]


def figure_versions():
    vs = load_versions()
    x0, x1, y0, y1 = 70, 720, 360, 40
    d0, d1 = date(2006, 1, 1).toordinal(), date(2027, 1, 1).toordinal()
    f0, f1 = fy_index(vs[0]["covers_fy"]), fy_index(vs[-1]["covers_fy"])

    def px(d):
        return x0 + (x1 - x0) * (d.toordinal() - d0) / (d1 - d0)

    def py(f):
        return y0 - (y0 - y1) * (f - f0) / (f1 - f0)

    pts = [(px(date.fromisoformat(v["stated_date"])), py(fy_index(v["covers_fy"])), v) for v in vs]
    month_only = sum(v["date_precision"] != "day" for v in vs)
    out = [HEAD.format(h=440),
           '<title id="t">Versions of the CEA CO2 Baseline Database by date and newest year covered</title>',
           (f'<desc id="d">{len(vs)} versions from {vs[0]["stated_date"]} to {vs[-1]["stated_date"]}. '
            f'Each covers one more financial year than the one before, except version 1.1, which '
            f'covers the same year as version 1.0. {month_only} versions state only a month.</desc>'),
           f'<rect width="760" height="440" fill="{SURFACE}"/>']
    for f in range(f0, f1 + 1, 3):
        out.append(f'<line x1="{x0}" x2="{x1}" y1="{py(f):.1f}" y2="{py(f):.1f}" stroke="{GRIDLINE}"/>')
        out.append(text(x0 - 8, py(f) + 4, f"{f}-{str(f + 1)[2:]}", MUTED, "end", 11))
    for yr in range(2006, 2027, 4):
        x = px(date(yr, 1, 1))
        out.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{y0}" y2="{y0 + 5}" stroke="{AXIS}"/>')
        out.append(text(x, y0 + 20, str(yr), MUTED, "middle", 11))
    out.append(f'<line x1="{x0}" x2="{x1}" y1="{y0}" y2="{y0}" stroke="{AXIS}"/>')
    out.append(f'<polyline fill="none" stroke="{AXIS}" stroke-width="1.5" points="'
               + " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in pts) + '"/>')
    for x, y, v in pts:
        label = v["version_label"]
        if v["date_precision"] == "day":
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{BLUE}" stroke="{SURFACE}" stroke-width="2">'
                       f'<title>{label}, {v["stated_date"]}, newest year {v["covers_fy"]}</title></circle>')
        else:
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{SURFACE}" stroke="{BLUE}" stroke-width="2">'
                       f'<title>{label}, {v["stated_date"][:7]} (month only), newest year {v["covers_fy"]}</title></circle>')
    for x, y, v in pts:                  # selective labels: the ends, the first month-only version, the repeat
        if v["version_label"] in ("v1.0", "v11.0", "v22.0"):
            end = v["version_label"] == "v22.0"
            out.append(text(x - 10 if end else x + 11, y + 17 if v["version_label"] == "v11.0" else y + 4,
                            v["version_label"].replace("v", "version "), INK, "end" if end else "start", 12, "600"))
    out += [text((x0 + x1) / 2, y0 + 40, "Date written in the workbook", INK2, "middle"),
            (f'<text transform="translate(18,{(y0 + y1) / 2:.0f}) rotate(-90)" fill="{INK2}" text-anchor="middle" '
             f'font-size="12">Newest financial year in the version</text>'),
            f'<circle cx="{x0 + 8}" cy="424" r="5" fill="{BLUE}" stroke="{SURFACE}" stroke-width="2"/>',
            text(x0 + 20, 428, "day given", INK2, size=12),
            f'<circle cx="{x0 + 110}" cy="424" r="5" fill="{SURFACE}" stroke="{BLUE}" stroke-width="2"/>',
            text(x0 + 122, 428, f"month only, drawn at the first of the month ({month_only} versions)", INK2, size=12)]
    return "\n".join(out + ["</svg>"]) + "\n"


def figure_spread():
    by_fy = series_points()
    fys = list(by_fy)
    x0, x1, y0, y1 = 70, 730, 340, 40
    vals = [v for obs in by_fy.values() for _, _, v in obs]
    lo, hi = (int(min(vals) * 20) / 20), (int(max(vals) * 20) + 1) / 20
    slot = (x1 - x0) / len(fys)

    def px(i):
        return x0 + slot * (i + 0.5)

    def py(v):
        return y0 - (y0 - y1) * (v - lo) / (hi - lo)

    o_fy, o_ver, o_val, o_rest = outlier(by_fy)
    multi = sum(len(o) > 1 for o in by_fy.values())
    out = [HEAD.format(h=440),
           '<title id="t">Values of the all-India weighted average factor across CEA versions, by financial year</title>',
           (f'<desc id="d">{SERIES}. {multi} of {len(fys)} financial years appear in more than one version. '
            f'For {o_fy}, version {o_ver[1:]} gives {o_val:.4f} where the other versions give {o_rest:.4f}.</desc>'),
           f'<rect width="760" height="440" fill="{SURFACE}"/>']
    n = round((hi - lo) / 0.05)
    for k in range(n + 1):
        v = lo + 0.05 * k
        out.append(f'<line x1="{x0}" x2="{x1}" y1="{py(v):.1f}" y2="{py(v):.1f}" stroke="{GRIDLINE}"/>')
        out.append(text(x0 - 8, py(v) + 4, f"{v:.2f}", MUTED, "end", 11))
    for i, fy in enumerate(fys):
        if i == len(fys) - 1 or (i % 4 == 0 and len(fys) - 1 - i >= 3):   # never two labels touching
            out.append(text(px(i), y0 + 20, fy[2:], MUTED, "middle", 11))
        obs = by_fy[fy]
        if len(obs) > 1:
            top, bot = max(v for _, _, v in obs), min(v for _, _, v in obs)
            out.append(f'<line x1="{px(i):.1f}" x2="{px(i):.1f}" y1="{py(top):.1f}" y2="{py(bot):.1f}" '
                       f'stroke="{AXIS}" stroke-width="3" stroke-linecap="round"/>')
    out.append(f'<line x1="{x0}" x2="{x1}" y1="{y0}" y2="{y0}" stroke="{AXIS}"/>')
    for i, fy in enumerate(fys):
        obs = by_fy[fy]
        _, fver, fval = obs[0]
        _, lver, lval = obs[-1]
        if len(obs) > 1:
            out.append(f'<circle cx="{px(i):.1f}" cy="{py(fval):.1f}" r="4" fill="{SURFACE}" stroke="{INK2}" stroke-width="1.5">'
                       f'<title>{fy}: first published in {fver}: {fval:.4f}</title></circle>')
        out.append(f'<circle cx="{px(i):.1f}" cy="{py(lval):.1f}" r="4" fill="{BLUE}" stroke="{SURFACE}" stroke-width="1.5">'
                   f'<title>{fy}: latest, {lver}: {lval:.4f}</title></circle>')
        if fy == o_fy:
            ov = next(v for _, ver, v in obs if ver == o_ver)
            out.append(f'<path d="M{px(i):.1f},{py(ov) - 6:.1f} l6,6 l-6,6 l-6,-6 z" fill="{ORANGE}" stroke="{SURFACE}" stroke-width="1.5">'
                       f'<title>{fy}: {o_ver}: {ov:.4f}</title></path>')
            out.append(text(px(i) + 12, py(ov) + 4, f"{o_ver.replace('v', 'version ')[:-2]}: {ov:.4f}", INK, size=12, weight="600"))
    out += [text((x0 + x1) / 2, y0 + 38, "Financial year", INK2, "middle"),
            (f'<text transform="translate(18,{(y0 + y1) / 2:.0f}) rotate(-90)" fill="{INK2}" text-anchor="middle" '
             f'font-size="12">tCO2/MWh</text>'),
            f'<circle cx="{x0 + 8}" cy="396" r="4" fill="{BLUE}" stroke="{SURFACE}" stroke-width="1.5"/>',
            text(x0 + 20, 400, "latest value", INK2),
            f'<circle cx="{x0 + 262}" cy="396" r="4" fill="{SURFACE}" stroke="{INK2}" stroke-width="1.5"/>',
            text(x0 + 274, 400, "value in the first version that published the year", INK2),
            f'<line x1="{x0 + 8}" x2="{x0 + 8}" y1="414" y2="428" stroke="{AXIS}" stroke-width="3" stroke-linecap="round"/>',
            text(x0 + 20, 425, "range across all versions of that year", INK2),
            f'<path d="M{x0 + 262},414 l6,6 l-6,6 l-6,-6 z" fill="{ORANGE}"/>',
            text(x0 + 274, 425, "largest departure from the other versions of its year", INK2)]
    return "\n".join(out + ["</svg>"]) + "\n"


def to_png(name):
    from playwright.sync_api import sync_playwright
    svg = FIGS / f"{name}.svg"
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 760, "height": 440}, device_scale_factor=4)
        pg.goto(svg.as_uri())
        pg.locator("svg").screenshot(path=str(FIGS / f"{name}.png"))
        b.close()


def main():
    write_figure(FIGS / "dib_fig1_versions.svg", figure_versions())
    write_figure(FIGS / "dib_fig2_spread.svg", figure_spread())
    print("figures -> docs/figures/dib_fig1_versions.svg, dib_fig2_spread.svg")
    if "--png" in sys.argv:
        for name in ("dib_fig1_versions", "dib_fig2_spread"):
            to_png(name)
        print("PNGs at 4x written")


if __name__ == "__main__":
    main()
