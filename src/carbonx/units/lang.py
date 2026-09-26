"""A small calculation language whose type checker rejects dimensional errors
before anything is evaluated. Rules and soundness argument:
docs/TYPE_SOUNDNESS.md.

    let activity : [kWh]     = 1200 [kWh]
    let factor   : [tCO2/MWh] = 0.7272 [tCO2/MWh]
    let e        : [tCO2e]    = activity * factor

Grammar (LL(1); the lexer's token language is regular):

    program := stmt* EOF
    stmt    := 'let' IDENT ':' UNIT '=' expr
    expr    := term (('+' | '-') term)*
    term    := atom (('*' | '/') atom)*
    atom    := NUMBER UNIT? | IDENT | '(' expr ')'

UNIT is a bracketed unit expression, parsed by core.parse_unit. A NUMBER with
no unit is dimensionless. Names are bound once: rebinding is an error, the
same no-overwrite rule the ledger follows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

from carbonx.units.core import (
    UNITS,
    Dimension,
    DimensionError,
    Quantity,
    Unit,
    parse_unit,
)


class LangError(ValueError):
    """Syntax error, unknown name, or rebinding. Not a dimensional error."""


@dataclass(frozen=True)
class Pos:
    line: int
    col: int

    def __str__(self) -> str:
        return f"{self.line}:{self.col}"


@dataclass(frozen=True)
class Num:
    value: Fraction
    unit: Unit
    pos: Pos


@dataclass(frozen=True)
class Var:
    name: str
    pos: Pos


@dataclass(frozen=True)
class Bin:
    op: str  # + - * /
    left: Expr
    right: Expr
    pos: Pos


Expr = Num | Var | Bin


@dataclass(frozen=True)
class Let:
    name: str
    unit: Unit
    expr: Expr
    pos: Pos


_TOKEN = re.compile(r"""
    (?P<ws>\s+|\#[^\n]*)
  | (?P<num>\d+(?:\.\d+)?)
  | (?P<unit>\[[^\]\n]*\])
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op>[-+*/():=])
""", re.VERBOSE)


@dataclass(frozen=True)
class _Tok:
    kind: str  # num unit name op let eof
    text: str
    pos: Pos


def _lex(src: str) -> list[_Tok]:
    toks, i, line, line_start = [], 0, 1, 0
    while i < len(src):
        m = _TOKEN.match(src, i)
        pos = Pos(line, i - line_start + 1)
        if not m:
            raise LangError(f"{pos}: unexpected character {src[i]!r}")
        kind = m.lastgroup
        assert kind is not None
        if kind != "ws":
            text = m[0]
            toks.append(_Tok("let" if text == "let" else kind, text, pos))
        for k in range(i, m.end()):
            if src[k] == "\n":
                line, line_start = line + 1, k + 1
        i = m.end()
    toks.append(_Tok("eof", "", Pos(line, i - line_start + 1)))
    return toks


class _Parser:
    def __init__(self, src: str) -> None:
        self.toks = _lex(src)
        self.i = 0

    @property
    def tok(self) -> _Tok:
        return self.toks[self.i]

    def take(self, kind: str, text: str | None = None) -> _Tok:
        t = self.tok
        if t.kind != kind or (text is not None and t.text != text):
            want = text or kind
            raise LangError(f"{t.pos}: expected {want!r}, got {t.text or 'end of input'!r}")
        self.i += 1
        return t

    def unit(self) -> Unit:
        t = self.take("unit")
        try:
            return parse_unit(t.text[1:-1])
        except ValueError as e:
            raise LangError(f"{t.pos}: {e}") from None

    def program(self) -> list[Let]:
        stmts = []
        while self.tok.kind != "eof":
            pos = self.take("let").pos
            name = self.take("name").text
            self.take("op", ":")
            unit = self.unit()
            self.take("op", "=")
            stmts.append(Let(name, unit, self.expr(), pos))
        return stmts

    def expr(self) -> Expr:
        e = self.term()
        while self.tok.kind == "op" and self.tok.text in "+-":
            op = self.take("op")
            e = Bin(op.text, e, self.term(), op.pos)
        return e

    def term(self) -> Expr:
        e = self.atom()
        while self.tok.kind == "op" and self.tok.text in "*/":
            op = self.take("op")
            e = Bin(op.text, e, self.atom(), op.pos)
        return e

    def atom(self) -> Expr:
        t = self.tok
        if t.kind == "num":
            self.i += 1
            unit = self.unit() if self.tok.kind == "unit" else UNITS["1"]
            return Num(Fraction(t.text), unit, t.pos)
        if t.kind == "name":
            self.i += 1
            return Var(t.text, t.pos)
        if t.kind == "op" and t.text == "(":
            self.i += 1
            e = self.expr()
            self.take("op", ")")
            return e
        raise LangError(f"{t.pos}: expected a number, name or '(', got "
                        f"{t.text or 'end of input'!r}")


def parse(src: str) -> list[Let]:
    return _Parser(src).program()


# ---- typing: Γ ⊢ e : D ----------------------------------------------------

def type_of(e: Expr, env: dict[str, Dimension]) -> Dimension:
    if isinstance(e, Num):                                   # T-Num
        return e.unit.dim
    if isinstance(e, Var):                                   # T-Var
        if e.name not in env:
            raise LangError(f"{e.pos}: {e.name!r} is not defined")
        return env[e.name]
    left, right = type_of(e.left, env), type_of(e.right, env)
    if e.op == "*":                                          # T-Mul
        return left * right
    if e.op == "/":                                          # T-Div
        return left / right
    if left != right:                                        # T-Add / T-Sub
        raise DimensionError(f"{e.pos}: cannot {'add' if e.op == '+' else 'subtract'}"
                             f" {right} {'to' if e.op == '+' else 'from'} {left}")
    return left


def check(program: list[Let]) -> dict[str, Dimension]:
    """Γ after the whole program, or DimensionError / LangError. Evaluates nothing."""
    env: dict[str, Dimension] = {}
    for s in program:
        if s.name in env:
            raise LangError(f"{s.pos}: {s.name!r} is already bound; names are bound once")
        d = type_of(s.expr, env)
        if d != s.unit.dim:                                  # T-Let
            raise DimensionError(f"{s.pos}: {s.name!r} is declared [{s.unit}] "
                                 f"({s.unit.dim}) but the expression is {d}")
        env[s.name] = d
    return env


# ---- evaluation -------------------------------------------------------------

def _eval(e: Expr, env: dict[str, Quantity]) -> Quantity:
    if isinstance(e, Num):
        return Quantity(e.value, e.unit)
    if isinstance(e, Var):
        return env[e.name]
    left, right = _eval(e.left, env), _eval(e.right, env)
    if e.op == "*":
        return left * right
    if e.op == "/":
        return left / right  # ZeroDivisionError is possible: not a type error
    return left + right if e.op == "+" else left - right


def evaluate(program: list[Let]) -> dict[str, Quantity]:
    """Assumes `check(program)` passed. Quantity still re-checks dimensions,
    defensively; the soundness theorem says those checks never fire."""
    env: dict[str, Quantity] = {}
    for s in program:
        env[s.name] = _eval(s.expr, env).to(s.unit)
    return env


def run(src: str) -> dict[str, Quantity]:
    program = parse(src)
    check(program)
    return evaluate(program)
