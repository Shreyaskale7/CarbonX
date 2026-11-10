"""The targets loader refuses what it cannot source. No database."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import load_targets as lt

ROW = {"facility_id": "1", "compliance_fy": "FY2025-26", "target": "9.5", "unit": "tCO2e/t",
       "status": "assumed", "citation": "test, not a notification", "url": "",
       "baseline_fy": "", "baseline_intensity": ""}


def test_a_complete_assumed_row_is_valid():
    assert lt.problems(ROW) == []


def test_a_notified_value_needs_the_url_it_was_read_in():
    assert lt.problems(ROW | {"status": "notified"}) == [
        "a 'notified' value needs the url of the notification you read it in"]
    assert lt.problems(ROW | {"status": "notified", "url": "https://example.test"}) == []


def test_missing_fields_bad_numbers_and_unknown_status_are_all_reported():
    why = " | ".join(lt.problems(ROW | {"citation": " ", "target": "nine", "status": "official"}))
    assert "missing citation" in why and "target is not a number" in why and "status must be" in why


def test_a_baseline_intensity_needs_its_year():
    assert "a baseline intensity needs its baseline_fy" in lt.problems(
        ROW | {"baseline_intensity": "12.5"})


def test_the_shipped_template_has_a_header_and_no_values():
    text = (Path(__file__).resolve().parents[1] / "data" / "targets" / "template.csv"
            ).read_text(encoding="utf-8").strip().splitlines()
    assert len(text) == 1 and text[0].startswith("facility_id,compliance_fy,target")
