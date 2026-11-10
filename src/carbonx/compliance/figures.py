"""One facility's gate-to-gate figures from a stored report, exactly. Shared by the entitlement and the
Form I draft, so the two cannot disagree.

A report prints each line's tCO2e and the production rounded to 6 places. Summing those would carry the
rounding into a compliance figure, so nothing rounded is read here: each inside line is recomputed by the
engine's own typed program from the inputs the report pinned (quantity, NCV, oxidation, factor value),
and production is rebuilt from the report's own production records and declared conversions. All
arithmetic is in exact fractions; callers round once, when they print.

Only activities tagged inside the boundary count (migration 0017). An untagged line is never assumed
inside: it makes the figures incomplete. Pure: no database, no clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from types import SimpleNamespace
from typing import Any

from carbonx.engine.calculate import emissions
from carbonx.units.core import Quantity, parse_unit


@dataclass(frozen=True)
class Figures:
    direct: Fraction                 # scope 1, energy related, inside the boundary, tCO2e
    indirect: Fraction               # scope 2, inside the boundary, tCO2e
    outside: Fraction                # tagged outside, tCO2e
    purchased_kwh: Fraction          # grid electricity inside the boundary
    production: Fraction | None      # in `production_unit`; None when the report has no denominator
    production_unit: str | None
    inside: int
    outside_count: int
    untagged: int
    unresolved: int

    @property
    def emissions(self) -> Fraction:
        return self.direct + self.indirect

    @property
    def complete(self) -> bool:
        return self.untagged == 0 and self.unresolved == 0

    @property
    def incomplete_because(self) -> str | None:
        if self.complete:
            return None
        return (f"{self.untagged} activity line(s) have no boundary tag and {self.unresolved} "
                "line(s) are unresolved; the figures are incomplete")


def _line_tco2e(line: dict[str, Any]) -> Fraction:
    """The engine's exact result for a report line, from the inputs the report pinned."""
    f = line["factor"]
    numerator, _, denominator = f["unit"].partition("/")
    factor: Any = SimpleNamespace(value=Decimal(f["value"]), numerator_unit=numerator,
                                  denominator_unit=denominator, factor_key=f["factor_key"],
                                  version_label=f["source_version"])
    if "ncv" in line:
        return emissions(Decimal(line["quantity"]), line["unit"], factor, Decimal(line["ncv"]),
                         line["ncv_unit"], Decimal(line["oxidation_factor"]))[1]
    return emissions(Decimal(line["quantity"]), line["unit"], factor)[1]


def _production(report: dict[str, Any], facility: dict[str, Any]) -> tuple[Fraction | None, str | None]:
    """The denominator the report used, unrounded. The report decides whether there is one (and
    withholds it when conversions are missing); this only removes the rounding."""
    shown = facility["production"]
    if shown is None:
        return None, None
    fid, unit = facility["facility_id"], shown["unit"]
    records = [r for r in report["production_records"] if r["facility_id"] == fid]
    if "from" not in shown:
        return sum((Fraction(r["quantity"]) for r in records), Fraction(0)), unit
    factors = {e["product_code"]: e["factor"] for e in report["product_equivalences"]
               if e["facility_id"] == fid}
    total = Fraction(0)
    for r in records:
        total += (Quantity(Fraction(r["quantity"]), parse_unit(r["unit"]))
                  * Quantity(Fraction(factors[r["product_code"]]),
                             parse_unit(f"{unit}/{r['unit']}"))).to(parse_unit(unit)).value
    return total, unit


def figures(report: dict[str, Any], facility: dict[str, Any],
            tags: dict[int, dict[str, Any]]) -> Figures:
    fid = facility["facility_id"]
    direct = indirect = outside = purchased = Fraction(0)
    n_in = n_out = n_untagged = 0
    kwh = parse_unit("kWh")
    for line in report["lines"]:
        if line["facility_id"] != fid:
            continue
        tag = tags.get(line["activity_id"])
        if tag is None:
            n_untagged += 1
            continue
        t = _line_tco2e(line)
        if tag["boundary"] != "inside":
            n_out, outside = n_out + 1, outside + t
            continue
        n_in += 1
        if line["scope"] == 1:
            direct += t
        else:
            indirect += t
        if line["activity_type"] == "grid_electricity":
            purchased += Quantity(Fraction(line["quantity"]), parse_unit(line["unit"])).to(kwh).value
    production, unit = _production(report, facility)
    return Figures(direct, indirect, outside, purchased, production, unit, n_in, n_out, n_untagged,
                   sum(1 for u in report["unresolved"] if u["facility_id"] == fid))
