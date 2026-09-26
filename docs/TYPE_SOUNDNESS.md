# Dimensional type system: rules, soundness, and where it stops

Code: `src/carbonx/units/core.py` (dimensions, units, quantities) and
`src/carbonx/units/lang.py` (the calculation language). Checked by
`tests/test_units.py`.

## 1. The claim, stated precisely

> A calculation that passes the type checker never raises a dimensional error
> when evaluated, and every bound name holds a quantity of exactly the
> dimension the checker predicted.

A common misreading is that `kWh × (tCO2e/litre)` is a dimensional error. It
is not. Multiplication is **total**: it composes any two dimensions, here into
`energy·co2e·volume⁻¹`, which is a perfectly valid if useless quantity. The
error is in *declaring* that product to be `tCO2e`. Dimensional errors arise in
exactly three places: addition, subtraction, and ascription (`let e : [tCO2e]`).
The type system is built around that.

## 2. Syntax

```
program := stmt* EOF
stmt    := 'let' IDENT ':' UNIT '=' expr
expr    := term (('+' | '-') term)*
term    := atom (('*' | '/') atom)*
atom    := NUMBER UNIT? | IDENT | '(' expr ')'
UNIT    := '[' unit ']'        unit := uatom (('*' | '/') uatom)*
                               uatom := NAME ('^' '-'? DIGITS)?
```

- **The token language is regular.** The lexer is a single regular expression
  (`lang._TOKEN`), i.e. a DFA. `unit` is regular too: it has no nesting.
- **The grammar is LL(1).** The alternatives of `atom` start with disjoint
  tokens (NUMBER, IDENT, `(`). Each `*`/`+` loop continues exactly when the
  next token is one of its operators, and those operators are not in the
  loop's FOLLOW set. `stmt` always starts with `let`, which cannot appear
  inside an `expr`, so a new `let` unambiguously ends the previous statement.
  The parser is therefore deterministic recursive descent with one token of
  lookahead and no backtracking.
- **Units are left-associative**: `kg/m3*s` means `(kg/m3)·s`. That is the usual
  ambiguity in unit notation, settled by fiat.
- **There is no unary minus, no branching and no loops.** Every program is a
  finite sequence of finite expression trees, so evaluation always terminates.
  The language is deliberately not Turing-complete.

## 3. Dimensions and units

- **Dimensions are a free abelian group.** A dimension is a vector in ℤ⁶ over
  the base dimensions `energy, mass, volume, co2e, currency, time`.
  Multiplication adds exponents, division subtracts them, and `dimensionless`
  is the zero vector.
- **CO2e is its own base dimension, not a kind of mass.** Otherwise
  `tCO2e / t` (GEI per tonne of product) would cancel to dimensionless, and
  every intensity would type-check against every other.
- **A unit is a pair (D, s):** a dimension and a positive rational scale to that
  dimension's base unit (J, kg, litre, kgCO2e, INR, s). Composition multiplies
  both parts, `(D₁, s₁)·(D₂, s₂) = (D₁+D₂, s₁s₂)`, so taking the scale is a
  group homomorphism. That is why unit conversion is **coherent**: the
  canonical value of a result does not depend on which units the inputs were
  written in.
- **Values are exact rationals (`Fraction`).** `1 [MWh] - 1000 [kWh]` is exactly
  0, not 1e-13. Decimals appear only when a result is finally rendered. This
  matters for invariant 1: reproducible reports need exact equality, not
  closeness.
- **`tCO2` is treated as `tCO2e`.** CO2 has a GWP of 1 by definition of CO2e,
  and CEA publishes its factors in tCO2.

## 4. Typing rules

Γ maps names to dimensions, and `dim(u)` is the dimension of unit `u`. The rule
names match the comments in `lang.type_of` and `lang.check`.

```
                                  x : D ∈ Γ
(T-Num)  Γ ⊢ n [u] : dim(u)       (T-Var)  ─────────
                                           Γ ⊢ x : D

         Γ ⊢ e₁ : D₁   Γ ⊢ e₂ : D₂            Γ ⊢ e₁ : D₁   Γ ⊢ e₂ : D₂
(T-Mul)  ────────────────────────   (T-Div)  ────────────────────────
         Γ ⊢ e₁ * e₂ : D₁ + D₂                Γ ⊢ e₁ / e₂ : D₁ − D₂

         Γ ⊢ e₁ : D   Γ ⊢ e₂ : D
(T-Add)  ───────────────────────   (and T-Sub for −, identically)
         Γ ⊢ e₁ + e₂ : D

         Γ ⊢ e : D    dim(u) = D    x ∉ dom(Γ)
(T-Let)  ───────────────────────────────────────
         Γ ⊢ let x : [u] = e  ⇒  Γ, x : D
```

- **Typing is syntax-directed.** Exactly one rule applies to each form, so the
  checker is a single bottom-up pass. In attribute-grammar terms, the
  dimension is a synthesised attribute.
- **Names are bound once** (`x ∉ dom(Γ)`). This is the same no-overwrite
  discipline as the ledger: a corrected value gets a new name, never an
  overwrite.

## 5. Soundness

**Evaluation.** `lang.evaluate` evaluates expressions bottom-up using
`Quantity` operations, and binds each `let` by converting to the declared unit
(`Quantity.to`). `Quantity.__add__`, `__sub__` and `to` check dimensions again
at run time, defensively. The theorem says those checks never fire.

**Environment agreement.** Write `E ⊨ Γ` when, for every `x : D` in Γ, the value
`E(x)` has dimension `D`.

**Lemma 1 (expressions).** If `Γ ⊢ e : D` and `E ⊨ Γ`, then evaluating `e` in
`E` raises no `DimensionError`, and it either produces a quantity of dimension
`D` or raises `ZeroDivisionError`.

*Proof.* By structural induction on the derivation of `Γ ⊢ e : D`.

- **T-Num.** The value is `Quantity(n, u)`, whose dimension is `dim(u) = D`.
- **T-Var.** The value is `E(x)`, and `E ⊨ Γ` gives it dimension `Γ(x) = D`.
- **T-Mul.** By induction, the operands have dimensions `D₁` and `D₂`.
  `Quantity.__mul__` performs no check and returns unit `u₁·u₂`, of dimension
  `D₁ + D₂`. `T-Div` is the same, with `D₁ − D₂`. A zero divisor raises
  `ZeroDivisionError`, which is allowed by the lemma.
- **T-Add.** By induction, both operands have dimension `D`. So the check in
  `Quantity.__add__` passes, and the result, expressed in the left operand's
  unit, has dimension `D`. `T-Sub` is identical. ∎

**Theorem (programs).** If `check(P)` returns Γ, then `evaluate(P)` either
raises `ZeroDivisionError`, or terminates with an environment `E ⊨ Γ` without
raising `DimensionError`.

*Proof.* By induction on the statements of `P`. Before the first statement, the
empty environment agrees with the empty context. For each `let x : [u] = e`,
the rule `T-Let` gives `Γ ⊢ e : D` with `D = dim(u)`. Lemma 1 then gives a
value of dimension `D`, so `Quantity.to(u)` passes its check, and the
extended environment agrees with the extended context. Termination follows
from §2. ∎

**Converse (no false alarms).** The checker is *exact*, not conservative. It
computes dimensions exactly and the language has no branching, so if `check`
raises `DimensionError`, evaluation would raise the same error at the same
node (unless a division by zero happens first). There are no false positives
to work around.

**How this is checked, beyond the proof.**
- `test_checker_agrees_with_oracle` generates 1,000 random expression trees
  with Hypothesis, about 83% of them well-typed with up to about 10
  operators.
- It compares the checker and evaluator against an independent oracle. The
  oracle has its own unit table, written from physical definitions
  (1 kWh = 3.6 MJ), and does its own exponent arithmetic.
- The test asserts three things: the checker accepts exactly the programs the
  oracle calls well-typed; accepted programs evaluate to the predicted
  dimension; and their value equals the oracle's value **exactly**.
- `mypy --strict` covers `src/carbonx/units`.

## 6. Where the guarantee stops

These escape hatches are the honest boundary of the claim. Each is a place
where a well-typed calculation can still be wrong.

1. **Substance blindness.** Dimensions record *what kind of* quantity,
   not *what stuff*. `1 [t] * 2.6 [tCO2e/t]` type-checks whether the tonne is
   coal and the factor is for coal, or the tonne is cement and the factor is
   for diesel. Matching a factor to its activity (`factor_key` against
   `activity_type`) is the engine's job in Phase 4. It is a runtime check, not
   a type guarantee.
2. **Fuel mass ↔ volume.** Converting litres of diesel to kg needs a density,
   written as a typed quantity `[kg/litre]`. The *dimension* is checked; the
   *value* is empirical and specific to the fuel and its temperature. Types
   cannot validate a density.
3. **Calorific basis.** Net and gross calorific values (NCV and GCV) are both
   `energy` and differ by several percent. An NCV-based factor applied to
   GCV-based activity data type-checks.
4. **Other greenhouse gases.** Only CO2 is identified with CO2e. `kg CH4` is
   just `mass`, so `kg CH4 × GWP [kgCO2e/kg]` type-checks, and so does the
   same GWP applied to kilograms of anything else. This is a special case of
   (1).
5. **Dimensionless quantities are all alike.** A Scope 2 share, a boiler
   efficiency and a percentage are all `[1]`, and adding them type-checks.
6. **Affine and logarithmic units** (°C, dB) are not representable, and they
   are excluded rather than approximated.
7. **Division by zero** is a runtime failure (`ZeroDivisionError`), outside the
   type system, and the theorem allows for it.
8. **The Python API is checked at run time only.** `Quantity` checks dimensions
   when an operation runs. Python's static type system (and mypy) cannot see
   dimensions, because it has no type-level integers. That is exactly why the
   calculation language exists: it is where the *static* guarantee lives.
   Engine code that wants the guarantee must go through `lang.check`.
