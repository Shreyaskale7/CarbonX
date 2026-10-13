"""Reports stop holding the write lock while they build.

Until now a report took its transaction time with fn_system_now(), which takes
the global write lock and keeps it until commit. Every writer in the system
waited for the whole report to be built.

The lock is needed only for one instant. Writers stamp their rows under the
lock and hold it until they commit, so whoever holds the lock knows that every
row stamped earlier is committed. A report therefore needs the lock just long
enough to read the clock: after that moment t, every row with a stamp below t
is visible, and everything the report reads is filtered AS OF t. Rows written
while it builds are stamped later and are excluded by that filter; rows closed
while it builds still contain t. This is the same argument that makes an old
report regenerate correctly, applied to the report's own build.

fn_report_time() takes the lock at session level, reads the clock and releases
it. It deliberately does NOT set the transaction's time floor: the report
writes no bitemporal row.

Still serialised, by design: audited writes, because each appends to the one
hash chain.

Revision ID: 0014
Revises: 0013
"""
from alembic import op

revision = "0014"
down_revision = "0013"

UPGRADE = """
CREATE FUNCTION fn_report_time() RETURNS TIMESTAMPTZ AS $$
DECLARE
    t TIMESTAMPTZ;
BEGIN
    PERFORM pg_advisory_lock(hashtext('carbonx.audit_chain'));
    t := clock_timestamp();
    PERFORM pg_advisory_unlock(hashtext('carbonx.audit_chain'));
    RETURN t;
END; $$ LANGUAGE plpgsql VOLATILE;
"""


def upgrade() -> None:
    op.get_bind().connection.dbapi_connection.execute(UPGRADE)


def downgrade() -> None:
    raise NotImplementedError("the ledger is append-only; restore from backup")
