"""A draft of BEE's Form I from a stored report. Pure tests need no database; the tag tests do."""
import json
from datetime import date
from decimal import Decimal

import psycopg
import pytest

from carbonx.compliance import boundary, form_i
from carbonx.engine.calculate import record_activity
from carbonx.engine.production import record_production
from carbonx.engine.report import generate_report
from carbonx.factors.registry import POLICY_DESCRIPTIONS, Policy, insert_factor


def line(activity_id: int, scope: int, tco2e: str, kind: str = "grid_electricity",
         quantity: str = "1000000", unit: str = "kWh") -> dict:
    return {"activity_id": activity_id, "facility_id": 1, "activity_type": kind, "scope": scope,
            "quantity": quantity, "unit": unit, "tco2e": tco2e}


def report(lines: list[dict], unresolved: list[dict] | None = None,
           production: dict | None = None) -> str:
    production = {"product_code": "al", "quantity": "100.000000", "unit": "t"} \
        if production is None else production
    return json.dumps({
        "org_id": 1, "compliance_year": "FY2025-26", "policy": "AS_OF_REPORT",
        "as_of": "2026-01-01T00:00:00+00:00", "lines": lines, "unresolved": unresolved or [],
        "facilities": [{"facility_id": 1, "production": production, "gei": None,
                        "gei_unit": None, "gei_withheld_because": None}]})


def tag(boundary_: str) -> dict:
    return {"tag_id": 1, "boundary": boundary_, "basis": "test"}


LINES = [line(1, 2, "700.000000"),                                       # 1,000,000 kWh grid
         line(2, 1, "280.000000", "fuel.diesel", "100", "kl")]           # direct combustion


def worksheet(lines, tags, **kw):
    return json.loads(form_i.form_i(report(lines, **kw), tags))["facilities"][0]


def test_inside_lines_fill_the_rows_and_the_specific_emission_is_exact():
    f = worksheet(LINES, {1: tag("inside"), 2: tag("inside")})
    assert f["5.1(b)(xi) direct GHG, energy related (tCO2e)"] == "280.000000"
    assert f["5.1(b)(xii) indirect GHG, energy related (tCO2e)"] == "700.000000"
    assert f["5.1(b)(i) electricity purchased (million kWh)"] == "1.000000"
    assert f["5.1(c)(iii) specific GHG emissions"] == {"value": "9.800000", "unit": "tCO2e/t"}
    assert f["complete"] is True


def test_an_outside_line_is_left_out_and_counted():
    f = worksheet(LINES, {1: tag("outside"), 2: tag("inside")})
    assert f["5.1(b)(xii) indirect GHG, energy related (tCO2e)"] == "0.000000"
    assert f["5.1(b)(i) electricity purchased (million kWh)"] == "0.000000"
    assert f["boundary"]["outside"] == 1 and f["boundary"]["outside_tco2e"] == "700.000000"


def test_an_untagged_line_is_never_assumed_inside():
    f = worksheet(LINES, {1: tag("inside")})                                  # activity 2 has no tag
    assert f["complete"] is False and f["boundary"]["untagged"] == 1
    assert f["5.1(c)(iii) specific GHG emissions"] is None
    assert "no boundary tag" in f["specific_withheld_because"]
    assert f["5.1(b)(xi) direct GHG, energy related (tCO2e)"] == "0.000000"   # not counted


def test_an_unresolved_line_makes_it_incomplete():
    f = worksheet(LINES, {1: tag("inside"), 2: tag("inside")},
                  unresolved=[{"facility_id": 1, "activity_id": 3}])
    assert f["complete"] is False and f["5.1(c)(iii) specific GHG emissions"] is None


def test_process_emissions_and_the_total_are_never_claimed():
    f = worksheet(LINES, {1: tag("inside"), 2: tag("inside")})
    assert f["5.1(b)(xiii) direct GHG, process related (tCO2e)"] is None
    assert f["5.1(b)(xiv) total direct and indirect (tCO2e)"] is None
    assert f["subtotal_excluding_process_tco2e"] == "980.000000"
    assert "not recorded" in f["process_note"]


def test_zero_production_withholds_the_specific_emission():
    f = worksheet(LINES, {1: tag("inside"), 2: tag("inside")},
                  production={"product_code": "al", "quantity": "0.000000", "unit": "t"})
    assert f["5.1(c)(iii) specific GHG emissions"] is None


def test_the_worksheet_is_canonical_and_says_what_it_is_not():
    out = form_i.form_i(report(LINES), {1: tag("inside"), 2: tag("inside")})
    assert out == form_i.form_i(report(LINES), {1: tag("inside"), 2: tag("inside")})
    parsed = json.loads(out)
    assert out == json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert "not a filing" in parsed["status"] and "not signed or certified" in parsed["status"]
    assert "general_details" in parsed["not_provided"]


# Database: tags are versioned, audited, and read AS OF the report's time.
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
        " published_on, source_url) VALUES ('TEST', 'fi', 'f1', 800002, '2026-01-01',"
        " 'https://example.test') RETURNING source_id").fetchone()
    insert_factor(conn, source_id=sid, factor_key=GRID, value=Decimal("0.700"),
                  numerator_unit="tCO2", denominator_unit="MWh", fy=FY)
    (org_id,) = conn.execute("INSERT INTO organisation (name) VALUES ('fi org')"
                             " RETURNING org_id").fetchone()
    (facility_id,) = conn.execute("INSERT INTO facility (org_id, name, state)"
                                  " VALUES (%s, 'p', 'OD') RETURNING facility_id",
                                  (org_id,)).fetchone()
    activity_id = record_activity(conn, facility_id=facility_id, activity_type="grid_electricity",
                                  quantity=Decimal(1_400_000), unit="kWh", **APRIL)  # 980 tCO2e
    record_production(conn, facility_id=facility_id, product_code="al", unit="t",
                      quantity=Decimal("98.0"), **APRIL)
    return org_id, activity_id


def test_a_tag_is_versioned_and_a_later_tag_does_not_change_an_earlier_worksheet(conn, plant):
    org_id, activity_id = plant
    first = boundary.tag_activity(conn, activity_id=activity_id, boundary="inside",
                                  basis="main meter")
    r = generate_report(conn, org_id, FY, Policy.VINTAGE_MATCHED)
    before = form_i.for_report(conn, r.report_id)
    assert json.loads(before)["facilities"][0]["5.1(c)(iii) specific GHG emissions"][
        "value"] == "10.000000"                                                    # 980 / 98
    second = boundary.tag_activity(conn, activity_id=activity_id, boundary="outside",
                                   basis="re-metered: this feeds the colony")
    assert form_i.for_report(conn, r.report_id) == before
    assert conn.execute("SELECT supersedes FROM activity_boundary WHERE tag_id = %s",
                        (second,)).fetchone()[0] == first
    later = generate_report(conn, org_id, FY, Policy.VINTAGE_MATCHED)
    assert json.loads(form_i.for_report(conn, later.report_id))["facilities"][0][
        "boundary"]["outside"] == 1


def test_a_tag_needs_a_basis_a_known_value_and_a_real_activity_and_is_immutable(conn, plant):
    _, activity_id = plant
    with pytest.raises(ValueError, match="basis"):
        boundary.tag_activity(conn, activity_id=activity_id, boundary="inside", basis=" ")
    with pytest.raises(ValueError, match="boundary must be"):
        boundary.tag_activity(conn, activity_id=activity_id, boundary="maybe", basis="x")
    with pytest.raises(LookupError):
        boundary.tag_activity(conn, activity_id=-1, boundary="inside", basis="x")
    tag_id = boundary.tag_activity(conn, activity_id=activity_id, boundary="inside", basis="x")
    for sql in ("UPDATE activity_boundary SET boundary = 'outside' WHERE tag_id = %s",
                "DELETE FROM activity_boundary WHERE tag_id = %s"):
        with pytest.raises(psycopg.Error), conn.transaction():
            conn.execute(sql, (tag_id,))
