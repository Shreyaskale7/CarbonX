"""Meters: activity-data uncertainty exists only with its calibration
certificate, a reading pins the meter as declared, and readings from one meter
are wrong together."""
import json
from datetime import date
from decimal import Decimal
from fractions import Fraction
from math import sqrt

import psycopg
import pytest

from carbonx.engine.calculate import edit_activity, record_activity
from carbonx.engine.meters import declare_meter
from carbonx.engine.report import generate_report, regenerate
from carbonx.factors.registry import POLICY_DESCRIPTIONS, Policy, insert_factor
from carbonx.uncertainty.propagate import Line, band, for_report

GRID = "grid.weighted_avg_incl_re_captive.incl_imports"


# ---- arithmetic (no database) ------------------------------------------------

def test_readings_from_one_meter_add_linearly_and_meters_combine_in_quadrature():
    one = [Line(1, Fraction(600), None, None, meter_id=7, meter_u=Fraction(1, 100)),
           Line(1, Fraction(400), None, None, meter_id=7, meter_u=Fraction(1, 100))]
    b = band(one)
    assert float(b.high) - 1000 == pytest.approx(10.0)             # (600 + 400) x 1%
    assert float(b.high_if_independent) - 1000 == pytest.approx(sqrt(6**2 + 4**2))
    two = [Line(1, Fraction(600), None, None, meter_id=7, meter_u=Fraction(1, 100)),
           Line(1, Fraction(400), None, None, meter_id=8, meter_u=Fraction(1, 100))]
    assert float(band(two).high) - 1000 == pytest.approx(sqrt(6**2 + 4**2))


def test_meter_and_factor_uncertainty_combine_and_missing_ones_are_counted():
    lines = [Line(1, Fraction(1000), Fraction(3, 100), Fraction(4, 100),
                  meter_id=7, meter_u=Fraction(3, 100)),
             Line(2, Fraction(500), None, None)]                    # no range, no meter
    b = band(lines)
    assert 1500 - float(b.low) == pytest.approx(sqrt(30**2 + 30**2))
    assert float(b.high) - 1500 == pytest.approx(50.0)              # sqrt(40^2 + 30^2)
    assert b.unquantified == Decimal("500.000000") and b.unmetered == Decimal("500.000000")


# ---- with a database -----------------------------------------------------------

@pytest.fixture
def plant(conn):
    for p, d in POLICY_DESCRIPTIONS.items():
        conn.execute("INSERT INTO resolution_policy (code, description) VALUES (%s, %s)"
                     " ON CONFLICT (code) DO NOTHING", (p.value, d))
    (sid,) = conn.execute(
        "INSERT INTO factor_source (publisher, dataset_name, version_label,"
        " version_ordinal, published_on, source_url) VALUES ('TEST', 'meters', 'm1',"
        " 820000, '2026-01-01', 'https://example.test') RETURNING source_id").fetchone()
    insert_factor(conn, source_id=sid, factor_key=GRID, value=Decimal("0.700"),
                  numerator_unit="tCO2", denominator_unit="MWh", fy="FY2025-26")
    (org_id,) = conn.execute("INSERT INTO organisation (name) VALUES ('meter org')"
                             " RETURNING org_id").fetchone()
    (fid,) = conn.execute("INSERT INTO facility (org_id, name, state) VALUES (%s, 'p', 'KA')"
                          " RETURNING facility_id", (org_id,)).fetchone()
    (cert,) = conn.execute(
        "INSERT INTO source_document (facility_id, doc_type, filename, storage_path, sha256)"
        " VALUES (%s, 'meter_reading', 'calibration.pdf', 'x', repeat('c', 64))"
        " RETURNING document_id", (fid,)).fetchone()
    return org_id, fid, cert


def _reading(conn, fid, month, meter_id, kwh=1_000_000):
    return record_activity(conn, facility_id=fid, activity_type="grid_electricity",
                           period_start=date(2025, month, 1), period_end=date(2025, month + 1, 1),
                           quantity=Decimal(kwh), unit="kWh", meter_id=meter_id)


def test_an_uncertainty_is_refused_without_its_certificate(conn, plant):
    _, fid, cert = plant
    with pytest.raises(ValueError, match="certificate"):
        declare_meter(conn, facility_id=fid, meter_code="HT-1", measures="grid_electricity",
                      uncertainty_pct=Decimal("0.5"))
    conn.execute("SAVEPOINT s")                 # and the database refuses it on its own
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("INSERT INTO meter (facility_id, meter_code, measures, uncertainty_pct,"
                     " system_time_range) VALUES (%s, 'HT-9', 'grid_electricity', 0.5,"
                     " tstzrange(fn_system_now(), NULL))", (fid,))
    conn.execute("ROLLBACK TO SAVEPOINT s")
    assert declare_meter(conn, facility_id=fid, meter_code="HT-1", measures="grid_electricity",
                         uncertainty_pct=Decimal("0.5"), calibration_document_id=cert)
    assert declare_meter(conn, facility_id=fid, meter_code="HT-2", measures="grid_electricity")


def test_a_reading_must_come_from_a_meter_that_measures_it_here(conn, plant):
    _, fid, _ = plant
    gas = declare_meter(conn, facility_id=fid, meter_code="GAS-1", measures="fuel.natural_gas")
    with pytest.raises(ValueError, match="cannot be the source"):
        _reading(conn, fid, 4, gas)
    with pytest.raises(LookupError):
        _reading(conn, fid, 4, 999_999_999)
    with pytest.raises(ValueError, match="does not change what it measures"):
        declare_meter(conn, facility_id=fid, meter_code="GAS-1", measures="grid_electricity")


def test_report_band_uses_the_stated_uncertainty_and_recalibration_does_not_reach_back(conn, plant):
    org_id, fid, cert = plant
    old = declare_meter(conn, facility_id=fid, meter_code="HT-1", measures="grid_electricity",
                        uncertainty_pct=Decimal("0.5"), calibration_document_id=cert)
    april = _reading(conn, fid, 4, old)                         # 700 tCO2e
    _reading(conn, fid, 5, old)                                 # 700 tCO2e
    _reading(conn, fid, 6, None)                                # 700 tCO2e, no meter stated
    before = generate_report(conn, org_id, "FY2025-26", Policy.VINTAGE_MATCHED)
    line = json.loads(before.output)["lines"][0]
    assert line["meter"] == {"meter_id": old, "code": "HT-1", "uncertainty_pct": "0.500",
                             "certificate_sha256": "c" * 64}
    b = for_report(conn, before.report_id)
    assert float(b.high) - 2100 == pytest.approx(7.0)           # (700 + 700) x 0.5%
    assert b.unmetered == Decimal("700.000000")
    assert any("calibration certificate" in why for why in b.basis)

    new = declare_meter(conn, facility_id=fid, meter_code="HT-1", measures="grid_electricity",
                        uncertainty_pct=Decimal(2), calibration_document_id=cert,
                        reason="recalibrated")
    assert new != old
    assert regenerate(conn, before.report_id).output == before.output
    assert float(for_report(conn, before.report_id).high) - 2100 == pytest.approx(7.0)
    corrected, _ = edit_activity(conn, april, quantity=Decimal(900_000), reason="re-read")
    assert conn.execute("SELECT meter_id FROM activity WHERE activity_id = %s",
                        (corrected,)).fetchone() == (old,)      # still that meter's reading


def test_meters_are_append_only(conn, plant):
    _, fid, _ = plant
    m = declare_meter(conn, facility_id=fid, meter_code="HT-1", measures="grid_electricity")
    for sql, exc in [("UPDATE meter SET meter_code = 'X' WHERE meter_id = %s",
                      psycopg.errors.RaiseException),
                     ("DELETE FROM meter WHERE meter_id = %s",
                      psycopg.errors.InsufficientPrivilege)]:
        conn.execute("SAVEPOINT s")
        with pytest.raises(exc):
            conn.execute(sql, (m,))
        conn.execute("ROLLBACK TO SAVEPOINT s")
