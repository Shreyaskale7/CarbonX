"""The baseline year's intensity, as a cited, versioned input.

BEE's procedure (p. 8, clause 3.4(5)): "The GHG emissions intensity shall be calculated for the
baseline year from the verified data for that year and submitted by the obligated entity." The
notified Schedule, as secondary sources describe it, gives each entity a baseline output and a
baseline intensity for FY2023-24 and its targets for the compliance years. The BEE text itself
never names the baseline year (docs/RQ3_FINDINGS.md), so the year is a stated input here, not
a built-in assumption, and every record says whether it was read from a notification or assumed.

One row per facility and baseline year, superseded and never edited, audited, and read AS OF a
report's time like every other input.

Revision ID: 0016
Revises: 0015
"""
from alembic import op

revision = "0016"
down_revision = "0015"

UPGRADE = """
CREATE TABLE baseline_record (
    baseline_id      BIGSERIAL PRIMARY KEY,
    facility_id      BIGINT NOT NULL REFERENCES facility(facility_id),
    baseline_fy      TEXT NOT NULL CHECK (baseline_fy ~ '^FY[0-9]{4}-[0-9]{2}$'),
    intensity        NUMERIC(18,9) NOT NULL CHECK (intensity >= 0),
    intensity_unit   TEXT NOT NULL CHECK (intensity_unit LIKE 'tCO2e/%'),
    output           NUMERIC(18,6) CHECK (output >= 0),         -- baseline-year production, if stated
    output_unit      TEXT,
    status           TEXT NOT NULL CHECK (status IN ('notified', 'assumed', 'verified')),
    source_citation  TEXT NOT NULL CHECK (btrim(source_citation) <> ''),
    source_url       TEXT,
    supersedes       BIGINT REFERENCES baseline_record(baseline_id),
    system_time_range TSTZRANGE NOT NULL DEFAULT tstzrange(now(), NULL),
    EXCLUDE USING gist (facility_id WITH =, baseline_fy WITH =, system_time_range WITH &&)
);

CREATE TRIGGER tg_guard_baseline_record BEFORE UPDATE OR DELETE ON baseline_record
    FOR EACH ROW EXECUTE FUNCTION fn_bitemporal_guard();
CREATE TRIGGER tg_insert_time_baseline_record BEFORE INSERT ON baseline_record
    FOR EACH ROW EXECUTE FUNCTION fn_insert_time_guard();
CREATE TRIGGER tg_no_truncate_baseline_record BEFORE TRUNCATE ON baseline_record
    FOR EACH STATEMENT EXECUTE FUNCTION fn_reject_change();
CREATE TRIGGER tg_audit_baseline_record
    AFTER INSERT OR UPDATE OR DELETE ON baseline_record
    FOR EACH ROW EXECUTE FUNCTION fn_audit('baseline_id');

GRANT SELECT, INSERT, UPDATE ON baseline_record TO carbonx_app;
GRANT USAGE, SELECT ON SEQUENCE baseline_record_baseline_id_seq TO carbonx_app;
"""


def upgrade() -> None:
    op.get_bind().connection.dbapi_connection.execute(UPGRADE)


def downgrade() -> None:
    raise NotImplementedError("the ledger is append-only; restore from backup")
