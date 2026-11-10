"""A draft of BEE's Form A from the entitlement of the same report. No database."""
import json

from compliance_helpers import fuel_line, grid_line, report, tag

from carbonx.compliance import entitlement as ent
from carbonx.compliance import form_a

TARGET = {"target_id": 7, "value": "9.000000000", "unit": "tCO2e/t", "status": "assumed",
          "source_citation": "test, not a notification", "source_url": None, "baseline_fy": None}
BASE = {"baseline_id": 3, "baseline_fy": "FY2023-24", "intensity": "12.500000000",
        "unit": "tCO2e/t", "output": "120.000000", "output_unit": "t", "status": "assumed",
        "source_citation": "test, not a notification", "source_url": None}
LINES = [grid_line(1), fuel_line(2)]                             # 980 tCO2e over 100 t
INSIDE = {1: tag("inside"), 2: tag("inside")}


def draft(tags=INSIDE, baseline=BASE) -> tuple[dict, dict]:
    entitled = ent.entitlements(report(LINES), {1: TARGET}, {1: baseline} if baseline else None, tags)
    return (json.loads(form_a.form_a(entitled))["facilities"][0],
            json.loads(entitled)["facilities"][0])


def test_field_7_is_the_entitlements_own_achieved_intensity():
    a, e = draft()
    assert a["7 achieved specific GHG emissions"] == e["achieved"] == {
        "value": "9.800000000", "unit": "tCO2e/t"}


def test_field_8_shows_both_readings_and_chooses_neither():
    a, _ = draft()
    f8 = a["8 production (baseline)"]
    assert f8["baseline_year_output"]["quantity"] == "120.000000"
    assert f8["production_in_this_cycle"] == {"quantity": "100.000000", "unit": "t"}
    assert "choice is the entity's" in f8["note"]
    assert draft(baseline=None)[0]["8 production (baseline)"]["baseline_year_output"] is None


def test_field_9_gives_the_signed_figure_and_never_a_certificate_count():
    a, e = draft()
    assert a["9 number of carbon credit certificates issued or purchased"] is None
    assert a["9 basis"]["entitlement_tco2e_equivalent"] == e["entitlement_tco2e_equivalent"] == "-80.000000"
    assert "no certificate count" in a["9 basis"]["note"] and "do not rely" in a["9 basis"]["note"]


def test_an_untagged_line_leaves_the_fields_empty_with_the_reason():
    a, _ = draft(tags={1: tag("inside")})
    assert a["7 achieved specific GHG emissions"] is None
    assert "no boundary tag" in a["9 basis"]["withheld_because"]


def test_what_belongs_to_the_entity_is_left_empty_and_nothing_is_signed():
    entitled = ent.entitlements(report(LINES), {1: TARGET}, None, INSIDE)
    out = form_a.form_a(entitled)
    parsed = json.loads(out)
    mine = parsed["facilities"][0]["to_be_filled_by_the_entity"]
    assert all(v is None for v in mine.values()) and any("signature" in k for k in mine)
    assert "not a filing" in parsed["status"] and "not signed or certified" in parsed["status"]
    assert out == json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
