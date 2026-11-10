"""Entitlement = (notified target - achieved) x production (BEE pp. 4, 22). The arithmetic and the
refusals need no database; the stored-target tests do, and are skipped when Postgres is down."""
import json
from datetime import date
from decimal import Decimal

import pytest

from carbonx.compliance import entitlement as ent
from carbonx.engine.calculate import record_activity
from carbonx.engine.production import record_production
from carbonx.engine.report import generate_report
from carbonx.factors.registry import POLICY_DESCRIPTIONS, Policy, insert_factor

TARGET = {"target_id": 7, "value": "9.000000000", "unit": "tCO2e/t", "status": "notified",
          "source_citation": "test notification, annex 1", "source_url": None, "baseline_fy": None}


def facility(gei: str | None = "10.000000000", qty: str = "98.000000", unit: str = "tCO2e/t",
             why: str | None = None) -> dict:
    return {"facility_id": 1, "tco2e": "980.000000", "gei": gei, "gei_unit": unit,
            "gei_withheld_because": why,
            "production": None if gei is None else {"product_code": "al", "quantity": qty,
                                                    "unit": "t"}}


def test_a_shortfall_is_negative_and_exact():
    out = ent.entitlement_for_facility(facility(), TARGET)       # (9 - 10) x 98
    assert out["entitlement_tco2e_equivalent"] == "-98.000000"
    assert out["outcome"].startswith("shortfall")


def test_a_surplus_is_positive_and_a_tie_is_on_target():
    assert ent.entitlement_for_facility(facility("8.500000000"), TARGET)[
        "entitlement_tco2e_equivalent"] == "49.000000"           # (9 - 8.5) x 98
    out = ent.entitlement_for_facility(facility("9.000000000"), TARGET)
    assert out["outcome"] == "on target" and out["entitlement_tco2e_equivalent"] == "0.000000"


def test_no_certificate_count_is_invented():
    out = ent.entitlement_for_facility(facility("8.5"), TARGET)
    assert "no certificate count" in out["note"]
    assert not any("count" in k for k in out if k != "note")


@pytest.mark.parametrize("fac, target, why", [
    (facility(None, why="zero production"), TARGET, "no achieved intensity: zero production"),
    (facility(), None, "no target recorded"),
    (facility(unit="tCO2e/MWh"), TARGET, "not comparable"),
])
def test_it_refuses_rather_than_guess(fac, target, why):
    out = ent.entitlement_for_facility(fac, target)
    assert out["entitlement_tco2e_equivalent"] is None and out["outcome"] is None
    assert why in out["withheld_because"]


def test_an_assumed_target_is_flagged_on_the_result():
    out = ent.entitlement_for_facility(facility(), TARGET | {"status": "assumed"})
    assert "assumed" in out["note"] and "do not rely" in out["note"]
    assert "assumed" not in ent.entitlement_for_facility(facility(), TARGET)["note"]


def test_the_output_is_canonical_and_covers_every_facility():
    report = json.dumps({"org_id": 1, "compliance_year": "FY2025-26", "policy": "AS_OF_REPORT",
                         "as_of": "2026-01-01T00:00:00+00:00",
                         "facilities": [facility() | {"facility_id": 2}, facility()]})
    one = ent.entitlements(report, {1: TARGET})
    assert one == ent.entitlements(report, {1: TARGET})           # a pure function
    parsed = json.loads(one)
    assert [f["facility_id"] for f in parsed["facilities"]] == [2, 1]
    assert parsed["facilities"][0]["withheld_because"] == "no target recorded for this facility and year"
    assert one == json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False)  # canonical


# Database: a stored target, superseded and audited, read AS OF the report's time.
FY = "FY2025-26"
GRID = "grid.weighted_avg_incl_re_captive.incl_imports"
APRIL = {"period_start": date(2025, 4, 1), "period_end": date(2025, 5, 1)}


@pytest.fixture
def plant(conn):
    for p, d in POLICY_DESCRIPTIONS.items():
        conn.execute("INSERT INTO resolution_policy (code, description) VALUES (%s, %s)"
                     " ON CONFLICT (code) DO NOTHING", (p.value, d))
    (sid,) = conn.execute(
        "INSERT INTO factor_source (publisher, dataset_name, version_label, version_ordinal,"
        " published_on, source_url) VALUES ('TEST', 'ent', 'e1', 800001, '2026-01-01',"
        " 'https://example.test') RETURNING source_id").fetchone()
    insert_factor(conn, source_id=sid, factor_key=GRID, value=Decimal("0.700"),
                  numerator_unit="tCO2", denominator_unit="MWh", fy=FY)
    (org_id,) = conn.execute("INSERT INTO organisation (name) VALUES ('ent org')"
                             " RETURNING org_id").fetchone()
    (facility_id,) = conn.execute("INSERT INTO facility (org_id, name, state)"
                                  " VALUES (%s, 'p', 'OD') RETURNING facility_id",
                                  (org_id,)).fetchone()
    record_activity(conn, facility_id=facility_id, activity_type="grid_electricity",
                    quantity=Decimal(1_400_000), unit="kWh", **APRIL)       # 980 tCO2e
    record_production(conn, facility_id=facility_id, product_code="al", unit="t",
                      quantity=Decimal("98.0"), **APRIL)
    return org_id, facility_id


def _target(conn, facility_id, value, **kw):
    return ent.set_target(conn, facility_id=facility_id, fy=FY, value=Decimal(value),
                          unit="tCO2e/t", status=kw.pop("status", "assumed"),
                          source_citation="test fixture, not a notification", **kw)


def test_a_stored_target_gives_the_entitlement_for_a_report(conn, plant):
    org_id, facility_id = plant
    _target(conn, facility_id, "9")
    r = generate_report(conn, org_id, FY, Policy.VINTAGE_MATCHED)
    out = json.loads(ent.for_report(conn, r.report_id))
    assert out["facilities"][0]["entitlement_tco2e_equivalent"] == "-98.000000"   # GEI is 10


def test_a_later_target_does_not_change_an_earlier_entitlement(conn, plant):
    org_id, facility_id = plant
    first = _target(conn, facility_id, "9")
    r = generate_report(conn, org_id, FY, Policy.VINTAGE_MATCHED)
    before = ent.for_report(conn, r.report_id)
    second = _target(conn, facility_id, "12", status="notified")                  # supersedes
    assert ent.for_report(conn, r.report_id) == before                           # still the target it read
    assert conn.execute("SELECT supersedes FROM intensity_target WHERE target_id = %s",
                        (second,)).fetchone()[0] == first
    later = generate_report(conn, org_id, FY, Policy.VINTAGE_MATCHED)
    assert json.loads(ent.for_report(conn, later.report_id))["facilities"][0][
        "entitlement_tco2e_equivalent"] == "196.000000"                          # (12 - 10) x 98


def test_a_target_needs_its_source_and_cannot_be_edited_or_deleted(conn, plant):
    _, facility_id = plant
    with pytest.raises(ValueError, match="where the target comes from"):
        ent.set_target(conn, facility_id=facility_id, fy=FY, value=Decimal(9), unit="tCO2e/t",
                       status="notified", source_citation="  ")
    with pytest.raises(ValueError, match="status"):
        ent.set_target(conn, facility_id=facility_id, fy=FY, value=Decimal(9), unit="tCO2e/t",
                       status="official", source_citation="x")
    tid = _target(conn, facility_id, "9")
    import psycopg
    for sql in ("UPDATE intensity_target SET value = 1 WHERE target_id = %s",
                "DELETE FROM intensity_target WHERE target_id = %s"):
        with pytest.raises(psycopg.Error), conn.transaction():
            conn.execute(sql, (tid,))
    assert conn.execute("SELECT count(*) FROM audit_event WHERE entity_table = 'intensity_target'"
                        " AND entity_id = %s", (tid,)).fetchone()[0] == 1
