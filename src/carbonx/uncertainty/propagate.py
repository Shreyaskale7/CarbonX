"""Uncertainty of a report's total, with the correlation between lines that
share a factor or a meter. See docs/UNCERTAINTY.md.

Invariant 6: uncertainty is never invented. Two sources are used, and both are
documents:
  - the range stored with a factor row, which for fuels is IPCC 2006's
    published 95% limits;
  - the expanded uncertainty a meter's calibration certificate states, which
    the database accepts only together with that certificate (migration 0013).
A line with neither contributes no width, and its emissions are reported as
having no stated uncertainty of that kind.

The point of the module is correlation. Lines that use the same factor row
are wrong together: if the diesel factor is 2% high, every diesel line is 2%
high. So their uncertainties add linearly, not in quadrature:

    correlated (right):   width = sqrt( sum over factors  (C_f * u_f)^2 )
                          where C_f is the total emissions using factor f
    independent (wrong):  width = sqrt( sum over lines    (c_i * u_i)^2 )

The same holds for readings from one meter: a meter that reads 0.5% high does
so every month. Factors and meters are treated as independent of each other
and of one another. Lower and upper sides are
propagated separately because IPCC's ranges are asymmetric; that is the usual
first-order approximation (IPCC "Approach 1"), not an exact interval.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from math import sqrt

import psycopg

from carbonx import db


@dataclass(frozen=True)
class Line:
    factor_id: int
    tco2e: Fraction
    down: Fraction | None   # relative: (value - lower) / value; None = no published range
    up: Fraction | None     # relative: (upper - value) / value
    meter_id: int | None = None
    meter_u: Fraction | None = None   # relative, symmetric; None = none stated


@dataclass(frozen=True)
class Band:
    total: Decimal
    low: Decimal
    high: Decimal
    low_if_independent: Decimal    # what treating every line as independent would give
    high_if_independent: Decimal
    unquantified: Decimal          # emissions whose factor has no published range
    basis: tuple[str, ...]
    unmetered: Decimal = Decimal(0)   # emissions whose reading has no stated uncertainty


def _d(x: float | Fraction) -> Decimal:
    return Decimal(f"{float(x):.6f}")


def band(lines: list[Line], basis: tuple[str, ...] = (),
         total: Fraction | None = None) -> Band:
    """`total`, if given, is the centre of the band: a report's own total,
    which is the exact sum rounded once, not the sum of its rounded lines."""
    if total is None:
        total = sum((ln.tco2e for ln in lines), Fraction(0))
    by_factor: dict[int, Fraction] = {}
    for ln in lines:
        by_factor[ln.factor_id] = by_factor.get(ln.factor_id, Fraction(0)) + ln.tco2e
    ranges = {ln.factor_id: (ln.down, ln.up) for ln in lines}

    by_meter: dict[int, Fraction] = {}   # emissions x stated uncertainty, summed per meter
    for ln in lines:
        if ln.meter_id is not None and ln.meter_u is not None:
            by_meter[ln.meter_id] = (by_meter.get(ln.meter_id, Fraction(0))
                                     + ln.tco2e * ln.meter_u)

    def width(side: int, correlated: bool) -> float:
        if correlated:   # one term per factor and per meter: shared errors add linearly
            terms = [by_factor[f] * (ranges[f][side] or 0) for f in by_factor]
            terms += list(by_meter.values())
        else:            # one term per line and source
            terms = [ln.tco2e * ((ln.down, ln.up)[side] or 0) for ln in lines]
            terms += [ln.tco2e * (ln.meter_u or 0) for ln in lines]
        return sqrt(float(sum(t * t for t in terms)))

    unquantified = sum((ln.tco2e for ln in lines if ln.down is None or ln.up is None),
                       Fraction(0))
    return Band(
        total=_d(total),
        low=_d(float(total) - width(0, True)), high=_d(float(total) + width(1, True)),
        low_if_independent=_d(float(total) - width(0, False)),
        high_if_independent=_d(float(total) + width(1, False)),
        unquantified=_d(unquantified), basis=basis,
        unmetered=_d(sum((ln.tco2e for ln in lines if ln.meter_u is None), Fraction(0))),
    )


def for_report(conn: psycopg.Connection, report_id: int) -> Band:
    """The band for a stored report. Reads only the report's own output and the
    factor rows it pinned, which are immutable, so the answer cannot drift."""
    row = conn.execute("SELECT output FROM report WHERE report_id = %s",
                       (report_id,)).fetchone()
    if row is None:
        raise LookupError(f"no report {report_id}")
    out = json.loads(row[0])
    ids = sorted({ln["factor"]["factor_id"] for ln in out["lines"]})
    factors = {fid: (value, low, high, why) for fid, value, low, high, why in conn.execute(
        "SELECT factor_id, value, uncertainty_low, uncertainty_high, uncertainty_basis"
        " FROM emission_factor WHERE factor_id = ANY(%s)", (ids,)).fetchall()}
    lines, basis = [], set()
    for ln in out["lines"]:
        value, low, high, why = factors[ln["factor"]["factor_id"]]
        has = low is not None and high is not None and value
        if has and why:
            basis.add(why)
        meter = ln.get("meter") or {}   # absent in reports made before meters existed
        stated = meter.get("uncertainty_pct")
        if stated:
            basis.add("activity data: expanded uncertainty stated on each meter's "
                      "calibration certificate")
        lines.append(Line(
            ln["factor"]["factor_id"], Fraction(ln["tco2e"]),
            Fraction(value - low) / Fraction(value) if has else None,
            Fraction(high - value) / Fraction(value) if has else None,
            meter.get("meter_id"), Fraction(stated) / 100 if stated else None))
    return band(lines, tuple(sorted(basis)), Fraction(out["totals"]["total_tco2e"]))


def main() -> None:
    ap = argparse.ArgumentParser(description="Uncertainty band for a stored report.")
    ap.add_argument("--report", type=int, required=True)
    args = ap.parse_args()
    with psycopg.connect(db.url()) as conn:
        b = for_report(conn, args.report)
    pct = lambda x: f"{100 * (x - b.total) / b.total:+.2f}%" if b.total else "n/a"
    print(f"total {b.total} tCO2e")
    print(f"  with correlation:   {b.low} to {b.high}  ({pct(b.low)} / {pct(b.high)})")
    print(f"  if independent:     {b.low_if_independent} to {b.high_if_independent}"
          f"  ({pct(b.low_if_independent)} / {pct(b.high_if_independent)})")
    print(f"  no published range: {b.unquantified} tCO2e of the total (point estimate)")
    print(f"  no stated meter uncertainty: {b.unmetered} tCO2e of the total")
    for why in b.basis:
        print(f"  basis: {why}")


if __name__ == "__main__":
    main()
