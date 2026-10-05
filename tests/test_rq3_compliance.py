"""The identity scripts/rq3_compliance.py rests on, checked against GEI computed
the long way. No database."""
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rq3_compliance import share_needed


def test_gei_change_is_share_times_factor_change():
    combustion, mwh, tonnes = Fraction(6000), Fraction(8000), Fraction(1000)
    f_b, f_a = Fraction("0.7275"), Fraction("0.6751")
    gei_b = (combustion + mwh * f_b) / tonnes
    gei_a = (combustion + mwh * f_a) / tonnes
    share = mwh * f_b / (combustion + mwh * f_b)
    assert gei_a / gei_b - 1 == share * (f_a / f_b - 1)


def test_share_needed():
    assert share_needed(-7.2, 3.0) == "42%"
    assert share_needed(-2.45, 3.0).startswith("never")
    assert share_needed(0.0, 1.0).startswith("never")
