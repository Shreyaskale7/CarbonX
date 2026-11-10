"""Entitlement = (notified target - achieved) x production (BEE pp. 4, 22), from the exact
gate-to-gate figures. The arithmetic and the refusals need no database; the stored-input tests do,
and are skipped when Postgres is down."""
import json
from datetime import date
from decimal import Decimal
from fractions import Fraction

import psycopg
import pytest
from compliance_helpers import fuel_line, grid_line, report, tag

from carbonx.compliance import boundary, form_i
from carbonx.compliance import entitlement as ent
from carbonx.compliance.baseline import set_baseline
from carbonx.compliance.figures import Figures
from carbonx.engine.calculate import record_activity
from carbonx.engine.production import record_production
from carbonx.engine.report import generate_report
from carbonx.factors.registry import POLICY_DESCRIPTIONS, Policy, insert_factor

TARGET = {"target_id": 7, "value": "9.000000000", "unit": "tCO2e/t", "status": "notified",
          "source_citation": "test notification, annex 1", "source_url": "https://example.test",
          "baseline_fy": None}
BASE = {"baseline_id": 3, "baseline_fy": "FY2023-24", "intensity": "12.500000000",
        "unit": "tCO2e/t", "output": None, "output_unit": None, "status": "notified",
        "source_citation": "test notification, schedule", "source_url": "https://example.test"}


def fig(emissions="980", production: str | None = "98", unit: str | None = "t",
        untagged: int = 0, unresolved: int = 0) -> Figures:
    return Figures(direct=Fraction(0), indirect=Fraction(emissions), outside=Fraction(0),
                   purchased_kwh=Fraction(0),
                   production=None if production is None else Fraction(production),
                   production_unit=unit, inside=1, outside_count=0, untagged=untagged,
                   unresolved=unresolved)


def one(f: Figures, target=TARGET, baseline=None, why=None) -> dict:
    return ent.entitlement_for_facility(1, f, target, baseline, why)


def test_a_shortfall_is_negative_and_exact():
    out = one(fig())                                             # 9 x 98 - 980
    assert out["entitlement_tco2e_equivalent"] == "-98.000000"
    assert out["outcome"].startswith("shortfall")
    assert out["achieved"] == {"value": "10.000000000", "unit": "tCO2e/t"}


def test_a_surplus_is_positive_and_a_tie_is_on_target():
    assert one(fig("833"))["entitlement_tco2e_equivalent"] == "49.000000"     # 882 - 833
    out = one(fig("882"))
    assert out["outcome"] == "on target" and out["entitlement_tco2e_equivalent"] == "0.000000"


def test_the_figure_does_not_carry_the_rounding_of_the_intensity():
    """10,000,000 t over 3,000,000 units is 3.333... Rounding that to 9 places first and then
    multiplying back would give 2000000.001; target x production - emissions is exactly 2,000,000."""
    out = one(fig("10000000", "3000000"), TARGET | {"value": "4"})
    assert out["entitlement_tco2e_equivalent"] == "2000000.000000"
    assert out["achieved"]["value"] == "3.333333333"             # shown rounded, never used


def test_no_certificate_count_is_invented():
    out = one(fig("833"))
    assert "no certificate count" in out["note"] and "another policy" in out["note"]
    assert not any("count" in k for k in out if k != "note")


@pytest.mark.parametrize("f, target, why", [
    (fig(production=None, unit=None), TARGET, "no achieved intensity: zero production"),
    (fig(production="0"), TARGET, "no achieved intensity"),
    (fig(), None, "no target recorded"),
    (fig(unit="MWh"), TARGET, "not comparable"),
    (fig(untagged=2), TARGET, "2 activity line(s) have no boundary tag"),
    (fig(unresolved=1), TARGET, "1 line(s) are unresolved"),
])
def test_it_refuses_rather_than_guess(f, target, why):
    out = one(f, target, why="zero production")
    assert out["entitlement_tco2e_equivalent"] is None and out["outcome"] is None
    assert why in out["withheld_because"]


def test_an_assumed_target_is_flagged_on_the_result():
    assert "do not rely" in one(fig(), TARGET | {"status": "assumed"})["note"]
    assert "do not rely" not in one(fig())["note"]


def test_a_notified_figure_needs_the_url_it_was_read_in():
    """Refused before the database is touched, so the API and the loader cannot differ on it."""
    common = {"facility_id": 1, "status": "notified", "source_citation": "gazette, schedule, row 4"}
    with pytest.raises(ValueError, match="needs the url"):
        ent.set_target(None, fy="FY2025-26", value=Decimal(9), unit="tCO2e/t", **common)
    with pytest.raises(ValueError, match="needs the url"):
        ent.set_target(None, fy="FY2025-26", value=Decimal(9), unit="tCO2e/t", source_url="  ",
                       **common)
    with pytest.raises(ValueError, match="needs the url"):
        set_baseline(None, baseline_fy="FY2023-24", intensity=Decimal(12), intensity_unit="tCO2e/t",
                     **common)


# From a report: only inside-boundary lines count, and the Form I draft shows the same intensity.
LINES = [grid_line(1), fuel_line(2)]                             # 700 + 280 tCO2e over 100 t


def facility_out(lines, tags, target=TARGET, **kw) -> dict:
    return json.loads(ent.entitlements(report(lines, **kw), {1: target}, None, tags))[
        "facilities"][0]


def test_lines_are_recomputed_exactly_and_only_inside_ones_count():
    both = facility_out(LINES, {1: tag("inside"), 2: tag("inside")})
    assert both["achieved"]["value"] == "9.800000000"            # 980 / 100
    assert both["entitlement_tco2e_equivalent"] == "-80.000000"  # 9 x 100 - 980
    fuel_only = facility_out(LINES, {1: tag("outside"), 2: tag("inside")})
    assert fuel_only["achieved"]["value"] == "2.800000000"
    assert fuel_only["entitlement_tco2e_equivalent"] == "620.000000"          # 900 - 280
    assert fuel_only["boundary"] == {"inside": 1, "outside": 1, "untagged": 0, "unresolved": 0}


def test_an_untagged_line_withholds_the_entitlement():
    out = facility_out(LINES, {1: tag("inside")})
    assert out["entitlement_tco2e_equivalent"] is None
    assert "no boundary tag" in out["withheld_because"]


@pytest.mark.parametrize("tags", [
    {1: tag("inside"), 2: tag("inside")},
    {1: tag("outside"), 2: tag("inside")},
])
def test_the_entitlement_and_the_form_i_draft_show_the_same_intensity(tags):
    achieved = facility_out(LINES, tags)["achieved"]
    specific = json.loads(form_i.form_i(report(LINES), tags))["facilities"][0][
        "5.1(c)(iii) specific GHG emissions"]
    assert Decimal(achieved["value"]) == Decimal(specific["value"])
    assert achieved["unit"] == specific["unit"]


def test_the_output_is_canonical():
    tags = {1: tag("inside"), 2: tag("inside")}
    out = ent.entitlements(report(LINES), {1: TARGET}, {1: BASE}, tags)
    assert out == ent.entitlements(report(LINES), {1: TARGET}, {1: BASE}, tags)
    assert out == json.dumps(json.loads(out), sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False)


# The baseline: informational, never part of the entitlement figure itself.
def test_reduction_against_the_baseline_is_shown_but_does_not_move_the_entitlement():
    with_base, without = one(fig(), baseline=BASE), one(fig())   # achieved 10, baseline 12.5
    assert with_base["reduction_vs_baseline_pct"] == "20.000000"
    assert with_base["entitlement_tco2e_equivalent"] == without["entitlement_tco2e_equivalent"]
    assert with_base["baseline_notes"] == []
    assert without["reduction_vs_baseline_pct"] is None
    assert "no baseline recorded" in without["baseline_notes"][0]


def test_an_assumed_baseline_or_a_year_mismatch_is_flagged():
    out = one(fig(), TARGET | {"baseline_fy": "FY2022-23"}, BASE | {"status": "assumed"})
    notes = " | ".join(out["baseline_notes"])
    assert "'assumed'" in notes and "FY2022-23" in notes and "FY2023-24" in notes


def test_a_baseline_in_another_unit_shows_no_reduction():
    out = one(fig(), baseline=BASE | {"unit": "tCO2e/MWh"})
    assert out["reduction_vs_baseline_pct"] is None
    assert "no reduction is shown" in out["baseline_notes"][0]
    assert out["entitlement_tco2e_equivalent"] == "-98.000000"   # the entitlement is unaffected


# Database: stored inputs, superseded and audited, read AS OF the report's time.
FY = "FY2025-26"
GRID = "grid.weighted_avg_incl_re_captive.incl_imports"
APRIL = {"period_start": date(2025, 4, 1), "period_end": date(2025, 5, 1)}
URL = "https://example.test/notification"


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
    activity_id = record_activity(conn, facility_id=facility_id, activity_type="grid_electricity",
                                  quantity=Decimal(1_400_000), unit="kWh", **APRIL)  # 980 tCO2e
    record_production(conn, facility_id=facility_id, product_code="al", unit="t",
                      quantity=Decimal("98.0"), **APRIL)
    return org_id, facility_id, activity_id


def _target(conn, facility_id, value, **kw):
    return ent.set_target(conn, facility_id=facility_id, fy=FY, value=Decimal(value),
                          unit="tCO2e/t", status=kw.pop("status", "assumed"),
                          source_citation="test fixture, not a notification", **kw)


def _entitled(conn, report_id) -> dict:
    return json.loads(ent.for_report(conn, report_id))["facilities"][0]


def test_a_stored_target_gives_the_entitlement_once_the_activity_is_tagged(conn, plant):
    org_id, facility_id, activity_id = plant
    _target(conn, facility_id, "9")
    untagged = generate_report(conn, org_id, FY, Policy.VINTAGE_MATCHED)
    assert "no boundary tag" in _entitled(conn, untagged.report_id)["withheld_because"]
    boundary.tag_activity(conn, activity_id=activity_id, boundary="inside", basis="main meter")
    assert "no boundary tag" in _entitled(conn, untagged.report_id)["withheld_because"]  # as of then
    tagged = generate_report(conn, org_id, FY, Policy.VINTAGE_MATCHED)
    assert _entitled(conn, tagged.report_id)["entitlement_tco2e_equivalent"] == "-98.000000"


def test_a_later_target_does_not_change_an_earlier_entitlement(conn, plant):
    org_id, facility_id, activity_id = plant
    boundary.tag_activity(conn, activity_id=activity_id, boundary="inside", basis="main meter")
    first = _target(conn, facility_id, "9")
    r = generate_report(conn, org_id, FY, Policy.VINTAGE_MATCHED)
    before = ent.for_report(conn, r.report_id)
    second = _target(conn, facility_id, "12", status="notified", source_url=URL)   # supersedes
    assert ent.for_report(conn, r.report_id) == before                           # the target it read
    assert conn.execute("SELECT supersedes FROM intensity_target WHERE target_id = %s",
                        (second,)).fetchone()[0] == first
    later = generate_report(conn, org_id, FY, Policy.VINTAGE_MATCHED)
    assert _entitled(conn, later.report_id)["entitlement_tco2e_equivalent"] == "196.000000"


def test_a_target_needs_its_source_and_cannot_be_edited_or_deleted(conn, plant):
    _, facility_id, _ = plant
    with pytest.raises(ValueError, match="where the target comes from"):
        ent.set_target(conn, facility_id=facility_id, fy=FY, value=Decimal(9), unit="tCO2e/t",
                       status="assumed", source_citation="  ")
    with pytest.raises(ValueError, match="status"):
        ent.set_target(conn, facility_id=facility_id, fy=FY, value=Decimal(9), unit="tCO2e/t",
                       status="official", source_citation="x")
    tid = _target(conn, facility_id, "9")
    for sql in ("UPDATE intensity_target SET value = 1 WHERE target_id = %s",
                "DELETE FROM intensity_target WHERE target_id = %s"):
        with pytest.raises(psycopg.Error), conn.transaction():
            conn.execute(sql, (tid,))
    assert conn.execute("SELECT count(*) FROM audit_event WHERE entity_table = 'intensity_target'"
                        " AND entity_id = %s", (tid,)).fetchone()[0] == 1


def test_a_stored_baseline_is_versioned_and_read_as_of_the_report(conn, plant):
    org_id, facility_id, activity_id = plant
    boundary.tag_activity(conn, activity_id=activity_id, boundary="inside", basis="main meter")
    _target(conn, facility_id, "9")
    first = set_baseline(conn, facility_id=facility_id, baseline_fy="FY2023-24",
                         intensity=Decimal("12.5"), intensity_unit="tCO2e/t", status="assumed",
                         source_citation="test fixture, not a notification")
    r = generate_report(conn, org_id, FY, Policy.VINTAGE_MATCHED)
    before = ent.for_report(conn, r.report_id)
    second = set_baseline(conn, facility_id=facility_id, baseline_fy="FY2023-24",
                          intensity=Decimal(20), intensity_unit="tCO2e/t", status="notified",
                          source_citation="test fixture", source_url=URL)
    assert ent.for_report(conn, r.report_id) == before
    assert json.loads(before)["facilities"][0]["reduction_vs_baseline_pct"] == "20.000000"
    assert conn.execute("SELECT supersedes FROM baseline_record WHERE baseline_id = %s",
                        (second,)).fetchone()[0] == first
    later = generate_report(conn, org_id, FY, Policy.VINTAGE_MATCHED)
    assert _entitled(conn, later.report_id)["reduction_vs_baseline_pct"] == "50.000000"
