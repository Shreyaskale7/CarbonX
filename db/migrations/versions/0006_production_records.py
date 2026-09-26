"""Production records: no double counting, and corrections keep their history.

GEI (the CCTS compliance metric) is emissions / production, so the
denominator must be as trustworthy as the numerator (council, 26 Sep 2026).
production_record had no overlap constraint: two current records for the
same basis and month would silently double the denominator and halve GEI.
It also had no way to say which record a correction replaces.

Revision ID: 0006
Revises: 0005
"""
from alembic import op

revision = "0006"
down_revision = "0005"

UPGRADE = """
ALTER TABLE production_record
    ADD COLUMN supersedes BIGINT REFERENCES production_record(production_id),
    ADD CONSTRAINT ex_production_record_current EXCLUDE USING gist (
        basis_id WITH =, period WITH &&, system_time_range WITH &&);
"""


def upgrade() -> None:
    op.get_bind().connection.dbapi_connection.execute(UPGRADE)


def downgrade() -> None:
    raise NotImplementedError("the ledger is append-only; restore from backup")
