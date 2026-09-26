"""Factor registry: supersession, resolution policies, and reproducibility.

v19 = 0.716 (FY2022-23) and v20 = 0.727 (FY2023-24) are the verified CEA
checkpoints. Every other value and every publication date is SYNTHETIC, chosen
only to make the policies disagree.
"""
from datetime import date
from decimal import Decimal

import psycopg
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from carbonx.factors.registry import (
    FactorNotFound,
    Policy,
    fy_start,
    insert_factor,
    report_deadline,
    resolve,
)

KEY = "grid.IN.weighted_avg"


def _source(conn, ordinal: int, published_on: date | None) -> int:
    row = conn.execute(
        "INSERT INTO factor_source (publisher, dataset_name, version_label,"
        " version_ordinal, published_on, source_url)"
        " VALUES ('CEA', 'CO2 Baseline Database', %s, %s, %s, 'https://cea.nic.in')"
        " RETURNING source_id",
        (f"v{ordinal}.0", ordinal, published_on),
    ).fetchone()
    return row[0]


def _put(conn, source_id: int, fy: str, value: str) -> int:
    return insert_factor(
        conn, source_id=source_id, factor_key=KEY, value=Decimal(value),
        numerator_unit="tCO2", denominator_unit="MWh", fy=fy,
    )


def _now(conn):
    return conn.execute("SELECT clock_timestamp()").fetchone()[0]


def _value(conn, fy, as_of, policy, **kw) -> Decimal | None:
    try:
        return resolve(conn, KEY, fy, as_of, policy, **kw).value
    except FactorNotFound:
        return None


@pytest.fixture
def cea(conn):
    """v19, v20, then v21 which adds FY2024-25 and revises FY2023-24."""
    _put(conn, _source(conn, 19, date(2023, 12, 1)), "FY2022-23", "0.716")
    _put(conn, _source(conn, 20, date(2024, 12, 1)), "FY2023-24", "0.727")
    before_v21 = _now(conn)
    v21 = _source(conn, 21, date(2026, 8, 15))  # after the 31 Jul 2026 deadline
    _put(conn, v21, "FY2024-25", "0.710")
    _put(conn, v21, "FY2023-24", "0.730")
    return before_v21


def test_fy_helpers():
    assert fy_start("FY2025-26") == date(2025, 4, 1)
    assert report_deadline("FY2025-26") == date(2026, 7, 31)
    for bad in ("FY2025-27", "2025-26", "FY25-26"):
        with pytest.raises(ValueError):
            fy_start(bad)


def test_policies_disagree_on_identical_data(conn, cea):
    """RQ3 in code: same data, same year, four policies, different answers."""
    now = _now(conn)
    fy = "FY2025-26"
    assert _value(conn, fy, now, Policy.VINTAGE_MATCHED) is None  # not published
    assert _value(conn, fy, now, Policy.LATEST_AVAILABLE) == Decimal("0.710")
    assert _value(conn, fy, now, Policy.AS_OF_REPORT) == Decimal("0.727")
    assert _value(conn, fy, now, Policy.BASELINE_FROZEN,
                  baseline_year="FY2023-24") == Decimal("0.727")


def test_revision_supersedes_without_overwriting(conn, cea):
    rows = conn.execute(
        "SELECT value, upper_inf(system_time_range), supersedes IS NOT NULL"
        " FROM emission_factor WHERE valid_time @> '2023-04-01'::date"
        " ORDER BY factor_id"
    ).fetchall()
    assert rows == [(Decimal("0.727"), False, False), (Decimal("0.730"), True, True)]


def test_as_of_reads_the_past(conn, cea):
    now = _now(conn)
    fy = "FY2023-24"
    assert _value(conn, fy, cea, Policy.VINTAGE_MATCHED) == Decimal("0.727")
    assert _value(conn, fy, now, Policy.VINTAGE_MATCHED) == Decimal("0.730")


def test_direct_overlapping_insert_is_rejected(conn, cea):
    with pytest.raises(psycopg.errors.ExclusionViolation):
        conn.execute(
            "INSERT INTO emission_factor (source_id, factor_key, value,"
            " numerator_unit, denominator_unit, valid_time)"
            " SELECT source_id, %s, 0.5, 'tCO2', 'MWh', '[2024-04-01,2025-04-01)'"
            " FROM factor_source LIMIT 1",
            (KEY,),
        )


FYS = ["FY2022-23", "FY2023-24", "FY2024-25"]
POLICY_ARGS = [
    (Policy.LATEST_AVAILABLE, {}),
    (Policy.VINTAGE_MATCHED, {}),
    (Policy.AS_OF_REPORT, {}),
    (Policy.BASELINE_FROZEN, {"baseline_year": "FY2022-23"}),
]


@settings(max_examples=40, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.lists(
    st.tuples(
        st.sampled_from(FYS),
        st.decimals("0.5", "1.0", places=3),
        st.dates(date(2022, 1, 1), date(2027, 12, 31)),
    ),
    min_size=1, max_size=8,
))
def test_resolve_is_reproducible_under_any_later_inserts(conn, ops):
    """Invariant 1 for factors: an answer given AS OF t never changes."""
    conn.execute("SAVEPOINT example")
    try:
        snapshots = []
        for ordinal, (fy, value, published_on) in enumerate(ops, start=1):
            _put(conn, _source(conn, ordinal, published_on), fy, str(value))
            t = _now(conn)
            snapshots.append((t, [
                _value(conn, "FY2024-25", t, p, **kw) for p, kw in POLICY_ARGS
            ]))
        for t, expected in snapshots:
            assert [
                _value(conn, "FY2024-25", t, p, **kw) for p, kw in POLICY_ARGS
            ] == expected
    finally:
        conn.execute("ROLLBACK TO SAVEPOINT example")
