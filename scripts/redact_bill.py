"""Redact a real bill's text and store it for the extraction evaluation.

    python scripts/redact_bill.py data/bills/bescom-01.pdf --discom BESCOM \
        --also "Your Name" --also "12 MG Road"                 # dry run: prints, writes nothing
    python scripts/redact_bill.py ... --write                    # after you have read the output

Input is a digital PDF (text via pdfplumber) or a .txt. The raw file stays where
it is (data/bills/ is git-ignored); only the redacted text and a sidecar JSON are
written to data/redacted_bills/. Fill in the sidecar by hand (consent, the true
consumption_kwh, tariff category) before committing: tests/test_redacted_bills.py
refuses a bill without them. Read docs/BILL_COLLECTION.md first.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carbonx.extraction.redact import redact, residual

OUT = ROOT / "data" / "redacted_bills"


def read_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages)
    return path.read_text(encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("source", type=Path)
    ap.add_argument("--discom", required=True, help="the utility, e.g. BESCOM")
    ap.add_argument("--also", action="append", default=[],
                    help="a name, street or employer to remove (repeatable)")
    ap.add_argument("--write", action="store_true", help="write the files (default: dry run)")
    args = ap.parse_args()

    raw = read_text(args.source)
    if not raw.strip():
        sys.exit("no text found: a scanned bill needs OCR first, which is not built")
    text, found = redact(raw, args.also)
    left = residual(text, args.also)
    print(text)
    print("\n--- redacted:", found or "nothing matched", "---", file=sys.stderr)
    if left:
        sys.exit(f"STOP: still recognisable as personal data: {left}")
    source_sha = hashlib.sha256(args.source.read_bytes()).hexdigest()
    bill_id = f"{args.discom.lower()}-{source_sha[:8]}"
    if not args.write:
        print(f"dry run. Read it all, then add --write to store it as {bill_id}.", file=sys.stderr)
        return
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{bill_id}.txt").write_text(text, encoding="utf-8", newline="\n")
    (OUT / f"{bill_id}.json").write_text(json.dumps({
        "id": bill_id, "discom": args.discom.upper(), "source_sha256": source_sha,
        "source_kind": args.source.suffix.lower().lstrip("."), "redactions": found,
        "consent": False, "consumption_kwh": None, "tariff_category": None,
        "reviewed_by": None, "notes": ""}, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote data/redacted_bills/{bill_id}.txt and .json. Fill in the .json by hand.",
          file=sys.stderr)


if __name__ == "__main__":
    main()
