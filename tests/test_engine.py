"""Phase 4 vertical slice: evidence -> activity -> typed calculation ->
ledger, and corrections that never overwrite. DB tests roll back.

Factors here come from a synthetic TEST source, never CEA.
"""
import queue
from datetime import date
from decimal import Decimal
from fractions import Fraction

import psycopg
import pytest
from fastapi.testclient import TestClient

from carbonx.api import main as api
from carbonx.engine.calculate import calculate, edit_activity, fy_of, record_activity
from carbonx.engine.provenance import provenance
from carbonx.evidence import store
from carbonx.evidence.store import store_document, verify_document
from carbonx.factors.registry import POLICY_DESCRIPTIONS, Policy, insert_factor

GRID = "grid.weighted_avg_incl_re_captive.incl_imports"
TEST_FACTOR = Decimal("0.7")  # synthetic


def test_fy_of():
    assert fy_of(date(2025, 4, 1)) == "FY2025-26"
    assert fy_of(date(2026, 3, 31)) == "FY2025-26"
    assert fy_of(date(2026, 4, 1)) == "FY2026-27"


@pytest.mark.parametrize("kw, match", [
    ({"activity_type": "diesel"}, "unknown activity_type"),
    ({"quantity": Decimal(-1)}, ">= 0"),
    ({"period_end": date(2025, 4, 1)}, "after period_start"),
    ({"period_end": date(2026, 5, 1)}, "one financial year"),
])
def test_activity_validation_happens_before_the_db(kw, match):
    args = {"facility_id": 1, "activity_type": "grid_electricity",
            "period_start": date(2025, 4, 1), "period_end": date(2025, 5, 1),
            "quantity": Decimal(1), "unit": "kWh"} | kw
    with pytest.raises(ValueError, match=match):
        record_activity(None, **args)  # type: ignore[arg-type]


def test_page_is_served():
    r = TestClient(api.app).get("/")
    assert r.status_code == 200 and "CarbonX" in r.text


@pytest.fixture
def world(conn, tmp_path, monkeypatch):
    """Policies, a synthetic factor for FY2025-26, and one facility."""
    monkeypatch.setattr(store, "EVIDENCE_DIR", tmp_path)
    for p, d in POLICY_DESCRIPTIONS.items():
        conn.execute("INSERT INTO resolution_policy (code, description) VALUES (%s, %s)"
                     " ON CONFLICT (code) DO NOTHING", (p.value, d))
    (source_id,) = conn.execute(
        "INSERT INTO factor_source (publisher, dataset_name, version_label,"
        " version_ordinal, published_on, source_url)"
        " VALUES ('TEST', 'synthetic', 'test-1', 99999, '2026-01-01',"
        " 'https://example.test')"
        " RETURNING source_id").fetchone()
    factor_id = insert_factor(conn, source_id=source_id, factor_key=GRID,
                              value=TEST_FACTOR, numerator_unit="tCO2",
                              denominator_unit="MWh", fy="FY2025-26")
    (org_id,) = conn.execute("INSERT INTO organisation (name) VALUES ('Test org')"
                             " RETURNING org_id").fetchone()
    (facility_id,) = conn.execute(
        "INSERT INTO facility (org_id, name, state) VALUES (%s, 'Test plant', 'KA')"
        " RETURNING facility_id", (org_id,)).fetchone()
    return {"facility_id": facility_id, "factor_id": factor_id}


def _activity(conn, world, kwh=1200, doc=None):
    return record_activity(conn, facility_id=world["facility_id"],
                           activity_type="grid_electricity",
                           period_start=date(2025, 4, 1), period_end=date(2025, 5, 1),
                           quantity=Decimal(kwh), unit="kWh", document_id=doc,
                           actor="tester")


def test_calculation_is_typed_exact_and_pins_its_factor(conn, world):
    c = calculate(conn, _activity(conn, world), Policy.VINTAGE_MATCHED)
    assert c.exact == Fraction(1200) * Fraction("0.7") / 1000  # kWh -> MWh, exactly
    assert c.tco2e == Decimal("0.840000")
    assert "let emissions : [tCO2e] = activity * factor" in c.program
    assert conn.execute("SELECT factor_id, program FROM calculation"
                        " WHERE calculation_id = %s", (c.calculation_id,)).fetchone() \
        == (world["factor_id"], c.program)
    assert conn.execute("SELECT tco2e FROM ledger_entry WHERE calculation_id = %s",
                        (c.calculation_id,)).fetchone() == (Decimal("0.840000"),)


def test_correction_closes_old_rows_and_keeps_them(conn, world):
    old_activity = _activity(conn, world)
    old = calculate(conn, old_activity, Policy.VINTAGE_MATCHED)
    new_activity, (new,) = edit_activity(conn, old_activity, quantity=Decimal(1500),
                                         reason="meter re-read", actor="tester")
    assert new.tco2e == Decimal("1.050000")
    # The old calculation is still there, closed, with its original value.
    assert conn.execute(
        "SELECT result_value, upper_inf(system_time_range) FROM calculation"
        " WHERE calculation_id = %s", (old.calculation_id,)).fetchone() \
        == (Decimal("0.840000"), False)
    current = conn.execute("SELECT count(*) FROM ledger_entry l JOIN calculation c"
                           " USING (calculation_id) WHERE c.activity_id IN (%s, %s)"
                           " AND upper_inf(l.system_time_range)",
                           (old_activity, new_activity)).fetchone()
    assert current == (1,)
    reasons = conn.execute("SELECT DISTINCT reason FROM audit_event WHERE entity_table ="
                           " 'activity' AND entity_id IN (%s, %s) AND reason <> ''",
                           (old_activity, new_activity)).fetchall()
    assert reasons == [("meter re-read",)]


def test_calculation_cannot_be_overwritten(conn, world):
    c = calculate(conn, _activity(conn, world), Policy.VINTAGE_MATCHED)
    conn.execute("SAVEPOINT s")
    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute("UPDATE calculation SET result_value = 0 WHERE calculation_id = %s",
                     (c.calculation_id,))
    conn.execute("ROLLBACK TO SAVEPOINT s")


def test_evidence_is_hashed_deduplicated_and_verifiable(conn, world):
    first = store_document(conn, data=b"synthetic bill", filename="../a.txt",
                           doc_type="electricity_bill")
    again = store_document(conn, data=b"synthetic bill", filename="b.txt",
                           doc_type="electricity_bill")
    assert (again.document_id, again.created, first.filename) == (first.document_id, False, "a.txt")
    assert verify_document(conn, first.document_id)
    (path,) = conn.execute("SELECT storage_path FROM source_document WHERE document_id"
                           " = %s", (first.document_id,)).fetchone()
    with open(path, "ab") as fh:
        fh.write(b" tampered")
    assert not verify_document(conn, first.document_id)


def test_provenance_walks_the_whole_chain(conn, world):
    doc = store_document(conn, data=b"synthetic bill 2", filename="bill.txt",
                         doc_type="electricity_bill")
    a = _activity(conn, world, doc=doc.document_id)
    calculate(conn, a, Policy.VINTAGE_MATCHED)
    _, (new,) = edit_activity(conn, a, quantity=Decimal(1300), reason="typo")
    p = provenance(conn, new.calculation_id)
    assert p["document"]["sha256"] == doc.sha256 and p["document"]["hash_verified"]
    assert p["factor"]["factor_id"] == world["factor_id"]
    assert p["factor"]["version_label"] == "test-1"
    assert [h["quantity"] for h in p["activity_history"]] == ["1200.000000"]
    assert len(p["calculations"]) == 2
    assert p["audit_chain"]["intact"]
    assert {e["reason"] for e in p["audit_events"]} >= {"typo"}


def test_api_round_trip(conn, world):
    api.app.dependency_overrides[api.db] = lambda: conn
    try:
        client = TestClient(api.app)
        d = client.post("/api/documents?filename=bill.txt", content=b"synthetic bill 3")
        assert d.status_code == 200, d.text
        r = client.post("/api/activities", json={
            "facility_id": world["facility_id"], "period_start": "2025-04-01",
            "period_end": "2025-05-01", "quantity": "1200",
            "document_id": d.json()["document_id"]})
        assert r.status_code == 200, r.text
        assert r.json()["tco2e"] == "0.840000"
        p = client.get(f"/api/calculations/{r.json()['calculation_id']}/provenance")
        assert p.json()["document"]["sha256"] == d.json()["sha256"]
        fix = client.patch(f"/api/activities/{r.json()['activity_id']}",
                           json={"quantity": "1000", "reason": "re-read"})
        assert fix.json()["calculations"][0]["tco2e"] == "0.700000"
        again = client.post("/api/activities", json={
            "facility_id": world["facility_id"], "period_start": "2025-04-01",
            "period_end": "2025-05-01", "quantity": "5"})
        assert again.status_code == 409  # correct it instead
        bad = client.post("/api/activities", json={
            "facility_id": world["facility_id"], "period_start": "2025-06-01",
            "period_end": "2025-07-01", "quantity": "1", "unit": "litre"})
        assert bad.status_code == 400 and "DimensionError" in bad.json()["detail"]
        # A failed calculation must not leave its activity behind (found in the
        # browser walkthrough: FactorNotFound used to commit the activity).
        none = client.post("/api/activities", json={
            "facility_id": world["facility_id"], "period_start": "2026-04-01",
            "period_end": "2026-05-01", "quantity": "1", "policy": "VINTAGE_MATCHED"})
        assert none.status_code == 400 and "FactorNotFound" in none.json()["detail"]
        assert conn.execute("SELECT count(*) FROM activity WHERE facility_id = %s"
                            " AND period = daterange('2026-04-01', '2026-05-01')",
                            (world["facility_id"],)).fetchone() == (0,)
    finally:
        api.app.dependency_overrides.clear()


def test_api_says_so_quickly_when_the_database_is_down(monkeypatch):
    monkeypatch.setattr(api, "URL", "postgresql://nobody@127.0.0.1:1/none")
    monkeypatch.setattr(api, "_idle", queue.LifoQueue(maxsize=4))   # no idle connections
    r = TestClient(api.app).get("/api/facilities")
    assert r.status_code == 503 and "not reachable" in r.json()["detail"]


def test_connections_are_reused_and_a_dead_one_is_replaced(conn, monkeypatch):
    """`conn` only makes this skip when Postgres is down."""
    monkeypatch.setattr(api, "_idle", queue.LifoQueue(maxsize=4))
    client = TestClient(api.app)
    assert client.get("/api/facilities").status_code == 200
    assert api._idle.qsize() == 1
    first = api._idle.queue[0]
    assert client.get("/api/facilities").status_code == 200
    assert api._idle.qsize() == 1 and api._idle.queue[0] is first      # reused
    first.close()                                                      # the database 'restarted'
    assert client.get("/api/facilities").status_code == 200
    assert api._idle.queue[0] is not first and not api._idle.queue[0].closed
    bad = client.post("/api/production", json={
        "facility_id": 999_999_999, "product_code": "x", "period_start": "2025-04-01",
        "period_end": "2025-05-01", "quantity": "1"})
    assert bad.status_code == 400 and "does not exist" in bad.json()["detail"]
    while not api._idle.empty():
        api._idle.get_nowait().close()


def test_site_pages_and_databaseless_endpoints():
    client = TestClient(api.app)
    for page in ("findings", "registry", "method", "ledger", "evidence", "reports"):
        assert client.get(f"/{page}").status_code == 200
    assert client.get("/static/site.css").status_code == 200
    assert client.get("/no-such-page").status_code == 404
    ok = client.post("/api/typecheck", json={
        "program": "let e : [tCO2e] = 1200 [kWh] * 0.7272 [tCO2/MWh]"}).json()
    assert ok["ok"] and ok["bindings"][0]["exact"] == "2727/3125"
    bad = client.post("/api/typecheck", json={
        "program": "let e : [tCO2e] = 1200 [kWh] * 2.68 [kgCO2e/litre]"}).json()
    assert not bad["ok"] and bad["error"] == "DimensionError"
    assert len(client.get("/api/lifecycle").json()["delta"]) == 7


def test_lifecycle_try_is_enforced_by_the_database_and_leaves_nothing(conn):
    client = TestClient(api.app)
    before = conn.execute("SELECT count(*) FROM credit").fetchone()
    r = client.post("/api/lifecycle/try", json={
        "symbols": ["issue", "transfer", "surrender", "transfer"]}).json()
    assert [s["ok"] for s in r["steps"]] == [True, True, True, False]
    assert r["steps"][2]["state"] == "SURRENDERED" and not r["accepted"]
    assert "not allowed" in r["steps"][3]["error"]
    assert client.post("/api/lifecycle/try", json={"symbols": ["retire"]}
                       ).json()["steps"][0]["ok"] is False
    assert conn.execute("SELECT count(*) FROM credit").fetchone() == before
