"""Report-shaped test data for the compliance tests: lines carry the inputs a real report pins."""
import json


def grid_line(activity_id: int, kwh: str = "1000000", factor: str = "0.700",
              facility_id: int = 1) -> dict:
    """Purchased electricity: kWh x tCO2/MWh. 1,000,000 kWh at 0.7 is 700 tCO2e."""
    return {"activity_id": activity_id, "facility_id": facility_id,
            "activity_type": "grid_electricity", "scope": 2, "quantity": kwh, "unit": "kWh",
            "factor": {"value": factor, "unit": "tCO2/MWh", "factor_key": "grid.test",
                       "source_version": "t1"},
            "tco2e": "rounded-and-never-read"}


def fuel_line(activity_id: int, tonnes: str = "140", facility_id: int = 1) -> dict:
    """Fuel: t x 20 GJ/t x 100 tCO2e/TJ. 140 t is 280 tCO2e."""
    return {"activity_id": activity_id, "facility_id": facility_id,
            "activity_type": "fuel.test_coal", "scope": 1, "quantity": tonnes, "unit": "t",
            "ncv": "20", "ncv_unit": "GJ/t", "oxidation_factor": "1",
            "factor": {"value": "100", "unit": "tCO2e/TJ", "factor_key": "fuel.test_coal.co2e",
                       "source_version": "t1"},
            "tco2e": "rounded-and-never-read"}


def report(lines: list[dict], production: str | None = "100", unresolved: list[dict] | None = None,
           withheld: str | None = None) -> str:
    """One facility, one product in tonnes. `production=None`: the report has no denominator."""
    shown = None if production is None else {"product_code": "al", "quantity": "shown-rounded",
                                             "unit": "t"}
    records = [] if production is None else [
        {"facility_id": 1, "product_code": "al", "quantity": production, "unit": "t"}]
    return json.dumps({
        "org_id": 1, "compliance_year": "FY2025-26", "policy": "AS_OF_REPORT",
        "as_of": "2026-01-01T00:00:00+00:00", "lines": lines, "unresolved": unresolved or [],
        "production_records": records, "product_equivalences": [],
        "facilities": [{"facility_id": 1, "production": shown, "gei": None, "gei_unit": None,
                        "gei_withheld_because": withheld}]})


def tag(boundary: str) -> dict:
    return {"tag_id": 1, "boundary": boundary, "basis": "test"}
