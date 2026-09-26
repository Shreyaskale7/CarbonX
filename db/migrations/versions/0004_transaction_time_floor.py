"""Transaction time can only move forward, and history cannot be truncated.

Found hunting for invariant-1 breaks (docs/ADVERSARIAL_LOG.md, attempts 5-8).
Migration 0003 made the *default* transaction time safe, but nothing stopped a
writer supplying its own:

  * INSERT ... system_time_range = tstzrange('2020-01-01', NULL) made a row
    retroactively visible to every report AS OF a time after 2020;
  * closing a row with an upper bound in the past removed it from reports that
    had seen it (reports read activities with @>);
  * TRUNCATE bypasses row triggers, so the guards never ran;
  * renaming a resolution_policy code changed what a stored report regenerates.

The rule now enforced: a transaction's *floor* is the clock time at which it
first took the global write lock (fn_system_now). Every system time it writes,
an inserted row's start or a closed row's end, must be >= that floor. Any
report taken before this transaction took the lock has T < floor, so no write
from this transaction can change what that report sees.

Revision ID: 0004
Revises: 0003
"""
from alembic import op

revision = "0004"
down_revision = "0003"

TEMPORAL = ["emission_factor", "production_basis", "production_record",
            "activity", "ledger_entry", "calculation"]
IMMUTABLE = ["factor_source", "source_document", "report", "resolution_policy"]

UPGRADE = """
CREATE OR REPLACE FUNCTION fn_system_now() RETURNS TIMESTAMPTZ AS $$
DECLARE
    t TIMESTAMPTZ;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext('carbonx.audit_chain'));
    t := clock_timestamp();
    IF coalesce(current_setting('carbonx.tx_floor', true), '') = '' THEN
        -- Transaction-local: reset at commit or rollback.
        PERFORM set_config('carbonx.tx_floor', t::text, true);
    END IF;
    RETURN t;
END; $$ LANGUAGE plpgsql VOLATILE;

CREATE FUNCTION fn_system_floor() RETURNS TIMESTAMPTZ AS $$
BEGIN
    IF coalesce(current_setting('carbonx.tx_floor', true), '') = '' THEN
        PERFORM fn_system_now();
    END IF;
    RETURN current_setting('carbonx.tx_floor')::timestamptz;
END; $$ LANGUAGE plpgsql VOLATILE;

CREATE FUNCTION fn_insert_time_guard() RETURNS TRIGGER AS $$
BEGIN
    IF NOT upper_inf(NEW.system_time_range)
       OR lower(NEW.system_time_range) < fn_system_floor() THEN
        RAISE EXCEPTION '%: a new row must start at or after this transaction''s'
            ' time (%) and be open-ended; got %',
            TG_TABLE_NAME, fn_system_floor(), NEW.system_time_range;
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION fn_bitemporal_guard() RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION '%: DELETE rejected; close system_time_range instead',
            TG_TABLE_NAME;
    END IF;
    IF (to_jsonb(NEW) - 'system_time_range')
           IS DISTINCT FROM (to_jsonb(OLD) - 'system_time_range')
       OR NOT upper_inf(OLD.system_time_range)
       OR upper_inf(NEW.system_time_range)
       OR lower(NEW.system_time_range) IS DISTINCT FROM lower(OLD.system_time_range)
    THEN
        RAISE EXCEPTION '%: in-place UPDATE rejected; only closing a current '
            'row''s system_time_range is allowed', TG_TABLE_NAME;
    END IF;
    IF upper(NEW.system_time_range) < fn_system_floor() THEN
        RAISE EXCEPTION '%: cannot close a row in the past (% < this transaction''s'
            ' time %)', TG_TABLE_NAME, upper(NEW.system_time_range), fn_system_floor();
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql;
""" + "".join(
    f"CREATE TRIGGER tg_insert_time_{t} BEFORE INSERT ON {t}"
    f" FOR EACH ROW EXECUTE FUNCTION fn_insert_time_guard();\n" for t in TEMPORAL
) + "".join(
    f"CREATE TRIGGER tg_no_truncate_{t} BEFORE TRUNCATE ON {t}"
    f" FOR EACH STATEMENT EXECUTE FUNCTION fn_reject_change();\n"
    for t in TEMPORAL + IMMUTABLE
) + """
CREATE TRIGGER tg_resolution_policy_immutable BEFORE UPDATE OR DELETE ON resolution_policy
    FOR EACH ROW EXECUTE FUNCTION fn_reject_change();
"""


def upgrade() -> None:
    op.get_bind().connection.dbapi_connection.execute(UPGRADE)


def downgrade() -> None:
    raise NotImplementedError("the ledger is append-only; restore from backup")
