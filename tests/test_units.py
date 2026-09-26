"""Dimensional type system: the acceptance tests in docs/BUILD_PLAN.md Phase 3,
and the soundness/completeness property from docs/TYPE_SOUNDNESS.md checked
against an independent oracle.
"""
from collections import Counter
from decimal import Decimal
from fractions import Fraction
from typing import NamedTuple

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from carbonx.units.core import BASES, DimensionError, Quantity, parse_unit
from carbonx.units.lang import LangError, check, evaluate, parse, run


def test_kwh_times_grid_factor_is_tco2e():
    env = run("""
        let activity : [kWh]      = 1200 [kWh]
        let factor   : [tCO2/MWh] = 0.7272 [tCO2/MWh]
        let e        : [tCO2e]    = activity * factor
    """)
    assert env["e"].value == Fraction("0.87264")  # exact, not approximately


def test_kwh_times_per_litre_factor_is_rejected_before_evaluation():
    # The divide-by-zero would fail at runtime; getting DimensionError instead
    # shows the checker rejected the program without evaluating it.
    with pytest.raises(DimensionError, match="declared"):
        check(parse("let e : [tCO2e] = 1200 [kWh] / 0 * 0.5 [tCO2e/litre]"))


def test_multiplication_is_total_only_ascription_and_addition_can_fail():
    # kWh * tCO2e/litre is a perfectly good quantity; it just is not tCO2e.
    env = run("let x : [kWh*tCO2e/litre] = 1200 [kWh] * 0.5 [tCO2e/litre]")
    assert env["x"].value == 600
    with pytest.raises(DimensionError, match="cannot add"):
        check(parse("let x : [kWh] = 1 [kWh] + 1 [kg]"))


def test_conversion_is_exact():
    assert run("let z : [kWh] = 1 [MWh] - 1000 [kWh]")["z"].value == 0
    assert run("let z : [GJ] = 1 [MWh]")["z"].value == Fraction("3.6")


def test_co2e_is_not_mass():
    """Otherwise tCO2e per tonne of product would be dimensionless."""
    with pytest.raises(DimensionError):
        check(parse("let x : [1] = 1 [tCO2e] / 1 [t]"))


def test_names_are_bound_once_and_must_exist():
    with pytest.raises(LangError, match="bound once"):
        check(parse("let x : [kWh] = 1 [kWh]\nlet x : [kWh] = 2 [kWh]"))
    with pytest.raises(LangError, match="not defined"):
        check(parse("let x : [kWh] = y"))


@pytest.mark.parametrize("src", ["let", "let x : [kWh] = ", "let x : [kWh] = (1",
                                 "let x : kWh = 1", "let x : [furlong] = 1", "1 + 1"])
def test_syntax_errors(src):
    with pytest.raises(LangError):
        parse(src)


def test_quantity_api_checks_too():
    kwh, kg = parse_unit("kWh"), parse_unit("kg")
    with pytest.raises(DimensionError):
        Quantity(Fraction(1), kwh) + Quantity(Fraction(1), kg)
    with pytest.raises(DimensionError):
        Quantity(Fraction(1), kwh).to(kg)


# ---- property: checker vs an independent oracle ---------------------------

# The oracle's own unit table, written from physical definitions, not copied
# from core.UNITS: {base: exponent}, and the scale to J / kg / litre / kgCO2e.
ORACLE_UNITS: dict[str, tuple[dict[str, int], Fraction]] = {
    "kWh": ({"energy": 1}, Fraction(3_600_000)),
    "MWh": ({"energy": 1}, Fraction(3_600_000_000)),
    "GJ": ({"energy": 1}, Fraction(10**9)),
    "kg": ({"mass": 1}, Fraction(1)),
    "t": ({"mass": 1}, Fraction(1000)),
    "litre": ({"volume": 1}, Fraction(1)),
    "kL": ({"volume": 1}, Fraction(1000)),
    "kgCO2e": ({"co2e": 1}, Fraction(1)),
    "tCO2e": ({"co2e": 1}, Fraction(1000)),
    "tCO2": ({"co2e": 1}, Fraction(1000)),
    "INR": ({"currency": 1}, Fraction(1)),
    "h": ({"time": 1}, Fraction(3600)),
    "tCO2/MWh": ({"co2e": 1, "energy": -1}, Fraction(1000, 3_600_000_000)),
    "kgCO2e/litre": ({"co2e": 1, "volume": -1}, Fraction(1)),
    "kg/litre": ({"mass": 1, "volume": -1}, Fraction(1)),
    "1": ({}, Fraction(1)),
}
BASE_UNIT = {"energy": "J", "mass": "kg", "volume": "litre", "co2e": "kgCO2e",
             "currency": "INR", "time": "s"}


class Oracle(NamedTuple):
    src: str
    dims: frozenset[tuple[str, int]] | None  # None: ill-typed
    value: Fraction | None                   # canonical; None: ill-typed or 1/0
    div0: bool


def _dims(d: dict[str, int]) -> frozenset[tuple[str, int]]:
    return frozenset((k, v) for k, v in d.items() if v)


@st.composite
def leaf(draw):
    unit = draw(st.sampled_from(sorted(ORACLE_UNITS)))
    n, places = draw(st.integers(1, 10**6)), draw(st.integers(0, 4))
    text = format(Decimal(n).scaleb(-places), "f")
    dims, scale = ORACLE_UNITS[unit]
    return Oracle(f"{text} [{unit}]", _dims(dims), Fraction(text) * scale, False)


def combine(op: str, a: Oracle, b: Oracle) -> Oracle:
    src = f"({a.src}) {op} ({b.src})"
    if a.dims is None or b.dims is None:
        return Oracle(src, None, None, False)
    if op in "+-":
        if a.dims != b.dims:
            return Oracle(src, None, None, False)
        dims = a.dims
    else:
        sign = 1 if op == "*" else -1
        c = Counter(dict(a.dims))
        for k, v in b.dims:
            c[k] += sign * v
        dims = _dims(c)
    div0 = a.div0 or b.div0 or (op == "/" and b.value == 0)
    if div0 or a.value is None or b.value is None:
        return Oracle(src, dims, None, div0)
    value = {"+": a.value + b.value, "-": a.value - b.value,
             "*": a.value * b.value, "/": a.value / b.value if b.value else None}[op]
    return Oracle(src, dims, value, False)


def twin(a: Oracle) -> Oracle:
    """a + a: always well-typed if a is, so deep trees are not all rejected."""
    return combine("+", a, a)


exprs = st.recursive(
    leaf(),
    lambda kids: st.one_of(
        st.builds(combine, st.sampled_from("+-*/"), kids, kids),
        kids.map(twin),
    ),
    max_leaves=12,
)


def canonical_unit(dims: frozenset[tuple[str, int]]) -> str:
    parts = [f"{BASE_UNIT[b]}^{e}" for b in BASES for k, e in dims if k == b]
    return "*".join(parts) or "1"


@settings(max_examples=1000, deadline=None)
@given(exprs)
def test_checker_agrees_with_oracle(e):
    """Soundness: accepted => evaluates to the predicted dimension and value.
    Completeness: rejected <=> the oracle says ill-typed."""
    if e.dims is None:
        with pytest.raises(DimensionError):
            check(parse(f"let r : [1] = {e.src}"))
        return
    program = parse(f"let r : [{canonical_unit(e.dims)}] = {e.src}")
    check(program)
    if e.div0:
        with pytest.raises(ZeroDivisionError):
            evaluate(program)
        return
    result = evaluate(program)["r"]
    assert _dims(dict(zip(BASES, result.dim.exps, strict=True))) == e.dims
    assert result.value == e.value  # exact rational equality
