"""Denominator versioning (component 2): GEI = emissions / production, with
production as bitemporal and as reproducible as emissions. Rolled back."""
import json
from datetime import date
from decimal import Decimal

import psycopg
import pytest

from carbonx.engine.calculate import record_activity
from carbonx.engine.production import (
    edit_production,
    record_production,
    set_equivalence,
)
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
    ("two_products", "no equivalent-product conversion declared for al, billet"),
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


# ---- equivalent product (migration 0011) ------------------------------------

def _two_products(conn, facility_id):
    record_production(conn, facility_id=facility_id, product_code="al", unit="t",
                      quantity=Decimal(90), **APRIL)
    record_production(conn, facility_id=facility_id, product_code="billet", unit="t",
                      quantity=Decimal(20), **APRIL)


def _declare(conn, facility_id, code, factor, unit="t", basis="sector practice (test)"):
    return set_equivalence(conn, facility_id=facility_id, product_code=code, fy=FY,
                           factor=Decimal(factor), equivalent_unit=unit, basis=basis)


def test_equivalent_product_gives_two_product_plants_an_intensity(conn, plant):
    org_id, facility_id = plant
    _two_products(conn, facility_id)
    _declare(conn, facility_id, "al", "1")
    _, half = _out(conn, org_id)                       # billet not declared yet
    assert half["gei"] is None
    assert half["facilities"][0]["gei_withheld_because"].endswith("declared for billet")
    _declare(conn, facility_id, "billet", "0.4")
    _, out = _out(conn, org_id)
    (fac,) = out["facilities"]
    assert fac["production"]["quantity"] == "98.000000"  # 90 + 0.4 x 20
    assert fac["production"]["unit"] == "t"
    assert [p["equivalent_quantity"] for p in fac["production"]["from"]] == [
        "90.000000", "8.000000"]
    assert fac["gei"] == out["gei"] == "10.000000000"   # 980 tCO2e / 98 t
    assert {e["basis"] for e in out["product_equivalences"]} == {"sector practice (test)"}


def test_main_product_reading_is_factor_zero_and_gives_a_different_intensity(conn, plant):
    """BEE allows 'the main product or an equivalent product'. Same plant,
    same data, two permitted denominators."""
    org_id, facility_id = plant
    _two_products(conn, facility_id)
    _declare(conn, facility_id, "al", "1")
    _declare(conn, facility_id, "billet", "0", basis="main product only")
    _, main = _out(conn, org_id)
    assert main["gei"] == "10.888888889"                  # 980 / 90
    _declare(conn, facility_id, "billet", "1", basis="tonne for tonne")
    _, mass = _out(conn, org_id)
    assert mass["gei"] == "8.909090909"                   # 980 / 110


def test_revising_a_conversion_does_not_reach_an_old_report(conn, plant):
    org_id, facility_id = plant
    _two_products(conn, facility_id)
    _declare(conn, facility_id, "al", "1")
    first = _declare(conn, facility_id, "billet", "0.4")
    before, _ = _out(conn, org_id)
    second = _declare(conn, facility_id, "billet", "0.5", basis="revised practice")
    _, after = _out(conn, org_id)
    assert after["gei"] == "9.800000000"                  # 980 / 100
    assert regenerate(conn, before.report_id).output == before.output
    assert conn.execute("SELECT supersedes FROM product_equivalence"
                        " WHERE equivalence_id = %s", (second,)).fetchone() == (first,)


def test_conversions_must_agree_on_the_equivalent_unit_and_have_the_right_dimension(conn, plant):
    org_id, facility_id = plant
    _two_products(conn, facility_id)
    _declare(conn, facility_id, "al", "1")
    _declare(conn, facility_id, "billet", "400", unit="kg")
    _, out = _out(conn, org_id)
    assert "different equivalent units" in out["facilities"][0]["gei_withheld_because"]
    with pytest.raises(ValueError, match="basis"):
        _declare(conn, facility_id, "billet", "0.4", basis="  ")
    with pytest.raises(ValueError, match=">= 0"):
        _declare(conn, facility_id, "billet", "-1")


def test_conversions_are_append_only_in_the_database(conn, plant):
    _, facility_id = plant
    eid = _declare(conn, facility_id, "al", "1")
    for sql, exc in [
        ("UPDATE product_equivalence SET factor = 2 WHERE equivalence_id = %s",
         psycopg.errors.RaiseException),                       # in-place edit
        ("DELETE FROM product_equivalence WHERE equivalence_id = %s",
         psycopg.errors.InsufficientPrivilege),                # the app cannot delete
    ]:
        conn.execute("SAVEPOINT s")
        with pytest.raises(exc):
            conn.execute(sql, (eid,))
        conn.execute("ROLLBACK TO SAVEPOINT s")
    conn.execute("SAVEPOINT s")
    with pytest.raises(psycopg.errors.ExclusionViolation):   # two current rows
        conn.execute(
            "INSERT INTO product_equivalence (facility_id, product_code, valid_time,"
            " factor, equivalent_unit, basis, system_time_range) VALUES (%s, 'al',"
            " '[2025-04-01,2026-04-01)', 2, 't', 'x', tstzrange(fn_system_now(), NULL))",
            (facility_id,))
    conn.execute("ROLLBACK TO SAVEPOINT s")
    assert conn.execute("SELECT count(*) FROM audit_event WHERE entity_table ="
                        " 'product_equivalence' AND entity_id = %s", (eid,)).fetchone()[0] == 1


def test_report_api_generates_and_verifies(conn, plant):
    """The viva demo path: generate under a policy, then verify byte-identity."""
    from fastapi.testclient import TestClient

    from carbonx.api import main as api
    org_id, facility_id = plant
    record_production(conn, facility_id=facility_id, product_code="al", unit="t",
                      quantity=Decimal("98.0"), **APRIL)
    api.app.dependency_overrides[api.db] = lambda: conn
    try:
        client = TestClient(api.app)
        r = client.post("/api/reports", json={"org_id": org_id, "policy": "VINTAGE_MATCHED"})
        assert r.status_code == 200, r.text
        assert r.json()["gei"] == "10.000000000"
        v = client.get(f"/api/reports/{r.json()['report_id']}/verify").json()
        assert v["byte_identical"] and v["regenerated_sha256"] == r.json()["sha256"]
        assert client.get("/api/reports/999999999/verify").status_code == 404
    finally:
        api.app.dependency_overrides.clear()
