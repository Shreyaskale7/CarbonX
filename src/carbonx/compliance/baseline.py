"""The baseline year's intensity: stated, cited, versioned (migration 0016).

BEE's text never names the baseline year, so it is an input. A record that was not read from a
notification or a verified submission is 'assumed', and results built on it say so.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

import psycopg

from carbonx.engine.calculate import set_audit_context, system_now
from carbonx.factors.registry import fy_start

STATUSES = {"notified", "assumed", "verified"}


def set_baseline(conn: psycopg.Connection, *, facility_id: int, baseline_fy: str,
                 intensity: Decimal, intensity_unit: str, status: str, source_citation: str,
                 output: Decimal | None = None, output_unit: str | None = None,
                 source_url: str | None = None, actor: str | None = None,
                 reason: str | None = None) -> int:
    """Record the baseline intensity for a facility. A new one for the same baseline year
    supersedes the current one; an entitlement computed earlier keeps the one it read."""
    if status not in STATUSES:
        raise ValueError(f"status must be one of {sorted(STATUSES)}")
    if not source_citation.strip():
        raise ValueError("state where the baseline comes from (notification, page, submission)")
    if not intensity_unit.startswith("tCO2e/") or len(intensity_unit) == len("tCO2e/"):
        raise ValueError("an intensity is tCO2e per unit of product, e.g. 'tCO2e/t'")
    if intensity < 0 or (output is not None and output < 0):
        raise ValueError("intensity and output cannot be negative")
    if (output is None) != (output_unit is None):
        raise ValueError("give the baseline output and its unit together, or neither")
    fy_start(baseline_fy)   # a malformed year fails here, not in a report
    with conn.transaction():
        set_audit_context(conn, actor, reason or source_citation)
        t = system_now(conn)
        old = conn.execute(
            "SELECT baseline_id FROM baseline_record WHERE facility_id = %s AND baseline_fy = %s"
            " AND upper_inf(system_time_range) FOR UPDATE", (facility_id, baseline_fy)).fetchone()
        if old:
            conn.execute("UPDATE baseline_record SET system_time_range ="
                         " tstzrange(lower(system_time_range), %s) WHERE baseline_id = %s",
                         (t, old[0]))
        row = conn.execute(
            "INSERT INTO baseline_record (facility_id, baseline_fy, intensity, intensity_unit,"
            " output, output_unit, status, source_citation, source_url, supersedes,"
            " system_time_range) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,"
            " tstzrange(%s, NULL)) RETURNING baseline_id",
            (facility_id, baseline_fy, intensity, intensity_unit, output, output_unit, status,
             source_citation.strip(), source_url, old[0] if old else None, t)).fetchone()
    assert row is not None
    return int(row[0])


def baselines_as_of(conn: psycopg.Connection, org_id: int,
                    as_of: datetime) -> dict[int, dict[str, Any]]:
    """The baseline known at `as_of` for each facility, keyed by facility. If a facility has
    records for more than one baseline year, the one with the latest baseline year is used."""
    rows = conn.execute(
        "SELECT b.facility_id, b.baseline_id, b.baseline_fy, b.intensity, b.intensity_unit,"
        " b.output, b.output_unit, b.status, b.source_citation, b.source_url"
        " FROM baseline_record b JOIN facility f USING (facility_id)"
        " WHERE f.org_id = %s AND b.system_time_range @> %s::timestamptz"
        " ORDER BY b.facility_id, b.baseline_fy", (org_id, as_of)).fetchall()
    out: dict[int, dict[str, Any]] = {}
    for fid, bid, fy, value, unit, output, output_unit, status, cite, url in rows:
        out[fid] = {"baseline_id": bid, "baseline_fy": fy, "intensity": format(value, "f"),
                    "unit": unit, "output": None if output is None else format(output, "f"),
                    "output_unit": output_unit, "status": status,
                    "source_citation": cite, "source_url": url}
    return out
