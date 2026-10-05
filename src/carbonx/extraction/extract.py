"""Extract consumption_kwh from a bill's text, with calibrated confidence.

Two extractors, so the learned one has a floor to beat:

  baseline()          hand-written rules (written from the training layouts only)
  ConsumptionModel    every number in the document is a candidate; a logistic
                      regression scores each from the words around it, its
                      table header and simple numeric cues; the top candidate
                      wins. Its confidence is temperature-scaled on a held-out
                      validation split, because raw scores are over-confident.

The model covers consumption_kwh, the value that feeds emissions. The billing
period and meter id are read by rules only (period, meter_id); the issuer is
not extracted.

Invariant 6: the confidence stored for an extraction must be the CALIBRATED
one. ece() measures how far confidence is from accuracy.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date
from itertools import pairwise
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression

NUMBER = re.compile(r"^[(₹]*(\d[\d,]*(?:\.\d+)?)[).,;:]*$")
WORD = re.compile(r"[a-z]+")
RULE = re.compile(r"units?\s+(?:consumed|billed)|billed\s+units|consumption\s*\(kwh\)"
                  r"|energy\s+consumed", re.IGNORECASE)


@dataclass(frozen=True)
class Candidate:
    value: float
    raw: str
    features: dict[str, float]


@dataclass(frozen=True)
class Extraction:
    value: float | None
    raw: str | None
    confidence: float | None   # calibrated for the model; None for the baseline
    method: str


def text_from_pdf(path: Path) -> str:
    """The text of a digital PDF bill, as the extractors expect it."""
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def _value(token: str) -> float | None:
    m = NUMBER.match(token)
    return float(m[1].replace(",", "")) if m else None


def _words(text: str) -> list[str]:
    return WORD.findall(text.lower())


def candidates(text: str) -> list[Candidate]:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    tokens = [ln.split() for ln in lines]
    values = [[_value(t) for t in row] for row in tokens]
    flat = {v for row in values for v in row if v is not None}
    diffs = {a - b for a in flat for b in flat if a > b}
    out = []
    for i, row in enumerate(tokens):
        cells = re.split(r"\s{2,}", lines[i].strip())
        numbers_here = sum(v is not None for v in values[i])
        for j, tok in enumerate(row):
            v = values[i][j]
            if v is None:
                continue
            f: dict[str, float] = {
                "log10": math.log10(v + 1), "decimal": float("." in tok),
                "line_pos": i / len(lines), "numbers_in_line": float(numbers_here),
                "last_in_line": float(j == len(row) - 1),
                "is_difference": float(v in diffs),
            }
            for w in _words(" ".join(row[max(0, j - 4):j])):
                f[f"L={w}"] = 1.0
            for w in _words(" ".join(row[j + 1:j + 3])):
                f[f"R={w}"] = 1.0
            # Table: the header cell above this number's cell.
            above = re.split(r"\s{2,}", lines[i - 1].strip()) if i else []
            if above and len(above) == len(cells) and not any(
                    x is not None for x in values[i - 1]):
                cell = next((k for k, c in enumerate(cells) if tok in c.split()), None)
                if cell is not None:
                    for w in _words(above[cell]):
                        f[f"H={w}"] = 1.0
            elif numbers_here == len(row) and i:   # a line of numbers only: label above
                for w in _words(lines[i - 1]):
                    f[f"H={w}"] = 1.0
                if i + 1 < len(lines):
                    for w in _words(lines[i + 1]):
                        f[f"N={w}"] = 1.0
            # The same words, position-free: 'kwh' beside a number and 'kwh' in
            # a column header are the same cue. Without this the vocabulary is
            # split by position and nothing transfers to a new layout.
            for key in [k for k in f if "=" in k]:
                f["A=" + key.split("=", 1)[1]] = 1.0
            out.append(Candidate(v, tok, f))
    return out


def baseline(text: str) -> Extraction:
    """Rules written from the training layouts. No confidence: rules have none."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    for i, line in enumerate(lines):
        m = RULE.search(line)
        if not m:
            continue
        after = [(_value(t), t) for t in line[m.end():].split()]
        hit = next(((v, t) for v, t in after if v is not None), None)
        if hit is None and i + 1 < len(lines):      # table header: last number below
            below = [(_value(t), t) for t in lines[i + 1].split()]
            hit = next(((v, t) for v, t in reversed(below) if v is not None), None)
        if hit:
            return Extraction(hit[0], hit[1], None, "baseline")
    return Extraction(None, None, None, "baseline")


def _softmax(z: np.ndarray) -> np.ndarray:
    e = np.exp(z - z.max())
    return e / e.sum()


class ConsumptionModel:
    def __init__(self) -> None:
        self.vec = DictVectorizer()
        self.clf = LogisticRegression(max_iter=5000, class_weight="balanced")
        self.temperature = 1.0

    def fit(self, texts: list[str], truths: list[float]) -> ConsumptionModel:
        feats, labels = [], []
        for text, truth in zip(texts, truths, strict=True):
            for c in candidates(text):
                feats.append(c.features)
                labels.append(int(c.value == truth))
        self.clf.fit(self.vec.fit_transform(feats), labels)
        return self

    def _scores(self, text: str) -> tuple[list[Candidate], np.ndarray]:
        cands = candidates(text)
        if not cands:
            return cands, np.array([])
        return cands, self.clf.decision_function(
            self.vec.transform([c.features for c in cands]))

    def fit_leave_one_layout_out(self, texts: list[str], truths: list[float],
                                 layouts: list[int]) -> float:
        """Fit on everything, but calibrate for LAYOUT SHIFT.

        A temperature fitted on documents from layouts the model trained on is
        fitted where the model is nearly always right, so it learns to be more
        confident, and is then confidently wrong on a new layout. Instead:
        hold each training layout out in turn, train on the rest, and score
        the held-out one. The temperature is fitted on those out-of-layout
        scores. Returns the leave-one-layout-out accuracy, an estimate of
        accuracy on unseen layouts that uses training data only.
        """
        docs, right = [], 0
        for held in sorted(set(layouts)):
            fold = ConsumptionModel().fit(
                [t for t, g in zip(texts, layouts, strict=True) if g != held],
                [y for y, g in zip(truths, layouts, strict=True) if g != held])
            for text, truth, g in zip(texts, truths, layouts, strict=True):
                if g != held:
                    continue
                cands, z = fold._scores(text)
                hit = np.array([c.value == truth for c in cands])
                right += bool(len(z)) and bool(hit[int(z.argmax())])
                if hit.any():
                    docs.append((z, hit))
        self.fit(texts, truths)
        self._fit_temperature(docs)
        return right / len(texts)

    def calibrate(self, texts: list[str], truths: list[float]) -> float:
        """Temperature scaling on held-out documents from the SAME layouts.
        Kept for comparison: see fit_leave_one_layout_out for why it is not
        enough."""
        docs = []
        for text, truth in zip(texts, truths, strict=True):
            cands, z = self._scores(text)
            hit = np.array([c.value == truth for c in cands])
            if hit.any():
                docs.append((z, hit))
        return self._fit_temperature(docs)

    def _fit_temperature(self, docs: list[tuple[np.ndarray, np.ndarray]]) -> float:
        """One scalar T minimising the negative log-likelihood of the true
        candidate over the given documents."""

        def nll(log_t: float) -> float:
            t = math.exp(log_t)
            return -sum(math.log(max(_softmax(z / t)[hit].sum(), 1e-12))
                        for z, hit in docs)

        # T >= 1 only: calibration may soften confidence, never sharpen it. If
        # the held-out documents contain no errors, the likelihood is maximised
        # by T -> 0 (certainty), which is "never seen failing", not evidence.
        self.temperature = math.exp(minimize_scalar(nll, bounds=(0, 5),
                                                    method="bounded").x)
        return self.temperature

    def predict(self, text: str, calibrated: bool = True) -> Extraction:
        cands, z = self._scores(text)
        if not cands:
            return Extraction(None, None, None, "model")
        p = _softmax(z / (self.temperature if calibrated else 1.0))
        top = int(p.argmax())
        return Extraction(cands[top].value, cands[top].raw, float(p[top]), "model")


def ece(confidences: list[float], correct: list[bool], bins: int = 10) -> float:
    """Expected calibration error: the weighted gap between confidence and
    accuracy over equal-width confidence bins. 0 is perfectly calibrated."""
    conf, ok = np.array(confidences), np.array(correct, dtype=float)
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for lo, hi in pairwise(edges):
        mask = (conf > lo) & (conf <= hi) if lo else (conf >= lo) & (conf <= hi)
        if mask.any():
            total += mask.mean() * abs(ok[mask].mean() - conf[mask].mean())
    return float(total)


# ---- other fields: rules only ------------------------------------------------
# Written from the training layouts (1-5) and never adjusted after seeing the
# others. There is no model and no confidence for these fields.

_DATE = re.compile(r"\b(\d{2})[-/](\d{2})[-/](\d{4})\b|\b(\d{2}) ([A-Z][a-z]{2}) (\d{4})\b"
                   r"|\b(\d{4})-(\d{2})-(\d{2})\b")
_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}
_METER = re.compile(r"\bmeter(?:\s+(?:no|serial|id))?\s*:?\s+([A-Z]{2,4}\d{4,})",
                    re.IGNORECASE)


def _dates(line: str) -> list[date]:
    out = []
    for m in _DATE.finditer(line):
        try:
            if m[1]:
                out.append(date(int(m[3]), int(m[2]), int(m[1])))
            elif m[4]:
                out.append(date(int(m[6]), _MONTHS[m[5]], int(m[4])))
            else:
                out.append(date(int(m[7]), int(m[8]), int(m[9])))
        except (ValueError, KeyError):
            pass
    return out


def period(text: str) -> tuple[date, date] | None:
    """The billing period: the first line that carries two dates."""
    for line in text.splitlines():
        found = _dates(line)
        if len(found) >= 2 and found[0] < found[1]:
            return found[0], found[1]
    return None


def meter_id(text: str) -> str | None:
    m = _METER.search(text)
    return m[1] if m else None
