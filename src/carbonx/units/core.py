"""Dimensions, units and quantities. See docs/TYPE_SOUNDNESS.md.

A Dimension is a vector of integer exponents over six base dimensions. CO2e
is a base dimension of its own, NOT a kind of mass: otherwise tCO2e per tonne
of cement would cancel to a dimensionless number and every GEI would
type-check against every other.

Values are exact rationals (Fraction). Unit conversion (1 MWh = 1000 kWh) is
then exact, so a report computed in kWh and one computed in MWh are equal, not
merely close: invariant 1 needs byte-identical output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

BASES = ("energy", "mass", "volume", "co2e", "currency", "time")


class DimensionError(TypeError):
    """Two quantities were combined or ascribed across dimensions."""


@dataclass(frozen=True)
class Dimension:
    exps: tuple[int, ...]

    def __mul__(self, other: Dimension) -> Dimension:
        return Dimension(tuple(a + b for a, b in zip(self.exps, other.exps, strict=True)))

    def __truediv__(self, other: Dimension) -> Dimension:
        return Dimension(tuple(a - b for a, b in zip(self.exps, other.exps, strict=True)))

    def __pow__(self, n: int) -> Dimension:
        return Dimension(tuple(a * n for a in self.exps))

    def __str__(self) -> str:
        parts = [b if e == 1 else f"{b}^{e}" for b, e in zip(BASES, self.exps, strict=True) if e]
        return "*".join(parts) or "dimensionless"


def base(name: str) -> Dimension:
    return Dimension(tuple(int(b == name) for b in BASES))


NONE = Dimension((0,) * len(BASES))
ENERGY, MASS, VOLUME, CO2E, CURRENCY, TIME = (base(b) for b in BASES)


@dataclass(frozen=True)
class Unit:
    """`scale` converts to the base unit of the dimension: J, kg, litre,
    kgCO2e, INR, s. 1 kWh = 3.6e6 J, so kWh has scale 3600000."""

    name: str
    dim: Dimension
    scale: Fraction

    def __mul__(self, other: Unit) -> Unit:
        return Unit(f"{self.name}*{other.name}", self.dim * other.dim,
                    self.scale * other.scale)

    def __truediv__(self, other: Unit) -> Unit:
        return Unit(f"{self.name}/{other.name}", self.dim / other.dim,
                    self.scale / other.scale)

    def __pow__(self, n: int) -> Unit:
        return Unit(f"{self.name}^{n}", self.dim**n, self.scale**n)

    def __str__(self) -> str:
        return self.name


def _u(name: str, dim: Dimension, scale: int | Fraction) -> Unit:
    return Unit(name, dim, Fraction(scale))


UNITS: dict[str, Unit] = {u.name: u for u in (
    _u("1", NONE, 1),
    _u("J", ENERGY, 1), _u("MJ", ENERGY, 10**6), _u("GJ", ENERGY, 10**9),
    _u("TJ", ENERGY, 10**12), _u("Wh", ENERGY, 3600), _u("kWh", ENERGY, 3_600_000),
    _u("MWh", ENERGY, 3_600_000_000), _u("GWh", ENERGY, 3_600_000_000_000),
    # International Table calorie, as used in energy statistics (IEA):
    # 1 kcal = 4186.8 J exactly, and 1 toe = 10^7 kcal = 41.868 GJ.
    _u("kcal", ENERGY, Fraction(41868, 10)), _u("toe", ENERGY, 41_868_000_000),
    _u("g", MASS, Fraction(1, 1000)), _u("kg", MASS, 1), _u("t", MASS, 1000),
    _u("litre", VOLUME, 1), _u("kL", VOLUME, 1000), _u("m3", VOLUME, 1000),
    _u("gCO2e", CO2E, Fraction(1, 1000)), _u("kgCO2e", CO2E, 1),
    _u("tCO2e", CO2E, 1000), _u("MtCO2e", CO2E, 10**9),
    # CO2 counts as CO2e at GWP 1, by definition of CO2e. CEA factors are tCO2.
    _u("kgCO2", CO2E, 1), _u("tCO2", CO2E, 1000),
    _u("INR", CURRENCY, 1),
    _u("s", TIME, 1), _u("h", TIME, 3600), _u("day", TIME, 86400),
)}

_UNIT_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9]*|\^-?\d+|\d+|\S")


def parse_unit(text: str) -> Unit:
    """'tCO2/MWh', 'kg*m3^-1', '1'. Left-associative: a/b*c = (a/b)*c.

    Grammar (regular):  unit := atom (('*' | '/') atom)*,  atom := NAME ('^' INT)?
    """
    toks, i, op = _UNIT_TOKEN.findall(text), 0, "*"
    result: Unit | None = None
    while True:
        if i >= len(toks) or toks[i] not in UNITS:
            raise ValueError(f"bad unit {text!r}: expected a unit name at token {i}")
        atom = UNITS[toks[i]]
        i += 1
        if i < len(toks) and toks[i].startswith("^"):
            atom, i = atom ** int(toks[i][1:]), i + 1
        result = atom if result is None else (result * atom if op == "*" else result / atom)
        if i == len(toks):
            return Unit(text.strip(), result.dim, result.scale)
        if toks[i] not in ("*", "/"):
            raise ValueError(f"bad unit {text!r}: expected * or / at token {i}")
        op, i = toks[i], i + 1


@dataclass(frozen=True)
class Quantity:
    value: Fraction
    unit: Unit

    @property
    def dim(self) -> Dimension:
        return self.unit.dim

    @property
    def canonical(self) -> Fraction:
        """The value in the base unit of its dimension."""
        return self.value * self.unit.scale

    def _same_dim(self, other: Quantity, op: str) -> None:
        if self.dim != other.dim:
            raise DimensionError(f"{self.unit} {op} {other.unit}: "
                                 f"{self.dim} vs {other.dim}")

    def __add__(self, other: Quantity) -> Quantity:
        self._same_dim(other, "+")
        return Quantity(self.value + other.canonical / self.unit.scale, self.unit)

    def __sub__(self, other: Quantity) -> Quantity:
        self._same_dim(other, "-")
        return Quantity(self.value - other.canonical / self.unit.scale, self.unit)

    def __mul__(self, other: Quantity) -> Quantity:
        return Quantity(self.value * other.value, self.unit * other.unit)

    def __truediv__(self, other: Quantity) -> Quantity:
        return Quantity(self.value / other.value, self.unit / other.unit)

    def to(self, unit: Unit) -> Quantity:
        if self.dim != unit.dim:
            raise DimensionError(f"cannot express {self.unit} ({self.dim}) "
                                 f"as {unit} ({unit.dim})")
        return Quantity(self.canonical / unit.scale, unit)

    def __str__(self) -> str:
        return f"{float(self.value):.6g} {self.unit}"
