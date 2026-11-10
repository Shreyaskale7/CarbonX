"""Notified GHG emission intensity targets, as a cited, versioned input.

BEE's procedure (pp. 4 and 22) gives an obligated entity's entitlement as
(specific GHG emission notified for the compliance cycle - specific GHG emission
achieved in the cycle) x production in the cycle. The achieved intensity is
already in every report. The notified target is not ours to know: it comes from
a Government notification, differs by entity and cycle, and may be revised.

So it is an input, like an emission factor: one row per facility and financial
year, bitemporal (superseded, never edited), audited, and read AS OF a report's
time so an old entitlement keeps the target it was computed with. A target
without a stated source is refused, and a figure we have not seen in a primary
source is stored as 'assumed', never as 'notified'.

Revision ID: 0015
Revises: 0014
"""
from alembic import op

revision = "0015"
down_revision = "0014"

UPGRADE = """
CREATE TABLE intensity_target (
    target_id        BIGSERIAL PRIMARY KEY,
    facility_id      BIGINT NOT NULL REFERENCES facility(facility_id),
    valid_time       DATERANGE NOT NULL,      -- the financial year (compliance year) it applies to
    value            NUMERIC(18,9) NOT NULL CHECK (value >= 0),
    unit             TEXT NOT NULL CHECK (unit LIKE 'tCO2e/%'),   -- per unit of (equivalent) product
    status           TEXT NOT NULL CHECK (status IN ('notified', 'assumed')),
    source_citation  TEXT NOT NULL CHECK (btrim(source_citation) <> ''),
    source_url       TEXT,
    baseline_fy      TEXT,                    -- the baseline year this target was derived from, if stated
    supersedes       BIGINT REFERENCES intensity_target(target_id),
    system_time_range TSTZRANGE NOT NULL DEFAULT tstzrange(now(), NULL),
    EXCLUDE USING gist (
        facility_id WITH =,
        valid_time WITH &&, system_time_range WITH &&
    )
);

CREATE TRIGGER tg_guard_intensity_target BEFORE UPDATE OR DELETE ON intensity_target
    FOR EACH ROW EXECUTE FUNCTION fn_bitemporal_guard();
CREATE TRIGGER tg_insert_time_intensity_target BEFORE INSERT ON intensity_target
    FOR EACH ROW EXECUTE FUNCTION fn_insert_time_guard();
CREATE TRIGGER tg_no_truncate_intensity_target BEFORE TRUNCATE ON intensity_target
    FOR EACH STATEMENT EXECUTE FUNCTION fn_reject_change();
CREATE TRIGGER tg_audit_intensity_target
    AFTER INSERT OR UPDATE OR DELETE ON intensity_target
    FOR EACH ROW EXECUTE FUNCTION fn_audit('target_id');

GRANT SELECT, INSERT, UPDATE ON intensity_target TO carbonx_app;
GRANT USAGE, SELECT ON SEQUENCE intensity_target_target_id_seq TO carbonx_app;
"""


def upgrade() -> None:
    op.get_bind().connection.dbapi_connection.execute(UPGRADE)


def downgrade() -> None:
    raise NotImplementedError("the ledger is append-only; restore from backup")
