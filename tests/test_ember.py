"""The Ember cross-check, on the committed extract. No database, no download."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ember_crosscheck as ec


def test_intensity_is_emissions_over_generation_for_the_same_months():
    data = {(2024, 4): (100.0, 60.0), (2024, 5): (300.0, 240.0), (2025, 4): (200.0, 100.0)}
    assert ec.intensity(data, 2024, {4, 5}) == pytest.approx(0.75)      # 300 / 400
    assert ec.intensity(data, 2025, {4}) == pytest.approx(0.5)
    assert ec.intensity(data, 2025, {4, 5}) is None                      # a month is missing


def test_extract_covers_whole_financial_years_and_gives_a_plausible_intensity():
    data = ec.monthly()
    for year in range(2019, 2025):                                       # FY2019-20 .. FY2024-25
        assert {m for y, m in data if y == year} == set(range(1, 13))
        assert 0.55 < ec.intensity(data, year, set(range(1, 13))) < 0.70
    assert {m for y, m in data if y == 2025} == {4, 5, 6, 7, 8, 9, 10, 11}


def test_a_partial_year_is_compared_over_the_same_months_only():
    """FY2025-26 has April to November. Its change must be measured against
    April to November of the year before, not the whole year: the months
    differ in how much coal the grid burns."""
    data = ec.monthly()
    months = {m for y, m in data if y == 2025}
    same = ec.intensity(data, 2025, months) / ec.intensity(data, 2024, months)
    whole = ec.intensity(data, 2025, months) / ec.intensity(data, 2024, set(range(1, 13)))
    assert same == pytest.approx(0.945, abs=0.005)
    assert abs(same - whole) > 0.01
