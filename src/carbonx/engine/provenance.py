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

from carbonx.engine.calculate import (
    activity_spec,
    emissions,
    fy_of,
    resolve_for,
    round6,
)
from carbonx.evidence.store import verify_document
from carbonx.factors.registry import FactorNotFound, Policy


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


def attestation(conn: psycopg.Connection, calculation_id: int,
                baseline_year: str | None = None) -> dict[str, Any]:
    """Which factor version this calculation used, and what the figure would be
    under every other resolution policy, AS OF the calculation's own time.

    This is RQ3 for one number: the same activity, the same moment, and the
    spread that the choice of policy alone produces. A fuel factor does not
    depend on the policy, so its rows are identical by construction.
    """
    row = conn.execute(
        "SELECT a.activity_type, lower(a.period), a.quantity, a.unit, a.ncv, a.ncv_unit,"
        " a.oxidation_factor, lower(c.system_time_range), c.result_value, p.code"
        " FROM calculation c JOIN activity a USING (activity_id)"
        " JOIN resolution_policy p USING (policy_id) WHERE c.calculation_id = %s",
        (calculation_id,)).fetchone()
    if row is None:
        raise LookupError(f"no calculation {calculation_id}")
    kind, start, quantity, unit, ncv, ncv_unit, oxidation, as_of, used, used_policy = row
    spec = activity_spec(kind)
    rows = []
    for policy in Policy:
        entry: dict[str, Any] = {"policy": policy.value, "used": policy.value == used_policy}
        if policy is Policy.BASELINE_FROZEN and baseline_year is None and not spec.is_fuel:
            rows.append(entry | {"unavailable": "needs a baseline year"})
            continue
        try:
            factor = resolve_for(conn, spec, fy_of(start), as_of, policy, baseline_year)
        except FactorNotFound:
            rows.append(entry | {"unavailable": "no factor exists under this policy "
                                                "at the time of calculation"})
            continue
        tco2e = round6(emissions(quantity, unit, factor, ncv, ncv_unit, oxidation)[1])
        rows.append(entry | {
            "tco2e": tco2e, "factor_value": factor.value,
            "factor_unit": f"{factor.numerator_unit}/{factor.denominator_unit}",
            "source_version": factor.version_label, "factor_year": factor.valid_from,
            "published_on": factor.published_on,
            "vs_used_pct": None if not used else round(
                (tco2e - used) * 100 / used, 2),
        })
    return plain({"calculation_id": calculation_id, "as_of": as_of,
                  "policy_dependent": not spec.is_fuel, "alternatives": rows})


def coverage(conn: psycopg.Connection, org_id: int) -> dict[str, Any]:
    """Audit coverage: the share of currently reported tCO2e whose activity
    carries a hashed source document. (A document on file, not a judgment that
    it supports the figure.)"""
    row = conn.execute(
        "SELECT coalesce(sum(c.result_value), 0),"
        " coalesce(sum(c.result_value) FILTER (WHERE a.document_id IS NOT NULL), 0)"
        " FROM calculation c JOIN activity a USING (activity_id)"
        " JOIN facility f ON f.facility_id = a.facility_id"
        " WHERE f.org_id = %s AND upper_inf(c.system_time_range)"
        " AND upper_inf(a.system_time_range)", (org_id,)).fetchone()
    assert row is not None
    total, traced = row
    return plain({"org_id": org_id, "total_tco2e": total, "traced_tco2e": traced,
                  "coverage_pct": None if not total else round(traced * 100 / total, 2)})
