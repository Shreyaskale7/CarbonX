# Credit lifecycle: automaton, safety properties, and how they are checked

Code: `src/carbonx/lifecycle/automaton.py` (under `mypy --strict`). Tests:
`tests/test_lifecycle.py`. This is component 10 of CLAUDE.md, a ToC
deliverable, shaped by the council ruling of 26 Sep 2026: *keep it small; make
the safety properties model-checked, not just tested.*

This is a lifecycle model, **not** trading: no order book, prices or matching
(all out of scope). Trading happens on IEX/PXIL; this models what the registry
must never allow.

## 1. The automaton

A deterministic finite automaton A = (Q, Σ, δ, q₀, F):

- Q = {NONE, ISSUED, HELD, SURRENDERED, RETIRED}
- Σ = {issue, transfer, surrender, retire}
- q₀ = NONE
- F = {SURRENDERED, RETIRED}
- δ is **partial**; any pair not listed is rejected (`IllegalTransition`):

```
NONE   --issue-->     ISSUED
ISSUED --transfer-->  HELD        HELD --transfer--> HELD
ISSUED --surrender--> SURRENDERED HELD --surrender--> SURRENDERED
ISSUED --retire-->    RETIRED     HELD --retire-->    RETIRED
```

**Language.** L(A) = `issue · transfer* · (surrender | retire)`: one issue, any
number of transfers, then exactly one terminal act.

**Proof.** Read off δ:
- the only transition out of q₀ is `issue`, to ISSUED;
- from ISSUED and HELD, `transfer` leads to HELD, and HELD loops on `transfer`;
- from ISSUED and HELD, `surrender` or `retire` leads into F;
- F has no outgoing transitions at all.

So a word reaches F exactly when it is one `issue`, then zero or more
`transfer`s, then one of `surrender` or `retire`, which is the expression
above. ∎

**Also checked by test** (`test_automaton_accepts_exactly_the_regular_language`):
A and the regular expression agree on every word over Σ up to length 7, all
21,845 of them. That is a bounded check, not a proof. Two automata this size
could first disagree on a longer word, which is why the proof above is the
argument and the test is the evidence.

## 2. The registry as a transition system

One credit is a word. A registry is many credits and organisations, and
bugs live in how they interact. A registry state is

  W = (s₁ … s_N, H₁ … H_M)

where sᵢ ∈ Q is credit i's state and H_o ⊆ {1..N} is the set of credits that
organisation o holds. Holdings are stored as *sets per organisation*, not as
one owner per credit, **so that a credit held by two organisations is
representable**. A model where double holding cannot even be written down
would make P2 true by construction, and checking it would prove nothing.

Actions, each enabled only where δ allows:

| Action | Effect |
|---|---|
| issue(i, o) | sᵢ: NONE → ISSUED, and i is added to H_o |
| transfer(i, o) | sᵢ → HELD; i is removed from its holder and added to H_o, for o not currently holding i |
| surrender(i), retire(i) | sᵢ → terminal; i is removed from every H |

## 3. Safety properties

- **P1: terminal states are absorbing.** No reachable path takes a surrendered
  or retired credit anywhere else (no re-surrender, no re-trade).
- **P2: exactly one holder while live.** A credit in ISSUED or HELD is in
  exactly one H_o; a credit in NONE, SURRENDERED or RETIRED is in none.
- **P3: conservation.** issued = |⋃ H_o| + #surrendered + #retired.

## 4. Proof for all N and M

**P1** is a property of δ alone: no pair (q, σ) with q ∈ F appears in δ, so
from a terminal state every symbol is rejected. This holds for every N and M,
because the registry only ever moves a credit along δ. The checker verifies
the premise directly and refuses to explore a δ that violates it.

**P2 is an inductive invariant.** Write I(W) for "for every i, sᵢ is live ⇔ i
belongs to exactly one H_o". Then:

- *Base.* In the initial state every sᵢ = NONE and every H_o = ∅, so I holds.
- *Step.* Each action changes exactly one credit i, and leaves every j ≠ i
  and its holdings untouched. So it suffices to check i, action by action:
  - **issue:** sᵢ was NONE, so by I it was in no H. It is now ISSUED and in
    exactly H_o.
  - **transfer:** sᵢ was live, so by I it was in exactly one H_p. The correct
    transfer removes i from H_p and adds it to H_o, where o ≠ p. It is still
    live, and in exactly one H.
  - **surrender / retire:** i becomes terminal and is removed from every H,
    so it is in none.

  In every case I holds afterwards.

**P3 follows from P2.** Under I, the live credits are exactly the elements of
⋃ H_o, and they are pairwise distinct across organisations, so |⋃ H_o| equals
the number of live credits. Every issued credit is either live or terminal,
so issued = live + terminal = |⋃ H_o| + #surrendered + #retired. ∎

### 4a. The induction step, run by machine

`prove_inductive(M)` does what the P2 step above does by hand, but for every
configuration instead of reasoning about them. It takes each single-credit
configuration (state, holders) that satisfies the invariant, reachable or not,
forms every pair of them (a two-credit registry), applies every enabled action
to either credit, and requires that (a) the invariant (P2 and P3) still holds
and (b) the *other* credit's state and holders did not change.

| M orgs | Invariant-satisfying configurations | (pair, action) cases | Failure |
|---|---|---|---|
| 1 | 5 | 50 | none |
| 2 | 7 | 196 | none |
| 3 | 9 | 486 | none |
| 4 | 11 | 968 | none |
| 5 | 13 | 1,690 | none |
| 6 | 15 | 2,700 | none |

Together with the base case (the empty registry satisfies the invariant) this
gives the invariant for every N, **given one lemma checked only by reading the
code**: an action reads and writes only the credit it names, so what holds for
a pair holds for any number. The check at two credits is the evidence for that
lemma for each M tried. Unlike section 5, it does not depend on which states a
run can reach, so it would catch an invariant that is merely *true so far*. The
same three broken transfers (copy, drop, and one that disturbs a neighbouring
credit) fail it, `test_inductive_check_rejects_the_same_mutants`.

What it still does not give: M is bounded by what we ran (the pattern in the
table is regular, and the by-hand proof covers every M, but the machine did not).
This is not a proof assistant.

## 5. Model checking: the mechanical evidence

`check(N, M)` explores the whole reachable state space breadth-first. It checks
P2 and P3 in every state, and P1 on δ. When a property fails it returns a
**shortest** counterexample (the sequence of actions that reaches the bad
state).

| N credits | M orgs | States explored | Expected (3+2M)ᴺ | Transitions | Violation |
|---|---|---|---|---|---|
| 2 | 2 | 49 | 7² = 49 | 196 | none |
| 3 | 3 | 729 | 9³ = 729 | 6,561 | none |
| 4 | 3 | 6,561 | 9⁴ = 6,561 | 78,732 | none |

**Why "expected".** With M ≥ 2 organisations, each credit can be in exactly
3 + 2M situations: unissued, surrendered, retired, or ISSUED or HELD at one of
the M organisations. So a complete exploration must visit (3+2M)ᴺ states. The
explored count matches exactly, which is evidence that the search skipped
nothing. It is asserted in the test.

**The checker is not vacuous.** A checker that never fails proves nothing, so
the tests give it deliberately broken models:

| Mutant | Found | Counterexample |
|---|---|---|
| δ gains RETIRED --transfer--> HELD | P1 | rejected before exploration |
| transfer *copies* the credit instead of moving it | P2 | `issue, transfer` (shortest) |
| transfer *drops* the credit | P2/P3 | found |

## 6. The same automaton, enforced in the database

Migration 0009 makes the database refuse what the automaton refuses, even if
the application is wrong (invariant 3).

- **δ is a table.** `credit_delta(from_state, symbol, to_state)` holds the
  seven transitions. `test_database_transition_table_equals_the_automaton`
  checks it equals `DELTA` in `automaton.py`, so the copy the proofs are about
  and the copy the database enforces cannot drift apart.
- **A credit changes only through a transition.** Inserting a
  `credit_transition` row fires a trigger that looks the move up in
  `credit_delta`, rejects it if absent, writes `from_state` and `to_state`
  itself, and updates the credit. A direct `UPDATE` or `DELETE` on `credit` is
  rejected, and transitions are append-only.
- **How P1–P3 hold there.** P1: `credit_delta` has no row leaving SURRENDERED
  or RETIRED. P2: the holder is one column, set only by the trigger, and a
  check constraint ties "has a holder" to "is ISSUED or HELD". P3 follows from
  P2, as in §4.

The three database tests pass on the local development Postgres (`scripts/dev_pg.py`, 2026-10-05). That is Postgres 18 in compatibility mode, not the target Postgres 16; CI is the authority and has not run yet.

## 7. Limits

- **The proof in §4 is by hand, with its induction step also run by machine**
  (§4a, M up to 6, N by a locality lemma read from the code). It is not
  mechanised in a proof assistant. A TLA+/TLC or Lean version would be the
  upgrade if the ToC examiner wants machine-checked proofs for all N and M.
- **The model has no quantities.** A credit is one indivisible unit. Real
  certificates are in tCO2e amounts and can be split. Splitting would add a
  "split" action and an amount-conservation property (P3 over sums, not
  counts).
- **Who may surrender, and when** (obligated entities with a shortfall, within
  a deadline) is a policy rule, not modelled here.
