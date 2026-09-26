"""Initial schema: applies db/schema.sql verbatim.

db/schema.sql is frozen at this revision. Never edit it; every later schema
change is a new migration.

Revision ID: 0001
"""
from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None

SCHEMA = Path(__file__).resolve().parents[2] / "schema.sql"


def upgrade() -> None:
    # Raw psycopg connection: it runs a multi-statement script (with $$ function
    # bodies) in one call, inside Alembic's transaction.
    op.get_bind().connection.dbapi_connection.execute(
        SCHEMA.read_text(encoding="utf-8")
    )


def downgrade() -> None:
    raise NotImplementedError("the ledger is append-only; restore from backup")
