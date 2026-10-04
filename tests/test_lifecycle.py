"""Credit lifecycle automaton: the language it accepts, and model-checked
safety properties, including proof that the checker catches broken models."""
import itertools
import re

from carbonx.lifecycle.automaton import (
    DELTA,
    State,
    Symbol,
    accepts,
    check,
    correct_transfer,
)

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


def test_correct_transfer_moves_rather_than_copies():
    from carbonx.lifecycle.automaton import World
    w = World((State.ISSUED,), (frozenset({0}), frozenset()))
    assert correct_transfer(w, 0, 1) == (frozenset(), frozenset({0}))
