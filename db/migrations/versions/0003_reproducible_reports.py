"""Close the holes that would let a report stop reproducing (invariant 1).

1. Commit-time race. A row's transaction time used to be taken before its
   transaction committed, with nothing ordering it against a report reading
   AS OF T. A writer could stamp t < T, commit after the report read, and
   appear on regeneration: a different hash. Now transaction time comes from
   fn_system_now(), which first takes the global lock the audit chain already
   uses (held to commit). A report takes the same lock before choosing T, so
   every row stamped before T is committed before the report reads.
2. factor_source was mutable, and published_on decides AS_OF_REPORT.
3. source_document was mutable, and reports carry its SHA-256.
4. A facility could be moved to another organisation, silently moving its
   activities between organisations' reports. (Names stay editable: reports
   carry ids, never names.)
5. report itself becomes immutable, and stores its canonical output and the
   engine version that produced it.

Revision ID: 0003
Revises: 0002
"""
from alembic import op

revision = "0003"
down_revision = "0002"

TEMPORAL = ["emission_factor", "production_basis", "production_record",
            "activity", "ledger_entry", "calculation"]

UPGRADE = """
CREATE FUNCTION fn_system_now() RETURNS TIMESTAMPTZ AS $$
BEGIN
    -- Same key as fn_audit: one serialisation domain for every write and
    -- every report. Re-entrant within a transaction; released at commit.
    -- ponytail: global lock; partition by organisation if writes contend.
    PERFORM pg_advisory_xact_lock(hashtext('carbonx.audit_chain'));
    RETURN clock_timestamp();
END; $$ LANGUAGE plpgsql VOLATILE;
""" + "".join(
    f"ALTER TABLE {t} ALTER COLUMN system_time_range"
    f" SET DEFAULT tstzrange(fn_system_now(), NULL);\n" for t in TEMPORAL
) + """
CREATE TRIGGER tg_factor_source_immutable BEFORE UPDATE OR DELETE ON factor_source
    FOR EACH ROW EXECUTE FUNCTION fn_reject_change();
CREATE TRIGGER tg_document_immutable BEFORE UPDATE OR DELETE ON source_document
    FOR EACH ROW EXECUTE FUNCTION fn_reject_change();

CREATE FUNCTION fn_facility_org_fixed() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.org_id IS DISTINCT FROM OLD.org_id THEN
        RAISE EXCEPTION 'facility % cannot move organisation: create a new facility',
            OLD.facility_id;
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER tg_facility_org_fixed BEFORE UPDATE ON facility
    FOR EACH ROW EXECUTE FUNCTION fn_facility_org_fixed();

ALTER TABLE report
    ADD COLUMN baseline_year TEXT,
    ADD COLUMN engine_version TEXT NOT NULL,
    ADD COLUMN output TEXT NOT NULL;
CREATE TRIGGER tg_report_immutable BEFORE UPDATE OR DELETE ON report
    FOR EACH ROW EXECUTE FUNCTION fn_reject_change();
"""


def upgrade() -> None:
    op.get_bind().connection.dbapi_connection.execute(UPGRADE)


def downgrade() -> None:
    raise NotImplementedError("the ledger is append-only; restore from backup")
