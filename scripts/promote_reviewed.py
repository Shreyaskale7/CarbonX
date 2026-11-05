"""Move bills a PERSON has reviewed from the local candidates folder into data/redacted_bills/.

    python scripts/promote_reviewed.py --review review.json

review.json comes from the page made by scripts/review_pack.py: {"reviewer": "...", "reviewed_on": "...",
"accepted": [bill ids]}. This script is the gate. For each accepted bill it checks again, by itself, that the
sidecar records consent, that there is a labelled consumption, that its status is verified or unverified,
that the label appears in the text, and that nothing recognisable as personal data (or an identifier-shaped
long number) is left. A bill that fails is refused and reported, whatever the reviewer ticked. Passing bills
are written to data/redacted_bills/ with `reviewed_by` and `reviewed_on` filled in; the originals in the
candidates folder are left where they are. It never invents a reviewer: no name, no promotion.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from review_pack import long_numbers, number_pattern

from carbonx.extraction.redact import residual

SRC = ROOT / "data" / "bills" / "work" / "candidates"
DEST = ROOT / "data" / "redacted_bills"
# an eight-digit counter printed on the form, not an identifier; reviewers are told about it in the checklist
ALLOWED_LONG: set[str] = set()


def refusal(meta: dict, text: str) -> str | None:
    if meta.get("consent") is not True:
        return "no consent recorded in the sidecar"
    if not meta.get("consumption_kwh"):
        return "no labelled consumption"
    if meta.get("label_status") not in ("verified", "unverified"):
        return f"label status is {meta.get('label_status')!r}"
    if not re.search(number_pattern(float(meta["consumption_kwh"])), text):
        return "the labelled consumption does not appear in the text"
    left = residual(text)
    if left:
        return f"still recognisable as personal data: {left[:2]}"
    ids = [n for n in long_numbers(text) if n not in ALLOWED_LONG]
    if ids:
        return f"identifier-shaped numbers left: {ids[:3]}"
    return None


def promote(review: dict, src: Path, dest: Path) -> tuple[list[str], dict[str, str]]:
    reviewer = (review.get("reviewer") or "").strip()
    if not reviewer:
        raise SystemExit("review.json has no reviewer name: nothing is promoted without a person's name")
    done, refused = [], {}
    dest.mkdir(parents=True, exist_ok=True)
    for bill_id in review.get("accepted", []):
        txt, meta_path = src / f"{bill_id}.txt", src / f"{bill_id}.json"
        if not (txt.exists() and meta_path.exists()):
            refused[bill_id] = "not found in the candidates folder"
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        text = txt.read_text(encoding="utf-8")
        why = refusal(meta, text)
        if why:
            refused[bill_id] = why
            continue
        meta["reviewed_by"], meta["reviewed_on"] = reviewer, review.get("reviewed_on")
        (dest / f"{bill_id}.txt").write_text(text, encoding="utf-8", newline="\n")
        (dest / f"{bill_id}.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8", newline="\n")
        done.append(bill_id)
    return done, refused


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--review", type=Path, required=True)
    ap.add_argument("--src", type=Path, default=SRC)
    ap.add_argument("--dest", type=Path, default=DEST)
    args = ap.parse_args()
    done, refused = promote(json.loads(args.review.read_text(encoding="utf-8")), args.src, args.dest)
    print(f"promoted {len(done)} bills to {args.dest}")
    for bill_id, why in refused.items():
        print(f"  REFUSED {bill_id}: {why}")
    if refused:
        sys.exit(1)


if __name__ == "__main__":
    main()
