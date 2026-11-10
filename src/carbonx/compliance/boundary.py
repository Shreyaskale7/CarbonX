"""Gate-to-gate boundary tags (migration 0017): which activities count toward a unit's intensity."""

from __future__ import annotations

from datetime import datetime

import psycopg

from carbonx.engine.calculate import set_audit_context, system_now

BOUNDARIES = {"inside", "outside"}


def tag_activity(conn: psycopg.Connection, *, activity_id: int, boundary: str, basis: str,
                 actor: str | None = None) -> int:
    """Say whether an activity is inside the gate-to-gate boundary, and why. A new tag for the same
    activity supersedes the current one; a Form I made earlier keeps the tag it read."""
    if boundary not in BOUNDARIES:
        raise ValueError(f"boundary must be one of {sorted(BOUNDARIES)}")
    if not basis.strip():
        raise ValueError("state the basis for the boundary (for example, which meter serves "
                         "which part of the plant): a verifier must be able to check it")
    with conn.transaction():
        set_audit_context(conn, actor, basis)
        t = system_now(conn)
        if conn.execute("SELECT 1 FROM activity WHERE activity_id = %s",
                        (activity_id,)).fetchone() is None:
            raise LookupError(f"no activity {activity_id}")
        old = conn.execute(
            "SELECT tag_id FROM activity_boundary WHERE activity_id = %s"
            " AND upper_inf(system_time_range) FOR UPDATE", (activity_id,)).fetchone()
        if old:
            conn.execute("UPDATE activity_boundary SET system_time_range ="
                         " tstzrange(lower(system_time_range), %s) WHERE tag_id = %s",
                         (t, old[0]))
        row = conn.execute(
            "INSERT INTO activity_boundary (activity_id, boundary, basis, supersedes,"
            " system_time_range) VALUES (%s, %s, %s, %s, tstzrange(%s, NULL)) RETURNING tag_id",
            (activity_id, boundary, basis.strip(), old[0] if old else None, t)).fetchone()
    assert row is not None
    return int(row[0])


def tags_as_of(conn: psycopg.Connection, activity_ids: list[int],
               as_of: datetime) -> dict[int, dict[str, object]]:
    """The tag known at `as_of` for each given activity; activities with none are absent."""
    if not activity_ids:
        return {}
    rows = conn.execute(
        "SELECT activity_id, tag_id, boundary, basis FROM activity_boundary"
        " WHERE activity_id = ANY(%s) AND system_time_range @> %s::timestamptz",
        (activity_ids, as_of)).fetchall()
    return {aid: {"tag_id": tid, "boundary": b, "basis": basis} for aid, tid, b, basis in rows}
