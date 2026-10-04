"""Exception log: what a verifier should look at before trusting a figure.

Each check is one query and reports facts, not opinions. An empty list means
none of these conditions was found; it is not a statement that the figures
are correct.
"""

from __future__ import annotations

from typing import Any

import psycopg

from carbonx.evidence.store import verify_document


def exceptions(conn: psycopg.Connection, org_id: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def add(kind: str, severity: str, detail: str, **ref: Any) -> None:
        out.append({"kind": kind, "severity": severity, "detail": detail, **ref})

    broken = conn.execute("SELECT * FROM fn_verify_audit_chain()").fetchone()
    if broken:
        add("audit_chain_broken", "high",
            f"the audit hash chain fails at event {broken[0]}: {broken[1]}",
            event_id=broken[0])

    for activity_id, kind, start in conn.execute(
            "SELECT a.activity_id, a.activity_type, lower(a.period) FROM activity a"
            " JOIN facility f USING (facility_id) WHERE f.org_id = %s"
            " AND upper_inf(a.system_time_range) AND a.document_id IS NULL"
            " ORDER BY a.activity_id", (org_id,)).fetchall():
        add("no_evidence", "medium",
            f"{kind} for {start:%b %Y} has no source document", activity_id=activity_id)

    for document_id, filename in conn.execute(
            "SELECT DISTINCT d.document_id, d.filename FROM source_document d"
            " JOIN activity a USING (document_id) JOIN facility f ON f.facility_id ="
            " a.facility_id WHERE f.org_id = %s ORDER BY d.document_id",
            (org_id,)).fetchall():
        if not verify_document(conn, document_id):
            add("evidence_hash_mismatch", "high",
                f"{filename}: the stored file is missing or no longer matches the "
                "SHA-256 recorded at upload", document_id=document_id)

    for activity_id, kind, start in conn.execute(
            "SELECT a.activity_id, a.activity_type, lower(a.period) FROM activity a"
            " JOIN facility f USING (facility_id) WHERE f.org_id = %s"
            " AND upper_inf(a.system_time_range) AND NOT EXISTS ("
            "   SELECT 1 FROM calculation c WHERE c.activity_id = a.activity_id"
            "   AND upper_inf(c.system_time_range)) ORDER BY a.activity_id",
            (org_id,)).fetchall():
        add("not_calculated", "low",
            f"{kind} for {start:%b %Y} has no current calculation", activity_id=activity_id)

    # A report still regenerates byte-identically after corrections; that is the
    # point. But a reader should know its figures have since been corrected.
    for report_id, year, n in conn.execute(
            "SELECT r.report_id, r.compliance_year, count(*) FROM report r"
            " JOIN facility f ON f.org_id = r.org_id"
            " JOIN activity a ON a.facility_id = f.facility_id"
            " WHERE r.org_id = %s AND a.supersedes IS NOT NULL"
            " AND lower(a.system_time_range) > r.as_of"
            " AND a.period <@ daterange("
            "   make_date(substring(r.compliance_year from 3 for 4)::int, 4, 1),"
            "   make_date(substring(r.compliance_year from 3 for 4)::int + 1, 4, 1))"
            " GROUP BY r.report_id, r.compliance_year ORDER BY r.report_id",
            (org_id,)).fetchall():
        add("corrected_after_report", "medium",
            f"report {report_id} ({year}) predates {n} later correction(s) to its "
            "activities; it still reproduces, but no longer reflects current data",
            report_id=report_id)

    for extraction_id, filename, confidence in conn.execute(
            "SELECT e.extraction_id, d.filename, e.confidence FROM extraction_result e"
            " JOIN source_document d USING (document_id)"
            " JOIN facility f ON f.facility_id = d.facility_id"
            " WHERE f.org_id = %s AND NOT e.human_verified ORDER BY e.extraction_id",
            (org_id,)).fetchall():
        add("extraction_unconfirmed", "low",
            f"{filename}: an extracted value (confidence {confidence}) has not been "
            "confirmed by a person", extraction_id=extraction_id)
    return out
