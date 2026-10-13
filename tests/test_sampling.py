"""Audit sampling by size: the arithmetic against known values, the selection's
guarantees as properties, and a sample drawn from a stored report."""
import json
from datetime import date
from decimal import Decimal
from fractions import Fraction

import psycopg
import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from carbonx.api import main as api
from carbonx.engine.calculate import record_activity
from carbonx.engine.report import generate_report
from carbonx.factors.registry import POLICY_DESCRIPTIONS, Policy, insert_factor
from carbonx.sampling import pps

GRID = "grid.weighted_avg_incl_re_captive.incl_imports"


# ---- arithmetic (no database) ------------------------------------------------

def test_confidence_factors_match_the_audit_tables():
    assert pps.confidence_factor(0.95) == pytest.approx(2.996, abs=0.001)      # "3.00"
    assert pps.confidence_factor(0.95, 1) == pytest.approx(4.744, abs=0.001)   # "4.75"
    assert pps.confidence_factor(0.95, 2) == pytest.approx(6.296, abs=0.001)   # "6.30"
    assert pps.confidence_factor(0.90) == pytest.approx(2.303, abs=0.001)      # "2.31"


def test_sample_size_is_population_times_factor_over_tolerable():
    assert pps.sample_size(Fraction(1000), Fraction(50), 0.95) == 60   # 1000 x 2.996 / 50
    assert pps.sample_size(Fraction(1000), Fraction(100), 0.95) == 30
    with pytest.raises(ValueError):
        pps.sample_size(Fraction(1000), Fraction(0), 0.95)


items = st.lists(st.integers(0, 5000), min_size=1, max_size=40).map(
    lambda vs: [pps.Item(k, Fraction(v, 10)) for k, v in enumerate(vs)])


@settings(max_examples=300, deadline=None)
@given(items=items, n=st.integers(1, 30), seed=st.text(max_size=8))
def test_selection_properties(items, n, seed):
    s = pps.select(items, n, seed)
    assert s == pps.select(list(reversed(items)), n, seed)          # deterministic, order-free
    chosen = [k for k, _ in s.certain] + list(s.sampled)
    assert len(chosen) == len(set(chosen))                           # no line twice
    value = {i.key: i.value for i in items}
    if s.interval is not None:
        assert len(s.sampled) == n - len(s.certain)                  # every planned hit lands
        assert all(value[k] < s.interval for k in s.sampled)
        left_out = set(value) - set(chosen)
        assert all(value[k] < s.interval for k in left_out)          # nothing large is skipped
    assert all(value[k] > 0 for k in s.sampled)                      # a zero line cannot be hit


def test_a_line_is_picked_in_proportion_to_its_size():
    """Over many seeds, a line a quarter of an interval in size is hit about a
    quarter of the time, and one three times larger three times as often."""
    items = [pps.Item(k, Fraction(v)) for k, v in enumerate([25, 75, 100, 100, 100])]
    hits = {0: 0, 1: 0}
    for seed in range(2000):
        s = pps.select(items, 4, str(seed))          # interval = 400 / 4 = 100
        for k in hits:
            hits[k] += k in s.sampled
    assert 0.21 < hits[0] / 2000 < 0.29
    assert 0.71 < hits[1] / 2000 < 0.79


def test_certain_items_are_taken_out_before_sampling():
    items = [pps.Item(1, Fraction(900)), pps.Item(2, Fraction(40)), pps.Item(3, Fraction(60)),
             pps.Item(4, Fraction(0), "no source document")]
    s = pps.select(items, 3, "x")
    assert dict(s.certain) == {1: "at least one sampling interval in size",
                               4: "no source document"}
    assert s.interval == 100 and set(s.sampled) <= {2, 3} and len(s.sampled) == 1


def test_evaluation_with_no_errors_and_with_one_half_tainted_line():
    interval, tolerable = Fraction(100), Fraction(350)
    clean = [("sampled", Fraction(80), Fraction(80))] * 3
    ev = pps.evaluate(clean, interval, 0.95, tolerable)
    assert ev.complete and ev.projected == 0
    assert float(ev.upper_over) == pytest.approx(299.6, abs=0.1)        # 2.996 x 100
    assert ev.within
    one = [*clean[:2], ("sampled", Fraction(80), Fraction(40))]          # taint 0.5
    ev = pps.evaluate(one, interval, 0.95, tolerable)
    assert ev.projected == 50                                            # 0.5 x 100
    assert float(ev.upper_over) == pytest.approx(299.6 + (474.4 - 299.6) * 0.5, abs=0.1)
    assert not ev.within                                                 # 387 > 350
    pending = [*clean, ("certain", Fraction(500), None)]
    assert not pps.evaluate(pending, interval, 0.95, tolerable).complete


# ---- on a stored report -------------------------------------------------------

@pytest.fixture
def report(conn):
    for p, d in POLICY_DESCRIPTIONS.items():
        conn.execute("INSERT INTO resolution_policy (code, description) VALUES (%s, %s)"
                     " ON CONFLICT (code) DO NOTHING", (p.value, d))
    (sid,) = conn.execute(
        "INSERT INTO factor_source (publisher, dataset_name, version_label,"
        " version_ordinal, published_on, source_url) VALUES ('TEST', 'pps', 's1',"
        " 810000, '2026-01-01', 'https://example.test') RETURNING source_id").fetchone()
    insert_factor(conn, source_id=sid, factor_key=GRID, value=Decimal("0.700"),
                  numerator_unit="tCO2", denominator_unit="MWh", fy="FY2025-26")
    (org_id,) = conn.execute("INSERT INTO organisation (name) VALUES ('pps org')"
                             " RETURNING org_id").fetchone()
    (fid,) = conn.execute("INSERT INTO facility (org_id, name, state) VALUES (%s, 'p', 'KA')"
                          " RETURNING facility_id", (org_id,)).fetchone()
    (doc,) = conn.execute(
        "INSERT INTO source_document (facility_id, doc_type, filename, storage_path, sha256)"
        " VALUES (%s, 'electricity_bill', 'b.pdf', 'x', repeat('a', 64))"
        " RETURNING document_id", (fid,)).fetchone()
    for m in range(12):   # eleven documented months, one without a document
        start = date(2025 + (m >= 9), (3 + m) % 12 + 1, 1)
        end = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
        record_activity(conn, facility_id=fid, activity_type="grid_electricity",
                        period_start=start, period_end=end, unit="kWh",
                        quantity=Decimal(100_000 + 10_000 * m),
                        document_id=None if m == 5 else doc)
    return generate_report(conn, org_id, "FY2025-26", Policy.VINTAGE_MATCHED)


def test_a_sample_can_be_rederived_from_the_report_alone(conn, report):
    sample_id = pps.draw(conn, report.report_id, tolerable_pct=Decimal(20), nonce="t")
    s = pps.summary(conn, sample_id)
    assert s["seed"] == f"{report.sha256}:t" and s["planned_n"] == 15
    lines = json.loads(report.output)["lines"]
    again = pps.select(
        [pps.Item(ln["activity_id"], Fraction(ln["tco2e"]),
                  None if ln["document_sha256"] else "no source document") for ln in lines],
        s["planned_n"], s["seed"])
    stored = {(i["activity_id"], i["stratum"]) for i in s["items"]}
    assert stored == ({(k, "certain") for k, _ in again.certain}
                      | {(k, "sampled") for k in again.sampled})
    undocumented = next(ln["activity_id"] for ln in lines if not ln["document_sha256"])
    assert (undocumented, "certain") in stored
    assert s["evaluation"]["within_tolerable"] is None            # nothing tested yet


def test_results_are_recorded_once_and_evaluated(conn, report):
    sample_id = pps.draw(conn, report.report_id, tolerable_pct=Decimal(20), nonce="r")
    s = pps.summary(conn, sample_id)
    for i in s["items"]:
        pps.record_result(conn, i["item_id"], Decimal(i["book_tco2e"]), "agrees with the bill")
    done = pps.summary(conn, sample_id)["evaluation"]
    assert done["complete"] and done["projected_tco2e"] == "0.000000"
    assert done["within_tolerable"] is True
    first = s["items"][0]["item_id"]
    with pytest.raises(LookupError, match="already has a result"):
        pps.record_result(conn, first, Decimal(1), "second thoughts")
    with pytest.raises(ValueError, match="what was checked"):
        pps.record_result(conn, first, Decimal(1), " ")


def test_sampling_api_draws_once_and_takes_results(conn, report):
    api.app.dependency_overrides[api.db] = lambda: conn
    try:
        client = TestClient(api.app)
        s = client.post(f"/api/reports/{report.report_id}/sample",
                        json={"tolerable_pct": "20"}).json()
        again = client.post(f"/api/reports/{report.report_id}/sample",
                            json={"tolerable_pct": "20"}).json()
        assert again["sample_id"] == s["sample_id"]           # the same draw, not a second one
        assert len(client.get(f"/api/reports/{report.report_id}/samples").json()) == 1
        item = s["items"][0]
        ok = client.post(f"/api/sample-items/{item['item_id']}/result",
                         json={"audited_tco2e": item["book_tco2e"], "finding": "agrees"})
        assert ok.status_code == 200
        twice = client.post(f"/api/sample-items/{item['item_id']}/result",
                            json={"audited_tco2e": "1", "finding": "changed my mind"})
        assert twice.status_code == 404
        assert client.get(f"/api/samples/{s['sample_id']}").json()["evaluation"]["tested"] == 1
        assert client.post("/api/reports/999999999/sample", json={}).status_code == 404
    finally:
        api.app.dependency_overrides.clear()


@pytest.mark.parametrize("sql, exc", [
    ("UPDATE audit_sample SET planned_n = 1 WHERE sample_id = %(s)s",
     psycopg.errors.InsufficientPrivilege),
    ("UPDATE audit_sample_item SET book_tco2e = 0 WHERE sample_id = %(s)s",
     psycopg.errors.InsufficientPrivilege),
    ("DELETE FROM audit_sample_item WHERE sample_id = %(s)s",
     psycopg.errors.InsufficientPrivilege),
    ("UPDATE audit_sample_item SET audited_tco2e = 1 WHERE sample_id = %(s)s",
     psycopg.errors.RaiseException),          # a result needs its note
])
def test_a_sample_cannot_be_rewritten(conn, report, sql, exc):
    sample_id = pps.draw(conn, report.report_id, tolerable_pct=Decimal(20), nonce="g")
    conn.execute("SAVEPOINT s")
    with pytest.raises(exc):
        conn.execute(sql, {"s": sample_id})
    conn.execute("ROLLBACK TO SAVEPOINT s")
