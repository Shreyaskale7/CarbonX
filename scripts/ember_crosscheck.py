"""Cross-check CEA's grid factor against Ember's independent estimate, and test
Ember's monthly data as an early indicator of the year CEA has not published.

    python scripts/ember_crosscheck.py   # -> data/ember/*.csv (if raw present), docs/EMBER_CROSSCHECK.md

Ember (ember-energy.org) publishes monthly generation and power-sector emissions
for India under CC BY 4.0. The raw file is large and is not committed; the
national monthly extract this script makes from it is, so the analysis runs
without the download. See data/ember/README.md.

The indicator is deliberately the simplest one: scale last year's CEA factor by
the change in Ember's intensity over the same months.
"""
import csv
import hashlib
import sys
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carbonx.forecast import nowcast as nc

RAW = ROOT / "data" / "raw" / "ember" / "india_monthly_full_release_long_format.csv"
EXTRACT = ROOT / "data" / "ember" / "india_monthly_national.csv"
OUT = ROOT / "docs" / "EMBER_CROSSCHECK.md"
SERIES = {"weighted average, incl. imports": "grid.weighted_avg.incl_imports",
          "incl. renewables and captive, incl. imports (used by CarbonX)":
              "grid.weighted_avg_incl_re_captive.incl_imports"}


def extract() -> str | None:
    """National monthly generation and emissions from the raw download."""
    if not RAW.exists():
        return None
    months: dict[str, dict[str, str]] = {}
    with RAW.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["State"] != "India Total":
                continue
            if r["Variable"] == "Total Generation" and r["Unit"] == "GWh":
                months.setdefault(r["Date"], {})["generation_gwh"] = r["Value"]
            elif r["Variable"] == "Total emissions" and r["Unit"] == "ktCO2":
                months.setdefault(r["Date"], {})["emissions_ktco2"] = r["Value"]
    EXTRACT.parent.mkdir(parents=True, exist_ok=True)
    with EXTRACT.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("month,generation_gwh,emissions_ktco2\n")
        for month in sorted(months):
            if len(months[month]) == 2:
                fh.write(f"{month[:7]},{months[month]['generation_gwh']},"
                         f"{months[month]['emissions_ktco2']}\n")
    return hashlib.sha256(RAW.read_bytes()).hexdigest()


def monthly() -> dict[tuple[int, int], tuple[float, float]]:
    """(FY start year, month) -> (generation GWh, emissions ktCO2)."""
    out = {}
    with EXTRACT.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            year, month = int(r["month"][:4]), int(r["month"][5:7])
            out[(year if month >= 4 else year - 1, month)] = (
                float(r["generation_gwh"]), float(r["emissions_ktco2"]))
    return out


def intensity(data: dict, year: int, months: set[int]) -> float | None:
    """tCO2/MWh over the given months of a financial year (ktCO2/GWh is the same unit)."""
    rows = [data.get((year, m)) for m in months]
    if any(r is None for r in rows):
        return None
    return sum(r[1] for r in rows) / sum(r[0] for r in rows)


def table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return "\n".join(lines + ["| " + " | ".join(r) + " |" for r in rows])


def pct(new: float, old: float) -> float:
    return 100 * (new / old - 1)


def main() -> None:
    extract()
    data = monthly()
    reg = nc.load(ROOT / "data" / "cea" / "factors.csv", ROOT / "data" / "cea" / "versions.csv")
    years = sorted({y for y, _ in data})
    have = {y: {m for yy, m in data if yy == y} for y in years}
    full = [y for y in years if len(have[y]) == 12]
    last_month = max(f"{y + (m < 4)}-{m:02d}" for y, m in data)

    # ---- levels and year-on-year changes, on years Ember covers completely
    levels, changes, agree = [], [], []
    for y in full:
        e = intensity(data, y, have[y])
        row = [nc.fy(y), f"{e:.4f}"]
        for key in SERIES.values():
            obs = reg[key].get(y)
            row.append(f"{obs[-1][2]:.4f} ({pct(obs[-1][2], e):+.1f}%)" if obs else "–")
        levels.append(row)
        if y - 1 in full:
            ember_change = pct(e, intensity(data, y - 1, have[y - 1]))
            row = [f"{nc.fy(y - 1)} → {nc.fy(y)}", f"{ember_change:+.2f}%"]
            for key in SERIES.values():
                a, b = reg[key].get(y), reg[key].get(y - 1)
                if a and b:
                    cea_change = pct(a[-1][2], b[-1][2])
                    row.append(f"{cea_change:+.2f}%")
                    agree.append((ember_change > 0) == (cea_change > 0))
                else:
                    row.append("–")
            changes.append(row)

    # ---- indicator: last year's CEA factor x Ember's change over the same months
    results, errors = [], {"naive": [], "ember": []}
    by_series: dict[str, list[tuple[float, float]]] = {}
    for label, key in SERIES.items():
        targets, _ = nc.backtest(reg[key])
        for t in targets:
            months = have.get(t.year, set()) & have.get(t.year - 1, set())
            now = intensity(data, t.year, months) if months else None
            before = intensity(data, t.year - 1, months) if months else None
            if not now or not before:
                continue
            naive = t.forecasts[nc.NAIVE]
            adjusted = naive * now / before
            e_naive, e_ember = pct(naive, t.actual), pct(adjusted, t.actual)
            by_series.setdefault(label, []).append((abs(e_naive), abs(e_ember)))
            errors["naive"].append(abs(e_naive))
            errors["ember"].append(abs(e_ember))
            results.append([label, nc.fy(t.year), str(len(months)), f"{t.actual:.4f}",
                            f"{naive:.4f} ({e_naive:+.2f}%)", f"{adjusted:.4f} ({e_ember:+.2f}%)",
                            "Ember-adjusted" if abs(e_ember) < abs(e_naive) else "naive"])
    wins = sum(r[-1] == "Ember-adjusted" for r in results)

    OUT.write_text("\n\n".join([
        "# Ember cross-check: an independent estimate of India's grid intensity",
        ("_Generated by `scripts/ember_crosscheck.py` from `data/ember/india_monthly_national.csv` "
         "and `data/cea/factors.csv`. Do not edit by hand._"),
        ("Ember publishes monthly generation and power-sector emissions for India "
         f"(CC BY 4.0; data to {last_month}). Dividing one by the other over a financial year "
         "gives a national carbon intensity that does not come from CEA's database. This file "
         "asks two things: do the two agree, and does Ember's monthly data say anything useful "
         "about a year CEA has not published yet?"),
        ("**Read this first.** (1) Ember and CEA do not measure the same thing: Ember divides "
         "all power-sector emissions by all generation; CEA's series are weighted averages of "
         "station emission rates under its own definitions. A constant gap between them is "
         "expected and is not an error in either. (2) Ember itself draws on Indian official "
         "generation statistics, so it is an independent *calculation*, not independent "
         "*measurement*. (3) The file used is Ember's current one, not what Ember had published "
         "at each past deadline, so the backtest below is more favourable to Ember than a real "
         "one would have been. (4) The Scope 2 qualifier applies to every percentage here."),
        "## Levels, tCO2/MWh",
        table(["financial year", "Ember"] + [f"CEA {k} (vs Ember)" for k in SERIES], levels),
        "## Year-on-year changes",
        table(["step", "Ember"] + [f"CEA {k}" for k in SERIES], changes),
        (f"The two move in the same direction in {sum(agree)} of {len(agree)} comparisons. "
         "With this few years that is a description, not a test."),
        "## As an early indicator",
        ("Nowcast = last year's CEA factor (as known before the target year was published) × "
         "the change in Ember's intensity over the months available in both years. *Naive* is "
         "last year's CEA factor alone (`docs/NOWCAST_RESULTS.md`)."),
        table(["series", "target year", "months of Ember data", "CEA first published",
               "naive (error)", "Ember-adjusted (error)", "closer"], results),
        (f"**Mean absolute error over these {len(results)} cases: naive "
         f"{mean(errors['naive']):.2f}%, Ember-adjusted {mean(errors['ember']):.2f}%.** "
         f"The Ember-adjusted nowcast was closer in {wins} of {len(results)}."),
        "By series, because the pooled figure hides a difference:",
        table(["series", "cases", "naive, mean abs. error", "Ember-adjusted, mean abs. error"],
              [[label, str(len(v)), f"{mean(a for a, _ in v):.2f}%",
                f"{mean(b for _, b in v):.2f}%"] for label, v in by_series.items()]),
        ("Ember's intensity counts renewable generation in its denominator, as the "
         "renewables-inclusive CEA series does and the plain weighted average does not. "
         "That is a plausible reason for the difference, and with two cases for one "
         "series it is no more than that."),
        "## What this does and does not show",
        ("- The cases are few and overlap (two CEA series, the same years), so this cannot "
         "establish that the indicator works. It can show whether it is worth pursuing.\n"
         "- If it helps, the practical meaning is for RQ3: by the reporting deadline an "
         "entity could know roughly where the unpublished factor will land, from public data.\n"
         "- If it does not help, that is also informative: the two sources define intensity "
         "differently enough that one does not track the other year to year.\n"
         "- A proper test needs Ember's archived monthly releases (what was actually public at "
         "each deadline). We have only the current file."),
    ]) + "\n", encoding="utf-8", newline="\n")
    print(f"ember -> {OUT.relative_to(ROOT)}: {len(results)} cases, naive "
          f"{mean(errors['naive']):.2f}% vs Ember-adjusted {mean(errors['ember']):.2f}%, "
          f"closer in {wins}")


if __name__ == "__main__":
    main()
