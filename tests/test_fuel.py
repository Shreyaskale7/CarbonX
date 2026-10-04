"""Scope 1 fuel combustion: BEE's Annexure IV factors, the typed program, and
(with a database) calculation and reporting."""
import csv
import json
from datetime import date
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from carbonx.engine.calculate import (
    activity_spec,
    calculate,
    emissions,
    record_activity,
)
from carbonx.engine.production import record_production
from carbonx.engine.report import generate_report
from carbonx.factors.registry import (
    POLICY_DESCRIPTIONS,
    EmissionFactor,
    Policy,
    insert_factor,
)
from carbonx.units.core import DimensionError
from carbonx.units.lang import run

ROOT = Path(__file__).resolve().parents[1]
GRID = "grid.weighted_avg_incl_re_captive.incl_imports"
APRIL = {"period_start": date(2025, 4, 1), "period_end": date(2025, 5, 1)}


def _coal(value="96.586") -> EmissionFactor:
    return EmissionFactor(1, 1, "fuel.other_bituminous_coal.co2e", "IN", Decimal(value),
                          "tCO2e", "TJ", date(2024, 4, 1), date(2027, 4, 1), "v1.0", 10,
                          None, "https://example.test")


# ---- no database -----------------------------------------------------------

def test_bee_table_is_complete_and_co2e_is_derived_as_documented():
    with (ROOT / "data" / "bee" / "fuel_factors.csv").open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert [int(r["sr_no"]) for r in rows] == list(range(1, 54))
    assert len({r["slug"] for r in rows}) == 53 and len({r["source_sha256"] for r in rows}) == 1
    for r in rows:  # co2e = co2 + (ch4*21 + n2o*310)/1000, GWPs from Annexure I
        expected = Decimal(r["co2_t_per_tj"]) + (
            Decimal(r["ch4_kg_per_tj"]) * 21 + Decimal(r["n2o_kg_per_tj"]) * 310) / 1000
        assert Decimal(r["co2e_t_per_tj"]) == expected
    by_slug = {r["slug"]: r for r in rows}
    assert by_slug["natural_gas"]["co2_t_per_tj"] == "56.10"         # p. 35, row 38
    assert by_slug["gas_diesel_oil"]["co2_t_per_tj"] == "74.10"      # p. 34, row 10
    assert by_slug["gas_works_gas"]["fuel"] == "Gas Works Gas"       # no page header glued on
    assert by_slug["municipal_waste_non_biomass_fraction"]["co2_t_per_tj"] == "91.70"


def test_energy_units_follow_the_iea_definitions():
    assert run("let x : [GJ] = 1 [toe]")["x"].value == Fraction("41.868")
    assert run("let x : [J] = 1 [kcal]")["x"].value == Fraction("4186.8")


def test_fuel_program_is_quantity_x_ncv_x_factor_x_oxidation():
    program, exact = emissions(Decimal(1000), "t", _coal(), Decimal(4000), "kcal/kg",
                               Decimal("0.98"))
    # 1000 t x 4000 kcal/kg = 4e9 kcal = 16.7472 TJ; x 96.586 x 0.98
    assert exact == Fraction("16.7472") * Fraction("96.586") * Fraction("0.98")
    assert "let emissions : [tCO2e] = fuel * ncv * factor * oxidation" in program


def test_ncv_in_other_units_gives_the_same_answer():
    a = emissions(Decimal(1000), "t", _coal(), Decimal("16.7472"), "GJ/t")[1]
    b = emissions(Decimal(1000), "t", _coal(), Decimal(4000), "kcal/kg")[1]
    assert a == b  # exactly: unit conversion is rational arithmetic


def test_wrong_ncv_unit_is_a_dimension_error():
    with pytest.raises(DimensionError):
        emissions(Decimal(1000), "t", _coal(), Decimal(4000), "kcal/litre")


def test_activity_types():
    assert activity_spec("fuel.natural_gas").factor_key == "fuel.natural_gas.co2e"
    assert activity_spec("fuel.natural_gas").scope == 1
    assert activity_spec("grid_electricity").scope == 2
    for bad in ("diesel", "fuel.", "fuel.Coal", "fuel.a b"):
        with pytest.raises(ValueError, match="unknown activity_type"):
            activity_spec(bad)


@pytest.mark.parametrize("kw, match", [
    ({"activity_type": "fuel.lignite"}, "needs ncv"),
    ({"activity_type": "grid_electricity", "ncv": Decimal(1), "ncv_unit": "GJ/t"}, "no ncv"),
    ({"activity_type": "fuel.lignite", "ncv": Decimal(-1), "ncv_unit": "GJ/t"}, "> 0"),
    ({"activity_type": "fuel.lignite", "ncv": Decimal(1), "ncv_unit": "GJ/t",
      "oxidation_factor": Decimal("1.2")}, "oxidation"),
    ({"activity_type": "fuel.lignite", "ncv": Decimal(1), "ncv_unit": "GJ/furlong"},
     "unit"),
])
def test_fuel_activity_validation_happens_before_the_db(kw, match):
    args = {"facility_id": 1, "quantity": Decimal(1), "unit": "t", **APRIL} | kw
    with pytest.raises(ValueError, match=match):
        record_activity(None, **args)  # type: ignore[arg-type]


# ---- with a database (rolled back) ------------------------------------------

@pytest.fixture
def plant(conn):
    for p, d in POLICY_DESCRIPTIONS.items():
        conn.execute("INSERT INTO resolution_policy (code, description) VALUES (%s, %s)"
                     " ON CONFLICT (code) DO NOTHING", (p.value, d))
    (sid,) = conn.execute(
        "INSERT INTO factor_source (publisher, dataset_name, version_label,"
        " version_ordinal, published_on, source_url) VALUES ('TEST', 'fuel', 'f1',"
        " 810000, '2026-01-01', 'https://example.test') RETURNING source_id").fetchone()
    # A slug no real table has, so real BEE rows can never interfere.
    insert_factor(conn, source_id=sid, factor_key="fuel.test_coal.co2e",
                  value=Decimal(100), numerator_unit="tCO2e", denominator_unit="TJ",
                  valid=(date(2024, 4, 1), date(2027, 4, 1)))
    insert_factor(conn, source_id=sid, factor_key=GRID, value=Decimal("0.700"),
                  numerator_unit="tCO2", denominator_unit="MWh", fy="FY2025-26")
    (org_id,) = conn.execute("INSERT INTO organisation (name) VALUES ('fuel org')"
                             " RETURNING org_id").fetchone()
    (fid,) = conn.execute("INSERT INTO facility (org_id, name, state) VALUES (%s, 'p',"
                          " 'OD') RETURNING facility_id", (org_id,)).fetchone()
    return org_id, fid


def test_fuel_activity_is_calculated_and_pinned(conn, plant):
    _, fid = plant
    a = record_activity(conn, facility_id=fid, activity_type="fuel.test_coal",
                        quantity=Decimal(1000), unit="t", ncv=Decimal(20), ncv_unit="GJ/t",
                        **APRIL)
    c = calculate(conn, a, Policy.AS_OF_REPORT)
    assert c.tco2e == Decimal("2000.000000")       # 1000 t x 20 GJ/t = 20 TJ x 100
    assert c.factor.factor_key == "fuel.test_coal.co2e"
    assert conn.execute("SELECT scope, ncv, ncv_unit FROM activity WHERE activity_id = %s",
                        (a,)).fetchone() == (1, Decimal("20.000000"), "GJ/t")


def test_report_covers_both_scopes_and_fuel_ignores_the_policy(conn, plant):
    org_id, fid = plant
    record_activity(conn, facility_id=fid, activity_type="fuel.test_coal",
                    quantity=Decimal(1000), unit="t", ncv=Decimal(20), ncv_unit="GJ/t",
                    **APRIL)
    record_activity(conn, facility_id=fid, activity_type="grid_electricity",
                    quantity=Decimal(1_000_000), unit="kWh", **APRIL)   # 700 tCO2e
    record_production(conn, facility_id=fid, product_code="al", unit="t",
                      quantity=Decimal(100), **APRIL)
    for policy in (Policy.VINTAGE_MATCHED, Policy.LATEST_AVAILABLE):
        out = json.loads(generate_report(conn, org_id, "FY2025-26", policy).output)
        assert out["totals"] == {"scope1_tco2e": "2000.000000",
                                 "scope2_tco2e": "700.000000",
                                 "total_tco2e": "2700.000000"}
        assert out["gei"] == "27.000000000"     # (2000 + 700) / 100 t
        fuel = next(x for x in out["lines"] if x["scope"] == 1)
        assert (fuel["ncv"], fuel["ncv_unit"], fuel["oxidation_factor"]) == \
            ("20.000000", "GJ/t", "1.000000")
