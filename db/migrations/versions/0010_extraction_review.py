"""Extraction results: audited, and reviewable by a person.

An extraction is a model's reading of a document. The only thing that may
change afterwards is that a person confirms it (human_verified); the value the
model produced, and its confidence, never change. So the application gets
UPDATE on that one column only, and a trigger rejects any other change.

Revision ID: 0010
Revises: 0009
"""
from alembic import op

revision = "0010"
down_revision = "0009"

UPGRADE = """
CREATE FUNCTION fn_extraction_guard() RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'extraction_result is append-only: DELETE rejected';
    END IF;
    IF (to_jsonb(NEW) - 'human_verified') IS DISTINCT FROM (to_jsonb(OLD) - 'human_verified')
       OR (OLD.human_verified AND NOT NEW.human_verified) THEN
        RAISE EXCEPTION 'extraction %: only human_verified may change, and only to true',
            OLD.extraction_id;
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER tg_extraction_guard BEFORE UPDATE OR DELETE ON extraction_result
    FOR EACH ROW EXECUTE FUNCTION fn_extraction_guard();
CREATE TRIGGER tg_no_truncate_extraction_result BEFORE TRUNCATE ON extraction_result
    FOR EACH STATEMENT EXECUTE FUNCTION fn_reject_change();
CREATE TRIGGER tg_audit_extraction AFTER INSERT OR UPDATE ON extraction_result
    FOR EACH ROW EXECUTE FUNCTION fn_audit('extraction_id');

GRANT UPDATE (human_verified) ON extraction_result TO carbonx_app;
"""


def upgrade() -> None:
    op.get_bind().connection.dbapi_connection.execute(UPGRADE)


def downgrade() -> None:
    raise NotImplementedError("the ledger is append-only; restore from backup")
