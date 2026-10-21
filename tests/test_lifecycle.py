"""Credit lifecycle automaton: the language it accepts, and model-checked
safety properties, including proof that the checker catches broken models."""
import itertools
import re
from decimal import Decimal

import psycopg
import pytest

from carbonx.lifecycle.automaton import (
    DELTA,
    State,
    Symbol,
    accepts,
    check,
    correct_transfer,
    prove_inductive,
)
from carbonx.lifecycle.registry import apply, create_credit

LIFECYCLE = re.compile(r"i t* (s|r)".replace(" ", ""))  # issue transfer* (surrender|retire)
LETTER = {Symbol.ISSUE: "i", Symbol.TRANSFER: "t", Symbol.SURRENDER: "s", Symbol.RETIRE: "r"}


def test_automaton_accepts_exactly_the_regular_language():
    """Checked on every word over the 4-letter alphabet up to length 7
    (21,845 words): the DFA and the regular expression agree on all of them."""
    n = 0
    for length in range(8):
        for word in itertools.product(Symbol, repeat=length):
            as_text = "".join(LETTER[s] for s in word)
            assert accepts(list(word)) == bool(LIFECYCLE.fullmatch(as_text)), as_text
            n += 1
    assert n == sum(4 ** k for k in range(8))


def test_safety_properties_hold_on_every_reachable_state():
    """With M >= 2 organisations each credit has exactly 3 + 2M situations
    (unissued, surrendered, retired, or ISSUED/HELD at one of M organisations),
    so a complete exploration visits (3 + 2M)^N registry states. Matching that
    count exactly shows nothing was skipped."""
    for n, m in [(2, 2), (3, 3), (4, 3)]:
        r = check(n_credits=n, n_orgs=m)
        assert r.violation is None
        assert r.states_explored == (3 + 2 * m) ** n


def test_checker_catches_a_retired_credit_being_traded():
    """P1 mutant: a retired credit that can be transferred again."""
    broken = DELTA | {(State.RETIRED, Symbol.TRANSFER): State.HELD}
    r = check(2, 2, delta=broken)
    assert r.violation is not None and r.violation.startswith("P1")


def test_checker_catches_double_holding_with_a_shortest_trace():
    """P2 mutant: transfer copies the credit instead of moving it."""
    def copy_transfer(w, credit, to):
        return tuple(h | {credit} if org == to else h for org, h in enumerate(w.holdings))

    r = check(2, 2, transfer=copy_transfer)
    assert r.violation is not None and r.violation.startswith("P2")
    assert [a[0] for a in r.counterexample] == [Symbol.ISSUE, Symbol.TRANSFER]


def test_checker_catches_a_lost_credit():
    """Mutant: a transfer that drops the credit instead of moving it. In this
    representation P3 (conservation) follows from P2 (one holder per live
    credit), so the loss is reported as whichever it trips first."""
    def lossy_transfer(w, credit, to):
        return tuple(h - {credit} for h in w.holdings)

    r = check(1, 2, transfer=lossy_transfer)
    assert r.violation is not None and r.violation.startswith(("P2", "P3"))


def test_invariant_is_inductive_from_every_configuration_not_only_reachable_ones():
    """The step for every N: every pair of invariant-satisfying configurations,
    every action, invariant kept and the other credit untouched."""
    for m in range(1, 6):
        r = prove_inductive(m)
        assert r.failure is None and r.steps > 0
    assert prove_inductive(2).configurations == 1 + 2 + 2 + 1 + 1   # NONE, ISSUED x2, HELD x2, 2 terminal


def test_inductive_check_rejects_the_same_mutants():
    def copy_transfer(w, credit, to):
        return tuple(h | {credit} if org == to else h for org, h in enumerate(w.holdings))

    def lossy_transfer(w, credit, to):
        return tuple(h - {credit} for h in w.holdings)

    def leaky_retire(w, credit, to):               # also disturbs a neighbouring credit
        return tuple(h | {1 - credit} if org == to else h for org, h in enumerate(w.holdings))

    for bad in (copy_transfer, lossy_transfer, leaky_retire):
        assert prove_inductive(2, transfer=bad).failure is not None, bad.__name__


def test_correct_transfer_moves_rather_than_copies():
    from carbonx.lifecycle.automaton import World
    w = World((State.ISSUED,), (frozenset({0}), frozenset()))
    assert correct_transfer(w, 0, 1) == (frozenset(), frozenset({0}))


# ---- the database enforces the same automaton (migration 0009) --------------

def _migration_delta():
    import importlib.util
    from pathlib import Path
    path = (Path(__file__).resolve().parents[1] / "db" / "migrations" / "versions"
            / "0009_credit_lifecycle.py")
    spec = importlib.util.spec_from_file_location("m0009", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.DELTA_ROWS


def test_database_transition_table_equals_the_automaton():
    """Two copies of delta must never drift: the proofs are about one, the
    database enforces the other."""
    in_db = {(State(a), Symbol(s)): State(b) for a, s, b in _migration_delta()}
    assert in_db == DELTA


@pytest.fixture
def orgs(conn):
    ids = [conn.execute("INSERT INTO organisation (name) VALUES (%s) RETURNING org_id",
                        (f"holder {i}",)).fetchone()[0] for i in range(2)]
    return ids


def _rejected(conn, fn):
    conn.execute("SAVEPOINT s")
    with pytest.raises(psycopg.errors.RaiseException):
        fn()
    conn.execute("ROLLBACK TO SAVEPOINT s")


def test_database_walks_a_legal_lifecycle(conn, orgs):
    a, b = orgs
    c = create_credit(conn, "FY2025-26", Decimal(100))
    assert apply(conn, c, Symbol.ISSUE, a) is State.ISSUED
    assert apply(conn, c, Symbol.TRANSFER, b) is State.HELD
    assert apply(conn, c, Symbol.SURRENDER) is State.SURRENDERED
    assert conn.execute("SELECT state, org_id FROM credit WHERE credit_id = %s",
                        (c,)).fetchone() == ("SURRENDERED", None)
    history = conn.execute("SELECT from_state, symbol, to_state FROM credit_transition"
                           " WHERE credit_id = %s ORDER BY transition_id", (c,)).fetchall()
    assert history == [("NONE", "issue", "ISSUED"), ("ISSUED", "transfer", "HELD"),
                       ("HELD", "surrender", "SURRENDERED")]


def test_database_rejects_what_the_automaton_rejects(conn, orgs):
    a, b = orgs
    c = create_credit(conn, "FY2025-26", Decimal(100))
    _rejected(conn, lambda: apply(conn, c, Symbol.TRANSFER, a))    # not issued yet
    apply(conn, c, Symbol.ISSUE, a)
    _rejected(conn, lambda: apply(conn, c, Symbol.ISSUE, b))       # issued twice
    _rejected(conn, lambda: apply(conn, c, Symbol.TRANSFER, a))    # to its own holder
    _rejected(conn, lambda: apply(conn, c, Symbol.TRANSFER))       # to nobody
    apply(conn, c, Symbol.RETIRE)
    for symbol in Symbol:                                          # P1: terminal absorbs
        _rejected(conn, lambda s=symbol: apply(
            conn, c, s, b if s in (Symbol.ISSUE, Symbol.TRANSFER) else None))


def test_a_credit_cannot_be_changed_except_by_a_transition(owner_conn):
    """Even the owner's direct UPDATE is refused, by trigger."""
    conn = owner_conn
    (org,) = conn.execute("INSERT INTO organisation (name) VALUES ('h')"
                          " RETURNING org_id").fetchone()
    c = create_credit(conn, "FY2025-26", Decimal(100))
    apply(conn, c, Symbol.ISSUE, org)
    _rejected(conn, lambda: conn.execute(
        "UPDATE credit SET state = 'RETIRED', org_id = NULL WHERE credit_id = %s", (c,)))
    _rejected(conn, lambda: conn.execute("DELETE FROM credit WHERE credit_id = %s", (c,)))
    _rejected(conn, lambda: conn.execute(
        "INSERT INTO credit (vintage_year, quantity_tco2e, state, org_id)"
        " VALUES ('FY2025-26', 1, 'HELD', %s)", (org,)))           # born already held
    _rejected(conn, lambda: conn.execute("UPDATE credit_transition SET symbol = 'retire'"))
