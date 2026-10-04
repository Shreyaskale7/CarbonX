"""Materiality assessments are records, like reports: append-only.

An assessment says what was concluded at a point in time. Editing one later
would rewrite that history, so UPDATE, DELETE and TRUNCATE are refused.

Revision ID: 0007
Revises: 0006
"""
from alembic import op

revision = "0007"
down_revision = "0006"

UPGRADE = """
CREATE TRIGGER tg_materiality_immutable BEFORE UPDATE OR DELETE ON materiality_assessment
    FOR EACH ROW EXECUTE FUNCTION fn_reject_change();
CREATE TRIGGER tg_no_truncate_materiality_assessment BEFORE TRUNCATE ON materiality_assessment
    FOR EACH STATEMENT EXECUTE FUNCTION fn_reject_change();
"""


def upgrade() -> None:
    op.get_bind().connection.dbapi_connection.execute(UPGRADE)


def downgrade() -> None:
    raise NotImplementedError("the ledger is append-only; restore from backup")
