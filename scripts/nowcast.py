"""Backtest of grid-factor nowcasts and the revision analysis.

    python scripts/nowcast.py   # data/cea/factors.csv -> docs/NOWCAST_RESULTS.md, figure

Method and limits: docs/NOWCAST.md. Code: src/carbonx/forecast/nowcast.py.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from figure_theme import write as write_figure

from carbonx.forecast import nowcast as nc

OUT = ROOT / "docs" / "NOWCAST_RESULTS.md"
FIG = ROOT / "docs" / "figures" / "nowcast_backtest.svg"
HEADLINE = "grid.weighted_avg.incl_imports"       # longest "average" series
ROBUSTNESS = ["grid.operating_margin.incl_imports", "grid.weighted_avg.excl_imports"]
USED = "grid.weighted_avg_incl_re_captive.incl_imports"   # engine/calculate.py
LEVELS = (0.8, 0.9)

INK, INK2, MUTED, GRIDLINE, AXIS, SURFACE, BLUE, ORANGE = (
    "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb", "#2a78d6", "#eb6834")


def table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return "\n".join(lines + ["| " + " | ".join(r) + " |" for r in rows])


def score_rows(targets: list[nc.Target]) -> list[list[str]]:
    return [[s.model, str(s.n), f"{s.mae:.2f}%", f"{s.rmse:.2f}%", f"{s.bias:+.2f}%",
             f"{s.worst:+.2f}%",
             "–" if s.model == nc.NAIVE else f"{s.beats_naive}/{s.comparable}",
             "–" if s.model == nc.NAIVE else f"{s.p_value:.2f}"]
            for s in nc.score(targets)]


def figure(targets: list[nc.Target], bands: list[tuple[int, float, float]]) -> str:
    """Actual first-published value against the naive nowcast, with the 80% band."""
    x0, x1, y0, y1 = 56, 730, 380, 100
    years = [t.year for t in targets]
    values = ([t.actual for t in targets] + [t.forecasts[nc.NAIVE] for t in targets]
              + [v for _, lo, hi in bands for v in (lo, hi)])
    lo = int(min(values) * 50) / 50          # round down to 0.02
    hi = int(max(values) * 50 + 1) / 50

    def px(year: int) -> float:
        return x0 + 20 + (x1 - x0 - 40) * (year - years[0]) / (years[-1] - years[0])

    def py(v: float) -> float:
        return y0 - (y0 - y1) * (v - lo) / (hi - lo)

    def text(x: float, y: float, s: str, fill: str = INK2, anchor: str = "start",
             size: int = 12, weight: str = "400") -> str:
        return (f'<text x="{x:.1f}" y="{y:.1f}" fill="{fill}" text-anchor="{anchor}"'
                f' font-size="{size}" font-weight="{weight}">{s}</text>')

    out = [
        ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 440" role="img"'
         ' font-family="system-ui, -apple-system, Segoe UI, sans-serif"'
         ' aria-labelledby="t d">'),
        '<title id="t">Each year\'s grid factor against the nowcast made before it was published</title>',
        (f'<desc id="d">{len(targets)} years. The nowcast is the previous year\'s value as'
         ' known at the time. Bars show the 80% band built from earlier errors.</desc>'),
        f'<rect width="760" height="440" fill="{SURFACE}"/>',
        text(x0, 28, "Each year's grid factor against the nowcast made before it was published",
             INK, size=15, weight="600"),
        text(x0, 46, f"All-India, {HEADLINE}, tCO2/MWh, as first published by CEA"),
        f'<line x1="{x0}" x2="{x0 + 18}" y1="68" y2="68" stroke="{BLUE}" stroke-width="2"/>',
        text(x0 + 24, 72, "Published value"),
        f'<circle cx="{x0 + 142}" cy="68" r="4" fill="{ORANGE}"/>',
        text(x0 + 152, 72, "Nowcast: last year's value"),
        f'<rect x="{x0 + 330}" y="61" width="6" height="14" fill="{AXIS}"/>',
        text(x0 + 342, 72, "80% band from earlier errors"),
    ]
    steps = round((hi - lo) / 0.02)
    for i in range(steps + 1):
        v = lo + 0.02 * i
        out.append(f'<line x1="{x0}" x2="{x1}" y1="{py(v):.1f}" y2="{py(v):.1f}"'
                   f' stroke="{GRIDLINE}" stroke-width="1"/>')
        out.append(text(x0 - 8, py(v) + 4, f"{v:.2f}", MUTED, "end"))
    for year, low, high in bands:
        out.append(f'<rect x="{px(year) - 3:.1f}" y="{py(high):.1f}" width="6"'
                   f' height="{py(low) - py(high):.1f}" fill="{AXIS}">'
                   f'<title>{nc.fy(year)}: 80% band {low:.4f} to {high:.4f}</title></rect>')
    runs: list[list[nc.Target]] = []   # the line breaks where a year was not usable
    for t in targets:
        if runs and runs[-1][-1].year == t.year - 1:
            runs[-1].append(t)
        else:
            runs.append([t])
    for run in runs:
        points = " ".join(f"{px(t.year):.1f},{py(t.actual):.1f}" for t in run)
        out.append(f'<polyline fill="none" stroke="{BLUE}" stroke-width="2"'
                   f' stroke-linejoin="round" points="{points}"/>')
        if len(run) == 1:
            out.append(f'<circle cx="{px(run[0].year):.1f}" cy="{py(run[0].actual):.1f}"'
                       f' r="3" fill="{BLUE}"/>')
    for t in targets:
        out.append(f'<circle cx="{px(t.year):.1f}" cy="{py(t.forecasts[nc.NAIVE]):.1f}" r="4"'
                   f' fill="{ORANGE}" stroke="{SURFACE}" stroke-width="2"><title>{nc.fy(t.year)}:'
                   f' nowcast {t.forecasts[nc.NAIVE]:.4f}, published {t.actual:.4f}'
                   f' ({t.error(nc.NAIVE):+.2f}%)</title></circle>')
        if (t.year - years[0]) % 4 == 0 or t.year == years[-1]:
            out.append(text(px(t.year), y0 + 18, nc.fy(t.year)[2:], MUTED, "middle", 11))
    out.append(text((x0 + x1) / 2, y0 + 40, "Financial year", INK2, "middle"))
    return "\n".join(out + ["</svg>"]) + "\n"


def main() -> None:
    reg = nc.load(ROOT / "data" / "cea" / "factors.csv", ROOT / "data" / "cea" / "versions.csv")
    targets, notes = nc.backtest(reg[HEADLINE])
    naive = next(s for s in nc.score(targets) if s.model == nc.NAIVE)
    best = min(nc.score(targets), key=lambda s: s.mae)
    cov = {lvl: nc.coverage(targets, lvl) for lvl in LEVELS}
    ratios = {t.year: t.actual / t.forecasts[nc.NAIVE] for t in targets}

    # Nowcasts for the series CarbonX uses. Its own history is too short to
    # give a band, so the band borrows the headline series' percentage errors.
    used = reg[USED]
    nowcasts, verdicts = [], []
    for year in (2025, 2026):
        ordinal = used[year][0][0] if year in used else 10 ** 9   # 2026: nothing published yet
        known = nc.as_known(used, ordinal)
        point = known[year - 1]
        past = [r for y, r in ratios.items() if y < year]
        row = [nc.fy(year), f"{point:.4f}"]
        actual = used[year][0][2] if year in used else None
        for lvl in LEVELS:
            low, high = nc.interval(point, past, lvl)
            row.append(f"{low:.4f} to {high:.4f}")
            if actual is not None and lvl == LEVELS[-1]:
                where = "inside" if low <= actual <= high else "outside"
                verdicts.append(
                    f"- **For the series CarbonX uses, the {nc.fy(year)} value fell {where} "
                    f"the {lvl:.0%} band** drawn from earlier years: published {actual:.4f}, "
                    f"band {low:.4f} to {high:.4f}."
                    + (" The fall that year was large by the standard of the previous two "
                       "decades." if where == "outside" else ""))
        row.append("not yet published" if actual is None
                   else f"{actual:.4f} ({100 * (point - actual) / actual:+.2f}% error)")
        nowcasts.append(row)

    rev_rows = []
    for key in (HEADLINE, USED):
        rev_rows += [[key, lag, str(n), f"{med:.3f}%", f"{big:.3f}%", f"{bias:+.3f}%"]
                     for lag, n, med, big, bias in nc.revision_summary(reg[key])]
    outliers = [(y, k, p) for y, k, p in nc.revisions(reg[HEADLINE]) if abs(p) > 2]
    final_median = next(r for r in nc.revision_summary(reg[HEADLINE]) if r[0] == "latest")[2]

    write_figure(FIG, figure(targets, cov[0.8][2]))

    robustness = []
    for key in ROBUSTNESS:
        t, _ = nc.backtest(reg[key])
        robustness += [f"### `{key}`", table(
            ["model", "years", "mean abs. error", "RMSE", "bias", "worst", "beats naive",
             "sign-test p"], score_rows(t))]
    used_targets, _ = nc.backtest(used)

    OUT.write_text("\n\n".join([
        "# Nowcast results: predicting the grid factor before CEA publishes it",
        "_Generated by `scripts/nowcast.py` from `data/cea/factors.csv`. Do not edit by hand._",
        ("Real data: CEA CO2 Baseline Database v1.0–v22.0. Each target is a financial "
         "year's **first-published** all-India value. Each forecast uses only values from "
         "versions published **before** that one (`docs/NOWCAST.md`). Errors are in percent "
         "of the published value."),
        ("**Scope 2 qualifier.** An error of *e* in the grid factor moves an entity's "
         "emission intensity by *e* times the Scope 2 share of its target basis "
         "(`docs/RQ1_RESULTS.md`), not by *e*."),
        "## Headline",
        (f"- **\"Use last year's value\" was wrong by {naive.mae:.2f}% on average** "
         f"(RMSE {naive.rmse:.2f}%, worst {naive.worst:+.2f}%) over {naive.n} years of "
         f"`{HEADLINE}`.\n"
         + ("- **Nothing simple beat it.** It had the lowest mean absolute error of the "
            "five models, and no alternative won in more than half of the years.\n"
            if best.model == nc.NAIVE else
            f"- Lowest mean absolute error: {best.model} ({best.mae:.2f}%).\n") +
         f"- **A band built from earlier errors held up:** the 80% band contained "
         f"{cov[0.8][0]} of {cov[0.8][1]} later values, the 90% band {cov[0.9][0]} of "
         f"{cov[0.9][1]}.\n"
         f"- **Which version matters far less than which year:** the median restatement "
         f"of a year, first to latest version, is {final_median:.3f}%, against a "
         f"{naive.mae:.2f}% mean error from using the wrong year.\n" + "\n".join(verdicts)),
        "![Published grid factor and the nowcast made before it, by year](figures/nowcast_backtest.svg)",
        f"## Backtest: `{HEADLINE}`",
        table(["model", "years", "mean abs. error", "RMSE", "bias", "worst", "beats naive",
               "sign-test p"], score_rows(targets)),
        ("*Beats naive* counts the years with a smaller absolute error than the naive "
         "forecast. The sign test asks whether that count differs from a coin toss; with "
         "about twenty years it can only detect a large difference. Five models were "
         "tried, so one small p-value among them would not be evidence either."),
        "Years not used: " + ("; ".join(notes) if notes else "none") + ".",
        "## The same backtest on other long series",
        *robustness,
        "## Nowcasts for the series CarbonX calculates with",
        (f"`{USED}` has only {len(used_targets)} usable one-year-ahead cases, too few to "
         "fit or test anything. The point nowcast is its own last known value. The band "
         "borrows the percentage errors of the headline series from earlier years, which "
         "assumes the two series miss by similar proportions: an assumption, not a result."),
        table(["year", "nowcast", "80% band", "90% band", "published"], nowcasts),
        (f"The {nowcasts[-1][0]} row is a prediction made on the v22.0 data, before CEA "
         "has published that year. It can be checked when the next version appears."),
        "## How CEA revises a year after first publishing it",
        table(["series", "restatement", "cases", "median abs. change", "largest", "mean signed"],
              rev_rows),
        ("*Restatement 1* is the first later version that republished the year, and so "
         "on; *latest* compares the first and the newest value."),
        ("**One anomaly.** " + "; ".join(
            f"{nc.fy(y)} moved by {p:+.2f}% at its restatement {k}" for y, k, p in outliers)
         + ". The value is in CEA's own workbook (v18.0, `Results!N13`, 0.7656; versions "
         "13 to 17 and 22 give 0.8237 for the same year). It is close to the "
         "renewables-inclusive figure one row below it. We do not know whether it is a "
         "slip or a deliberate one-off; it is a question for CEA. A reader of v18.0 alone "
         "would have seen it as the official value.") if outliers else "",
        "## What this does and does not show",
        ("- It **measures** the cost of the \"latest at the deadline\" reading of BEE's "
         "rule: historically about 2% of the factor, sometimes 5 to 6%.\n"
         "- It gives the grid factor an **empirical forecast band**. That is the "
         "uncertainty of a guess made before publication. It is not an uncertainty of "
         "the published factor, and `carbonx.uncertainty` does not use it.\n"
         "- It does **not** show that the factor is unpredictable in principle. It shows "
         "that about twenty yearly values cannot support anything beyond the naive "
         "forecast. A model using generation-mix data would do better, but CEA computes "
         "the factor from that data, so that would be accounting, not forecasting."),
    ]) + "\n", encoding="utf-8", newline="\n")
    print(f"nowcast -> {OUT.relative_to(ROOT)}: naive MAE {naive.mae:.2f}% over {naive.n} years;"
          f" 80% band covered {cov[0.8][0]}/{cov[0.8][1]}")


if __name__ == "__main__":
    main()
