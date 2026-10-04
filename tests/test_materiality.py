"""Materiality engine: base-year recalculation flagged at the 5% threshold.
Synthetic TEST factors; rolled back."""
from datetime import date
from decimal import Decimal

import psycopg
import pytest

from carbonx.engine.calculate import record_activity
from carbonx.engine.report import generate_report, regenerate
from carbonx.factors.registry import POLICY_DESCRIPTIONS, Policy, insert_factor
from carbonx.materiality.assess import assess

GRID = "grid.weighted_avg_incl_re_captive.incl_imports"
BASE = "FY2023-24"


@pytest.fixture
def baseline(conn):
    """A base-year report: 1,000 MWh at 0.700 tCO2/MWh = 700 tCO2e."""
    for p, d in POLICY_DESCRIPTIONS.items():
        conn.execute("INSERT INTO resolution_policy (code, description) VALUES (%s, %s)"
                     " ON CONFLICT (code) DO NOTHING", (p.value, d))
    (org_id,) = conn.execute("INSERT INTO organisation (name) VALUES ('m')"
                             " RETURNING org_id").fetchone()
    (fid,) = conn.execute("INSERT INTO facility (org_id, name, state) VALUES (%s, 'p',"
                          " 'KA') RETURNING facility_id", (org_id,)).fetchone()
    new_version(conn, 700_001, "0.700")
    record_activity(conn, facility_id=fid, activity_type="grid_electricity",
                    period_start=date(2023, 4, 1), period_end=date(2023, 5, 1),
                    quantity=Decimal(1_000_000), unit="kWh")
    return generate_report(conn, org_id, BASE, Policy.LATEST_AVAILABLE)


def new_version(conn, ordinal, value):
    (sid,) = conn.execute(
        "INSERT INTO factor_source (publisher, dataset_name, version_label,"
        " version_ordinal, published_on, source_url) VALUES ('TEST', 'm', %s, %s,"
        " '2024-01-01', 'https://example.test') RETURNING source_id",
        (f"m{ordinal}", ordinal)).fetchone()
    return insert_factor(conn, source_id=sid, factor_key=GRID, value=Decimal(value),
                         numerator_unit="tCO2", denominator_unit="MWh", fy=BASE)


def test_small_revision_is_not_material(conn, baseline):
    fid = new_version(conn, 700_002, "0.7245")          # +3.5%
    a = assess(conn, baseline.report_id, "factor_supersession", fid)
    assert (a.before_tco2e, a.after_tco2e) == (Decimal("700.000000"), Decimal("724.500000"))
    assert a.pct_change == Decimal("3.5000") and not a.requires_recalc
    assert "does not reach" in a.disclosure and "DRAFT" in a.disclosure


def test_revision_at_threshold_requires_recalculation(conn, baseline):
    new_version(conn, 700_002, "0.735")                  # exactly +5%
    a = assess(conn, baseline.report_id, "factor_supersession")
    assert a.pct_change == Decimal("5.0000") and a.requires_recalc
    assert "recalculation is required" in a.disclosure


def test_baseline_report_itself_still_reproduces(conn, baseline):
    new_version(conn, 700_002, "0.800")
    assess(conn, baseline.report_id, "factor_supersession")
    assert regenerate(conn, baseline.report_id).output == baseline.output


def test_assessments_are_append_only(owner_conn):
    conn = owner_conn
    for p, d in POLICY_DESCRIPTIONS.items():
        conn.execute("INSERT INTO resolution_policy (code, description) VALUES (%s, %s)"
                     " ON CONFLICT (code) DO NOTHING", (p.value, d))
    (org_id,) = conn.execute("INSERT INTO organisation (name) VALUES ('m2')"
                             " RETURNING org_id").fetchone()
    (aid,) = conn.execute(
        "INSERT INTO materiality_assessment (org_id, trigger_type, baseline_year,"
        " before_tco2e, after_tco2e, pct_change, requires_recalc)"
        " VALUES (%s, 'data_correction', %s, 1, 1, 0, false) RETURNING assessment_id",
        (org_id, BASE)).fetchone()
    conn.execute("SAVEPOINT s")
    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute("UPDATE materiality_assessment SET requires_recalc = true"
                     " WHERE assessment_id = %s", (aid,))
    conn.execute("ROLLBACK TO SAVEPOINT s")


def test_unknown_trigger_is_rejected(conn):
    with pytest.raises(ValueError):
        assess(conn, 1, "vibes")
