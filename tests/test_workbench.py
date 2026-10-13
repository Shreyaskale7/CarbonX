"""Review queue and exception log. The DB tests roll back."""
import random
from datetime import date
from decimal import Decimal

import psycopg
import pytest
from fastapi.testclient import TestClient

from carbonx.api import main as api
from carbonx.engine.calculate import calculate, edit_activity, record_activity
from carbonx.engine.exceptions import exceptions
from carbonx.engine.provenance import attestation, coverage
from carbonx.engine.report import generate_report
from carbonx.evidence import store
from carbonx.evidence.store import store_document
from carbonx.extraction import review
from carbonx.extraction.synthetic import make_bill
from carbonx.factors.registry import POLICY_DESCRIPTIONS, Policy, insert_factor
from carbonx.uncertainty.propagate import for_report

APRIL = {"period_start": date(2025, 4, 1), "period_end": date(2025, 5, 1)}


def test_the_served_model_reads_a_training_layout_bill():
    """No database: the process-wide model is trained once and works."""
    bill = make_bill(random.Random(11), 1)
    e = review.model().predict(bill.text)
    assert e.value == bill.kwh and 0 <= e.confidence <= 1
    assert review.model() is review.model()          # cached, not retrained


@pytest.fixture
def org(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(store, "EVIDENCE_DIR", tmp_path)
    for p, d in POLICY_DESCRIPTIONS.items():
        conn.execute("INSERT INTO resolution_policy (code, description) VALUES (%s, %s)"
                     " ON CONFLICT (code) DO NOTHING", (p.value, d))
    (org_id,) = conn.execute("INSERT INTO organisation (name) VALUES ('wb org')"
                             " RETURNING org_id").fetchone()
    (fid,) = conn.execute("INSERT INTO facility (org_id, name, state) VALUES (%s, 'p',"
                          " 'KA') RETURNING facility_id", (org_id,)).fetchone()
    return org_id, fid


def _kinds(conn, org_id):
    return sorted(e["kind"] for e in exceptions(conn, org_id))


def test_extraction_is_stored_queued_and_confirmable_once(conn, org):
    _, fid = org
    bill = make_bill(random.Random(3), 2)
    doc = store_document(conn, data=bill.text.encode(), filename="bill.txt",
                         doc_type="electricity_bill", facility_id=fid,
                         mime_type="text/plain")
    row = review.extract_document(conn, doc.document_id)
    assert row["parsed_value"] == Decimal(bill.kwh) and not row["human_verified"]
    assert row["model_version"] == review.MODEL_VERSION
    assert [q["extraction_id"] for q in review.review_queue(conn)
            if q["document_id"] == doc.document_id] == [row["extraction_id"]]
    review.confirm(conn, row["extraction_id"])
    assert all(q["extraction_id"] != row["extraction_id"]
               for q in review.review_queue(conn))
    # The reading itself can never be changed, only confirmed.
    conn.execute("SAVEPOINT s")
    with pytest.raises((psycopg.errors.RaiseException,
                        psycopg.errors.InsufficientPrivilege)):
        conn.execute("UPDATE extraction_result SET parsed_value = 1 WHERE"
                     " extraction_id = %s", (row["extraction_id"],))
    conn.execute("ROLLBACK TO SAVEPOINT s")


def test_exception_log_reports_what_it_finds(conn, org):
    org_id, fid = org
    assert _kinds(conn, org_id) == []
    # No evidence, and not calculated.
    a = record_activity(conn, facility_id=fid, activity_type="grid_electricity",
                        quantity=Decimal(1000), unit="kWh", **APRIL)
    assert _kinds(conn, org_id) == ["no_evidence", "not_calculated"]
    # A report, then a correction: the report is now behind the data.
    generate_report(conn, org_id, "FY2025-26", Policy.LATEST_AVAILABLE)
    edit_activity(conn, a, quantity=Decimal(900), reason="re-read")
    assert "corrected_after_report" in _kinds(conn, org_id)


def test_exception_log_catches_a_tampered_document(conn, org):
    org_id, fid = org
    doc = store_document(conn, data=b"synthetic", filename="b.txt",
                         doc_type="electricity_bill", facility_id=fid)
    record_activity(conn, facility_id=fid, activity_type="grid_electricity",
                    quantity=Decimal(1), unit="kWh", document_id=doc.document_id, **APRIL)
    assert "evidence_hash_mismatch" not in _kinds(conn, org_id)
    (path,) = conn.execute("SELECT storage_path FROM source_document WHERE document_id"
                           " = %s", (doc.document_id,)).fetchone()
    with open(path, "ab") as fh:
        fh.write(b" tampered")
    assert "evidence_hash_mismatch" in _kinds(conn, org_id)


def test_workbench_endpoints(conn, org):
    org_id, fid = org
    bill = make_bill(random.Random(5), 1)
    api.app.dependency_overrides[api.db] = lambda: conn
    try:
        client = TestClient(api.app)
        d = client.post(f"/api/documents?filename=bill.txt&facility_id={fid}",
                        content=bill.text.encode(),
                        headers={"Content-Type": "text/plain"}).json()
        e = client.post(f"/api/documents/{d['document_id']}/extract")
        assert e.status_code == 200, e.text
        assert Decimal(e.json()["parsed_value"]) == bill.kwh
        assert any(q["extraction_id"] == e.json()["extraction_id"]
                   for q in client.get("/api/review-queue").json())
        assert client.post(f"/api/extractions/{e.json()['extraction_id']}/confirm"
                           ).json()["human_verified"]
        assert client.get(f"/api/exceptions?org_id={org_id}").status_code == 200
        assert client.post("/api/documents/999999999/extract").status_code == 404
    finally:
        api.app.dependency_overrides.clear()


# ---- attestation, coverage, and the uncertainty band of a stored report ------

GRID = "grid.weighted_avg_incl_re_captive.incl_imports"


def _factor(conn, ordinal, key, value, published, low=None, high=None, **when):
    (sid,) = conn.execute(
        "INSERT INTO factor_source (publisher, dataset_name, version_label,"
        " version_ordinal, published_on, source_url) VALUES ('TEST', 'wb', %s, %s, %s,"
        " 'https://example.test') RETURNING source_id",
        (f"wb{ordinal}", ordinal, published)).fetchone()
    return insert_factor(conn, source_id=sid, factor_key=key, value=Decimal(value),
                         numerator_unit="tCO2e", denominator_unit=when.pop("per", "MWh"),
                         uncertainty_low=low, uncertainty_high=high,
                         uncertainty_basis="test range" if low else None, **when)


def test_report_and_registry_endpoints(conn, org):
    """Needs no bill reader, so it runs where scikit-learn cannot load."""
    org_id, fid = org
    api.app.dependency_overrides[api.db] = lambda: conn
    try:
        client = TestClient(api.app)
        _factor(conn, 880_001, GRID, "0.7", date(2026, 1, 1), fy="FY2025-26")
        aid = record_activity(conn, facility_id=fid, activity_type="grid_electricity",
                              period_start=date(2025, 4, 1), period_end=date(2025, 5, 1),
                              quantity=Decimal(1000), unit="kWh")
        calculate(conn, aid, Policy.VINTAGE_MATCHED)
        r = client.post("/api/reports", json={"org_id": org_id}).json()
        listed = client.get("/api/reports").json()
        assert listed[0]["report_id"] == r["report_id"]
        assert listed[0]["sha256"] == r["sha256"]
        assert any(k["factor_key"] == GRID for k in client.get("/api/factors").json())
        band = client.get(f"/api/reports/{r['report_id']}/uncertainty").json()
        assert band["total"] == r["total_tco2e"]
        m = client.post(f"/api/reports/{r['report_id']}/materiality",
                        json={"trigger_type": "allocation_change"}).json()
        assert m["requires_recalc"] is False and "Following an allocation" in m["disclosure"]
        made = client.post("/api/production", json={
            "facility_id": fid, "product_code": "al", "period_start": "2025-04-01",
            "period_end": "2025-05-01", "quantity": "10"})
        assert made.status_code == 200 and made.json()["production_id"]
        # a second product: intensity withheld, with the reason, until both are declared
        client.post("/api/production", json={
            "facility_id": fid, "product_code": "billet", "period_start": "2025-04-01",
            "period_end": "2025-05-01", "quantity": "5"})
        client.post("/api/reports", json={"org_id": org_id})
        newest = client.get("/api/reports").json()[0]
        assert newest["gei"] is None
        assert "declared for al, billet" in newest["gei_withheld_because"][0]
        for code, factor in (("al", "1"), ("billet", "0.5")):
            assert client.post("/api/equivalences", json={
                "facility_id": fid, "product_code": code, "factor": factor,
                "basis": "test practice"}).status_code == 200
        assert client.post("/api/equivalences", json={
            "facility_id": fid, "product_code": "al", "factor": "1", "basis": ""}
        ).status_code == 422
        assert len(client.get(f"/api/equivalences?org_id={org_id}").json()) == 2
        done = client.post("/api/reports", json={"org_id": org_id}).json()
        assert done["gei"] == "0.056000000"          # 0.7 tCO2e / (10 + 0.5 x 5) t
        assert client.get("/api/reports").json()[0]["gei_unit"] == "tCO2e/t"
        history = client.get(f"/api/factors?factor_key={GRID}").json()
        assert any(h["version_label"] == "wb880001" for h in history)
    finally:
        api.app.dependency_overrides.clear()


def test_attestation_shows_the_figure_under_every_policy(conn, org):
    """RQ3 for one number: same activity, same moment, different policies."""
    _, fid = org
    _factor(conn, 950_001, GRID, "0.710", date(2025, 11, 1), fy="FY2024-25")
    _factor(conn, 950_002, GRID, "0.675", date(2026, 8, 1), fy="FY2025-26")  # after deadline
    a = record_activity(conn, facility_id=fid, activity_type="grid_electricity",
                        quantity=Decimal(1_000_000), unit="kWh", **APRIL)
    c = calculate(conn, a, Policy.VINTAGE_MATCHED)
    att = attestation(conn, c.calculation_id)
    by = {x["policy"]: x for x in att["alternatives"]}
    assert att["policy_dependent"]
    assert by["VINTAGE_MATCHED"]["used"] and by["VINTAGE_MATCHED"]["tco2e"] == "675.000000"
    assert by["AS_OF_REPORT"]["tco2e"] == "710.000000"       # only the earlier version
    assert by["AS_OF_REPORT"]["vs_used_pct"] == "5.19"
    assert "baseline year" in by["BASELINE_FROZEN"]["unavailable"]


def test_coverage_counts_only_emissions_with_a_document(conn, org):
    org_id, fid = org
    _factor(conn, 950_003, GRID, "1.000", date(2026, 1, 1), fy="FY2025-26")
    doc = store_document(conn, data=b"synthetic bill", filename="b.txt",
                         doc_type="electricity_bill", facility_id=fid)
    with_doc = record_activity(conn, facility_id=fid, activity_type="grid_electricity",
                               quantity=Decimal(300_000), unit="kWh",
                               document_id=doc.document_id, **APRIL)
    without = record_activity(conn, facility_id=fid, activity_type="grid_electricity",
                              quantity=Decimal(100_000), unit="kWh",
                              period_start=date(2025, 5, 1), period_end=date(2025, 6, 1))
    for a in (with_doc, without):
        calculate(conn, a, Policy.VINTAGE_MATCHED)
    assert coverage(conn, org_id) == {"org_id": org_id, "total_tco2e": "400.000000",
                                      "traced_tco2e": "300.000000", "coverage_pct": "75.00"}


def test_uncertainty_band_of_a_stored_report(conn, org):
    """Three months on one fuel factor with a published range: the band is the
    full range (correlated), wider than the independent-lines band by sqrt(3)."""
    org_id, fid = org
    _factor(conn, 950_004, "fuel.test_gas.co2e", "50", date(2026, 1, 1), per="TJ",
            low=Decimal(48), high=Decimal(53),
            valid=(date(2024, 4, 1), date(2027, 4, 1)))
    for month in (4, 5, 6):
        record_activity(conn, facility_id=fid, activity_type="fuel.test_gas",
                        quantity=Decimal(100), unit="t", ncv=Decimal(20), ncv_unit="GJ/t",
                        period_start=date(2025, month, 1),
                        period_end=date(2025, month + 1, 1))      # 100 tCO2e each
    r = generate_report(conn, org_id, "FY2025-26", Policy.LATEST_AVAILABLE)
    b = for_report(conn, r.report_id)
    assert (b.total, b.low, b.high) == (Decimal("300.000000"), Decimal("288.000000"),
                                        Decimal("318.000000"))    # -4% / +6% of the total
    assert float(b.high_if_independent) == pytest.approx(300 + 18 / 3 ** 0.5, abs=1e-5)
    assert b.unquantified == Decimal("0.000000") and b.basis == ("test range",)
