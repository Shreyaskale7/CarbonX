"""Nowcasting: the vintage rule (no future data), the models on series where
the right answer is known, and the real registry. No database."""
from pathlib import Path

import pytest

from carbonx.forecast import nowcast as nc

ROOT = Path(__file__).resolve().parents[1]


def _series(*versions: tuple[int, dict[int, float]]) -> nc.Series:
    """Build a series from (ordinal, {year: value}) versions."""
    out: nc.Series = {}
    for ordinal, values in versions:
        for year, value in values.items():
            out.setdefault(year, []).append((ordinal, f"v{ordinal}", value))
    return out


def test_as_known_never_sees_the_target_version_or_later():
    s = _series((10, {2000: 1.0, 2001: 1.1}), (20, {2001: 1.2, 2002: 1.3}),
                (30, {2001: 9.9, 2002: 9.9, 2003: 1.4}))
    assert nc.as_known(s, 20) == {2000: 1.0, 2001: 1.1}      # v20's restatement hidden
    assert nc.as_known(s, 30) == {2000: 1.0, 2001: 1.2, 2002: 1.3}


def test_backtest_history_ignores_later_restatements():
    """Version 70 rewrites every earlier year to 99. No forecast made before
    version 70 may contain a 99."""
    versions = [(10 * (i + 1), {2000 + j: 1.0 + 0.01 * j for j in range(max(0, i - 2), i + 5)})
                for i in range(6)]
    versions.append((70, {y: 99.0 for y in range(2000, 2011)} | {2011: 1.11}))
    targets, _ = nc.backtest(_series(*versions))
    assert targets, "the synthetic series should yield targets"
    for t in targets:
        if t.version != "v70":
            assert 99.0 not in t.history
        assert t.forecasts[nc.NAIVE] == t.history[-1]


def test_models_are_exact_where_they_should_be():
    flat, line = [0.8] * 8, [0.9 - 0.01 * i for i in range(8)]
    for name, model in nc.MODELS.items():
        assert model(flat) == pytest.approx(0.8), name
    for name in ("drift (average change so far)", "recent drift (last three changes)",
                 "linear trend", "AR(1) on changes"):
        assert nc.MODELS[name](line) == pytest.approx(0.82), name
    assert nc.naive(line) == pytest.approx(0.83)


def test_sign_test_and_interval():
    assert nc.sign_test(5, 10) == 1.0
    assert nc.sign_test(0, 10) == pytest.approx(2 / 1024)
    low, high = nc.interval(1.0, [0.9, 0.95, 1.0, 1.05, 1.1], 0.8)
    assert low < 1.0 < high and low == pytest.approx(0.92) and high == pytest.approx(1.08)


def test_coverage_uses_only_earlier_errors():
    """Constant series, then one jump: the band before the jump has zero width
    and the jump must be counted as a miss, not absorbed into its own band."""
    values = {y: 1.0 for y in range(2000, 2020)} | {2020: 2.0}
    s = _series(*[(10 * (y - 1999), {yy: v for yy, v in values.items() if yy <= y})
                  for y in range(2004, 2021)])
    targets, _ = nc.backtest(s)
    covered, tested, bands = nc.coverage(targets, 0.8)
    assert tested == len(bands) and covered == tested - 1
    assert bands[-1][1:] == (1.0, 1.0)


def test_revisions_measure_from_the_first_published_value():
    s = _series((10, {2000: 1.0}), (20, {2000: 1.01}), (30, {2000: 0.99}))
    assert nc.revisions(s) == [(2000, 1, pytest.approx(1.0)), (2000, 2, pytest.approx(-1.0))]
    assert nc.revision_summary(s)[-1][0] == "latest"


def test_real_registry_naive_is_not_beaten():
    """The reported result, pinned: on CEA's weighted average, no alternative has
    a lower mean absolute error than last year's value."""
    reg = nc.load(ROOT / "data" / "cea" / "factors.csv", ROOT / "data" / "cea" / "versions.csv")
    targets, _ = nc.backtest(reg["grid.weighted_avg.incl_imports"])
    scores = {s.model: s for s in nc.score(targets)}
    assert len(targets) == 20
    assert scores[nc.NAIVE].mae == pytest.approx(1.99, abs=0.01)
    assert min(scores.values(), key=lambda s: s.mae).model == nc.NAIVE
    for t in targets:   # every history really is from before the target's version
        ordinal = reg["grid.weighted_avg.incl_imports"][t.year][0][0]
        known = nc.as_known(reg["grid.weighted_avg.incl_imports"], ordinal)
        assert t.history[-1] == known[t.year - 1]
