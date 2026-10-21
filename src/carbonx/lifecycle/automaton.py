"""Carbon credit lifecycle: a finite automaton, and a model checker that
proves its safety properties by exhaustive exploration. See docs/LIFECYCLE.md.

One credit's life is a word over {issue, transfer, surrender, retire}. The
automaton has five states:

    NONE --issue--> ISSUED --transfer--> HELD --transfer--> HELD
                    ISSUED | HELD --surrender--> SURRENDERED   (terminal)
                    ISSUED | HELD --retire-->    RETIRED       (terminal)

Every other (state, symbol) pair is undefined, which means rejected. The complete
lifecycles form the regular language  issue transfer* (surrender | retire).

The model checker runs a whole registry: N credits, M organisations, and
holdings recorded as a set of credits per organisation, so that a credit held
twice is *representable* and the checker can catch it. It explores every
reachable registry state breadth-first and checks:

    P1  terminal states are absorbing: nothing ever leaves SURRENDERED/RETIRED
    P2  every live credit is held by exactly one organisation; a
        surrendered, retired or unissued credit is held by none
    P3  conservation: issued = held + surrendered + retired

A violation comes back with the shortest action sequence that reaches it.

`prove_inductive` is the check for every N: it does not walk reachable states, it
takes *every* pair of single-credit configurations that satisfy the invariant
(reachable or not) and shows each action keeps it and leaves the other credit
alone. That is the induction step of the hand proof, run by machine.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from enum import StrEnum


class State(StrEnum):
    NONE = "NONE"
    ISSUED = "ISSUED"
    HELD = "HELD"
    SURRENDERED = "SURRENDERED"
    RETIRED = "RETIRED"


class Symbol(StrEnum):
    ISSUE = "issue"
    TRANSFER = "transfer"
    SURRENDER = "surrender"
    RETIRE = "retire"


Delta = dict[tuple[State, Symbol], State]

DELTA: Delta = {
    (State.NONE, Symbol.ISSUE): State.ISSUED,
    (State.ISSUED, Symbol.TRANSFER): State.HELD,
    (State.HELD, Symbol.TRANSFER): State.HELD,
    (State.ISSUED, Symbol.SURRENDER): State.SURRENDERED,
    (State.HELD, Symbol.SURRENDER): State.SURRENDERED,
    (State.ISSUED, Symbol.RETIRE): State.RETIRED,
    (State.HELD, Symbol.RETIRE): State.RETIRED,
}
TERMINAL = frozenset({State.SURRENDERED, State.RETIRED})
LIVE = frozenset({State.ISSUED, State.HELD})


class IllegalTransition(ValueError):
    pass


def step(state: State, symbol: Symbol, delta: Delta = DELTA) -> State:
    try:
        return delta[(state, symbol)]
    except KeyError:
        raise IllegalTransition(f"{symbol} is not allowed from {state}") from None


def run(word: list[Symbol], delta: Delta = DELTA) -> State:
    """The state a word leads to from NONE, or IllegalTransition."""
    state = State.NONE
    for symbol in word:
        state = step(state, symbol, delta)
    return state


def accepts(word: list[Symbol], delta: Delta = DELTA) -> bool:
    """Is this a complete lifecycle (ends surrendered or retired)?"""
    try:
        return run(word, delta) in TERMINAL
    except IllegalTransition:
        return False


# ---- the registry model -----------------------------------------------------

@dataclass(frozen=True)
class World:
    states: tuple[State, ...]                 # per credit
    holdings: tuple[frozenset[int], ...]      # per organisation: credits it holds


Action = tuple[Symbol, int, int | None]       # (symbol, credit, organisation)
Transfer = Callable[[World, int, int], tuple[frozenset[int], ...]]


def correct_transfer(w: World, credit: int, to: int) -> tuple[frozenset[int], ...]:
    """Move the credit: out of its holder, into `to`."""
    return tuple((h - {credit}) | ({credit} if org == to else set())
                 for org, h in enumerate(w.holdings))


def _successors(w: World, n_orgs: int, delta: Delta,
                transfer: Transfer) -> Iterator[tuple[Action, World]]:
    for c, s in enumerate(w.states):
        for (src, symbol), dst in delta.items():
            if src != s:
                continue
            if symbol is Symbol.ISSUE:
                for org in range(n_orgs):
                    holdings = tuple(h | {c} if o == org else h
                                     for o, h in enumerate(w.holdings))
                    yield (symbol, c, org), World(_set(w.states, c, dst), holdings)
            elif symbol is Symbol.TRANSFER:
                for org in range(n_orgs):
                    if c not in w.holdings[org]:
                        yield (symbol, c, org), World(_set(w.states, c, dst),
                                                      transfer(w, c, org))
            else:  # surrender / retire: leaves every holding
                holdings = tuple(h - {c} for h in w.holdings)
                yield (symbol, c, None), World(_set(w.states, c, dst), holdings)


def _set(states: tuple[State, ...], i: int, s: State) -> tuple[State, ...]:
    return states[:i] + (s,) + states[i + 1:]


def _violation(w: World) -> str | None:
    for c, s in enumerate(w.states):
        holders = sum(c in h for h in w.holdings)
        if s in LIVE and holders != 1:
            return f"P2: credit {c} is {s} but held by {holders} organisations"
        if s not in LIVE and holders != 0:
            return f"P2: credit {c} is {s} but still held by {holders} organisation(s)"
    issued = sum(s is not State.NONE for s in w.states)
    held = len(set().union(*w.holdings)) if w.holdings else 0
    ended = sum(s in TERMINAL for s in w.states)
    if issued != held + ended:
        return f"P3: issued {issued} != held {held} + surrendered/retired {ended}"
    return None


@dataclass(frozen=True)
class CheckResult:
    states_explored: int
    transitions: int
    violation: str | None
    counterexample: list[Action]


def check(n_credits: int, n_orgs: int, delta: Delta = DELTA,
          transfer: Transfer = correct_transfer) -> CheckResult:
    """Explore every reachable registry state. Returns the first violation
    found (breadth-first, so its counterexample is a shortest one)."""
    for src, symbol in delta:
        if src in TERMINAL:  # P1 is a property of the automaton itself
            return CheckResult(0, 0, f"P1: {src} has an outgoing '{symbol}' transition",
                               [])
    start = World((State.NONE,) * n_credits, (frozenset(),) * n_orgs)
    parent: dict[World, tuple[World, Action] | None] = {start: None}
    queue, transitions = deque([start]), 0
    while queue:
        w = queue.popleft()
        if (v := _violation(w)) is not None:
            return CheckResult(len(parent), transitions, v, _trace(parent, w))
        for action, nxt in _successors(w, n_orgs, delta, transfer):
            transitions += 1
            if nxt not in parent:
                parent[nxt] = (w, action)
                queue.append(nxt)
    return CheckResult(len(parent), transitions, None, [])


def _trace(parent: dict[World, tuple[World, Action] | None], w: World) -> list[Action]:
    actions: list[Action] = []
    while (p := parent[w]) is not None:
        w, action = p
        actions.append(action)
    return actions[::-1]


@dataclass(frozen=True)
class InductiveResult:
    configurations: int           # single-credit configurations satisfying the invariant
    steps: int                    # (pair of configurations, action) cases checked
    failure: str | None


def prove_inductive(n_orgs: int, delta: Delta = DELTA,
                    transfer: Transfer = correct_transfer) -> InductiveResult:
    """The induction step of the proof in docs/LIFECYCLE.md section 4, by machine.

    Take every pair of single-credit configurations (state, holders) that
    satisfy the invariant, whether or not a run can reach them. For every
    action on either credit, the result must satisfy the invariant, and the
    other credit must not change. With the base case (the empty registry
    satisfies it) that gives the invariant for every N, *given* the locality
    lemma that an action reads and writes only the credit it names; the check
    at N=2 confirms it for each M tried. M is still bounded by the caller.
    """
    def world(a: tuple[State, frozenset[int]], b: tuple[State, frozenset[int]]) -> World:
        return World((a[0], b[0]), tuple(
            frozenset(c for c, cfg in enumerate((a, b)) if org in cfg[1])
            for org in range(n_orgs)))

    def view(w: World, c: int) -> tuple[State, frozenset[int]]:
        return w.states[c], frozenset(o for o, h in enumerate(w.holdings) if c in h)

    orgs = range(n_orgs)
    subsets = [frozenset(o for o in orgs if m >> o & 1) for m in range(2 ** n_orgs)]
    good = [(st, h) for st in State for h in subsets
            if _violation(World((st,), tuple(frozenset({0}) if o in h else frozenset()
                                             for o in orgs))) is None]
    if _violation(World((State.NONE,), (frozenset(),) * n_orgs)) is not None:
        return InductiveResult(len(good), 0, "base case: the empty registry violates the invariant")
    steps = 0
    for a in good:
        for b in good:
            w = world(a, b)
            for action, nxt in _successors(w, n_orgs, delta, transfer):
                steps += 1
                c = action[1]
                if (v := _violation(nxt)) is not None:
                    return InductiveResult(len(good), steps, f"step {action} from {a}, {b}: {v}")
                if view(nxt, 1 - c) != view(w, 1 - c):
                    return InductiveResult(len(good), steps,
                                           f"frame: {action} changed credit {1 - c}")
    return InductiveResult(len(good), steps, None)
