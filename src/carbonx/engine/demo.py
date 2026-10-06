"""Before/after demonstration of invariant 1, as data. Used by
scripts/demo_reproducibility.py and by the Reports page.

The caller owns the transaction and MUST roll it back: the revision is
fictional (publisher DEMO) and must never enter the real registry.
"""
import json
from decimal import Decimal
from typing import Any

import psycopg

from carbonx.engine.calculate import edit_activity, fy_of
from carbonx.engine.report import Report, generate_report, regenerate
from carbonx.factors.registry import Policy, insert_factor

GRID = "grid.weighted_avg_incl_re_captive.incl_imports"
REVISED = Decimal("0.700000000")
EXTRA_KWH = 50_000


def _summary(r: Report) -> dict[str, Any]:
    return {"report_id": r.report_id, "sha256": r.sha256,
            "total_tco2e": json.loads(r.output)["totals"]["total_tco2e"]}


def run(conn: psycopg.Connection, org_id: int, fy: str = "FY2025-26") -> dict[str, Any]:
    """Report, then a factor revision and a backdated correction, then a new
    report (different) and the first one regenerated (identical)."""
    # Open the outer transaction first: with none open, the conn.transaction()
    # inside generate_report would COMMIT, and reports are append-only.
    conn.execute("SELECT 1")
    before = generate_report(conn, org_id, fy, Policy.VINTAGE_MATCHED)

    row = conn.execute(
        "INSERT INTO factor_source (publisher, dataset_name, version_label,"
        " version_ordinal, published_on, source_url) VALUES ('DEMO',"
        " 'fictional revision', 'v22.1-demo', 221, current_date,"
        " 'https://example.test') RETURNING source_id").fetchone()
    assert row is not None
    insert_factor(conn, source_id=row[0], factor_key=GRID, value=REVISED,
                  numerator_unit="tCO2", denominator_unit="MWh", fy=fy)

    correction = None
    act = conn.execute(
        "SELECT a.activity_id, a.quantity, lower(a.period) FROM activity a"
        " JOIN facility f USING (facility_id) WHERE f.org_id = %s"
        " AND upper_inf(a.system_time_range) AND a.activity_type = 'grid_electricity'"
        " AND lower(a.period) >= %s ORDER BY lower(a.period), a.activity_id LIMIT 1",
        (org_id, f"{fy[2:6]}-04-01")).fetchone()
    if act and fy_of(act[2]) == fy:
        edit_activity(conn, act[0], quantity=act[1] + EXTRA_KWH,
                      reason="demo: backdated meter correction")
        correction = {"month": f"{act[2]:%b %Y}", "from_kwh": format(act[1], "f"),
                      "to_kwh": format(act[1] + EXTRA_KWH, "f")}

    after = generate_report(conn, org_id, fy, Policy.VINTAGE_MATCHED)
    again = regenerate(conn, before.report_id)
    return {"fy": fy, "before": _summary(before),
            "revision": {"factor": format(REVISED, "f"), "unit": "tCO2/MWh"},
            "correction": correction, "after": _summary(after),
            "regenerated": _summary(again),
            "byte_identical": again.output == before.output}
