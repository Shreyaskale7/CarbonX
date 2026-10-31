"""Read the facts that matter off a JdVVNL HT-5 bill, as a LABELLING AID for the real-bill evaluation.

This is not an extractor under test. It reads the printed meter table (the KWH row: present reading,
last reading, difference, multiplication factor, consumption) and the twelve-month history table by
rule, so that a person has something to check each bill against. Every label it proposes is checked three
ways before it is believed:

  1. difference x multiplication factor equals the printed consumption;
  2. the printed consumption equals the gross consumption column;
  3. the bill's consumption equals the history-table entry for the same month on the NEXT bill, which
     is a different place on a different document.

A bill that fails a check, or that a check cannot be run on, is reported as such, never silently kept.
Raw bills stay on the owner's machine; this module only sees text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

NUM = r"\d+(?:\.\d+)?"
KWH_ROW = re.compile(rf"\bKWH\b\s+({NUM})\s+({NUM})\s+({NUM})\s+({NUM})\s+({NUM})\s+({NUM})")
MONTH = re.compile(r"\b(20\d{2}(?:0[1-9]|1[0-2]))\b")


@dataclass
class Read:
    month: str | None = None
    present: float | None = None
    last: float | None = None
    diff: float | None = None
    mf: float | None = None
    consumption: float | None = None
    gross: float | None = None
    history: dict[str, float] = field(default_factory=dict)
    printed: set[float] = field(default_factory=set)   # every number printed on the bill
    billed_net: float | None = None                  # the next bill's history figure, when it differs
    problems: list[str] = field(default_factory=list)


def read_bill(lines: list[str]) -> Read:
    """`lines`: the bill's text, one table row per line, tokens separated by spaces."""
    r = Read()
    for ln in lines:
        if r.month is None and (m := re.search(r"\b(20\d{2}(?:0[1-9]|1[0-2]))\s+80\d\d\b", ln)):
            r.month = m[1]
        if r.consumption is None and (m := KWH_ROW.search(ln)):
            r.present, r.last, r.diff, r.mf, r.consumption, r.gross = (float(x) for x in m.groups())
        if re.match(r"\s*Bill Month\b", ln):
            months = MONTH.findall(ln)
            r.history = {m: float("nan") for m in months}
        if re.match(r"\s*Consumption\s+\d", ln) and r.history:
            values = re.findall(NUM, ln)
            if len(values) == len(r.history):
                r.history = dict(zip(r.history, (float(v) for v in values), strict=True))
    r.printed = {float(x) for x in re.findall(NUM, " ".join(lines))}
    if r.month is None:
        r.problems.append("billing month not found")
    if r.consumption is None:
        r.problems.append("KWH row not found")
    else:
        if abs(r.diff * r.mf - r.consumption) > max(1.0, 1e-4 * r.consumption):
            r.problems.append(f"difference x factor ({r.diff * r.mf:.2f}) is not the printed consumption ({r.consumption})")
        if abs(r.gross - r.consumption) > max(1.0, 1e-4 * r.consumption):
            r.problems.append("gross consumption differs from consumption")
        if abs((r.present - r.last) - r.diff) > 0.01:
            r.problems.append("present minus last reading is not the printed difference")
    return r


def cross_check(reads: list[Read]) -> None:
    """Check each bill against the next readable bill's history table, which prints the BILLED consumption.
    Billed consumption can legitimately differ from the metered one (a consumer with offsets is billed on a
    net figure), so a different history value is accepted if it is a number printed on this very bill, and
    is then recorded as `billed_net`. If it matches nothing on the bill, the bill is flagged. A bill with no
    later readable bill is recorded as unchecked, not as correct."""
    for r in reads:
        if r.consumption is None or r.month is None:
            continue
        nxt = [x for x in reads if x.month and x.month > r.month and r.month in x.history
               and x.history[r.month] == x.history[r.month]]   # skip a later bill whose table was unreadable (nan)
        if not nxt:
            r.problems.append("unchecked: no later readable bill in the set")
            continue
        later = min(nxt, key=lambda x: x.month)
        seen = later.history[r.month]
        if abs(seen - r.consumption) <= max(1.0, 1e-4 * r.consumption):
            continue
        if any(abs(seen - p) <= 0.5 for p in r.printed):
            r.billed_net = seen
            continue
        r.problems.append(f"history on the {later.month} bill gives {seen:.2f}, a number not printed on this bill; "
                          f"its meter row gives {r.consumption:.2f}")


def lines_from_boxes(boxes: list[dict], tol: float = 0.55) -> list[str]:
    """Rebuild table rows from OCR word boxes: boxes whose vertical centres are within `tol` of a
    box height belong to one row; each row is read left to right."""
    boxes = sorted(boxes, key=lambda b: (b["y0"] + b["y1"]) / 2)
    rows: list[list[dict]] = []
    for b in boxes:
        yc, h = (b["y0"] + b["y1"]) / 2, max(b["y1"] - b["y0"], 1)
        if rows:
            last = rows[-1]
            ly = sum((x["y0"] + x["y1"]) / 2 for x in last) / len(last)
            if abs(yc - ly) <= tol * h:
                last.append(b)
                continue
        rows.append([b])
    return [" ".join(x["text"] for x in sorted(r, key=lambda b: b["x0"])) for r in rows]


def _number(text: str) -> float | None:
    t = text.strip().replace(",", "")
    return float(t) if re.fullmatch(r"\d+(?:\.\d+)?", t) else None


def read_scan(boxes: list[dict]) -> Read:
    """Fallback for scans, which are slightly tilted, so a value's height drifts across the page and one
    table row is split over several OCR lines. Work by COLUMN instead: in each column of the meter table
    the first of the three values is the KWH row's. Then check the arithmetic on what was found: present -
    last = difference, difference x factor = printed consumption. If it does not hold, say so."""
    r = Read()
    head = next((b for b in boxes if re.match(r"Meter\s*No", b["text"])), None)
    kwh = [b for b in boxes if re.fullmatch(r"KWH\.?", b["text"].strip(), re.IGNORECASE) and (head is None or b["y0"] > head["y1"])]
    if not kwh:
        r.problems.append("KWH row not found")
        return r
    label = min(kwh, key=lambda b: b["y0"])
    ly, h = (label["y0"] + label["y1"]) / 2, max(label["y1"] - label["y0"], 1)
    cells = sorted(((b["x0"] + b["x1"]) / 2, (b["y0"] + b["y1"]) / 2, v) for b in boxes
                   if (v := _number(b["text"])) is not None and b["x0"] > label["x1"] and ly - 2.5 * h <= (b["y0"] + b["y1"]) / 2 <= ly + 4 * h)
    columns: list[list[tuple[float, float]]] = []
    last_x = None
    for x, y, v in cells:
        if last_x is None or x - last_x > 70:
            columns.append([])
        columns[-1].append((y, v))
        last_x = x
    first = [min(c)[1] for c in columns if len(c) >= 2]                # the KWH row's value in each column (topmost)
    if len(first) < 5:
        r.problems.append("meter table columns not recognised")
    else:
        r.present, r.last, r.diff, r.mf, r.consumption = first[:5]
        r.gross = first[5] if len(first) > 5 else first[4]
        if not (abs((r.present - r.last) - r.diff) <= 0.02 + 5e-4 * r.diff
                and abs(r.diff * r.mf - r.consumption) <= max(5.0, 1e-3 * r.consumption)):
            r.problems.append("scan: readings, factor and consumption do not agree (OCR or table misread)")
            r.consumption = None
    months = sorted((b["y0"], b["x0"], m[0]) for b in boxes
                     if (m := re.fullmatch(r"20\d{2}(?:0[1-9]|1[0-2])", b["text"].strip())))
    r.month = months[0][2] if months else None
    if r.month is None:
        r.problems.append("billing month not found")
    r.history = _history_by_position(boxes)
    r.printed = {v for b in boxes for t in b["text"].split() if (v := _number(t)) is not None}
    return r


def _history_by_position(boxes: list[dict]) -> dict[str, float]:
    """The twelve-month table, read by position: each month header with the value directly below it."""
    title = next((b for b in boxes if "Last Twelve" in b["text"] or b["text"].startswith("Billed Consumption")), None)
    if title is None:
        return {}
    months = [b for b in boxes if re.fullmatch(r"20\d{2}(?:0[1-9]|1[0-2])", b["text"].strip()) and b["y0"] > title["y0"] - 30]
    values = [b for b in boxes if re.fullmatch(r"\d+\.\d{2}", b["text"].strip())]
    out: dict[str, float] = {}
    for m in months:
        mx, my = (m["x0"] + m["x1"]) / 2, (m["y0"] + m["y1"]) / 2
        below = [v for v in values if 5 < (v["y0"] + v["y1"]) / 2 - my < 90 and abs((v["x0"] + v["x1"]) / 2 - mx) < 60]
        if below:
            best = min(below, key=lambda v: abs((v["x0"] + v["x1"]) / 2 - mx) + 0.3 * abs((v["y0"] + v["y1"]) / 2 - my))
            out[m["text"].strip()] = float(best["text"])
    return out
