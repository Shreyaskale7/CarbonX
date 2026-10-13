"""Audit samples drawn from a stored report, and what the verifier found.

A sample is planned once and never changed: its parameters and its seed fix
which lines were selected, so the selection can be re-derived from the report.
Each selected line then receives one result (the audited figure and a note),
recorded once. The application may set those three columns and nothing else.

The older `sampling_run` and `sampling_selection` tables in the frozen schema
were shaped for a learned ranker (risk score, rank). They are left unused.

Revision ID: 0012
Revises: 0011
"""
from alembic import op

revision = "0012"
down_revision = "0011"

UPGRADE = """
CREATE TABLE audit_sample (
    sample_id        BIGSERIAL PRIMARY KEY,
    report_id        BIGINT NOT NULL REFERENCES report(report_id),
    confidence       NUMERIC(5,4) NOT NULL CHECK (confidence > 0 AND confidence < 1),
    tolerable_pct    NUMERIC(6,3) NOT NULL CHECK (tolerable_pct > 0),
    seed             TEXT NOT NULL,           -- report hash + nonce
    population_tco2e NUMERIC(18,6) NOT NULL,
    planned_n        INT NOT NULL CHECK (planned_n > 0),
    interval_tco2e   NUMERIC(18,6),           -- NULL when every line is certain
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (report_id, seed, confidence, tolerable_pct)
);

CREATE TABLE audit_sample_item (
    item_id        BIGSERIAL PRIMARY KEY,
    sample_id      BIGINT NOT NULL REFERENCES audit_sample(sample_id),
    activity_id    BIGINT NOT NULL REFERENCES activity(activity_id),
    stratum        TEXT NOT NULL CHECK (stratum IN ('certain', 'sampled')),
    reason         TEXT NOT NULL,
    book_tco2e     NUMERIC(18,6) NOT NULL,    -- the figure in the report
    audited_tco2e  NUMERIC(18,6) CHECK (audited_tco2e >= 0),
    finding        TEXT,
    tested_at      TIMESTAMPTZ,
    UNIQUE (sample_id, activity_id)
);

CREATE FUNCTION fn_sample_item_guard() RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'audit_sample_item is append-only: DELETE rejected';
    END IF;
    IF (to_jsonb(NEW) - 'audited_tco2e' - 'finding' - 'tested_at')
           IS DISTINCT FROM (to_jsonb(OLD) - 'audited_tco2e' - 'finding' - 'tested_at')
       OR OLD.audited_tco2e IS NOT NULL
       OR NEW.audited_tco2e IS NULL OR NEW.finding IS NULL THEN
        RAISE EXCEPTION 'sample item %: a result is recorded once, with a figure and a note',
            OLD.item_id;
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER tg_sample_immutable BEFORE UPDATE OR DELETE ON audit_sample
    FOR EACH ROW EXECUTE FUNCTION fn_reject_change();
CREATE TRIGGER tg_no_truncate_audit_sample BEFORE TRUNCATE ON audit_sample
    FOR EACH STATEMENT EXECUTE FUNCTION fn_reject_change();
CREATE TRIGGER tg_sample_item_guard BEFORE UPDATE OR DELETE ON audit_sample_item
    FOR EACH ROW EXECUTE FUNCTION fn_sample_item_guard();
CREATE TRIGGER tg_no_truncate_audit_sample_item BEFORE TRUNCATE ON audit_sample_item
    FOR EACH STATEMENT EXECUTE FUNCTION fn_reject_change();
CREATE TRIGGER tg_audit_sample
    AFTER INSERT OR UPDATE OR DELETE ON audit_sample
    FOR EACH ROW EXECUTE FUNCTION fn_audit('sample_id');
CREATE TRIGGER tg_audit_sample_item
    AFTER INSERT OR UPDATE OR DELETE ON audit_sample_item
    FOR EACH ROW EXECUTE FUNCTION fn_audit('item_id');

GRANT SELECT, INSERT ON audit_sample, audit_sample_item TO carbonx_app;
GRANT UPDATE (audited_tco2e, finding, tested_at) ON audit_sample_item TO carbonx_app;
GRANT USAGE, SELECT ON SEQUENCE audit_sample_sample_id_seq, audit_sample_item_item_id_seq
    TO carbonx_app;
"""


def upgrade() -> None:
    op.get_bind().connection.dbapi_connection.execute(UPGRADE)


def downgrade() -> None:
    raise NotImplementedError("the ledger is append-only; restore from backup")
