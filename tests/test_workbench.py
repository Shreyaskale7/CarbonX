"""Review queue and exception log. The DB tests roll back."""
import random
from datetime import date
from decimal import Decimal

import psycopg
import pytest
from fastapi.testclient import TestClient

from carbonx.api import main as api
from carbonx.engine.calculate import edit_activity, record_activity
from carbonx.engine.exceptions import exceptions
from carbonx.engine.report import generate_report
from carbonx.evidence import store
from carbonx.evidence.store import store_document
from carbonx.extraction import review
from carbonx.extraction.synthetic import make_bill
from carbonx.factors.registry import POLICY_DESCRIPTIONS, Policy

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
