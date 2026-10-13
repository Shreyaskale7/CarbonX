"""Meters: the measuring half of a monitoring plan, and where activity-data
uncertainty is allowed to come from.

A meter row says which device measures what at a facility. It may state an
uncertainty, but only together with the calibration certificate that states
it: the CHECK below refuses an uncertainty with no document. That keeps
invariant 6 (uncertainty is never invented) true for activity data too.

An activity may name the meter it was read from. It pins that meter ROW, the
way a calculation pins a factor row, so re-declaring a meter after a
recalibration does not reach readings already taken with the old one.

Revision ID: 0013
Revises: 0012
"""
from alembic import op

revision = "0013"
down_revision = "0012"

UPGRADE = """
CREATE TABLE meter (
    meter_id         BIGSERIAL PRIMARY KEY,
    facility_id      BIGINT NOT NULL REFERENCES facility(facility_id),
    meter_code       TEXT NOT NULL CHECK (btrim(meter_code) <> ''),  -- as on the device or bill
    measures         TEXT NOT NULL,          -- an activity type, e.g. grid_electricity
    -- Expanded uncertainty at about 95%, in percent of reading, as stated on
    -- the calibration certificate. NULL: none is claimed.
    uncertainty_pct  NUMERIC(6,3) CHECK (uncertainty_pct > 0 AND uncertainty_pct <= 100),
    calibration_document_id BIGINT REFERENCES source_document(document_id),
    calibrated_on    DATE,
    note             TEXT,
    supersedes       BIGINT REFERENCES meter(meter_id),
    system_time_range TSTZRANGE NOT NULL DEFAULT tstzrange(now(), NULL),
    CONSTRAINT uncertainty_needs_its_certificate
        CHECK (uncertainty_pct IS NULL OR calibration_document_id IS NOT NULL),
    EXCLUDE USING gist (
        facility_id WITH =, meter_code WITH =, system_time_range WITH &&
    )
);

ALTER TABLE activity ADD COLUMN meter_id BIGINT REFERENCES meter(meter_id);

CREATE TRIGGER tg_guard_meter BEFORE UPDATE OR DELETE ON meter
    FOR EACH ROW EXECUTE FUNCTION fn_bitemporal_guard();
CREATE TRIGGER tg_insert_time_meter BEFORE INSERT ON meter
    FOR EACH ROW EXECUTE FUNCTION fn_insert_time_guard();
CREATE TRIGGER tg_no_truncate_meter BEFORE TRUNCATE ON meter
    FOR EACH STATEMENT EXECUTE FUNCTION fn_reject_change();
CREATE TRIGGER tg_audit_meter
    AFTER INSERT OR UPDATE OR DELETE ON meter
    FOR EACH ROW EXECUTE FUNCTION fn_audit('meter_id');

GRANT SELECT, INSERT, UPDATE ON meter TO carbonx_app;
GRANT USAGE, SELECT ON SEQUENCE meter_meter_id_seq TO carbonx_app;
"""


def upgrade() -> None:
    op.get_bind().connection.dbapi_connection.execute(UPGRADE)


def downgrade() -> None:
    raise NotImplementedError("the ledger is append-only; restore from backup")
