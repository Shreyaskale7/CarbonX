"""Every number, table and figure in the IEEE paper (paper/main.tex), from the data.

    python scripts/paper_build.py              # data/cea/*.csv -> paper/numbers.tex, paper/tables/*.tex
    python scripts/paper_build.py --figures    # also paper/figs/*.pdf (needs matplotlib)
    python scripts/paper_build.py --check      # fail unless the committed files equal what the data give

main.tex holds no literal figure of its own: it uses the macros in numbers.tex and
the files in tables/ and figs/. tests/test_paper.py enforces that. The arithmetic
reuses the functions that write docs/RQ1_RESULTS.md, RQ3_COMPLIANCE.md and
NOWCAST_RESULTS.md, and is cross-checked against docs/RQ2_RESULTS.md, so the paper,
the docs and the console cannot say different things. Nothing here is typed in.
"""
import csv
import hashlib
import json
import sys
from collections import defaultdict
from itertools import pairwise
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import rq1_materiality as rq1
import rq3_compliance as rq3

from carbonx.forecast import nowcast as nc

PAPER = ROOT / "paper"
FACTORS, VERSIONS = ROOT / "data" / "cea" / "factors.csv", ROOT / "data" / "cea" / "versions.csv"
MANIFEST = ROOT / "data" / "cea" / "manifest.json"
HEADLINE = "grid.weighted_avg.incl_imports"             # the longest all-India "average" series
USED = rq3.GRID                                         # the series with renewables and captive plants
DEADLINE = "31 July 2026"                               # first CCTS compliance deadline (CLAUDE.md, domain facts)
LONG_SERIES = ["grid.weighted_avg.excl_imports", "grid.weighted_avg.incl_imports",
               "grid.operating_margin.excl_imports", "grid.operating_margin.incl_imports",
               "grid.combined_margin.excl_imports", "grid.combined_margin.incl_imports",
               "grid.build_margin.excl_imports"]
SHORT = {"grid.weighted_avg.excl_imports": "Weighted average, excl. imports",
         "grid.weighted_avg.incl_imports": "Weighted average, incl. imports",
         "grid.operating_margin.excl_imports": "Operating margin, excl. imports",
         "grid.operating_margin.incl_imports": "Operating margin, incl. imports",
         "grid.combined_margin.excl_imports": "Combined margin, excl. imports",
         "grid.combined_margin.incl_imports": "Combined margin, incl. imports",
         "grid.build_margin.excl_imports": "Build margin, excl. imports"}
METHOD_BREAK = {("grid.build_margin", "FY2023-24"), ("grid.combined_margin", "FY2023-24")}
SHARES = [10, 20, 30, 40, 50, 60, 80, 100]
LEVELS = (0.8, 0.9)                                     # band levels, as scripts/nowcast.py
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]


def pct(new: float, old: float) -> float:
    return 100 * (new - old) / old


def thousands(n: int) -> str:
    return f"{n:,}"


def long_date(iso: str) -> str:
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{d} {MONTHS[m - 1]} {y}"


def month_year(iso: str) -> str:
    y, m, _ = (int(x) for x in iso.split("-"))
    return f"{MONTHS[m - 1]} {y}"


def tex_share(text: str) -> str:
    """Escape the percent sign (a bare one starts a LaTeX comment); 'never (...)' becomes 'never'."""
    return "never" if text.startswith("never") else text.replace("%", "\\%")


def read_rows():
    with FACTORS.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    with VERSIONS.open(encoding="utf-8") as fh:
        versions = list(csv.DictReader(fh))
    return rows, versions


def series_by_fy(rows, ordinal):
    out = defaultdict(lambda: defaultdict(list))
    for f in rows:
        if f["geography"] == "IN":
            out[f["factor_key"]][f["fy"]].append((ordinal[f["version_label"]], f["version_label"], float(f["value"])))
    for by_fy in out.values():
        for obs in by_fy.values():
            obs.sort()
    return out


def first_steps(key, by_fy):
    """First-published year-on-year steps, as scripts/rq2_deltas.py defines them."""
    fys, steps = sorted(by_fy), []
    for prev, fy in pairwise(fys):
        _, first_v, value = by_fy[fy][0]
        same = [x for x in by_fy[prev] if x[1] == first_v]
        if not same:
            continue
        if any(key.startswith(k) and fy == b for k, b in METHOD_BREAK):
            continue
        steps.append((fy, pct(value, same[0][2])))
    return steps


def revisions(by_fy):
    return [abs(pct(o[-1][2], o[0][2])) for o in by_fy.values() if len(o) > 1]


def compute() -> dict:
    rows, versions = read_rows()
    ordinal = {v["version_label"]: int(v["version_ordinal"]) for v in versions}
    series = series_by_fy(rows, ordinal)
    value, first = rq3.load_values()
    n: dict[str, str] = {}

    # data
    n["nVersions"] = str(len(versions))
    n["nValues"] = thousands(len(rows))
    n["nIndia"] = thousands(sum(r["geography"] == "IN" for r in rows))
    fys = sorted({r["fy"] for r in rows})
    n["nYears"], n["firstFY"], n["lastFY"] = str(len(fys)), fys[0][2:], fys[-1][2:]
    n["nSeriesKeys"] = str(len({r["factor_key"] for r in rows}))
    n["dateFirst"], n["dateLast"] = month_year(versions[0]["stated_date"]), month_year(versions[-1]["stated_date"])
    n["yearFirst"], n["yearLast"] = versions[0]["stated_date"][:4], versions[-1]["stated_date"][:4]
    n["lastVersion"] = versions[-1]["version_label"].replace("v", "").replace(".0", "")
    n["lastStated"], n["deadline"] = long_date(versions[-1]["stated_date"]), DEADLINE
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    last_url = next(v for v in manifest["versions"] if v["version_label"] == versions[-1]["version_label"])["database"]["url"]
    n["uploadFolder"] = "/".join(last_url.split("/baseline/")[1].split("/")[:2])
    n["shaFactors"] = hashlib.sha256(FACTORS.read_bytes()).hexdigest()[:12]
    n["shaVersions"] = hashlib.sha256(VERSIONS.read_bytes()).hexdigest()[:12]

    # the readings (baseline FY2023-24, as scripts/rq3_compliance.py)
    base = rq3.DEFAULT_BASELINE
    rd = rq3.readings(value, first, base)
    f_base, f_dead, f_after = (value[(first[base], base)], value[(rq3.AT_DEADLINE, "FY2024-25")], value[(rq3.AFTER, "FY2025-26")])
    d_dead, d_after = rd[1][2], rd[2][2]
    n.update(fyAssess="2025-26", fyAtDeadline="2024-25", verDeadline=rq3.AT_DEADLINE[1:3], verAfter=rq3.AFTER[1:3],
             tgtLow=f"{rq3.TARGETS[0]:.0f}", tgtHigh=f"{rq3.TARGETS[1]:.0f}", thresh=f"{rq1.THRESHOLD:.0f}",
             baseYear=base[2:], fBase=f"{f_base:.4f}", fDeadline=f"{f_dead:.4f}", fAfter=f"{f_after:.4f}",
             dDeadline=f"{abs(d_dead):.2f}", dAfter=f"{abs(d_after):.2f}",
             gapReadings=f"{abs(pct(f_after, f_dead)):.2f}",
             shNeeded1After=f"{100 * 1 / abs(d_after):.0f}", shNeeded3After=f"{100 * 3 / abs(d_after):.0f}",
             shNeeded1Deadline=f"{100 * 1 / abs(d_dead):.0f}")
    reading_rows = []
    for (name, used, d), label in zip(rd, ["Same factor as the baseline year", "Latest at the reporting deadline",
                                          "Latest once the FY2025-26 factor exists"], strict=True):
        shown = used.split(" (")[0]
        ver = used.split("(")[1].rstrip(")")
        reading_rows.append(f"{label} & {shown} & {ver.split(', ')[0].replace('.0', '')} & "
                            f"{'$-$' if d < 0 else ''}{abs(d):.2f}\\% & "
                            f"{tex_share(rq3.share_needed(d, 1.0))} & {tex_share(rq3.share_needed(d, 3.0))} \\\\")

    # the four average series, same version and year
    def spread(version, fy):
        vals = [x[2] for k in rq1.SERIES for x in series[k].get(fy, []) if x[1] == version]
        return min(vals), max(vals), pct(max(vals), min(vals))
    lo22, hi22, sp22 = spread("v22.0", "FY2025-26")
    _, _, sp21 = spread("v21.0", "FY2024-25")
    n.update(avgLow=f"{lo22:.4f}", avgHigh=f"{hi22:.4f}", spreadTwoTwo=f"{sp22:.2f}", spreadTwoOne=f"{sp21:.1f}",
             shareSeries=f"{100 * 5 / sp22:.0f}")
    effects = {e[0]: float(e[2].rstrip("%")) for e in rq1.effects()}
    n["revLargestFY"] = max(((fy, abs(pct(o[-1][2], o[0][2]))) for fy, o in series[USED].items() if len(o) > 1),
                            key=lambda t: t[1])[0][2:]

    # year-on-year steps, headline series, and the long series table
    steps = first_steps(HEADLINE, series[HEADLINE])
    mags = [abs(s) for _, s in steps]
    revs = revisions(series[HEADLINE])
    n.update(nSteps=str(len(steps)), nOverOne=str(sum(m > 1 for m in mags)), nOverThree=str(sum(m > 3 for m in mags)),
             medStep=f"{median(mags):.2f}", maxStep=f"{max(mags):.2f}", lastStep=f"{abs(steps[-1][1]):.2f}",
             lastStepFY=steps[-1][0][2:], medRev=f"{median(revs):.2f}", maxRev=f"{max(revs):.2f}")
    step_rows = []
    for key in LONG_SERIES:
        st = first_steps(key, series[key])
        m = [abs(s) for _, s in st]
        r = revisions(series[key])
        step_rows.append(f"{SHORT[key]} & {len(m)} & {median(m):.2f}\\% & {max(m):.2f}\\% & {sum(x > 1 for x in m)} & "
                         f"{sum(x > 3 for x in m)} & {median(r):.2f}\\% \\\\")

    # the nowcast backtest
    reg = nc.load(FACTORS, VERSIONS)
    targets, _ = nc.backtest(reg[HEADLINE])
    scores = nc.score(targets)
    naive = next(s for s in scores if s.model == nc.NAIVE)
    c80, t80, _ = nc.coverage(targets, LEVELS[0])
    c90, t90, _ = nc.coverage(targets, LEVELS[1])
    beating = sum(1 for s in scores if s.model != nc.NAIVE and s.mae < naive.mae and s.p_value < 0.05)
    n.update(lvlLow=f"{100 * LEVELS[0]:.0f}", lvlHigh=f"{100 * LEVELS[1]:.0f}", nTargets=str(naive.n), naiveMAE=f"{naive.mae:.2f}", naiveRMSE=f"{naive.rmse:.2f}",
             naiveWorst=f"{abs(naive.worst):.2f}", covEighty=str(c80), covEightyOf=str(t80),
             covNinety=str(c90), covNinetyOf=str(t90), nBeating=str(beating), nModels=str(len(scores) - 1))
    model_rows = [f"{s.model} & {s.mae:.2f}\\% & {s.rmse:.2f}\\% & "
                  f"{'--' if s.model == nc.NAIVE else f'{s.beats_naive}/{s.comparable}'} & "
                  f"{'--' if s.model == nc.NAIVE else f'{s.p_value:.2f}'} \\\\" for s in scores]
    used_series = reg[USED]                      # the band for the series with renewables and captive plants
    ratios = {t.year: t.actual / t.forecasts[nc.NAIVE] for t in targets}
    ordinal_new = used_series[2025][0][0]
    point = nc.as_known(used_series, ordinal_new)[2024]
    low, high = nc.interval(point, [r for y, r in ratios.items() if y < 2025], LEVELS[1])
    n.update(bandLow=f"{low:.4f}", bandHigh=f"{high:.4f}", bandPublished=f"{used_series[2025][0][2]:.4f}",
             bandOutside="outside" if not low <= used_series[2025][0][2] <= high else "inside")

    # the sensitivity curve, as numbers for the table of shares
    sens_rows = " & ".join(f"{s}\\%" for s in SHARES)
    n["effectSeries"], n["effectLatest"] = f"{effects['series']:.2f}", f"{abs(effects['latest']):.2f}"
    n["effectRevision"] = f"{abs(effects['revision']):.2f}"

    v22_series = [k for k in rq1.SERIES if any(x[1] == "v22.0" for x in series[k].get("FY2025-26", []))]
    plot = {"candidates": [("baseline", f_base, "v20"), ("deadline", f_dead, "v21")]
            + [(k, series[k]["FY2025-26"][-1][2], "v22") for k in v22_series],
            "kinds": {k: abs(v) for k, v in effects.items()}, "steps": steps,
            "errors": [(nc.fy(t.year), t.error(nc.NAIVE)) for t in targets]}
    return {"n": n, "tables": {"tab_readings": "\n".join(reading_rows), "tab_steps": "\n".join(step_rows),
                                "tab_nowcast": "\n".join(model_rows), "sens_header": sens_rows},
            "plot": plot, "series": series}


def render_numbers(n: dict) -> str:
    head = "% Generated by scripts/paper_build.py from data/cea/*.csv. Do not edit by hand.\n"
    return head + "".join(f"\\newcommand{{\\{k}}}{{{v}}}\n" for k, v in sorted(n.items()))


def render_tables(t: dict) -> dict[str, str]:
    return {name: "% Generated by scripts/paper_build.py. Do not edit by hand.\n" + body + "\n"
            for name, body in t.items() if name != "sens_header"}


def figures(res: dict, outdir: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
                         "font.size": 8, "axes.linewidth": 0.6, "pdf.fonttype": 42, "ps.fonttype": 42,
                         "svg.hashsalt": "carbonx"})
    outdir.mkdir(parents=True, exist_ok=True)
    meta = {"CreationDate": None, "Creator": None, "Producer": None}
    plot = res["plot"]
    ink, mid, lt = "#000000", "#555555", "#bbbbbb"

    fig, ax = plt.subplots(figsize=(3.4, 2.3))                                  # Fig. 1: candidate factors
    names = {"baseline": "baseline year FY" + res["n"]["baseYear"] + " (v20)", "deadline": "latest at deadline (v21)",
             "grid.weighted_avg.excl_imports": "v22: average, excl. imports",
             "grid.weighted_avg.incl_imports": "v22: average, incl. imports",
             "grid.weighted_avg_incl_re_captive.excl_imports": "v22: avg.+RE+captive, excl. imp.",
             "grid.weighted_avg_incl_re_captive.incl_imports": "v22: avg.+RE+captive, incl. imp."}
    pts = [(names[label], v, ver) for label, v, ver in plot["candidates"]]
    ys = list(range(len(pts)))[::-1]
    for y, (label, v, ver) in zip(ys, pts, strict=True):
        ax.plot([v], [y], marker={"v20": "s", "v21": "^", "v22": "o"}[ver], color=ink, ms=4.5, mfc="white" if ver != "v22" else ink)
        ax.annotate(f"{v:.4f}", (v, y), xytext=(5, -2.5), textcoords="offset points", fontsize=7, color=mid)
    ax.set_yticks(ys, [p[0] for p in pts], fontsize=6.5)
    ax.set_xlabel("Grid emission factor (tCO$_2$/MWh)")
    ax.set_xlim(0.64, 0.91)
    ax.grid(axis="x", color=lt, lw=0.4)
    fig.subplots_adjust(left=0.45, right=0.97, top=0.97, bottom=0.2)
    fig.savefig(outdir / "fig_candidates.pdf", metadata=meta)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(3.4, 2.2))                                  # Fig. 2: sensitivity
    xs = [0, 100]
    style = {"series": ("-", ink, "series choice"), "latest": ("--", mid, "reading of ``latest''"),
             "revision": (":", mid, "revision of a past year")}
    for k, (ls, c, lab) in style.items():
        ax.plot(xs, [0, plot["kinds"][k]], ls, color=c, lw=1.2, label=lab.replace("``", '"').replace("''", '"'))
    ax.axhline(5, color=ink, lw=0.6)
    ax.text(1, 5.5, "5% threshold", fontsize=7)
    ax.set_xlabel("Scope 2 share of the target basis (%)")
    ax.set_ylabel("Change in total (%)")
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 25)
    ax.legend(frameon=False, fontsize=7, loc="upper left", bbox_to_anchor=(0.0, 0.92))
    ax.grid(color=lt, lw=0.4)
    fig.tight_layout(pad=0.4)
    fig.savefig(outdir / "fig_sensitivity.pdf", metadata=meta)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(3.4, 2.1))                                  # Fig. 3: step sizes
    steps = plot["steps"]
    ax.axhspan(1, 3, color="#dddddd", lw=0)
    ax.bar(range(len(steps)), [abs(s) for _, s in steps], width=0.7, color=mid)
    ax.set_xticks(range(0, len(steps), 4), [steps[i][0][2:] for i in range(0, len(steps), 4)], fontsize=6, rotation=45, ha="right")
    ax.set_ylabel("|Year-on-year change| (%)")
    ax.set_xlabel("Financial year the change arrived in")
    ax.text(len(steps) - 1, 3.15, "1 to 3%", fontsize=7, ha="right")
    fig.tight_layout(pad=0.4)
    fig.savefig(outdir / "fig_steps.pdf", metadata=meta)
    plt.close(fig)


def outputs(res: dict) -> dict[Path, str]:
    out = {PAPER / "numbers.tex": render_numbers(res["n"])}
    out.update({PAPER / "tables" / f"{k}.tex": v for k, v in render_tables(res["tables"]).items()})
    return out


def submit_check() -> None:
    text = (PAPER / "main.tex").read_text(encoding="utf-8")
    body = text[text.index("\\begin{document}"):]
    found = body.count("\\verify{")
    if found:
        sys.exit(f"{found} open \\verify items remain in paper/main.tex: resolve each before submitting")
    print("no open \\verify items")


def main() -> None:
    if "--submit-check" in sys.argv:
        return submit_check()
    res = compute()
    files = outputs(res)
    if "--check" in sys.argv:
        bad = [p.relative_to(ROOT) for p, text in files.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
        if bad:
            sys.exit(f"stale: {[str(b) for b in bad]}; run python scripts/paper_build.py")
        print("paper numbers and tables equal what the data give")
        return
    for p, text in files.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
    print(f"{len(res['n'])} numbers and {len(files) - 1} tables -> paper/")
    if "--figures" in sys.argv:
        figures(res, PAPER / "figs")
        print("figures -> paper/figs/")


if __name__ == "__main__":
    main()
