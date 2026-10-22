"""Redact a real utility bill's TEXT before it goes anywhere near the repository.

The extraction model reads text (what pdfplumber pulls out of a digital PDF), so
this works on text. The raw PDF never leaves its owner's machine; what is stored
is the redacted text plus a sidecar with the SHA-256 of the original file.

What it removes, and how:

  * email addresses, phone numbers, GSTIN, PAN: replaced by a tag
  * values after labels such as "Consumer No", "Account No", "RR No", "K No":
    replaced by a pseudonym ID-xxxxxx, so two mentions in one bill still match
  * meter ids: replaced by MTR + six digits, so the meter-id reader still works
  * PIN codes after "PIN"/"Pincode", or ending an address line
  * the value (and up to three following lines) after Name/Address labels
  * anything you pass as `also`: the owner's name, street, employer, in full and
    word by word (words of three letters or more)

What it does NOT do, and cannot: understand a bill. Labels vary by utility, so a
name or address printed without a label can slip through. A person must read the
redacted text before it is committed, and `residual` is only a floor: it catches
what the patterns know about. Pseudonyms use a random salt that is discarded, so
they cannot be reversed or linked across bills.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections import Counter

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
GSTIN = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")
PAN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
MOBILE = re.compile(r"(?<![\d.])(?:\+?91[\s-]?)?[6-9]\d{9}(?!\d)")
LANDLINE = re.compile(r"(?<![\d.])0\d{2,4}[\s-]\d{6,8}(?!\d)")
ID_LABEL = re.compile(
    r"(?P<label>\b(?:consumer|account|a/c|customer|service\s+connection|contract\s+account|"
    r"connection|installation|rr|ca|sc|k)\s*(?:no|number|id)?\.?\s*[:#\-]?\s*)"
    r"(?P<value>[A-Z0-9][A-Z0-9/-]{5,})", re.IGNORECASE)
METER = re.compile(r"(?P<label>\bmeter(?:\s+(?:no|serial|id|number))?\.?\s*[:#\-]?\s+)"
                   r"(?P<value>[A-Z]{0,4}\d{4,}[A-Z0-9]*)", re.IGNORECASE)
PIN_LABELLED = re.compile(r"(?P<label>\b(?:pin(?:\s*code)?|postal\s*code)\s*[:\-]?\s*)"
                          r"(?P<value>\d{3}\s?\d{3})\b", re.IGNORECASE)
PIN_ENDING = re.compile(r"(?<=[A-Za-z][,\s-])(\d{6})\s*$")   # only on lines that look like addresses
PERSON_LABEL = re.compile(
    r"^(?P<label>[ \t]*(?:name\s+of\s+(?:the\s+)?consumer|consumer\s+name|customer\s+name|"
    r"billing\s+name|name\s+and\s+address|name)[ \t]*[:\-][ \t]*)(?P<value>.*)$",
    re.IGNORECASE | re.MULTILINE)
ADDRESS_LABEL = re.compile(
    r"^(?P<label>[ \t]*(?:billing\s+address|supply\s+address|installation\s+address|"
    r"service\s+address|premises|address)[ \t]*[:\-]?[ \t]*)(?P<value>.*)$",
    re.IGNORECASE | re.MULTILINE)

REDACTED = "[REDACTED]"


def _pseudo(value: str, salt: bytes) -> str:
    return hashlib.sha256(salt + value.upper().encode()).hexdigest()


def _lines_after(text: str, end: int, count: int) -> tuple[int, int]:
    """The span of up to `count` non-empty continuation lines after position `end`."""
    start, stop, taken = end, end, 0
    while taken < count:
        nl = text.find("\n", stop)
        if nl == -1:
            break
        nxt = text.find("\n", nl + 1)
        line = text[nl + 1: nxt if nxt != -1 else len(text)]
        if not line.strip() or ":" in line:      # a blank line or another "label: value" ends it
            break
        stop, taken = (nxt if nxt != -1 else len(text)), taken + 1
        if nxt == -1:
            break
    return start, stop


def redact(text: str, also: list[str] | None = None,
           salt: bytes | None = None) -> tuple[str, dict[str, int]]:
    """Returns (redacted text, how many of each kind were replaced)."""
    salt = salt if salt is not None else os.urandom(16)
    found: Counter[str] = Counter()

    def tag(kind: str, token: str):
        def sub(m: re.Match[str]) -> str:
            found[kind] += 1
            return token
        return sub

    for kind, pattern in (("email", EMAIL), ("gstin", GSTIN), ("pan", PAN),
                          ("mobile", MOBILE), ("landline", LANDLINE)):
        text = pattern.sub(tag(kind, f"[{kind.upper()}]"), text)

    def meter(m: re.Match[str]) -> str:
        found["meter"] += 1
        return m["label"] + "MTR" + str(int(_pseudo(m["value"], salt), 16))[:6].zfill(6)

    def ident(m: re.Match[str]) -> str:
        found["identifier"] += 1
        return m["label"] + "ID-" + _pseudo(m["value"], salt)[:6]

    text = METER.sub(meter, text)
    text = ID_LABEL.sub(ident, text)
    text = PIN_LABELLED.sub(lambda m: (found.update(pin=1), m["label"] + "[PIN]")[1], text)
    text = "\n".join(PIN_ENDING.sub(lambda m: (found.update(pin=1), "[PIN]")[1], ln) if "," in ln else ln
                     for ln in text.split("\n"))   # a bare six-digit consumption must survive

    for kind, pattern, follow in (("name", PERSON_LABEL, 0), ("address", ADDRESS_LABEL, 3)):
        out, last = [], 0
        for m in pattern.finditer(text):
            if m.start() < last:
                continue
            out.append(text[last:m.start("value")])
            _, stop = _lines_after(text, m.end(), follow)
            out.append(REDACTED)
            found[kind] += 1
            last = stop
        out.append(text[last:])
        text = "".join(out)

    for literal in also or []:
        parts = [literal.strip()] + [w for w in re.split(r"\W+", literal) if len(w) >= 3]
        for part in sorted({p for p in parts if p}, key=len, reverse=True):
            pattern = re.compile(r"\s+".join(re.escape(w) for w in part.split()), re.IGNORECASE)
            text, n = pattern.subn(REDACTED, text)
            found["listed"] += n
    return text, dict(found)


def residual(text: str, also: list[str] | None = None) -> list[str]:
    """What is still recognisable as personal data. Empty is the floor, not a clearance."""
    left = [f"{k}: {m.group()}" for k, p in (("email", EMAIL), ("gstin", GSTIN), ("pan", PAN),
                                              ("mobile", MOBILE), ("landline", LANDLINE))
            for m in p.finditer(text)]
    for literal in also or []:
        for part in [literal.strip()] + [w for w in re.split(r"\W+", literal) if len(w) >= 3]:
            if part and re.search(re.escape(part), text, re.IGNORECASE):
                left.append(f"listed: {part}")
    return left
