"""Invariant 1: a report generated at T regenerates byte-identically AS OF T,
whatever happens afterwards. Verified by property-based testing.

    pytest tests/test_reproducibility.py                          # 100 sequences
    HYPOTHESIS_PROFILE=thorough pytest tests/test_reproducibility.py  # 10,000

Each generated sequence interleaves every operation that could plausibly
change a past report, generating reports under all four policies after every
step; at the end every report is regenerated and compared byte for byte.
Factors here are synthetic (publisher TEST).
"""
import threading
import time
import uuid
from datetime import date
from decimal import Decimal

import psycopg
import pytest
from conftest import connect
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from carbonx.engine.calculate import edit_activity, record_activity
from carbonx.engine.production import (
    edit_production,
    record_production,
    set_equivalence,
)
from carbonx.engine.report import (
    EngineVersionMismatch,
    generate_report,
    regenerate,
    verify,
)
from carbonx.factors.registry import POLICY_DESCRIPTIONS, Policy, insert_factor

GRID = "grid.weighted_avg_incl_re_captive.incl_imports"
GAS = "fuel.natural_gas.co2e"
FY = "FY2025-26"
FACTOR_FYS = ["FY2023-24", "FY2024-25", "FY2025-26"]
MONTHS = [(date(2025 + (m >= 9), (3 + m) % 12 + 1, 1)) for m in range(12)]  # Apr..Mar


def _month_end(start: date) -> date:
    return date(start.year + (start.month == 12), start.month % 12 + 1, 1)


def _policies(conn):
    for p, d in POLICY_DESCRIPTIONS.items():
        conn.execute("INSERT INTO resolution_policy (code, description) VALUES (%s, %s)"
                     " ON CONFLICT (code) DO NOTHING", (p.value, d))


def _reports(conn, org_id):
    return [generate_report(conn, org_id, FY, p,
                            "FY2023-24" if p is Policy.BASELINE_FROZEN else None)
            for p in Policy]


REJECTED = (psycopg.errors.RaiseException, psycopg.errors.InsufficientPrivilege)


def _raises_db_error(conn, sql, params=(), exc=REJECTED):
    """The database refuses: by a trigger, or (for the app role) by privilege."""
    conn.execute("SAVEPOINT attempt")
    with pytest.raises(exc):
        conn.execute(sql, params)
    conn.execute("ROLLBACK TO SAVEPOINT attempt")


values = st.decimals("0.500", "1.000", places=3)
published = st.dates(date(2023, 1, 1), date(2027, 12, 31))
quantities = st.integers(0, 2_000_000).map(Decimal)
fuel_values = st.decimals("40.000", "110.000", places=3)   # tCO2e/TJ
ncvs = st.decimals("20.0", "55.0", places=1)               # GJ/t
ops = st.lists(st.one_of(
    st.tuples(st.just("new_factor_version"), st.sampled_from(FACTOR_FYS), values, published),
    st.tuples(st.just("late_older_version"), st.sampled_from(FACTOR_FYS), values, published),
    st.tuples(st.just("activity_arrives"), st.integers(0, 11), quantities),
    st.tuples(st.just("backdated_correction"), st.integers(0, 11), quantities),
    st.tuples(st.just("rename"), st.text(  # any name Postgres can store (no NUL)
        st.characters(codec="utf-8", exclude_characters="\x00"), min_size=1, max_size=20)),
    st.tuples(st.just("tamper_factor_source")),
    st.tuples(st.just("move_facility")),
    st.tuples(st.just("production_arrives"), st.integers(0, 11), quantities),
    st.tuples(st.just("production_correction"), st.integers(0, 11), quantities),
    st.tuples(st.just("second_product_arrives"), st.integers(0, 11), quantities),
    st.tuples(st.just("conversion_declared"), st.sampled_from(["al", "billet"]),
              st.decimals("0.00", "2.00", places=2)),
    st.tuples(st.just("new_fuel_factor"), fuel_values, published),
    st.tuples(st.just("fuel_arrives"), st.integers(0, 11), quantities, ncvs),
    st.tuples(st.just("fuel_correction"), st.integers(0, 11), quantities, ncvs),
), min_size=1, max_size=8)


@settings(deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture,
                                                HealthCheck.too_slow])
@given(initial=st.sets(st.integers(0, 11), max_size=4), sequence=ops)
def test_reports_reproduce_after_any_sequence(conn, initial, sequence):
    conn.execute("SAVEPOINT example")
    try:
        _policies(conn)
        (org_id,) = conn.execute("INSERT INTO organisation (name) VALUES ('P5 org')"
                                 " RETURNING org_id").fetchone()
        (other_org,) = conn.execute("INSERT INTO organisation (name) VALUES ('other')"
                                    " RETURNING org_id").fetchone()
        (facility_id,) = conn.execute(
            "INSERT INTO facility (org_id, name, state) VALUES (%s, 'P5 plant', 'KA')"
            " RETURNING facility_id", (org_id,)).fetchone()
        counters = {"new": 100_000, "late": 50_000}
        current: dict[int, int] = {}
        produced: dict[int, int] = {}
        burned: dict[int, int] = {}
        second: set[int] = set()

        def add_factor(kind, fy, value, pub, key=GRID, units=("tCO2", "MWh")):
            counters[kind] += 1
            (source_id,) = conn.execute(
                "INSERT INTO factor_source (publisher, dataset_name, version_label,"
                " version_ordinal, published_on, source_url) VALUES ('TEST', 'synthetic',"
                " %s, %s, %s, 'https://example.test') RETURNING source_id",
                (f"{kind}-{counters[kind]}", counters[kind], pub)).fetchone()
            insert_factor(conn, source_id=source_id, factor_key=key, value=value,
                          numerator_unit=units[0], denominator_unit=units[1], fy=fy)

        def add_fuel_factor(value, pub):
            add_factor("new", FY, value, pub, GAS, ("tCO2e", "TJ"))

        def arrive(m, qty):
            if m not in current:
                current[m] = record_activity(
                    conn, facility_id=facility_id, activity_type="grid_electricity",
                    period_start=MONTHS[m], period_end=_month_end(MONTHS[m]),
                    quantity=qty, unit="kWh")

        add_factor("new", "FY2025-26", Decimal("0.700"), date(2026, 1, 1))
        add_fuel_factor(Decimal("56.155"), date(2024, 7, 1))
        for m in sorted(initial):
            arrive(m, Decimal(1_000_000))
        reports = _reports(conn, org_id)

        for op, *args in sequence:
            if op == "new_factor_version":
                add_factor("new", *args)
            elif op == "late_older_version":  # arrives after newer versions exist
                add_factor("late", *args)
            elif op == "activity_arrives":    # possibly for an earlier month
                arrive(*args)
            elif op == "backdated_correction" and args[0] in current:
                current[args[0]], _ = edit_activity(
                    conn, current[args[0]], quantity=args[1], reason="backdated fix")
            elif op == "rename":              # names are mutable; reports hold ids
                conn.execute("UPDATE organisation SET name = %s WHERE org_id = %s",
                             (args[0], org_id))
                conn.execute("UPDATE facility SET name = %s WHERE facility_id = %s",
                             (args[0], facility_id))
            elif op == "tamper_factor_source":
                _raises_db_error(conn, "UPDATE factor_source SET published_on ="
                                 " '2000-01-01' WHERE publisher = 'TEST'")
            elif op == "production_arrives" and args[0] not in produced:
                produced[args[0]] = record_production(
                    conn, facility_id=facility_id, product_code="al", unit="t",
                    period_start=MONTHS[args[0]], period_end=_month_end(MONTHS[args[0]]),
                    quantity=args[1] / 1000)
            elif op == "production_correction" and args[0] in produced:
                produced[args[0]] = edit_production(
                    conn, produced[args[0]], quantity=args[1] / 1000, reason="re-weighed")
            elif op == "second_product_arrives" and args[0] not in second:
                second.add(args[0])           # the plant now has two products
                record_production(
                    conn, facility_id=facility_id, product_code="billet", unit="t",
                    period_start=MONTHS[args[0]], period_end=_month_end(MONTHS[args[0]]),
                    quantity=args[1] / 1000)
            elif op == "conversion_declared":  # declared, or revised if one exists
                set_equivalence(conn, facility_id=facility_id, product_code=args[0],
                                fy=FY, factor=args[1], equivalent_unit="t",
                                basis="generated")
            elif op == "new_fuel_factor":     # a default fuel factor is superseded
                add_fuel_factor(*args)
            elif op == "fuel_arrives" and args[0] not in burned:
                burned[args[0]] = record_activity(
                    conn, facility_id=facility_id, activity_type="fuel.natural_gas",
                    period_start=MONTHS[args[0]], period_end=_month_end(MONTHS[args[0]]),
                    quantity=args[1] / 1000, unit="t", ncv=args[2], ncv_unit="GJ/t")
            elif op == "fuel_correction" and args[0] in burned:  # quantity and NCV
                burned[args[0]], _ = edit_activity(
                    conn, burned[args[0]], quantity=args[1] / 1000, ncv=args[2],
                    reason="lab NCV and weighbridge correction")
            elif op == "move_facility":
                _raises_db_error(conn, "UPDATE facility SET org_id = %s"
                                 " WHERE facility_id = %s", (other_org, facility_id))
            reports += _reports(conn, org_id)

        if burned:  # not vacuous: the fuel lines did reach the reports
            assert '"fuel.natural_gas"' in reports[-1].output
        for r in reports:
            again = regenerate(conn, r.report_id)
            assert again.output == r.output
            assert again.sha256 == r.sha256
    finally:
        conn.execute("ROLLBACK TO SAVEPOINT example")


def test_policies_differ_but_each_reproduces(conn):
    """The demo's step 6 in miniature: switching policy changes the figure;
    the original report still reproduces."""
    _policies(conn)
    (org_id,) = conn.execute("INSERT INTO organisation (name) VALUES ('demo')"
                             " RETURNING org_id").fetchone()
    (facility_id,) = conn.execute("INSERT INTO facility (org_id, name, state)"
                                  " VALUES (%s, 'p', 'KA') RETURNING facility_id",
                                  (org_id,)).fetchone()
    for i, (fy, value, pub) in enumerate([("FY2024-25", "0.710", date(2025, 11, 1)),
                                          ("FY2025-26", "0.675", date(2026, 8, 1))]):
        (sid,) = conn.execute(
            "INSERT INTO factor_source (publisher, dataset_name, version_label,"
            " version_ordinal, published_on, source_url) VALUES ('TEST', 'demo', %s,"
            " %s, %s, 'https://example.test') RETURNING source_id",
            (f"d{i}", 900_000 + i, pub)).fetchone()
        insert_factor(conn, source_id=sid, factor_key=GRID, value=Decimal(value),
                      numerator_unit="tCO2", denominator_unit="MWh", fy=fy)
    record_activity(conn, facility_id=facility_id, activity_type="grid_electricity",
                    period_start=date(2025, 4, 1), period_end=date(2025, 5, 1),
                    quantity=Decimal(1_000_000), unit="kWh")
    vintage = generate_report(conn, org_id, FY, Policy.VINTAGE_MATCHED)
    deadline = generate_report(conn, org_id, FY, Policy.AS_OF_REPORT)
    assert '"total_tco2e":"675.000000"' in vintage.output
    assert '"total_tco2e":"710.000000"' in deadline.output
    assert verify(conn, vintage.report_id) and verify(conn, deadline.report_id)


def test_report_rows_are_immutable(owner_conn):
    """Even the owner's UPDATE/DELETE is refused, by trigger."""
    conn = owner_conn
    _policies(conn)
    (org_id,) = conn.execute("INSERT INTO organisation (name) VALUES ('x')"
                             " RETURNING org_id").fetchone()
    r = generate_report(conn, org_id, FY, Policy.VINTAGE_MATCHED)
    trigger = psycopg.errors.RaiseException
    _raises_db_error(conn, "UPDATE report SET output_sha256 = repeat('0', 64)"
                     " WHERE report_id = %s", (r.report_id,), trigger)
    _raises_db_error(conn, "DELETE FROM report WHERE report_id = %s",
                     (r.report_id,), trigger)


def test_regenerate_refuses_under_another_engine_version(conn):
    _policies(conn)
    (org_id,) = conn.execute("INSERT INTO organisation (name) VALUES ('x')"
                             " RETURNING org_id").fetchone()
    (rid,) = conn.execute(
        "INSERT INTO report (org_id, compliance_year, policy_id, as_of, total_tco2e,"
        " output_sha256, engine_version, output) SELECT %s, %s, policy_id, now(), 0,"
        " repeat('0', 64), '0.0.0-old', '{}' FROM resolution_policy LIMIT 1"
        " RETURNING report_id", (org_id, FY)).fetchone()
    with pytest.raises(EngineVersionMismatch):
        regenerate(conn, rid)


def test_report_waits_for_an_in_flight_writer():
    """The commit-time race, on two real connections. A writer stamps its row
    and has not committed; a report starting now must wait for it, then see
    it. Before migration 0003 the report read immediately and missed it, and
    a later regeneration saw it: a different hash.

    Commits real rows (the ledger is append-only, so they cannot be removed);
    they belong to a uniquely named organisation.
    """
    setup, writer = connect(), connect()
    try:
        _policies(setup)
        name = f"concurrency-test {uuid.uuid4()}"
        (org_id,) = setup.execute("INSERT INTO organisation (name) VALUES (%s)"
                                  " RETURNING org_id", (name,)).fetchone()
        (facility_id,) = setup.execute(
            "INSERT INTO facility (org_id, name, state) VALUES (%s, 'p', 'KA')"
            " RETURNING facility_id", (org_id,)).fetchone()
        setup.commit()

        # Open the writer's transaction first: with none open, psycopg's
        # conn.transaction() inside record_activity would begin AND commit.
        writer.execute("SELECT 1")
        record_activity(writer, facility_id=facility_id, activity_type="grid_electricity",
                        period_start=date(2025, 4, 1), period_end=date(2025, 5, 1),
                        quantity=Decimal(1000), unit="kWh")  # stamped, not committed

        result = {}

        def report():
            try:
                with connect() as c:
                    r = generate_report(c, org_id, FY, Policy.LATEST_AVAILABLE)
                    c.commit()
                    result["report"] = r
                    result["reproduces"] = verify(c, r.report_id)
            # BaseException: pytest's skip is one. A crash must not pass as "didn't wait".
            except BaseException as e:  # noqa: BLE001
                result["error"] = e

        t = threading.Thread(target=report)
        t.start()
        time.sleep(0.5)
        assert "error" not in result, result.get("error")
        # Not decisive on its own: before 0003 the report also blocked, but only
        # at its audited INSERT, after it had already read. The two assertions
        # after the commit are the ones that fail without the fix (checked:
        # docs/ADVERSARIAL_LOG.md, attempt 1).
        assert t.is_alive(), "report did not wait for the in-flight writer"
        writer.commit()
        t.join(timeout=10)
        assert not t.is_alive()
        assert "error" not in result, result.get("error")
        assert '"activity_id"' in result["report"].output  # it saw the write
        assert result["reproduces"]
    finally:
        writer.rollback()
        writer.close()
        setup.close()


# ---- migration 0004: transaction time only moves forward ------------------

def _facility(conn):
    (org_id,) = conn.execute("INSERT INTO organisation (name) VALUES (%s)"
                             " RETURNING org_id", (f"p5 {uuid.uuid4()}",)).fetchone()
    (facility_id,) = conn.execute("INSERT INTO facility (org_id, name, state)"
                                  " VALUES (%s, 'p', 'KA') RETURNING facility_id",
                                  (org_id,)).fetchone()
    return facility_id


def test_backdated_transaction_time_is_rejected(conn):
    """Would make a row retroactively visible to every earlier report."""
    facility_id = _facility(conn)
    _raises_db_error(conn, "INSERT INTO activity (facility_id, activity_type, scope, period,"
                     " quantity, unit, system_time_range) VALUES (%s, 'grid_electricity', 2,"
                     " '[2025-04-01,2025-05-01)', 1, 'kWh', tstzrange('2020-01-01', NULL))",
                     (facility_id,))


def test_closing_a_row_in_the_past_is_rejected():
    """Would hide a row from reports that saw it. Needs a row committed by an
    earlier transaction (commits real rows under a unique organisation)."""
    first, second = connect(), connect()
    try:
        activity_id = record_activity(
            first, facility_id=_facility(first), activity_type="grid_electricity",
            period_start=date(2025, 4, 1), period_end=date(2025, 5, 1),
            quantity=Decimal(1), unit="kWh")
        first.commit()
        _raises_db_error(second, "UPDATE activity SET system_time_range = tstzrange("
                         "lower(system_time_range), lower(system_time_range)"
                         " + interval '1 microsecond') WHERE activity_id = %s",
                         (activity_id,))
    finally:
        second.rollback()
        first.close()
        second.close()


@pytest.mark.parametrize("table", ["activity", "emission_factor", "calculation",
                                   "ledger_entry", "report", "factor_source",
                                   "source_document", "resolution_policy"])
def test_history_cannot_be_truncated(owner_conn, table):
    """Even the owner's TRUNCATE is refused, by statement trigger."""
    _raises_db_error(owner_conn, f"TRUNCATE {table} CASCADE",
                     exc=psycopg.errors.RaiseException)


def test_policy_codes_are_immutable(owner_conn):
    """A stored report names its policy by id; renaming the code would change
    what it regenerates as. Refused by trigger, even for the owner."""
    _policies(owner_conn)
    _raises_db_error(owner_conn, "UPDATE resolution_policy SET code = 'X'"
                     " WHERE code = 'VINTAGE_MATCHED'", exc=psycopg.errors.RaiseException)


# ---- migration 0005: the application cannot switch the rules off ----------

@pytest.mark.parametrize("sql", [
    "SET session_replication_role = replica",   # turns every trigger off
    "ALTER TABLE activity DISABLE TRIGGER ALL",
    "DROP TRIGGER tg_guard_activity ON activity",
    "DELETE FROM activity",
    "TRUNCATE activity",
    ("INSERT INTO audit_event (entity_table, entity_id, action, occurred_at, event_hash)"
     " VALUES ('x', 0, 'INSERT', now(), repeat('0', 64))"),   # forge an audit row
    "UPDATE factor_source SET published_on = '2000-01-01'",
])
def test_app_role_cannot_bypass_the_database_rules(conn, sql):
    """docs/ADVERSARIAL_LOG.md attempt 12: as superuser, these broke invariant 1.
    As carbonx_app they are refused before any trigger is even needed."""
    _raises_db_error(conn, sql, exc=psycopg.errors.InsufficientPrivilege)
