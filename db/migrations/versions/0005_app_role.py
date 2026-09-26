"""Run the application as a non-owner role (council finding, 26 Sep 2026).

Every invariant enforced by triggers (2, 3, and 1 via migrations 0003–0004)
was void while the app connected as the schema owner, which here is a
superuser: `SET session_replication_role = replica` turned every trigger off,
and docs/ADVERSARIAL_LOG.md attempt 12 showed reports then stop reproducing.

carbonx_app can:
  * read everything except the migration bookkeeping;
  * INSERT into ledger tables, and UPDATE only where a row may be closed
    (temporal tables) or renamed (organisation, facility). The triggers still
    decide what an UPDATE may change.
It cannot: DELETE, TRUNCATE, ALTER or DROP anything, disable triggers, set
session_replication_role, or write audit_event directly. fn_audit runs as its
owner (SECURITY DEFINER), so audit rows can only come from the trigger.

The password is a local-development default, like docker-compose.yml's.
Change it in any shared deployment. Future migrations that add tables must
GRANT to carbonx_app explicitly.

Revision ID: 0005
Revises: 0004
"""
from alembic import op

revision = "0005"
down_revision = "0004"

INSERT = ["organisation", "facility", "factor_source", "emission_factor",
          "resolution_policy", "production_basis", "production_record",
          "source_document", "extraction_result", "activity", "calculation",
          "ledger_entry", "report", "materiality_assessment", "credit",
          "credit_transition", "sampling_run", "sampling_selection"]
UPDATE = ["organisation", "facility", "emission_factor", "production_basis",
          "production_record", "activity", "calculation", "ledger_entry"]
READ = [*INSERT, "audit_event", "mv_facility_period_emissions", "mv_audit_coverage"]

UPGRADE = """
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'carbonx_app') THEN
        CREATE ROLE carbonx_app LOGIN PASSWORD 'carbonx_app'
            NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO carbonx_app', current_database());
END $$;
GRANT USAGE ON SCHEMA public TO carbonx_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO carbonx_app;
""" + f"""
GRANT SELECT ON {", ".join(READ)} TO carbonx_app;
GRANT INSERT ON {", ".join(INSERT)} TO carbonx_app;
GRANT UPDATE ON {", ".join(UPDATE)} TO carbonx_app;
""" + """
-- Audit rows come only from the trigger, which runs as the table owner.
ALTER FUNCTION fn_audit() SECURITY DEFINER SET search_path = public, pg_temp;
"""


def upgrade() -> None:
    op.get_bind().connection.dbapi_connection.execute(UPGRADE)


def downgrade() -> None:
    raise NotImplementedError("the ledger is append-only; restore from backup")
