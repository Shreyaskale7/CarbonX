"""Audit sampling by size: which lines of a report should a verifier test?

The method is monetary-unit sampling from financial audit, with tonnes of CO2e
in place of money. Every tonne has the same chance of being picked, so a line
is picked in proportion to its size, and what is found in the sample can be
projected to the whole report with a stated confidence.

    1. Size.      n = population x factor(confidence) / tolerable misstatement
    2. Certain.   Lines at least one interval large, and lines with no source
                  document, are always tested. They are not sampled.
    3. Sample.    The rest, systematically: one hit every `interval` tonnes,
                  from a start fixed by the seed.
    4. Evaluate.  Once tested: projected misstatement and a Stringer upper
                  limit, compared with the tolerable misstatement.

Everything is exact arithmetic, and the selection depends only on the report
and the seed, so anyone holding both can re-derive it. Method, sources and
limits: docs/SAMPLING.md.

This is arithmetic for a verifier to use. It reaches no conclusion about a
report; that is the accredited verifier's judgement.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from math import ceil, exp
from typing import Any

import psycopg

from carbonx.engine.calculate import set_audit_context


def confidence_factor(confidence: float, errors: int = 0) -> float:
    """The Poisson mean L with P(X <= errors | L) = 1 - confidence: the largest
    error rate (in errors per sample) still consistent with seeing `errors`.
    For 95% and no errors this is 3.00, the familiar audit table value."""
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between 0 and 1")

    def cdf(mean: float) -> float:
        term = total = exp(-mean)
        for k in range(1, errors + 1):
            term *= mean / k
            total += term
        return total

    lo, hi = 0.0, 10.0 + 10.0 * errors
    for _ in range(80):   # bisection: cdf falls as the mean rises
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if cdf(mid) > 1 - confidence else (lo, mid)
    return (lo + hi) / 2


def sample_size(population: Fraction, tolerable: Fraction, confidence: float) -> int:
    """Hits needed so that finding no error supports "misstatement is below
    `tolerable`" at `confidence`."""
    if tolerable <= 0:
        raise ValueError("tolerable misstatement must be positive")
    return max(1, ceil(population * Fraction(confidence_factor(confidence)) / tolerable))


def _start(seed: str) -> Fraction:
    """A fraction in [0, 1) fixed by the seed: no hidden random state."""
    return Fraction(int(hashlib.sha256(seed.encode()).hexdigest(), 16) % 10**9, 10**9)


@dataclass(frozen=True)
class Item:
    key: int            # activity_id
    value: Fraction     # tCO2e as reported
    certain_because: str | None = None   # a fact that puts it in the 100% stratum


@dataclass(frozen=True)
class Selection:
    planned_n: int
    interval: Fraction | None            # None when every line ended up certain
    certain: tuple[tuple[int, str], ...]   # (key, reason)
    sampled: tuple[int, ...]


def select(items: list[Item], planned_n: int, seed: str) -> Selection:
    """Deterministic. Items are taken in key order; a zero-size line cannot be
    hit, and is tested only if a fact makes it certain."""
    items = sorted(items, key=lambda i: i.key)
    certain = {i.key: i.certain_because for i in items if i.certain_because}
    while True:   # a line as large as the interval would be hit for sure: test it outright
        rest = [i for i in items if i.key not in certain]
        hits = planned_n - len(certain)
        total = sum((i.value for i in rest), Fraction(0))
        if hits <= 0 or total == 0:
            return Selection(planned_n, None, tuple(sorted(certain.items())), ())
        interval = total / hits
        big = [i for i in rest if i.value >= interval]
        if not big:
            break
        certain |= {i.key: "at least one sampling interval in size" for i in big}
    point, running, sampled = _start(seed) * interval, Fraction(0), []
    for item in rest:
        running += item.value
        if point < running:           # each line is smaller than the interval: one hit at most
            sampled.append(item.key)
            point += interval
    return Selection(planned_n, interval, tuple(sorted(certain.items())), tuple(sampled))


@dataclass(frozen=True)
class Evaluation:
    tested: int
    selected: int
    known: Fraction            # net misstatement found in the certain stratum (book - audited)
    projected: Fraction        # known + interval x sum of sampled taints
    upper_over: Fraction       # Stringer upper limit on overstatement
    upper_under: Fraction      # the same construction applied to understatements
    tolerable: Fraction

    @property
    def complete(self) -> bool:
        return self.tested == self.selected

    @property
    def within(self) -> bool:
        return (self.complete and self.upper_over <= self.tolerable
                and self.upper_under <= self.tolerable)


def evaluate(results: list[tuple[str, Fraction, Fraction | None]], interval: Fraction | None,
             confidence: float, tolerable: Fraction) -> Evaluation:
    """`results`: (stratum, book, audited or None if not tested yet).

    A sampled line's taint is (book - audited) / book. The Stringer bound adds,
    to the no-error allowance, each taint weighted by how much one more error
    raises the Poisson factor, largest taint first. It is conservative.
    """
    tested = [(s, b, a) for s, b, a in results if a is not None]
    known = sum((b - a for s, b, a in tested if s == "certain"), Fraction(0))
    taints = [(b - a) / b for s, b, a in tested if s == "sampled" and b]
    step = interval or Fraction(0)
    known_over = sum((max(b - a, Fraction(0)) for s, b, a in tested if s == "certain"),
                     Fraction(0))
    known_under = sum((max(a - b, Fraction(0)) for s, b, a in tested if s == "certain"),
                      Fraction(0))

    def stringer(ts: list[Fraction]) -> Fraction:
        ts = sorted((min(t, Fraction(1)) for t in ts if t > 0), reverse=True)
        bound = Fraction(confidence_factor(confidence, 0))
        for k, t in enumerate(ts, start=1):
            bound += Fraction(confidence_factor(confidence, k)
                              - confidence_factor(confidence, k - 1)) * t
        return bound * step

    return Evaluation(
        tested=len(tested), selected=len(results), known=known,
        projected=known + step * sum(taints, Fraction(0)),
        upper_over=known_over + stringer(taints),
        upper_under=known_under + stringer([-t for t in taints]),
        tolerable=tolerable)


# ---- on a stored report ------------------------------------------------------

def population(conn: psycopg.Connection, report_id: int) -> tuple[list[Item], str]:
    """The report's own lines, and its hash. A line with no source document is
    a certain item: an untraced figure is looked at, not sampled."""
    row = conn.execute("SELECT output, output_sha256 FROM report WHERE report_id = %s",
                       (report_id,)).fetchone()
    if row is None:
        raise LookupError(f"no report {report_id}")
    lines = json.loads(row[0])["lines"]
    return [Item(ln["activity_id"], Fraction(ln["tco2e"]),
                 None if ln["document_sha256"] else "no source document")
            for ln in lines], row[1]


def draw(conn: psycopg.Connection, report_id: int, *, confidence: Decimal = Decimal("0.95"),
         tolerable_pct: Decimal = Decimal(5), nonce: str = "1",
         actor: str | None = None) -> int:
    """Plan and store a sample for a report. The seed is the report's hash plus
    a nonce, so the selection can be re-derived from the report alone."""
    items, sha = population(conn, report_id)
    total = sum((i.value for i in items), Fraction(0))
    if total <= 0:
        raise ValueError("the report has no emissions to sample")
    tolerable = total * Fraction(tolerable_pct) / 100
    n = sample_size(total, tolerable, float(confidence))
    seed = f"{sha}:{nonce}"
    chosen = select(items, n, seed)
    book = {i.key: i.value for i in items}

    def money(x: Fraction) -> Decimal:
        return Decimal(round(x * 10**6)).scaleb(-6)

    with conn.transaction():
        set_audit_context(conn, actor, f"audit sample of report {report_id}")
        row = conn.execute(
            "INSERT INTO audit_sample (report_id, confidence, tolerable_pct, seed,"
            " population_tco2e, planned_n, interval_tco2e)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING sample_id",
            (report_id, confidence, tolerable_pct, seed, money(total), n,
             None if chosen.interval is None else money(chosen.interval))).fetchone()
        assert row is not None
        rows = ([(row[0], k, "certain", why, money(book[k])) for k, why in chosen.certain]
                + [(row[0], k, "sampled", "hit by the sampling interval", money(book[k]))
                   for k in chosen.sampled])
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO audit_sample_item (sample_id, activity_id, stratum, reason,"
                " book_tco2e) VALUES (%s, %s, %s, %s, %s)", rows)
    return int(row[0])


def record_result(conn: psycopg.Connection, item_id: int, audited_tco2e: Decimal,
                  finding: str, actor: str | None = None) -> None:
    """What the verifier found for one selected line. Recorded once."""
    if audited_tco2e < 0:
        raise ValueError("audited value must be >= 0")
    if not finding.strip():
        raise ValueError("say what was checked, even when the figure stands")
    with conn.transaction():
        set_audit_context(conn, actor, finding)
        done = conn.execute(
            "UPDATE audit_sample_item SET audited_tco2e = %s, finding = %s, tested_at = now()"
            " WHERE item_id = %s AND audited_tco2e IS NULL RETURNING item_id",
            (audited_tco2e, finding.strip(), item_id)).fetchone()
    if done is None:
        raise LookupError(f"item {item_id} does not exist or already has a result")


def summary(conn: psycopg.Connection, sample_id: int) -> dict[str, Any]:
    head = conn.execute(
        "SELECT report_id, confidence, tolerable_pct, seed, population_tco2e, planned_n,"
        " interval_tco2e, created_at FROM audit_sample WHERE sample_id = %s",
        (sample_id,)).fetchone()
    if head is None:
        raise LookupError(f"no sample {sample_id}")
    report_id, confidence, tolerable_pct, seed, total, planned, interval, created = head
    items = conn.execute(
        "SELECT i.item_id, i.activity_id, i.stratum, i.reason, i.book_tco2e, i.audited_tco2e,"
        " i.finding, a.activity_type, lower(a.period), f.name"
        " FROM audit_sample_item i JOIN activity a USING (activity_id)"
        " JOIN facility f USING (facility_id) WHERE i.sample_id = %s"
        " ORDER BY i.stratum, lower(a.period), i.activity_id", (sample_id,)).fetchall()
    tolerable = Fraction(total) * Fraction(tolerable_pct) / 100
    ev = evaluate([(s, Fraction(b), None if a is None else Fraction(a))
                   for _, _, s, _, b, a, *_ in items],
                  None if interval is None else Fraction(interval), float(confidence), tolerable)

    def pct(x: Fraction) -> str:
        return f"{float(100 * x / Fraction(total)):.3f}"

    return {
        "sample_id": sample_id, "report_id": report_id, "confidence": str(confidence),
        "tolerable_pct": str(tolerable_pct), "seed": seed, "created_at": created.isoformat(),
        "population_tco2e": format(total, "f"), "planned_n": planned,
        "interval_tco2e": None if interval is None else format(interval, "f"),
        "items": [{"item_id": iid, "activity_id": aid, "stratum": s, "reason": why,
                   "book_tco2e": format(b, "f"),
                   "audited_tco2e": None if a is None else format(a, "f"), "finding": note,
                   "activity_type": kind, "period_start": start.isoformat(), "facility": fac}
                  for iid, aid, s, why, b, a, note, kind, start, fac in items],
        "evaluation": {
            "tested": ev.tested, "selected": ev.selected, "complete": ev.complete,
            "projected_tco2e": f"{float(ev.projected):.6f}",
            "projected_pct": pct(ev.projected),
            "upper_overstatement_pct": pct(ev.upper_over),
            "upper_understatement_pct": pct(ev.upper_under),
            "within_tolerable": ev.within if ev.complete else None,
        },
    }
