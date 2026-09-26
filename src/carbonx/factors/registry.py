"""Bitemporal emission factor registry and version-resolution policies.

Factors are never overwritten (invariant 2). A revision closes the current row's
system_time_range and inserts a new row that `supersedes` it; the DB trigger
fn_bitemporal_guard rejects anything else.

resolve() reads only rows whose system time began at or before `as_of`, and
ignores whether they were closed later. So for a fixed `as_of` its answer can
never change, whatever is inserted afterwards (invariant 1, for factors).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

import psycopg
from psycopg.rows import TupleRow, class_row


class Policy(StrEnum):
    """Which factor applies to a compliance year. BEE may not say (RQ3)."""

    # Newest factor for any FY <= the compliance year, known at as_of.
    LATEST_AVAILABLE = "LATEST_AVAILABLE"
    # The factor whose valid_time is the compliance year itself. Often does not
    # exist yet at the reporting deadline: that absence is the RQ3 finding.
    VINTAGE_MATCHED = "VINTAGE_MATCHED"
    # As LATEST_AVAILABLE, but only versions published by the report deadline.
    AS_OF_REPORT = "AS_OF_REPORT"
    # The first-published value for the entity's baseline FY, never revised.
    BASELINE_FROZEN = "BASELINE_FROZEN"


POLICY_DESCRIPTIONS: dict[Policy, str] = {
    Policy.LATEST_AVAILABLE: "Newest factor for any FY up to the compliance "
    "year, as known at the query time.",
    Policy.VINTAGE_MATCHED: "Factor whose valid FY equals the compliance year.",
    Policy.AS_OF_REPORT: "Newest factor for any FY up to the compliance year, "
    "restricted to versions published by the report deadline.",
    Policy.BASELINE_FROZEN: "First-published factor for the baseline FY, "
    "ignoring later revisions.",
}


class FactorNotFound(LookupError):
    pass


@dataclass(frozen=True)
class EmissionFactor:
    factor_id: int
    source_id: int
    factor_key: str
    geography: str
    value: Decimal
    numerator_unit: str
    denominator_unit: str
    valid_from: date
    valid_to: date  # exclusive
    version_label: str
    version_ordinal: int
    published_on: date | None
    source_url: str


_FY = re.compile(r"FY(\d{4})-(\d{2})")


def fy_start(fy: str) -> date:
    """'FY2025-26' -> 2025-04-01 (Indian financial year)."""
    m = _FY.fullmatch(fy)
    if not m or (int(m[1]) + 1) % 100 != int(m[2]):
        raise ValueError(f"not a financial year like 'FY2025-26': {fy!r}")
    return date(int(m[1]), 4, 1)


def report_deadline(fy: str) -> date:
    """31 July after the FY ends.

    Verified for FY2025-26 only (deadline 31 July 2026); assumed for other
    years until docs/RQ3_FINDINGS.md says otherwise.
    """
    return date(fy_start(fy).year + 1, 7, 31)


def insert_factor(
    conn: psycopg.Connection[TupleRow],
    *,
    source_id: int,
    factor_key: str,
    value: Decimal,
    numerator_unit: str,
    denominator_unit: str,
    fy: str,
    geography: str = "IN",
    margin_type: str | None = None,
    uncertainty_low: Decimal | None = None,
    uncertainty_high: Decimal | None = None,
    uncertainty_basis: str | None = None,
) -> int:
    """Record a factor for one FY, superseding the current row if there is one.

    Never UPDATEs a value. Returns the new factor_id.
    """
    start = fy_start(fy)
    valid = f"[{start},{date(start.year + 1, 4, 1)})"
    with conn.transaction(), conn.cursor() as cur:
        # fn_system_now() (migration 0003): clock time taken under the global
        # write lock, so no report can read AS OF a time before this commits.
        # A clock, not now(): a factor inserted and superseded in the
        # same transaction would otherwise get an empty [t, t) range.
        cur.execute("SELECT fn_system_now()")
        row = cur.fetchone()
        assert row is not None
        t = row[0]
        cur.execute(
            "SELECT factor_id FROM emission_factor"
            " WHERE factor_key = %s AND geography = %s"
            "   AND valid_time && %s::daterange AND upper_inf(system_time_range)"
            " FOR UPDATE",
            (factor_key, geography, valid),
        )
        current = [r[0] for r in cur.fetchall()]
        if len(current) > 1:
            raise ValueError(f"{factor_key} {fy} overlaps {len(current)} rows")
        if current:
            cur.execute(
                "UPDATE emission_factor SET system_time_range ="
                " tstzrange(lower(system_time_range), %s) WHERE factor_id = %s",
                (t, current[0]),
            )
        cur.execute(
            "INSERT INTO emission_factor (source_id, factor_key, value,"
            " numerator_unit, denominator_unit, geography, margin_type,"
            " uncertainty_low, uncertainty_high, uncertainty_basis, valid_time,"
            " system_time_range, supersedes)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::daterange,"
            " tstzrange(%s, NULL), %s) RETURNING factor_id",
            (
                source_id, factor_key, value, numerator_unit, denominator_unit,
                geography, margin_type, uncertainty_low, uncertainty_high,
                uncertainty_basis, valid, t, current[0] if current else None,
            ),
        )
        new = cur.fetchone()
        assert new is not None
        return int(new[0])


_RESOLVE = """
SELECT ef.factor_id, ef.source_id, ef.factor_key, ef.geography, ef.value,
       ef.numerator_unit, ef.denominator_unit,
       lower(ef.valid_time) AS valid_from, upper(ef.valid_time) AS valid_to,
       fs.version_label, fs.version_ordinal, fs.published_on, fs.source_url
FROM emission_factor ef JOIN factor_source fs USING (source_id)
WHERE ef.factor_key = %(key)s AND ef.geography = %(geo)s
  AND lower(ef.system_time_range) <= %(as_of)s
  AND lower(ef.valid_time) <= %(latest_fy)s
  AND (%(exact_fy)s::date IS NULL OR ef.valid_time @> %(exact_fy)s::date)
  AND (%(published_by)s::date IS NULL OR fs.published_on <= %(published_by)s)
ORDER BY lower(ef.valid_time) DESC, {version_order},
         lower(ef.system_time_range) DESC, ef.factor_id DESC
LIMIT 1
"""


def resolve(
    conn: psycopg.Connection[TupleRow],
    factor_key: str,
    compliance_year: str,
    as_of: datetime,
    policy: Policy,
    *,
    geography: str = "IN",
    baseline_year: str | None = None,
) -> EmissionFactor:
    """The factor `policy` selects for `compliance_year`, as known at `as_of`.

    Deterministic for a fixed `as_of`: later inserts start after it and are
    invisible, and closing a row does not hide it.
    """
    year = fy_start(compliance_year)
    exact_fy: date | None = None
    published_by: date | None = None
    version_order = "fs.version_ordinal DESC"
    if policy is Policy.VINTAGE_MATCHED:
        exact_fy = year
    elif policy is Policy.AS_OF_REPORT:
        published_by = report_deadline(compliance_year)
    elif policy is Policy.BASELINE_FROZEN:
        if baseline_year is None:
            raise ValueError("BASELINE_FROZEN needs baseline_year")
        exact_fy = year = fy_start(baseline_year)
        version_order = "fs.version_ordinal ASC"

    sql = _RESOLVE.format(version_order=version_order)
    with conn.cursor(row_factory=class_row(EmissionFactor)) as cur:
        cur.execute(sql, {
            "key": factor_key, "geo": geography, "as_of": as_of,
            "latest_fy": year, "exact_fy": exact_fy, "published_by": published_by,
        })
        found = cur.fetchone()
    if found is None:
        raise FactorNotFound(
            f"{policy}: no {factor_key}/{geography} factor for {compliance_year}"
            f" known at {as_of.isoformat()}"
        )
    return found
