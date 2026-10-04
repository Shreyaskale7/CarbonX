"""Fuel combustion (Scope 1): an activity carries its calorific value.

BEE's formula (Compliance Procedure, Annexure II, equations III and IV):

    emissions = fuel quantity x NCV x emission factor x oxidation factor

NCV and the oxidation factor are measured per fuel lot, so they belong to the
activity row, versioned and audited with it. Both are NULL / 1 for
electricity. BEE's 2024-27 targets count combustion plus purchased
electricity, so without this a reported GEI covers only part of the basis.

Revision ID: 0008
Revises: 0007
"""
from alembic import op

revision = "0008"
down_revision = "0007"

UPGRADE = """
ALTER TABLE activity
    ADD COLUMN ncv NUMERIC(18,6),
    ADD COLUMN ncv_unit TEXT,                       -- e.g. 'kcal/kg', 'GJ/t'
    ADD COLUMN oxidation_factor NUMERIC(8,6) NOT NULL DEFAULT 1,
    ADD CONSTRAINT ck_activity_ncv CHECK ((ncv IS NULL) = (ncv_unit IS NULL)),
    ADD CONSTRAINT ck_activity_ncv_positive CHECK (ncv IS NULL OR ncv > 0),
    ADD CONSTRAINT ck_activity_oxidation
        CHECK (oxidation_factor > 0 AND oxidation_factor <= 1);
"""


def upgrade() -> None:
    op.get_bind().connection.dbapi_connection.execute(UPGRADE)


def downgrade() -> None:
    raise NotImplementedError("the ledger is append-only; restore from backup")
