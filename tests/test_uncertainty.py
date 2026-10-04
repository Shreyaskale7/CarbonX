"""Correlated uncertainty propagation. Pure arithmetic: no database."""
from decimal import Decimal
from fractions import Fraction as F
from math import sqrt

import pytest

from carbonx.uncertainty.propagate import Line, band

U = F(4, 100)  # a 4% range each side


def test_lines_sharing_a_factor_add_linearly():
    """Three facilities on one factor are wrong together: the band is the full
    4% of the total, not 4% / sqrt(3)."""
    b = band([Line(1, F(100), U, U)] * 3)
    assert (b.low, b.high) == (Decimal("288.000000"), Decimal("312.000000"))
    naive = 300 * 0.04 / sqrt(3)
    assert float(b.high_if_independent) == pytest.approx(300 + naive, abs=1e-6)
    # The plan's acceptance test: correlated is demonstrably wider, by sqrt(3).
    assert (float(b.high) - 300) / (float(b.high_if_independent) - 300) == \
        pytest.approx(sqrt(3))


def test_different_factors_combine_in_quadrature():
    b = band([Line(1, F(300), U, U), Line(2, F(400), U, U)])
    assert float(b.high) == pytest.approx(700 + sqrt(12 ** 2 + 16 ** 2))   # = 720
    assert (b.high, b.high_if_independent) == (Decimal("720.000000"),) * 2   # one line each


def test_asymmetric_ranges_are_kept_asymmetric():
    b = band([Line(1, F(1000), F(3, 100), F(5, 100))])
    assert (b.low, b.high) == (Decimal("970.000000"), Decimal("1050.000000"))


def test_no_published_range_means_no_invented_width():
    """Invariant 6: a factor without a range is a point estimate, and says so."""
    b = band([Line(1, F(500), None, None), Line(2, F(100), U, U)])
    assert b.unquantified == Decimal("500.000000")
    assert (b.low, b.high) == (Decimal("596.000000"), Decimal("604.000000"))


def test_empty_report():
    b = band([])
    assert (b.total, b.low, b.high, b.unquantified) == (Decimal("0.000000"),) * 4
