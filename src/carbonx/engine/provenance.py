"""The provenance chain for one calculation: everything an auditor needs to
reconstruct a reported figure. Which document, which reading, which factor and
which version of it, who entered it, and what it was before correction.

Values come back as strings (never floats), so nothing is lost in JSON.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.rows import dict_row

from carbonx.evidence.store import verify_document


def plain(v: Any) -> Any:
    if isinstance(v, Decimal):
        return format(v, "f")
    if isinstance(v, datetime | date):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: plain(x) for k, x in v.items()}
    if isinstance(v, list):
        return [plain(x) for x in v]
    return v


def provenance(conn: psycopg.Connection, calculation_id: int) -> dict[str, Any]:
    with conn.cursor(row_factory=dict_row) as cur:
        calc = cur.execute("""
            SELECT c.calculation_id, c.result_value AS tco2e, c.result_unit,
                   c.engine_version, c.program, p.code AS policy,
                   lower(c.system_time_range) AS computed_at,
                   upper(c.system_time_range) AS superseded_at,
                   c.activity_id, c.factor_id,
                   o.org_id, o.name AS organisation, f.facility_id,
                   f.name AS facility, f.state
            FROM calculation c
            JOIN resolution_policy p USING (policy_id)
            JOIN activity a USING (activity_id)
            JOIN facility f ON f.facility_id = a.facility_id
            JOIN organisation o ON o.org_id = f.org_id
            WHERE c.calculation_id = %s""", (calculation_id,)).fetchone()
        if calc is None:
            raise LookupError(f"no calculation {calculation_id}")

        # The activity and every earlier version it corrects, newest first.
        history = cur.execute("""
            WITH RECURSIVE chain AS (
                SELECT a.*, 0 AS depth FROM activity a WHERE activity_id = %s
                UNION ALL
                SELECT a.*, chain.depth + 1 FROM activity a
                JOIN chain ON a.activity_id = chain.supersedes)
            SELECT activity_id, activity_type, scope, lower(period) AS period_start,
                   upper(period) AS period_end, quantity, unit, document_id,
                   ncv, ncv_unit, oxidation_factor,
                   supersedes, lower(system_time_range) AS recorded_at,
                   upper(system_time_range) AS superseded_at
            FROM chain ORDER BY depth""", (calc["activity_id"],)).fetchall()
        ids = [h["activity_id"] for h in history]

        factor = cur.execute("""
            SELECT ef.factor_id, ef.factor_key, ef.geography, ef.value,
                   ef.numerator_unit || '/' || ef.denominator_unit AS unit,
                   lower(ef.valid_time) AS valid_from, upper(ef.valid_time) AS valid_to,
                   ef.supersedes, fs.publisher, fs.dataset_name, fs.version_label,
                   fs.published_on, fs.covers_fy, fs.source_url,
                   fs.file_sha256 AS source_file_sha256
            FROM emission_factor ef JOIN factor_source fs USING (source_id)
            WHERE ef.factor_id = %s""", (calc["factor_id"],)).fetchone()

        document = None
        if history[0]["document_id"] is not None:
            document = cur.execute("""
                SELECT document_id, doc_type, filename, sha256, mime_type, issuer,
                       uploaded_at, redacted
                FROM source_document WHERE document_id = %s""",
                (history[0]["document_id"],)).fetchone()
            assert document is not None
            document["hash_verified"] = verify_document(conn, document["document_id"])

        calculations = cur.execute("""
            SELECT c.calculation_id, c.result_value AS tco2e, p.code AS policy,
                   c.activity_id, lower(c.system_time_range) AS computed_at,
                   upper(c.system_time_range) AS superseded_at
            FROM calculation c JOIN resolution_policy p USING (policy_id)
            WHERE c.activity_id = ANY(%s) ORDER BY c.calculation_id""",
            (ids,)).fetchall()

        audit = cur.execute("""
            SELECT event_id, entity_table, entity_id, action, actor, reason,
                   occurred_at, event_hash
            FROM audit_event
            WHERE (entity_table = 'activity' AND entity_id = ANY(%s))
               OR (entity_table = 'calculation' AND entity_id = ANY(%s))
            ORDER BY event_id""",
            (ids, [c["calculation_id"] for c in calculations])).fetchall()
        broken = cur.execute("SELECT * FROM fn_verify_audit_chain()").fetchone()

    return plain({
        "calculation": calc,
        "activity": history[0],
        "activity_history": history[1:],
        "factor": factor,
        "document": document,
        "calculations": calculations,
        "audit_events": audit,
        "audit_chain": {"intact": broken is None, "first_break": broken},
    })
