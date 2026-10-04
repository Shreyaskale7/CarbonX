"""Credits in the database. The rules live in the DB (migration 0009): this is
only the two statements an application needs.

A credit is created unissued. Every change after that is one credit_transition
row; the trigger checks it against the automaton, fills in the states, and
updates the credit. An illegal move raises a database error, whatever this
code does.
"""

from __future__ import annotations

from decimal import Decimal

import psycopg

from carbonx.lifecycle.automaton import State, Symbol


def create_credit(conn: psycopg.Connection, vintage_year: str,
                  quantity_tco2e: Decimal) -> int:
    row = conn.execute(
        "INSERT INTO credit (vintage_year, quantity_tco2e) VALUES (%s, %s)"
        " RETURNING credit_id", (vintage_year, quantity_tco2e)).fetchone()
    assert row is not None
    return int(row[0])


def apply(conn: psycopg.Connection, credit_id: int, symbol: Symbol,
          to_org: int | None = None) -> State:
    """Record one transition. Returns the credit's new state."""
    row = conn.execute(
        "INSERT INTO credit_transition (credit_id, symbol, to_org_id)"
        " VALUES (%s, %s, %s) RETURNING to_state", (credit_id, symbol.value, to_org)
    ).fetchone()
    assert row is not None
    return State(row[0])
