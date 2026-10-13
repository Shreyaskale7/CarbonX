"""Anchors catch what the hash chain alone cannot: history rewritten by someone
able to recompute the chain. Uses the owner connection, rolled back."""
import json
from datetime import date
from decimal import Decimal

from carbonx.engine.calculate import record_activity
from carbonx.engine.exceptions import exceptions
from carbonx.evidence import anchor

RECOMPUTE = (
    "UPDATE audit_event SET event_hash = encode(digest(fn_audit_payload(prev_hash,"
    " entity_table, entity_id, action, old_value, new_value, actor, reason, occurred_at),"
    " 'sha256'), 'hex') WHERE event_id = %s")


def _three_events(conn):
    (org_id,) = conn.execute("INSERT INTO organisation (name) VALUES ('anchor org')"
                             " RETURNING org_id").fetchone()
    (fid,) = conn.execute("INSERT INTO facility (org_id, name, state) VALUES (%s, 'p', 'KA')"
                          " RETURNING facility_id", (org_id,)).fetchone()
    for month in (4, 5, 6):
        record_activity(conn, facility_id=fid, activity_type="grid_electricity",
                        period_start=date(2025, month, 1), period_end=date(2025, month + 1, 1),
                        quantity=Decimal(1000), unit="kWh")
    return org_id


def test_anchor_matches_until_history_is_rewritten_consistently(owner_conn, tmp_path, monkeypatch):
    conn, path = owner_conn, tmp_path / "anchors.jsonl"
    monkeypatch.setattr(anchor, "ANCHORS", path)
    org_id = _three_events(conn)
    made = anchor.record(conn, path)
    assert json.loads(path.read_text().splitlines()[0])["event_hash"] == made["event_hash"]
    assert anchor.check(conn, path)["problems"] == []

    # A database owner rewrites the event before the anchored one, then repairs
    # the chain so that it is internally consistent again.
    head_id, earlier = (r[0] for r in conn.execute(
        "SELECT event_id FROM audit_event ORDER BY event_id DESC LIMIT 2").fetchall())
    assert head_id == made["event_id"]
    conn.execute("ALTER TABLE audit_event DISABLE TRIGGER tg_audit_event_append_only")
    conn.execute("UPDATE audit_event SET reason = 'nothing to see' WHERE event_id = %s",
                 (earlier,))
    conn.execute(RECOMPUTE, (earlier,))
    conn.execute("UPDATE audit_event SET prev_hash = (SELECT event_hash FROM audit_event"
                 " WHERE event_id = %s) WHERE event_id = %s", (earlier, head_id))
    conn.execute(RECOMPUTE, (head_id,))

    assert conn.execute("SELECT * FROM fn_verify_audit_chain()").fetchone() is None  # looks fine
    problems = anchor.check(conn, path)["problems"]
    assert len(problems) == 1 and f"event {head_id} had hash" in problems[0]
    assert "audit_chain_anchor_mismatch" in {e["kind"] for e in exceptions(conn, org_id)}


def test_anchors_from_another_database_are_reported_not_ignored(owner_conn, tmp_path):
    path = tmp_path / "anchors.jsonl"
    assert anchor.check(owner_conn, path) == {
        "anchors": 0, "checked": 0, "problems": [], "latest": None,
        "head": anchor.head(owner_conn)}
    _three_events(owner_conn)
    path.write_text(json.dumps({"chain": "f" * 64, "event_id": 1, "event_hash": "0" * 64,
                                "anchored_at": "2026-01-01T00:00:00+00:00"}) + "\n")
    result = anchor.check(owner_conn, path)
    assert result["checked"] == 0 and "belongs to this database" in result["problems"][0]
