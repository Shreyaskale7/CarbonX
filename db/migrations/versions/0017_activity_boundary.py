"""Which activities lie inside the gate-to-gate boundary.

CCTS intensity targets are gate-to-gate (BEE p. 4; docs/RQ3_FINDINGS.md): only emissions from sources
inside the notified unit's boundary count. An activity such as electricity for a staff colony outside
the gate is real but does not belong in the unit's intensity. Whether an activity is inside is a
judgement the entity makes and a verifier checks, so it is recorded, with its basis, not inferred.

A side table, not a column on `activity`: activity rows cannot be edited in place, and changing the
report code to read a new column would change ENGINE_VERSION and stop every stored report from
regenerating. A tag is versioned (superseded, never edited), audited, and read AS OF a report's own
time. An activity with no tag is "untagged", never defaulted to inside.

Revision ID: 0017
Revises: 0016
"""
from alembic import op

revision = "0017"
down_revision = "0016"

UPGRADE = """
CREATE TABLE activity_boundary (
    tag_id           BIGSERIAL PRIMARY KEY,
    activity_id      BIGINT NOT NULL REFERENCES activity(activity_id),
    boundary         TEXT NOT NULL CHECK (boundary IN ('inside', 'outside')),
    basis            TEXT NOT NULL CHECK (btrim(basis) <> ''),   -- why: a verifier must be able to check it
    supersedes       BIGINT REFERENCES activity_boundary(tag_id),
    system_time_range TSTZRANGE NOT NULL DEFAULT tstzrange(now(), NULL),
    EXCLUDE USING gist (activity_id WITH =, system_time_range WITH &&)
);

CREATE TRIGGER tg_guard_activity_boundary BEFORE UPDATE OR DELETE ON activity_boundary
    FOR EACH ROW EXECUTE FUNCTION fn_bitemporal_guard();
CREATE TRIGGER tg_insert_time_activity_boundary BEFORE INSERT ON activity_boundary
    FOR EACH ROW EXECUTE FUNCTION fn_insert_time_guard();
CREATE TRIGGER tg_no_truncate_activity_boundary BEFORE TRUNCATE ON activity_boundary
    FOR EACH STATEMENT EXECUTE FUNCTION fn_reject_change();
CREATE TRIGGER tg_audit_activity_boundary
    AFTER INSERT OR UPDATE OR DELETE ON activity_boundary
    FOR EACH ROW EXECUTE FUNCTION fn_audit('tag_id');

GRANT SELECT, INSERT, UPDATE ON activity_boundary TO carbonx_app;
GRANT USAGE, SELECT ON SEQUENCE activity_boundary_tag_id_seq TO carbonx_app;
"""


def upgrade() -> None:
    op.get_bind().connection.dbapi_connection.execute(UPGRADE)


def downgrade() -> None:
    raise NotImplementedError("the ledger is append-only; restore from backup")
