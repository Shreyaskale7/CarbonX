"""Make calculation bitemporal; let an activity name the row it corrects.

calculation.superseded_by was set by an in-place UPDATE, so a report re-run
AS OF an earlier time could not tell which calculation was current then
(invariant 1). It is replaced by system_time_range plus the bitemporal guard,
like every other temporal table.

Also stores the typed calculation program itself (units/lang.py source), so
the provenance chain shows exactly what was computed.

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"

UPGRADE = """
DROP MATERIALIZED VIEW mv_audit_coverage;

ALTER TABLE calculation DROP COLUMN superseded_by;
ALTER TABLE calculation
    ADD COLUMN system_time_range TSTZRANGE NOT NULL DEFAULT tstzrange(now(), NULL),
    ADD COLUMN program TEXT NOT NULL,
    -- One current calculation per activity and policy, at any system time.
    ADD CONSTRAINT ex_calculation_current EXCLUDE USING gist (
        activity_id WITH =, policy_id WITH =, system_time_range WITH &&);

CREATE TRIGGER tg_guard_calculation BEFORE UPDATE OR DELETE ON calculation
    FOR EACH ROW EXECUTE FUNCTION fn_bitemporal_guard();

-- The activity row this one corrects: "what it was before correction".
ALTER TABLE activity ADD COLUMN supersedes BIGINT REFERENCES activity(activity_id);

CREATE MATERIALIZED VIEW mv_audit_coverage AS
-- fraction of reported tCO2e whose lineage terminates in a hashed document.
SELECT f.facility_id,
       sum(c.result_value) FILTER (WHERE d.sha256 IS NOT NULL) AS traced_tco2e,
       sum(c.result_value)                                     AS total_tco2e,
       CASE WHEN sum(c.result_value) = 0 THEN NULL
            ELSE round(100 * sum(c.result_value)
                 FILTER (WHERE d.sha256 IS NOT NULL) / sum(c.result_value), 2)
       END AS coverage_pct
FROM calculation c
JOIN activity a  ON a.activity_id = c.activity_id
JOIN facility f  ON f.facility_id = a.facility_id
LEFT JOIN source_document d ON d.document_id = a.document_id
WHERE upper_inf(c.system_time_range)
GROUP BY f.facility_id;
"""


def upgrade() -> None:
    op.get_bind().connection.dbapi_connection.execute(UPGRADE)


def downgrade() -> None:
    raise NotImplementedError("the ledger is append-only; restore from backup")
