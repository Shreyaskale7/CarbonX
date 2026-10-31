"""Turn a PDF of JdVVNL HT-5 bills (one bill per page) into redacted candidates for the real-bill evaluation.

    python scripts/ingest_jdvvnl.py --group A --pdf BILLS.pdf --also "CONSUMER NAME" --also "AREA"
    python scripts/ingest_jdvvnl.py --group B --ocr "data/bills/work/x_*.ocr.json" --source-pdf SCANS.pdf --also ...

Digital PDFs are read with pdfplumber; scans are read from OCR word boxes (made outside this script).
For each page: read the facts (scripts/jdvvnl_label.py), redact the text (src/carbonx/extraction/redact.py,
plus every identifier found on the page itself), refuse if anything recognisable is left, and write
`<utility>-<hash>.txt` and a sidecar `.json` to --out (default data/bills/work/candidates, git-ignored).

Nothing is written to data/redacted_bills/: that folder is for bills whose owners have agreed and whose
redacted text a person has read, and the sidecar's `consent` and `reviewed_by` are theirs to fill in.
The consumer is recorded only as the letter given in --group, never by name.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import jdvvnl_label as jl

from carbonx.extraction.redact import redact, residual

IDS_ON_PAGE = [
    re.compile(r"\bJDVVNL\d{8,}\b"),                          # the bank account string embeds the K number
    re.compile(r"\b3\d{11}\b"),                               # K number, twelve digits
    re.compile(r"Ac[ce]\s*No\.?[:.\s]*(\d{6,10})"),         # 'Ace' is an OCR misreading of 'Acc' re.compile(r"Bill\s*No\.?[:.\s]*(\d{6,12})"),
    re.compile(r"\b(?:0[1-9]|1[0-2])\d{7}\b"),                # bill number: month, year, serial (OCR separates it from its label)
    re.compile(r"^(\S+)\s+(?:\d\s+)?(?:KWH|KVAH|KVA)\b", re.MULTILINE),  # meter numbers; some rows carry a serial index
    re.compile(r"\bQ\d{6,8}\b"),                              # rooftop solar meter
]


def pages(args) -> list[tuple[int, list[str], list[dict] | None]]:
    """(page number, text rows, OCR boxes or None for a digital PDF)."""
    if args.pdf:
        import pdfplumber
        with pdfplumber.open(args.pdf) as pdf:
            return [(i + 1, (pg.extract_text() or "").splitlines(), None) for i, pg in enumerate(pdf.pages)]
    out = []
    for i, p in enumerate(sorted(Path().glob(args.ocr))):
        boxes = json.loads(p.read_text(encoding="utf-8"))
        out.append((i + 1, jl.lines_from_boxes(boxes), boxes))
    return out


def read_page(lines: list[str], boxes: list[dict] | None) -> jl.Read:
    if boxes is None:
        return jl.read_bill(lines)
    return jl.read_scan(boxes)                     # scans: by column and position


def identifiers(text: str) -> list[str]:
    found: set[str] = set()
    for pat in IDS_ON_PAGE:
        for m in pat.finditer(text):
            found.add(m.group(m.lastindex or 0))
    return sorted(found)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--group", required=True, help="a letter for the consumer, never its name")
    ap.add_argument("--pdf", type=Path, help="a digital PDF, one bill per page")
    ap.add_argument("--ocr", help="glob of OCR box files, one per page (scans)")
    ap.add_argument("--source-pdf", type=Path, help="the original file, for its checksum (scans)")
    ap.add_argument("--also", action="append", default=[], help="a name or place to remove (repeatable)")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "bills" / "work" / "candidates")
    args = ap.parse_args()
    if bool(args.pdf) == bool(args.ocr):
        sys.exit("give exactly one of --pdf or --ocr")
    source = args.pdf or args.source_pdf
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest() if source else None

    pgs = pages(args)
    reads = [read_page(lines, boxes) for _, lines, boxes in pgs]
    jl.cross_check(reads)
    args.out.mkdir(parents=True, exist_ok=True)
    tally = {"verified": 0, "unverified": 0, "flagged": 0, "blocked": 0}
    for (page, lines, _), read in zip(pgs, reads, strict=True):
        raw = "\n".join(lines)
        loose = bool(args.ocr)                          # OCR runs words together: match names ignoring spaces
        text, found = redact(raw, args.also + identifiers(raw), loose=loose)
        left = residual(text, args.also + identifiers(raw), loose=loose)
        problems = [p for p in read.problems if not p.startswith("unchecked")]
        status = ("flagged" if problems or read.consumption is None
                  else "unverified" if any(p.startswith("unchecked") for p in read.problems) else "verified")
        if left:
            tally["blocked"] += 1
            print(f"  page {page}: BLOCKED, still recognisable: {len(left)} item(s); nothing written")
            continue
        tally[status] += 1
        bill_id = f"jdvvnl-{args.group.lower()}-{(read.month or f'p{page}')}-{hashlib.sha256(text.encode()).hexdigest()[:6]}"
        sub = args.out if status != "flagged" else args.out / "flagged"
        sub.mkdir(exist_ok=True)
        (sub / f"{bill_id}.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
        (sub / f"{bill_id}.json").write_text(json.dumps({
            "id": bill_id, "discom": "JDVVNL", "consumer_group": args.group.upper(), "page": page,
            "billing_month": read.month, "tariff_category": "HT-5 large industrial",
            "consumption_kwh": read.consumption if status != "flagged" else None,
            "label_basis": "KWH row of the printed meter table, checked against difference x factor, "
                           "the gross column and the next bill's twelve-month history",
            "billed_net_kwh": read.billed_net, "label_status": status, "label_problems": read.problems,
            "source_kind": "pdf-text" if args.pdf else "scan+ocr", "source_sha256": source_sha, "redactions": found,
            "consent": False, "reviewed_by": None, "notes": ""}, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"group {args.group.upper()}: {len(pgs)} pages -> {tally}")


if __name__ == "__main__":
    main()
