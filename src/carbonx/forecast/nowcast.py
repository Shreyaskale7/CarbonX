"""Nowcasting the grid emission factor, and how CEA revises it.

The question (RQ3): when reports are due, the year's factor is not published.
Using "the latest" one is a forecast of it by last year's value. How wrong is
that forecast, and does anything simple do better?

The rule that makes the answer honest is the vintage rule: to predict the
first-published value of financial year t, use only values from CEA versions
published BEFORE the version that first published t. Later restatements of
earlier years are not allowed in. `as_known` implements it; a test guards it.

Pure Python on data/cea/factors.csv. No database, no fitted library model:
with about twenty yearly targets, anything richer would be fitting noise.
Method and limits: docs/NOWCAST.md.
"""

from __future__ import annotations

import csv
from collections.abc import Callable
from dataclasses import dataclass
from itertools import pairwise
from math import comb, sqrt
from pathlib import Path
from statistics import mean, median

Observation = tuple[int, str, float]          # (version ordinal, version label, value)
Series = dict[int, list[Observation]]         # FY start year -> observations, oldest first


def load(factors: Path, versions: Path, geography: str = "IN") -> dict[str, Series]:
    with versions.open(encoding="utf-8") as fh:
        ordinal = {v["version_label"]: int(v["version_ordinal"]) for v in csv.DictReader(fh)}
    out: dict[str, Series] = {}
    with factors.open(encoding="utf-8") as fh:
        for f in csv.DictReader(fh):
            if f["geography"] == geography:
                out.setdefault(f["factor_key"], {}).setdefault(int(f["fy"][2:6]), []).append(
                    (ordinal[f["version_label"]], f["version_label"], float(f["value"])))
    for series in out.values():
        for obs in series.values():
            obs.sort()
    return out


def fy(year: int) -> str:
    return f"FY{year}-{(year + 1) % 100:02d}"


def as_known(series: Series, before_ordinal: int) -> dict[int, float]:
    """Each year's value as last published by a version strictly older than
    `before_ordinal`. This is everything a forecaster could have seen."""
    known = {}
    for year, obs in series.items():
        seen = [o for o in obs if o[0] < before_ordinal]
        if seen:
            known[year] = seen[-1][2]
    return known


# ---- models: each maps a history (consecutive years, oldest first) to next year

def naive(h: list[float]) -> float:
    """Last year's value: what "use the latest factor" does."""
    return h[-1]


def drift(h: list[float]) -> float:
    """Last value plus the average yearly change so far."""
    return h[-1] + (h[-1] - h[0]) / (len(h) - 1)


def recent_drift(h: list[float]) -> float:
    """Last value plus the average of the last three yearly changes."""
    k = min(3, len(h) - 1)
    return h[-1] + (h[-1] - h[-1 - k]) / k


def _ols(x: list[float], y: list[float]) -> tuple[float, float]:
    mx, my = mean(x), mean(y)
    sxx = sum((a - mx) ** 2 for a in x)
    slope = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True)) / sxx if sxx else 0.0
    return my - slope * mx, slope


def trend(h: list[float]) -> float:
    """Straight line through the whole history, extended one year."""
    a, b = _ols([float(i) for i in range(len(h))], h)
    return a + b * len(h)


def ar1_changes(h: list[float]) -> float:
    """AR(1) on yearly changes: does this year's change predict next year's?"""
    d = [b - a for a, b in pairwise(h)]
    if len(d) < 3:
        return drift(h)
    c, phi = _ols(d[:-1], d[1:])
    return h[-1] + c + max(-1.0, min(1.0, phi)) * d[-1]   # clamp: keep it stationary


MODELS: dict[str, Callable[[list[float]], float]] = {
    "naive (last year's value)": naive,
    "drift (average change so far)": drift,
    "recent drift (last three changes)": recent_drift,
    "linear trend": trend,
    "AR(1) on changes": ar1_changes,
}
NAIVE = "naive (last year's value)"
MIN_HISTORY = 5


@dataclass(frozen=True)
class Target:
    year: int
    version: str                 # the version that first published it
    actual: float
    history: tuple[float, ...]   # consecutive years ending at year - 1, as known before
    forecasts: dict[str, float]

    def error(self, model: str) -> float:
        """Forecast error in percent of the actual value (positive = too high)."""
        return 100 * (self.forecasts[model] - self.actual) / self.actual


def backtest(series: Series, skip: frozenset[int] = frozenset()) -> tuple[list[Target], list[str]]:
    """One-year-ahead forecasts of every year's first-published value, each from
    the history known before that publication. Returns the targets and a note
    for each year that could not be used."""
    targets, notes = [], []
    for year in sorted(series):
        ordinal, version, actual = series[year][0]
        known = as_known(series, ordinal)
        history: list[float] = []
        y = year - 1
        while y in known:
            history.insert(0, known[y])
            y -= 1
        if year in skip:
            notes.append(f"{fy(year)}: excluded (method change)")
        elif year - 1 not in known:
            if known:
                notes.append(f"{fy(year)}: {fy(year - 1)} was not yet published when "
                             f"{version} came out, so this is not a one-year-ahead case")
        elif len(history) < MIN_HISTORY:
            notes.append(f"{fy(year)}: only {len(history)} earlier years known")
        else:
            targets.append(Target(year, version, actual, tuple(history),
                                  {name: m(history) for name, m in MODELS.items()}))
    return targets, notes


def sign_test(wins: int, n: int) -> float:
    """Two-sided exact binomial p-value for `wins` out of `n` against 1/2."""
    if n == 0:
        return 1.0
    k = min(wins, n - wins)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / float(2 ** n))


@dataclass(frozen=True)
class Score:
    model: str
    n: int
    mae: float       # mean absolute error, percent
    rmse: float
    bias: float      # mean signed error, percent
    worst: float
    beats_naive: int
    comparable: int  # years where the two forecasts differ
    p_value: float


def score(targets: list[Target]) -> list[Score]:
    out = []
    for name in MODELS:
        errs = [t.error(name) for t in targets]
        pairs = [(abs(t.error(name)), abs(t.error(NAIVE))) for t in targets]
        wins = sum(a < b for a, b in pairs)
        differ = sum(a != b for a, b in pairs)
        out.append(Score(name, len(errs), mean(abs(e) for e in errs),
                         sqrt(mean(e * e for e in errs)), mean(errs),
                         max(errs, key=abs), wins, differ, sign_test(wins, differ)))
    return out


def quantile(xs: list[float], q: float) -> float:
    """Linear-interpolated sample quantile."""
    s = sorted(xs)
    pos = q * (len(s) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def interval(point: float, past_ratios: list[float], level: float) -> tuple[float, float]:
    """Empirical band: scale the point forecast by the quantiles of past
    actual/forecast ratios. No distribution is assumed."""
    tail = (1 - level) / 2
    return point * quantile(past_ratios, tail), point * quantile(past_ratios, 1 - tail)


MIN_ERRORS = 8   # past errors needed before a band is drawn from them


def coverage(targets: list[Target], level: float) -> tuple[int, int, list[tuple[int, float, float]]]:
    """Out of sample: each year's band is built only from earlier years' naive
    errors. Returns (covered, tested, [(year, low, high)])."""
    ratios: list[float] = []
    covered, bands = 0, []
    for t in targets:
        point = t.forecasts[NAIVE]
        if len(ratios) >= MIN_ERRORS:
            low, high = interval(point, ratios, level)
            bands.append((t.year, low, high))
            covered += low <= t.actual <= high
        ratios.append(t.actual / point)
    return covered, len(bands), bands


def revisions(series: Series) -> list[tuple[int, int, float]]:
    """(year, lag, percent change from the first-published value) for every
    later version that restated the year. Lag 1 is the first restatement."""
    out = []
    for year, obs in series.items():
        first = obs[0][2]
        out += [(year, lag, 100 * (o[2] - first) / first)
                for lag, o in enumerate(obs[1:], start=1)]
    return out


def revision_summary(series: Series, lags: range = range(1, 6)) -> list[tuple[str, int, float, float, float]]:
    """Per lag (and for the final restatement): n, median |revision|, largest
    |revision|, mean signed revision. All in percent."""
    rows = revisions(series)
    table = []
    for lag in lags:
        r = [p for _, k, p in rows if k == lag]
        if r:
            table.append((str(lag), len(r), median(abs(p) for p in r),
                          max(abs(p) for p in r), mean(r)))
    final = [100 * (obs[-1][2] - obs[0][2]) / obs[0][2] for obs in series.values() if len(obs) > 1]
    if final:
        table.append(("latest", len(final), median(abs(p) for p in final),
                      max(abs(p) for p in final), mean(final)))
    return table
