"""Equivalent product: an intensity for plants that make more than one product.

BEE's procedure (p. 8, clause 3.4(4)): "where more than one product is
produced, the main product or an equivalent product worked out from the
product mix per standard practice prevalent in the obligated entity's sector
shall be considered." It gives no conversion. So the conversion is an input,
not a formula: the entity declares, per product and financial year, a factor
into the equivalent product, and the basis it claims for it. "Main product
only" is the same thing with factor 0 for the others.

Because it changes a reported intensity, a declaration is bitemporal like
every other input: superseded, never edited; audited; and read AS OF a
report's time, so an old report keeps the conversion it was made with.

Revision ID: 0011
Revises: 0010
"""
from alembic import op

revision = "0011"
down_revision = "0010"

UPGRADE = """
CREATE TABLE product_equivalence (
    equivalence_id   BIGSERIAL PRIMARY KEY,
    facility_id      BIGINT NOT NULL REFERENCES facility(facility_id),
    product_code     TEXT NOT NULL,
    valid_time       DATERANGE NOT NULL,     -- the financial year it applies to
    factor           NUMERIC(18,9) NOT NULL CHECK (factor >= 0),
    equivalent_unit  TEXT NOT NULL,          -- unit of the equivalent product
    basis            TEXT NOT NULL CHECK (btrim(basis) <> ''),  -- the practice claimed
    supersedes       BIGINT REFERENCES product_equivalence(equivalence_id),
    system_time_range TSTZRANGE NOT NULL DEFAULT tstzrange(now(), NULL),
    EXCLUDE USING gist (
        facility_id WITH =, product_code WITH =,
        valid_time WITH &&, system_time_range WITH &&
    )
);

CREATE TRIGGER tg_guard_equivalence BEFORE UPDATE OR DELETE ON product_equivalence
    FOR EACH ROW EXECUTE FUNCTION fn_bitemporal_guard();
CREATE TRIGGER tg_insert_time_product_equivalence BEFORE INSERT ON product_equivalence
    FOR EACH ROW EXECUTE FUNCTION fn_insert_time_guard();
CREATE TRIGGER tg_no_truncate_product_equivalence BEFORE TRUNCATE ON product_equivalence
    FOR EACH STATEMENT EXECUTE FUNCTION fn_reject_change();
CREATE TRIGGER tg_audit_equivalence
    AFTER INSERT OR UPDATE OR DELETE ON product_equivalence
    FOR EACH ROW EXECUTE FUNCTION fn_audit('equivalence_id');

GRANT SELECT, INSERT, UPDATE ON product_equivalence TO carbonx_app;
GRANT USAGE, SELECT ON SEQUENCE product_equivalence_equivalence_id_seq TO carbonx_app;
"""


def upgrade() -> None:
    op.get_bind().connection.dbapi_connection.execute(UPGRADE)


def downgrade() -> None:
    raise NotImplementedError("the ledger is append-only; restore from backup")
