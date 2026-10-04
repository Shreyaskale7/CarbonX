"""Enforce the credit lifecycle automaton in the database.

docs/LIFECYCLE.md proves the automaton safe; this makes the database refuse
anything the automaton does not allow, even if the application is wrong
(invariant 3). "Belt and braces": the same transition function, twice.

  * credit_delta holds delta: (from_state, symbol) -> to_state. It must equal
    lifecycle/automaton.py's DELTA; tests/test_lifecycle.py checks that.
  * A credit's state and holder change ONLY by inserting a credit_transition
    row. The trigger looks the move up in credit_delta, rejects it if absent,
    fills in from_state and to_state itself, and updates the credit.
  * Direct UPDATE or DELETE of a credit is rejected, and transitions are
    append-only.

P1 (terminal states absorb) holds because credit_delta has no row leaving
SURRENDERED or RETIRED. P2 (one holder) holds because the holder is a single
column, set only by the trigger. P3 (conservation) follows from P2.

Revision ID: 0009
Revises: 0008
"""
from alembic import op

revision = "0009"
down_revision = "0008"

# (from_state, symbol, to_state). Frozen here; compared with DELTA by a test.
DELTA_ROWS = [
    ("NONE", "issue", "ISSUED"),
    ("ISSUED", "transfer", "HELD"),
    ("HELD", "transfer", "HELD"),
    ("ISSUED", "surrender", "SURRENDERED"),
    ("HELD", "surrender", "SURRENDERED"),
    ("ISSUED", "retire", "RETIRED"),
    ("HELD", "retire", "RETIRED"),
]

UPGRADE = """
CREATE TABLE credit_delta (
    from_state TEXT NOT NULL,
    symbol     TEXT NOT NULL,
    to_state   TEXT NOT NULL,
    PRIMARY KEY (from_state, symbol)
);
INSERT INTO credit_delta (from_state, symbol, to_state) VALUES
""" + ",\n".join(f"    ('{a}', '{s}', '{b}')" for a, s, b in DELTA_ROWS) + """;

-- A credit starts unissued and unheld; only a transition changes that.
ALTER TABLE credit ALTER COLUMN org_id DROP NOT NULL;
ALTER TABLE credit ALTER COLUMN state SET DEFAULT 'NONE';
ALTER TABLE credit ADD CONSTRAINT ck_credit_state
    CHECK (state IN ('NONE', 'ISSUED', 'HELD', 'SURRENDERED', 'RETIRED'));
-- Held exactly when live: P2 at the level of one row.
ALTER TABLE credit ADD CONSTRAINT ck_credit_holder
    CHECK ((state IN ('ISSUED', 'HELD')) = (org_id IS NOT NULL));
ALTER TABLE credit_transition
    ADD COLUMN to_org_id BIGINT REFERENCES organisation(org_id);

CREATE FUNCTION fn_credit_transition() RETURNS TRIGGER AS $$
DECLARE
    v_state  TEXT;
    v_holder BIGINT;
    v_next   TEXT;
BEGIN
    SELECT state, org_id INTO v_state, v_holder
    FROM credit WHERE credit_id = NEW.credit_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'credit % does not exist', NEW.credit_id;
    END IF;

    SELECT to_state INTO v_next FROM credit_delta
    WHERE from_state = v_state AND symbol = NEW.symbol;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'credit %: "%" is not allowed from state %',
            NEW.credit_id, NEW.symbol, v_state;
    END IF;

    IF NEW.symbol IN ('issue', 'transfer') THEN
        IF NEW.to_org_id IS NULL THEN
            RAISE EXCEPTION 'credit %: "%" needs to_org_id', NEW.credit_id, NEW.symbol;
        END IF;
        IF NEW.symbol = 'transfer' AND NEW.to_org_id = v_holder THEN
            RAISE EXCEPTION 'credit %: already held by organisation %',
                NEW.credit_id, v_holder;
        END IF;
    ELSIF NEW.to_org_id IS NOT NULL THEN
        RAISE EXCEPTION 'credit %: "%" takes no to_org_id', NEW.credit_id, NEW.symbol;
    END IF;

    -- The database, not the caller, records what the move was.
    NEW.from_state := v_state;
    NEW.to_state := v_next;
    UPDATE credit SET state = v_next, org_id = NEW.to_org_id
    WHERE credit_id = NEW.credit_id;
    RETURN NEW;
END; $$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp;

CREATE TRIGGER tg_credit_transition BEFORE INSERT ON credit_transition
    FOR EACH ROW EXECUTE FUNCTION fn_credit_transition();

-- A credit changes only from inside the transition trigger (depth 2), never
-- by a direct statement (depth 1).
CREATE FUNCTION fn_credit_guard() RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.state <> 'NONE' OR NEW.org_id IS NOT NULL THEN
            RAISE EXCEPTION 'a credit is created unissued; use an "issue" transition';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' OR pg_trigger_depth() < 2 THEN
        RAISE EXCEPTION 'credit %: % rejected; record a credit_transition instead',
            OLD.credit_id, TG_OP;
    END IF;
    IF NEW.credit_id <> OLD.credit_id OR NEW.quantity_tco2e <> OLD.quantity_tco2e
       OR NEW.vintage_year <> OLD.vintage_year THEN
        RAISE EXCEPTION 'credit %: only state and holder may change', OLD.credit_id;
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER tg_credit_guard BEFORE INSERT OR UPDATE OR DELETE ON credit
    FOR EACH ROW EXECUTE FUNCTION fn_credit_guard();
CREATE TRIGGER tg_credit_transition_append_only BEFORE UPDATE OR DELETE ON credit_transition
    FOR EACH ROW EXECUTE FUNCTION fn_reject_change();
CREATE TRIGGER tg_credit_delta_immutable BEFORE INSERT OR UPDATE OR DELETE ON credit_delta
    FOR EACH ROW EXECUTE FUNCTION fn_reject_change();
CREATE TRIGGER tg_no_truncate_credit BEFORE TRUNCATE ON credit
    FOR EACH STATEMENT EXECUTE FUNCTION fn_reject_change();
CREATE TRIGGER tg_no_truncate_credit_transition BEFORE TRUNCATE ON credit_transition
    FOR EACH STATEMENT EXECUTE FUNCTION fn_reject_change();
CREATE TRIGGER tg_no_truncate_credit_delta BEFORE TRUNCATE ON credit_delta
    FOR EACH STATEMENT EXECUTE FUNCTION fn_reject_change();

CREATE TRIGGER tg_audit_credit AFTER INSERT OR UPDATE ON credit
    FOR EACH ROW EXECUTE FUNCTION fn_audit('credit_id');
CREATE TRIGGER tg_audit_credit_transition AFTER INSERT ON credit_transition
    FOR EACH ROW EXECUTE FUNCTION fn_audit('transition_id');

-- The app records transitions and reads; the trigger (as owner) updates credits.
GRANT SELECT ON credit_delta TO carbonx_app;
"""


def upgrade() -> None:
    op.get_bind().connection.dbapi_connection.execute(UPGRADE)


def downgrade() -> None:
    raise NotImplementedError("the ledger is append-only; restore from backup")
