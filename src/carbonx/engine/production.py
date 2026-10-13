"""Production: the GEI denominator, versioned like everything else.

GEI = emissions / product output. A production basis says what is counted
(facility, product, unit, allocation rule) for one financial year; production
records carry the quantities. Both are bitemporal, and a correction closes the
old record and inserts a new one that `supersedes` it, exactly like activity.

Plants with more than one product: BEE's procedure says "the main product or
an equivalent product worked out from the product mix per standard practice
prevalent in the obligated entity's sector" and gives no conversion. So the
conversion is declared, not built in: `set_equivalence` records a factor into
the equivalent product for one product and year, with the basis claimed for
it. Declarations are bitemporal too. A plant with several products and an
incomplete set of declarations gets no GEI, and the report says which is
missing.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import psycopg

from carbonx.engine.calculate import fy_of, set_audit_context, system_now
from carbonx.factors.registry import fy_start
from carbonx.units.core import parse_unit

ALLOCATION_RULES = {"none", "mass", "economic"}


def _basis(conn: psycopg.Connection, facility_id: int, product_code: str, unit: str,
           allocation_rule: str, fy: str, t: datetime) -> int:
    """The current basis for this facility, product and FY, created if absent."""
    start = fy_start(fy)
    row = conn.execute(
        "SELECT basis_id, unit, allocation_rule FROM production_basis"
        " WHERE facility_id = %s AND product_code = %s AND valid_time @> %s::date"
        " AND upper_inf(system_time_range)", (facility_id, product_code, start)).fetchone()
    if row:
        if (row[1], row[2]) != (unit, allocation_rule):
            raise ValueError(
                f"{product_code} for {fy} is counted in {row[1]} ({row[2]} allocation); "
                f"changing the basis is a boundary change, not a data entry")
        return int(row[0])
    new = conn.execute(
        "INSERT INTO production_basis (facility_id, product_code, unit, allocation_rule,"
        " valid_time, system_time_range)"
        " VALUES (%s, %s, %s, %s, daterange(%s, %s), tstzrange(%s, NULL))"
        " RETURNING basis_id",
        (facility_id, product_code, unit, allocation_rule, start,
         date(start.year + 1, 4, 1), t)).fetchone()
    assert new is not None
    return int(new[0])


def record_production(
    conn: psycopg.Connection, *, facility_id: int, product_code: str, unit: str,
    period_start: date, period_end: date, quantity: Decimal,
    allocation_rule: str = "none", document_id: int | None = None,
    actor: str | None = None, reason: str | None = None,
    supersedes: int | None = None, t: datetime | None = None,
) -> int:
    """Insert a production record. `period_end` is exclusive."""
    if quantity < 0:
        raise ValueError("quantity must be >= 0")
    if allocation_rule not in ALLOCATION_RULES:
        raise ValueError(f"allocation_rule must be one of {sorted(ALLOCATION_RULES)}")
    if period_end <= period_start:
        raise ValueError("period_end must be after period_start (it is exclusive)")
    if fy_of(period_start) != fy_of(period_end - timedelta(days=1)):
        raise ValueError("a production period must lie within one financial year")
    parse_unit(unit)  # unknown units fail here, not inside a report
    with conn.transaction():
        set_audit_context(conn, actor, reason)
        t = t or system_now(conn)
        basis_id = _basis(conn, facility_id, product_code, unit, allocation_rule,
                          fy_of(period_start), t)
        row = conn.execute(
            "INSERT INTO production_record (basis_id, period, quantity, unit, document_id,"
            " supersedes, system_time_range)"
            " VALUES (%s, daterange(%s, %s), %s, %s, %s, %s, tstzrange(%s, NULL))"
            " RETURNING production_id",
            (basis_id, period_start, period_end, quantity, unit, document_id,
             supersedes, t)).fetchone()
    assert row is not None
    return int(row[0])


def set_equivalence(conn: psycopg.Connection, *, facility_id: int, product_code: str,
                    fy: str, factor: Decimal, equivalent_unit: str, basis: str,
                    actor: str | None = None, reason: str | None = None) -> int:
    """Declare how one product converts into the equivalent product for a
    financial year: quantity x factor, in `equivalent_unit`. Factor 0 leaves a
    product out (the "main product" reading). A new declaration supersedes the
    current one; reports made earlier keep the one they read."""
    if factor < 0:
        raise ValueError("factor must be >= 0")
    if not basis.strip():
        raise ValueError("state the basis for the conversion: BEE leaves it to sector "
                         "practice, so a verifier must be able to see which one")
    parse_unit(equivalent_unit)
    start = fy_start(fy)
    with conn.transaction():
        set_audit_context(conn, actor, reason or basis)
        t = system_now(conn)
        old = conn.execute(
            "SELECT equivalence_id FROM product_equivalence WHERE facility_id = %s"
            " AND product_code = %s AND valid_time @> %s::date"
            " AND upper_inf(system_time_range) FOR UPDATE",
            (facility_id, product_code, start)).fetchone()
        if old:
            conn.execute("UPDATE product_equivalence SET system_time_range ="
                         " tstzrange(lower(system_time_range), %s)"
                         " WHERE equivalence_id = %s", (t, old[0]))
        row = conn.execute(
            "INSERT INTO product_equivalence (facility_id, product_code, valid_time,"
            " factor, equivalent_unit, basis, supersedes, system_time_range)"
            " VALUES (%s, %s, daterange(%s, %s), %s, %s, %s, %s, tstzrange(%s, NULL))"
            " RETURNING equivalence_id",
            (facility_id, product_code, start, date(start.year + 1, 4, 1), factor,
             equivalent_unit, basis.strip(), old[0] if old else None, t)).fetchone()
    assert row is not None
    return int(row[0])


def edit_production(conn: psycopg.Connection, production_id: int, *, quantity: Decimal,
                    reason: str, actor: str | None = None) -> int:
    """Correct a production quantity. The old record stays retrievable AS OF
    any earlier time. Returns the new production_id."""
    if not reason.strip():
        raise ValueError("a correction needs a reason; it goes in the audit trail")
    with conn.transaction():
        set_audit_context(conn, actor, reason)
        t = system_now(conn)
        old = conn.execute(
            "SELECT pb.facility_id, pb.product_code, pr.unit, pb.allocation_rule,"
            " lower(pr.period), upper(pr.period), pr.document_id"
            " FROM production_record pr JOIN production_basis pb USING (basis_id)"
            " WHERE pr.production_id = %s AND upper_inf(pr.system_time_range)"
            " FOR UPDATE OF pr", (production_id,)).fetchone()
        if old is None:
            raise LookupError(f"production record {production_id} does not exist "
                              "or was superseded")
        conn.execute("UPDATE production_record SET system_time_range ="
                     " tstzrange(lower(system_time_range), %s) WHERE production_id = %s",
                     (t, production_id))
        facility_id, product_code, unit, rule, start, end, document_id = old
        return record_production(
            conn, facility_id=facility_id, product_code=product_code, unit=unit,
            period_start=start, period_end=end, quantity=quantity,
            allocation_rule=rule, document_id=document_id, actor=actor,
            reason=reason, supersedes=production_id, t=t)
