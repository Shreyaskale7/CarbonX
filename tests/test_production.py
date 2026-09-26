"""Denominator versioning (component 2): GEI = emissions / production, with
production as bitemporal and as reproducible as emissions. Rolled back."""
import json
from datetime import date
from decimal import Decimal

import psycopg
import pytest

from carbonx.engine.calculate import record_activity
from carbonx.engine.production import edit_production, record_production
from carbonx.engine.report import generate_report, regenerate
from carbonx.factors.registry import POLICY_DESCRIPTIONS, Policy, insert_factor

GRID = "grid.weighted_avg_incl_re_captive.incl_imports"
FY = "FY2025-26"
APRIL = {"period_start": date(2025, 4, 1), "period_end": date(2025, 5, 1)}


@pytest.fixture
def plant(conn):
    for p, d in POLICY_DESCRIPTIONS.items():
        conn.execute("INSERT INTO resolution_policy (code, description) VALUES (%s, %s)"
                     " ON CONFLICT (code) DO NOTHING", (p.value, d))
    (sid,) = conn.execute(
        "INSERT INTO factor_source (publisher, dataset_name, version_label,"
        " version_ordinal, published_on, source_url) VALUES ('TEST', 'gei', 'g1',"
        " 800000, '2026-01-01', 'https://example.test') RETURNING source_id").fetchone()
    insert_factor(conn, source_id=sid, factor_key=GRID, value=Decimal("0.700"),
                  numerator_unit="tCO2", denominator_unit="MWh", fy=FY)
    (org_id,) = conn.execute("INSERT INTO organisation (name) VALUES ('gei org')"
                             " RETURNING org_id").fetchone()
    (facility_id,) = conn.execute("INSERT INTO facility (org_id, name, state)"
                                  " VALUES (%s, 'p', 'OD') RETURNING facility_id",
                                  (org_id,)).fetchone()
    record_activity(conn, facility_id=facility_id, activity_type="grid_electricity",
                    quantity=Decimal(1_400_000), unit="kWh", **APRIL)  # 980 tCO2e
    return org_id, facility_id


def _out(conn, org_id, policy=Policy.VINTAGE_MATCHED):
    r = generate_report(conn, org_id, FY, policy)
    return r, json.loads(r.output)


def test_gei_is_emissions_over_production_exactly(conn, plant):
    org_id, facility_id = plant
    record_production(conn, facility_id=facility_id, product_code="al", unit="t",
                      quantity=Decimal("98.0"), **APRIL)
    _, out = _out(conn, org_id)
    (fac,) = out["facilities"]
    assert fac["tco2e"] == "980.000000"
    assert fac["production"] == {"product_code": "al", "quantity": "98.000000", "unit": "t"}
    assert fac["gei"] == out["gei"] == "10.000000000"  # 980 tCO2e / 98 t
    assert fac["gei_unit"] == "tCO2e/t"


def test_production_correction_is_versioned_and_old_reports_reproduce(conn, plant):
    org_id, facility_id = plant
    pid = record_production(conn, facility_id=facility_id, product_code="al", unit="t",
                            quantity=Decimal("98.0"), **APRIL)
    before, _ = _out(conn, org_id)
    new_pid = edit_production(conn, pid, quantity=Decimal("100.0"), reason="weighbridge")
    _, after = _out(conn, org_id)
    assert after["gei"] == "9.800000000"
    assert regenerate(conn, before.report_id).output == before.output  # still 10.0
    assert conn.execute("SELECT supersedes FROM production_record WHERE production_id"
                        " = %s", (new_pid,)).fetchone() == (pid,)


def test_overlapping_production_is_rejected(conn, plant):
    _, facility_id = plant
    record_production(conn, facility_id=facility_id, product_code="al", unit="t",
                      quantity=Decimal(1), **APRIL)
    conn.execute("SAVEPOINT s")
    with pytest.raises(psycopg.errors.ExclusionViolation):  # would double the denominator
        record_production(conn, facility_id=facility_id, product_code="al", unit="t",
                          quantity=Decimal(1), **APRIL)
    conn.execute("ROLLBACK TO SAVEPOINT s")


def test_basis_cannot_silently_change_unit(conn, plant):
    _, facility_id = plant
    record_production(conn, facility_id=facility_id, product_code="al", unit="t",
                      quantity=Decimal(1), **APRIL)
    with pytest.raises(ValueError, match="boundary change"):
        record_production(conn, facility_id=facility_id, product_code="al", unit="kg",
                          quantity=Decimal(1), period_start=date(2025, 5, 1),
                          period_end=date(2025, 6, 1))


@pytest.mark.parametrize("setup, reason", [
    ("none", "no production recorded"),
    ("two_products", "more than one product"),
    ("unresolved", "unresolved"),
])
def test_gei_is_withheld_rather_than_wrong(conn, plant, setup, reason):
    org_id, facility_id = plant
    if setup != "none":
        record_production(conn, facility_id=facility_id, product_code="al", unit="t",
                          quantity=Decimal(98), **APRIL)
    if setup == "two_products":
        record_production(conn, facility_id=facility_id, product_code="billet", unit="t",
                          quantity=Decimal(5), **APRIL)
    if setup == "unresolved":  # no incl-RE-captive factor exists for FY2010-11 (series starts FY2016-17)
        _, out = _out(conn, org_id, Policy.LATEST_AVAILABLE)
        assert out["gei"] is not None
        r = generate_report(conn, org_id, FY, Policy.BASELINE_FROZEN, "FY2010-11")
        out = json.loads(r.output)
    else:
        _, out = _out(conn, org_id)
    (fac,) = out["facilities"]
    assert fac["gei"] is None and out["gei"] is None
    assert reason in fac["gei_withheld_because"]
