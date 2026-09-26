"""DB-layer invariants 2, 3 and 5. Needs Postgres from docker compose, migrated.

Each test runs in a transaction that is rolled back, so the DB is left clean.
"""
import psycopg
import pytest


def _factor(cur) -> int:
    cur.execute(
        "INSERT INTO factor_source (publisher, dataset_name, version_label,"
        " version_ordinal, source_url) VALUES"
        " ('CEA', 'CO2 Baseline Database', 'v19.0', 19, 'https://cea.nic.in')"
        " RETURNING source_id"
    )
    (source_id,) = cur.fetchone()
    cur.execute(
        "INSERT INTO emission_factor (source_id, factor_key, value,"
        " numerator_unit, denominator_unit, valid_time) VALUES"
        " (%s, 'grid.IN.weighted_avg', 0.716, 'tCO2', 'MWh',"
        "  '[2022-04-01,2023-04-01)') RETURNING factor_id",
        (source_id,),
    )
    return cur.fetchone()[0]


def _raises(cur, sql, params=()):
    cur.execute("SAVEPOINT s")
    with pytest.raises(psycopg.errors.RaiseException):
        cur.execute(sql, params)
    cur.execute("ROLLBACK TO SAVEPOINT s")


def test_factor_value_cannot_be_overwritten(cur):
    fid = _factor(cur)
    _raises(cur, "UPDATE emission_factor SET value = 0.9 WHERE factor_id = %s", (fid,))
    _raises(cur, "DELETE FROM emission_factor WHERE factor_id = %s", (fid,))


def test_factor_can_be_closed_once(cur):
    fid = _factor(cur)
    close = (
        "UPDATE emission_factor SET system_time_range ="
        " tstzrange(lower(system_time_range), now() + interval '1 second')"
        " WHERE factor_id = %s"
    )
    cur.execute(close, (fid,))
    _raises(cur, close, (fid,))  # already closed: history is frozen


def test_audit_records_real_entity_id(cur):
    fid = _factor(cur)
    cur.execute(
        "SELECT entity_id FROM audit_event WHERE entity_table = 'emission_factor'"
        " ORDER BY event_id DESC LIMIT 1"
    )
    assert cur.fetchone()[0] == fid


def test_audit_log_is_append_only_and_chain_verifies(cur):
    fid = _factor(cur)
    cur.execute(  # second event, so there is a prev_hash link to check
        "UPDATE emission_factor SET system_time_range ="
        " tstzrange(lower(system_time_range), now() + interval '1 second')"
        " WHERE factor_id = %s",
        (fid,),
    )
    cur.execute("SELECT * FROM fn_verify_audit_chain()")
    assert cur.fetchall() == []
    _raises(cur, "UPDATE audit_event SET actor = 'mallory'")
    _raises(cur, "DELETE FROM audit_event")
    _raises(cur, "TRUNCATE audit_event")


def test_tampering_is_detected(cur):
    _factor(cur)
    # Simulate a superuser bypassing the append-only trigger.
    cur.execute("ALTER TABLE audit_event DISABLE TRIGGER tg_audit_event_append_only")
    cur.execute(
        "UPDATE audit_event SET actor = 'mallory'"
        " WHERE event_id = (SELECT max(event_id) FROM audit_event)"
    )
    cur.execute("SELECT problem FROM fn_verify_audit_chain()")
    assert cur.fetchone()[0] == "event_hash does not match contents"
