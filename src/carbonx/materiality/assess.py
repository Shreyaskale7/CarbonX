"""Materiality engine: does a change require base-year recalculation?

A stored baseline report says what the base year's emissions WERE (as of its
own time, reproducibly). Recomputing the same report as of NOW says what they
ARE, after whatever has happened since: a factor supersession, a correction,
new evidence. If the change reaches the threshold (SBTi: >= 5% of base-year
emissions), recalculation is required, and a disclosure is drafted.

GHG Protocol requires base-year recalculation when emission factors are
updated but prescribes no numeric threshold; the 5% here is SBTi's. The
drafted text is a starting point for a human, not a verification opinion.

    python -m carbonx.materiality.assess --report 7 --trigger factor_supersession
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

import psycopg

from carbonx import db
from carbonx.engine.calculate import round6, set_audit_context, system_now
from carbonx.engine.report import build
from carbonx.factors.registry import Policy

TRIGGERS = {"factor_supersession", "boundary_change", "data_correction",
            "allocation_change"}
THRESHOLD_PCT = Decimal("5.0")


@dataclass(frozen=True)
class Assessment:
    assessment_id: int
    before_tco2e: Decimal
    after_tco2e: Decimal
    pct_change: Decimal
    requires_recalc: bool
    disclosure: str


def _draft(fy: str, policy: str, before: Decimal, after: Decimal, pct: Decimal,
           trigger: str, required: bool, gei: tuple[str | None, str | None]) -> str:
    verb = "exceeds" if required else "does not reach"
    gei_line = ""
    if gei[0] and gei[1]:
        gei_line = f" GEI moves from {gei[0]} to {gei[1]} tCO2e per unit of product."
    return (
        f"DRAFT, for review by the reporting entity and its verifier. "
        f"Following {'an' if trigger[0] in 'aeiou' else 'a'} "
        f"{trigger.replace('_', ' ')}, base-year ({fy}) emissions "
        f"recomputed under the {policy} factor-resolution policy change from "
        f"{before} to {after} tCO2e ({pct:+}%).{gei_line} This {verb} the "
        f"{THRESHOLD_PCT}% significance threshold (SBTi), so base-year "
        f"recalculation is {'required' if required else 'not required'} on that "
        f"basis. The GHG Protocol requires recalculation when emission factors are "
        f"updated and sets no numeric threshold. The original report remains "
        f"reproducible as of its generation time."
    )


def assess(conn: psycopg.Connection, baseline_report_id: int, trigger_type: str,
           trigger_ref: int | None = None, actor: str | None = None) -> Assessment:
    if trigger_type not in TRIGGERS:
        raise ValueError(f"trigger_type must be one of {sorted(TRIGGERS)}")
    with conn.transaction():
        set_audit_context(conn, actor, f"materiality: {trigger_type}")
        row = conn.execute(
            "SELECT r.org_id, r.compliance_year, p.code, r.baseline_year, r.output"
            " FROM report r JOIN resolution_policy p USING (policy_id)"
            " WHERE r.report_id = %s", (baseline_report_id,)).fetchone()
        if row is None:
            raise LookupError(f"no report {baseline_report_id}")
        org_id, fy, code, baseline_year, output = row
        before_out = json.loads(output)
        now_out = json.loads(build(conn, org_id, fy, Policy(code), system_now(conn),
                                   baseline_year))
        before = Decimal(before_out["totals"]["total_tco2e"])
        after = Decimal(now_out["totals"]["total_tco2e"])
        if before == 0:
            raise ValueError("baseline emissions are zero; a percentage change is undefined")
        pct = round6(Fraction(after - before) * 100 / Fraction(before)).quantize(
            Decimal("0.0001"))
        required = abs(pct) >= THRESHOLD_PCT
        text = _draft(fy, code, before, after, pct, trigger_type, required,
                      (before_out.get("gei"), now_out.get("gei")))
        rec = conn.execute(
            "INSERT INTO materiality_assessment (org_id, trigger_type, trigger_ref,"
            " baseline_year, before_tco2e, after_tco2e, pct_change, threshold_pct,"
            " requires_recalc, disclosure_text)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING assessment_id",
            (org_id, trigger_type, trigger_ref, fy, before, after, pct, THRESHOLD_PCT,
             required, text)).fetchone()
    assert rec is not None
    return Assessment(int(rec[0]), before, after, pct, required, text)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", type=int, required=True, help="the baseline report id")
    ap.add_argument("--trigger", required=True, choices=sorted(TRIGGERS))
    ap.add_argument("--trigger-ref", type=int)
    args = ap.parse_args()
    with psycopg.connect(db.url()) as conn:
        a = assess(conn, args.report, args.trigger, args.trigger_ref,
                   actor="carbonx.materiality.assess")
    print(f"assessment {a.assessment_id}: {a.before_tco2e} -> {a.after_tco2e} tCO2e "
          f"({a.pct_change:+}%), recalculation "
          f"{'REQUIRED' if a.requires_recalc else 'not required'}\n\n{a.disclosure}")


if __name__ == "__main__":
    main()
