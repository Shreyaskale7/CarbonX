"""Evaluate consumption_kwh extraction on REAL, redacted bills, one group held out at a time.

    python scripts/eval_real_bills.py                 # one UTILITY held out: data/redacted_bills/ -> docs/EXTRACTION_REAL_RESULTS.md
    python scripts/eval_real_bills.py --by consumer   # one CONSUMER held out (a single utility's bills; weaker, see below)
    python scripts/eval_real_bills.py --dir X --out Y # somewhere else (e.g. candidates not yet cleared for the repository)

Default (--by discom): for each utility D, train on the synthetic training layouts plus every real bill from
the OTHER utilities, calibrate with leave-one-layout-out, then score on D, which the model has never seen.
This is the "held out by DISCOM" test from CLAUDE.md and the only one that says anything about an unseen
utility's layout.

--by consumer is for when all bills come from ONE utility and one bill form: each consumer in turn is held
out. That tests whether the model carries over from one consumer's bills to another's on a form it may have
seen, which is far easier than an unseen layout; the report says so at the top and must be quoted that way.

Each row compares two models: trained on synthetic bills only (what exists today), and also trained on the
other groups' real bills. Both are scored on the held-out group.

It refuses to write a results file until there is enough to say something: at least MIN_GROUPS groups with at
least MIN_PER bills each. Below that, a table of percentages would look like a finding and be noise. Every
file it reads must carry consent, a reviewer and a true consumption (tests/test_redacted_bills.py).
"""
import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carbonx.extraction.extract import ConsumptionModel, baseline, ece
from carbonx.extraction.synthetic import SEEN, corpus

DIR = ROOT / "data" / "redacted_bills"
OUT = ROOT / "docs" / "EXTRACTION_REAL_RESULTS.md"
MIN_GROUPS, MIN_PER = 3, 5
SYNTH_PER_LAYOUT = 100
KEYS = {"discom": "discom", "consumer": "consumer_group"}


def load(directory: Path, local_analysis: bool = False) -> list[dict]:
    bills = []
    for txt in sorted(directory.glob("*.txt")):
        meta = json.loads(txt.with_suffix(".json").read_text(encoding="utf-8"))
        if local_analysis:
            if not meta.get("consumption_kwh"):
                continue                      # a bill with no label cannot be scored
        elif not (meta.get("consent") is True and meta.get("reviewed_by") and meta.get("consumption_kwh")):
            sys.exit(f"{txt.name}: consent, reviewer and true consumption must be filled in the sidecar")
        bills.append({"id": meta["id"], "discom": meta["discom"], "consumer_group": meta.get("consumer_group", "?"),
                      "kwh": float(meta["consumption_kwh"]), "text": txt.read_text(encoding="utf-8")})
    return bills


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% interval for a proportion: honest about what a handful of bills can say."""
    if n == 0:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def enough(bills: list[dict], by: str = "discom") -> tuple[bool, str]:
    key = KEYS[by]
    counts: dict[str, int] = {}
    for b in bills:
        counts[b[key]] = counts.get(b[key], 0) + 1
    usable = {g: n for g, n in counts.items() if n >= MIN_PER}
    what = "utilities" if by == "discom" else "consumers (one utility)"
    msg = (f"{len(bills)} bills from {len(counts)} {what} {dict(sorted(counts.items()))}; "
           f"need {MIN_GROUPS} with {MIN_PER}+ bills each")
    return len(usable) >= MIN_GROUPS, msg


def score(model: ConsumptionModel, test: list[dict]) -> dict:
    pred = [model.predict(b["text"]) for b in test]
    ok = [p.value == b["kwh"] for p, b in zip(pred, test, strict=True)]
    conf = [p.confidence or 0.0 for p in pred]
    return {"right": sum(ok), "conf": sum(conf) / len(test), "ece": ece(conf, ok), "ok": ok, "confs": conf}


def run(bills: list[dict], by: str = "discom", synth_per_layout: int = SYNTH_PER_LAYOUT) -> dict[str, dict]:
    key = KEYS[by]
    synth = corpus(synth_per_layout, SEEN, seed=20260926)
    groups = sorted({b[key] for b in bills if sum(x[key] == b[key] for x in bills) >= MIN_PER})
    synth_only = ConsumptionModel()
    synth_only.fit_leave_one_layout_out([s.text for s in synth], [s.kwh for s in synth], [s.layout for s in synth])
    out = {}
    for held in groups:
        train = [b for b in bills if b[key] != held]
        both = ConsumptionModel()
        both.fit_leave_one_layout_out(
            [s.text for s in synth] + [b["text"] for b in train], [s.kwh for s in synth] + [b["kwh"] for b in train],
            [s.layout for s in synth] + [100 + sorted({x[key] for x in bills}).index(b[key]) for b in train])
        test = [b for b in bills if b[key] == held]
        base = [baseline(b["text"]).value == b["kwh"] for b in test]
        out[held] = {"n": len(test), "baseline": sum(base), "synthetic_only": score(synth_only, test),
                     "with_real": score(both, test)}
    return out


def pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def cell(right: int, n: int) -> str:
    lo, hi = wilson(right, n)
    return f"{right}/{n} ({pct(lo)} to {pct(hi)})"


LOCAL_BANNER = ("> **LOCAL ANALYSIS. NOT FOR PUBLICATION.** These bills have no recorded consent and no person has "
                "reviewed their labels or their redaction. This file is for the authors' own reading; do not commit it, "
                "quote it, or move the bills into `data/redacted_bills/` until `consent` and `reviewed_by` are filled in "
                "by a person.\n")


def report(res: dict[str, dict], by: str = "discom", local: bool = False) -> str:
    n = sum(r["n"] for r in res.values())
    tot = {k: sum(r[k]["right"] for r in res.values()) for k in ("synthetic_only", "with_real")}
    base = sum(r["baseline"] for r in res.values())
    rows = [f"| {g} | {r['n']} | {r['baseline']}/{r['n']} | {cell(r['synthetic_only']['right'], r['n'])} | "
            f"{cell(r['with_real']['right'], r['n'])} | {pct(r['with_real']['conf'])} | {r['with_real']['ece']:.2f} |"
            for g, r in res.items()]
    if by == "discom":
        title = "# Extraction on real bills, one utility held out at a time"
        caveat = (f"> **Read the counts first.** {n} real bills from {len(res)} utilities. Each row is a utility the "
                  "model had never seen. With this few bills the intervals are wide and the calibration error is "
                  "noisy; neither is a general statement about Indian electricity bills, and neither says anything "
                  "about a utility that is not in this table.")
        head = "held-out utility"
    else:
        title = "# Extraction on real bills, one consumer held out at a time (a single utility)"
        caveat = (f"> **This is not an unseen-utility test.** All {n} bills come from one utility and one bill form, "
                  f"for {len(res)} consumers. Each row is a consumer the model had not seen, on a form the model may "
                  "have seen other consumers' bills of. That is much easier than an unseen layout and says nothing "
                  "about other utilities. Read the 'synthetic only' column as what the pipeline does on a real form "
                  "it has never seen.")
        head = "held-out consumer"
    return "\n".join([
        title, "_Generated by `scripts/eval_real_bills.py`. Do not edit by hand._", *([LOCAL_BANNER] if local else []), caveat, "",
        (f"| {head} | bills | rule baseline | model, synthetic training only (95% interval) | "
         "model, also trained on the other groups' real bills (95% interval) | mean confidence | ECE |"),
        "|---|---|---|---|---|---|---|", *rows,
        f"| **all** | {n} | {base}/{n} | {cell(tot['synthetic_only'], n)} | {cell(tot['with_real'], n)} | | |", "",
        ("'Correct' means the extracted number equals the consumption labelled for that bill. The labels come from "
         "the printed meter table and were checked against other fields of the bills (their sidecars say how); "
         "they are not independent human readings unless a reviewer has re-read them. Confidence is "
         "temperature-scaled by leave-one-layout-out. Compare with `docs/EXTRACTION_RESULTS.md`, which is "
         "synthetic."), ""])


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--by", choices=sorted(KEYS), default="discom")
    ap.add_argument("--dir", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--local-analysis", action="store_true",
                    help="score candidates that no person has cleared; needs explicit --dir and --out")
    args = ap.parse_args(argv or [])
    if args.local_analysis and not (args.dir and args.out):
        sys.exit("--local-analysis needs explicit --dir and --out, so it can never overwrite the real results")
    bills = load(args.dir or DIR, args.local_analysis)
    ok, msg = enough(bills, args.by)
    if not ok:
        print("not enough real bills to evaluate:", msg)
        return
    out = args.out or OUT
    out.write_text(report(run(bills, args.by), args.by, args.local_analysis), encoding="utf-8", newline="\n")
    print(f"real bills -> {out}: {msg}")


if __name__ == "__main__":
    main(sys.argv[1:])
