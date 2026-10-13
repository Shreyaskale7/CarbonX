"""Meters: which device measures what, and how well, with the certificate.

The measuring half of a monitoring plan. A meter may state an uncertainty only
with the calibration certificate that states it (the database refuses
otherwise), so activity-data uncertainty is evidence-backed or absent, never
assumed. Re-declaring a meter supersedes the old row; readings already taken
keep the row they were recorded against. See docs/UNCERTAINTY.md.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import psycopg

from carbonx.engine.calculate import activity_spec, set_audit_context, system_now


def declare_meter(conn: psycopg.Connection, *, facility_id: int, meter_code: str,
                  measures: str, uncertainty_pct: Decimal | None = None,
                  calibration_document_id: int | None = None,
                  calibrated_on: date | None = None, note: str | None = None,
                  actor: str | None = None, reason: str | None = None) -> int:
    """Declare a meter, or re-declare it (for example after recalibration).

    `uncertainty_pct` is the expanded uncertainty at about 95%, in percent of
    reading, as the calibration certificate states it. It needs
    `calibration_document_id`: a hashed copy of that certificate.
    """
    activity_spec(measures)   # an unknown activity type fails here
    code = meter_code.strip()
    if not code:
        raise ValueError("a meter needs the code written on the device or the bill")
    if uncertainty_pct is not None and calibration_document_id is None:
        raise ValueError("an uncertainty needs the calibration certificate that states it")
    if uncertainty_pct is not None and not 0 < uncertainty_pct <= 100:
        raise ValueError("uncertainty_pct must be between 0 and 100")
    with conn.transaction():
        set_audit_context(conn, actor, reason or f"meter {code} declared")
        t = system_now(conn)
        old = conn.execute(
            "SELECT meter_id, measures FROM meter WHERE facility_id = %s AND meter_code = %s"
            " AND upper_inf(system_time_range) FOR UPDATE", (facility_id, code)).fetchone()
        if old and old[1] != measures:
            raise ValueError(f"meter {code} measures {old[1]}; a meter does not change "
                             "what it measures. Declare the other device under its own code")
        if old:
            conn.execute("UPDATE meter SET system_time_range ="
                         " tstzrange(lower(system_time_range), %s) WHERE meter_id = %s",
                         (t, old[0]))
        row = conn.execute(
            "INSERT INTO meter (facility_id, meter_code, measures, uncertainty_pct,"
            " calibration_document_id, calibrated_on, note, supersedes, system_time_range)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, tstzrange(%s, NULL)) RETURNING meter_id",
            (facility_id, code, measures, uncertainty_pct, calibration_document_id,
             calibrated_on, note, old[0] if old else None, t)).fetchone()
    assert row is not None
    return int(row[0])
