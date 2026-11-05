"""Build a single local HTML page for a person to review candidate bills, and read their sign-off.

    python scripts/review_pack.py                       # data/bills/work/candidates -> data/bills/work/REVIEW.html
    python scripts/promote_reviewed.py --review review.json   # after the reviewer downloads review.json

For each bill the page shows the redacted text with the labelled consumption highlighted, the label's
status and checks, and an automatic scan for anything still recognisable as personal data. The reviewer
ticks the bills they have READ AND ACCEPT, types their name, and downloads review.json. Nothing is sent
anywhere; the page is one local file (it holds redacted text only, but keep it local all the same).

The reviewer is vouching for two things, and the page says so for each bill: that nothing that identifies a
person or a business is left in the text, and that the highlighted number is the consumption the bill shows.
"""
import argparse
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carbonx.extraction.redact import residual

DIR = ROOT / "data" / "bills" / "work" / "candidates"
OUT = ROOT / "data" / "bills" / "work" / "REVIEW.html"


def number_pattern(value: float) -> str:
    """A regex matching `value` as printed on a bill: any trailing zeros after the decimal point are allowed,
    and no further digit may follow. (A '%g' format would round a large figure to six digits.)"""
    plain = format(value, "f").rstrip("0").rstrip(".") if value != int(value) else str(int(value))
    whole, _, frac = plain.partition(".")
    return r"(?<![\d.])" + re.escape(whole) + (r"\." + re.escape(frac) + r"0*" if frac else r"(?:\.0+)?") + r"(?!\d)"


def long_numbers(text: str) -> list[str]:
    """Integers of eight to thirteen digits with no decimals: what an identifier looks like."""
    return re.findall(r"(?<![\d.])\d{8,13}(?![\d.]|\.\d)", text)


def build(directory: Path) -> str:
    cards, total = [], 0
    for txt in sorted(directory.glob("*.txt")):
        meta = json.loads(txt.with_suffix(".json").read_text(encoding="utf-8"))
        if not meta.get("consumption_kwh"):
            continue
        text = txt.read_text(encoding="utf-8")
        pat = re.compile(number_pattern(float(meta["consumption_kwh"])))
        shown = pat.sub(lambda m: "\0" + m.group() + "\1", html.escape(text)).replace("\0", "<mark>").replace("\1", "</mark>")
        hits = len(pat.findall(text))
        leaks = residual(text) + [f"long number: {n}" for n in long_numbers(text)]
        flags = []
        if leaks:
            flags.append("<b class=bad>SCAN: " + html.escape("; ".join(leaks)) + "</b>")
        else:
            flags.append("<span class=ok>scan: nothing recognisable left</span>")
        if not hits:
            flags.append("<b class=bad>the label does not appear in the text</b>")
        net = meta.get("billed_net_kwh")
        cards.append(
            f"<article data-id='{html.escape(meta['id'])}'><header><label><input type=checkbox class=ok-box> "
            f"<b>{html.escape(meta['id'])}</b></label> <span class=tag>consumer {html.escape(str(meta.get('consumer_group', '?')))}</span> "
            f"<span class=tag>{html.escape(str(meta.get('billing_month')))}</span> <span class=tag>{html.escape(meta['label_status'])}</span></header>"
            f"<p>Label: <b>{meta['consumption_kwh']:,.2f} kWh</b> ({html.escape(meta['label_basis'])})"
            + (f". The next bill's history table gives <b>{net:,.2f}</b> (a different, printed figure)." if net else "")
            + f"</p><p>{' | '.join(flags)} | highlighted occurrences: {hits}</p>"
            f"<details><summary>Redacted text ({len(text.splitlines())} lines)</summary><pre>{shown}</pre></details></article>")
        total += 1
    css = ("body{font:14px/1.4 Segoe UI,Calibri,sans-serif;max-width:1000px;margin:20px auto;padding:0 12px;color:#111}"
           "article{border:1px solid #bbb;border-radius:6px;padding:8px 12px;margin:10px 0}header{display:flex;gap:10px;align-items:center}"
           ".tag{background:#eaf2f1;border-radius:4px;padding:1px 6px;font-size:12px}.ok{color:#0a7}.bad{color:#c22}mark{background:#f2a93b}"
           "pre{white-space:pre-wrap;background:#f6f6f6;padding:8px;font:12px/1.35 Consolas,monospace;max-height:420px;overflow:auto}"
           "#bar{position:sticky;top:0;background:#fff;border-bottom:2px solid #0f4c5c;padding:8px 0;z-index:5}button{padding:6px 12px}")
    js = """
const q = (s) => [...document.querySelectorAll(s)];
function count(){ document.getElementById('n').textContent = q('.ok-box:checked').length + ' of ' + q('.ok-box').length + ' accepted'; }
document.addEventListener('change', count); count();
document.getElementById('all').onclick = () => { q('article').forEach(a => { if (!a.querySelector('.bad')) a.querySelector('.ok-box').checked = true; }); count(); };
document.getElementById('save').onclick = () => {
  const name = document.getElementById('name').value.trim();
  if (!name) { alert('Type your name first: it is recorded as the reviewer.'); return; }
  const ids = q('article').filter(a => a.querySelector('.ok-box').checked).map(a => a.dataset.id);
  const blob = new Blob([JSON.stringify({reviewer: name, reviewed_on: new Date().toISOString().slice(0, 10), accepted: ids}, null, 2)], {type: 'application/json'});
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'review.json'; a.click();
};"""
    return (f"<!doctype html><meta charset=utf-8><title>Bill review</title><style>{css}</style><h1>Bill review ({total} bills)</h1>"
            "<p>For each bill: read the redacted text. <b>Tick it only if (1)</b> nothing in it identifies a person or a business "
            "(names, addresses, plot or account numbers, meter numbers, phones, emails, tax IDs, place names), "
            "<b>and (2)</b> the highlighted number is the consumption in kWh that the bill shows. Compare with the original PDF for a sample. "
            "Bills with a red flag cannot be ticked with the button below; tick them by hand only after fixing the cause.</p>"
            "<div id=bar>Your name: <input id=name size=24> <button id=all>Tick every bill with no red flag</button> "
            "<button id=save>Download review.json</button> <span id=n></span></div>" + "".join(cards) + f"<script>{js}</script>")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", type=Path, default=DIR)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    page = build(args.dir)
    args.out.write_text(page, encoding="utf-8", newline="\n")
    print(f"review pack -> {args.out}  ({page.count('<article')} bills)")


if __name__ == "__main__":
    main()
