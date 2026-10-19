"""The single-file console (src/carbonx/api/static/console.html).

Two kinds of check. The embedded data must be exactly what the engine produced
(hashes, links, the stored sample, the registry). And the JavaScript that
re-implements the engine's arithmetic in the browser must agree with the Python
engine on many inputs: if the two ever disagree, the console would show a
figure the engine did not produce. The second kind needs node and skips
without it. No database.
"""
import hashlib
import json
import random
import re
import shutil
import subprocess
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from unittest import mock

import pytest

from carbonx.sampling import pps

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "src" / "carbonx" / "api" / "static" / "console.html"
PAGE = HTML.read_text(encoding="utf-8")
DATA = json.loads(re.search(r'<script id="data"[^>]*>(.*?)</script>', PAGE, re.DOTALL).group(1))


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---- the embedded data is what the engine produced ----------------------------

def test_every_embedded_report_hashes_to_its_stored_hash():
    assert len(DATA["reports"]) >= 8
    for r in DATA["reports"]:
        assert sha(r["output"]) == r["sha256"], r["id"]
        body = json.loads(r["output"])
        assert body["totals"]["total_tco2e"] == r["total"] and body["policy"] == r["policy"]


def test_the_embedded_audit_window_is_a_valid_chain():
    window = DATA["audit"]["window"]
    assert len(window) >= 5
    for i, e in enumerate(window):
        assert sha(e["payload"]) == e["hash"], e["id"]
        if i:
            assert e["prev"] == window[i - 1]["hash"], e["id"]


def test_the_stored_sample_is_what_a_fresh_draw_gives():
    ref = DATA["sampling"]
    rep = next(r for r in DATA["reports"] if r["id"] == ref["report_id"])
    items = [pps.Item(ln["activity_id"], Fraction(ln["tco2e"]),
                      None if ln["document_sha256"] else "no source document")
             for ln in json.loads(rep["output"])["lines"]]
    fresh = pps.select(items, Fraction(ref["interval"]), ref["seed"])
    assert ref["seed"] == f"{rep['sha256']}:{ref['nonce']}"
    assert {(i["activity_id"], i["stratum"]) for i in ref["items"]} == (
        {(k, "certain") for k, _ in fresh.certain} | {(k, "sampled") for k in fresh.sampled})


def test_ledger_figures_equal_the_reports_lines_and_the_registry_equals_the_csv():
    vint = next(r for r in reversed(DATA["reports"]) if r["policy"] == "VINTAGE_MATCHED")
    lines = {ln["activity_id"]: ln["tco2e"] for ln in json.loads(vint["output"])["lines"]}
    assert {r["activity_id"]: r["tco2e"] for r in DATA["ledger"]} == lines
    import csv
    csv_rows = {(f["factor_key"], f["fy"], f["version_label"]): float(f["value"])
                for f in csv.DictReader((ROOT / "data" / "cea" / "factors.csv").open(encoding="utf-8"))
                if f["geography"] == "IN"}
    embedded = {(s["key"], fy, v): val for s in DATA["registry"]["series"] for fy, v, val in s["points"]}
    assert embedded.keys() == csv_rows.keys()
    assert all(abs(embedded[k] - csv_rows[k]) < 5e-10 for k in csv_rows)


def test_the_file_is_self_contained_and_follows_the_house_rules():
    assert "__DATA__" not in PAGE
    assert not re.search(r'(src|href)="https?:', PAGE.replace(
        "".join(re.findall(r'"source_url":"[^"]*"', PAGE)), ""))       # only CEA source links in data
    assert "<link" not in PAGE and "@import" not in PAGE and "fetch(" not in PAGE
    assert not re.search("[–—]", PAGE)                          # no en or em dashes
    assert "synthetic" in PAGE.lower() and "does not verify" in PAGE
    assert "</script>" not in re.search(r'<script id="data"[^>]*>(.*?)</script>', PAGE, re.DOTALL).group(1)


# ---- the browser's arithmetic agrees with the engine ---------------------------

NODE = shutil.which("node")
HARNESS = r"""
const fs = require("fs"), vm = require("vm"), {webcrypto} = require("crypto");
const page = fs.readFileSync(process.argv[1], "utf8"), job = JSON.parse(fs.readFileSync(0, "utf8"));
const block = page.split("/* ==== PURE LOGIC START ====")[1].split("/* ==== PURE LOGIC END ====")[0].replace(/^[^\n]*\n/, "");
const ctx = vm.createContext({crypto: webcrypto, TextEncoder, console});
vm.runInContext(block + "\nthis.L = {parseDec, formatScaled, emissionsScaled, sha256Hex, confidenceFactor, intervalFor, seedFraction, selectLines, evaluateSample};", ctx);
const L = ctx.L;
(async () => {
  const out = {emissions: [], hashes: [], draws: [], evals: [], factors: [], selects: []};
  for (const r of job.ledger) out.emissions.push(L.formatScaled(L.emissionsScaled(r, r.quantity), 6));
  for (const t of job.texts) out.hashes.push(await L.sha256Hex(t));
  for (const c of job.draws) {
    const items = c.items.map((i) => ({key: i.key, value: L.parseDec(i.value, 6), reason: i.reason}));
    const total = items.reduce((a, i) => a + i.value, 0n);
    const j = L.intervalFor(total, c.tol, c.conf), sel = L.selectLines(items, j, await L.seedFraction(c.seed));
    out.draws.push({interval: L.formatScaled(j, 6), certain: sel.certain, sampled: sel.sampled});
  }
  for (const c of job.selects) {
    const sel = L.selectLines(c.items.map((v, i) => ({key: i + 1, value: L.parseDec(v, 6), reason: null})), BigInt(c.j), BigInt(c.h9));
    out.selects.push({certain: sel.certain, sampled: sel.sampled});
  }
  for (const e of job.evals) out.evals.push(L.evaluateSample(e.results, e.interval, e.conf, e.tolerable));
  for (const c of [0.9, 0.95, 0.99]) for (const k of [0, 1, 2, 3]) out.factors.push(L.confidenceFactor(c, k));
  console.log(JSON.stringify(out));
})();
"""


def _run_node(job: dict) -> dict:
    done = subprocess.run([NODE, "-e", HARNESS, str(HTML)], input=json.dumps(job), capture_output=True,
                          text=True, check=False, timeout=120)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout)


def _items(report):
    return [pps.Item(ln["activity_id"], Fraction(ln["tco2e"]),
                     None if ln["document_sha256"] else "no source document")
            for ln in json.loads(report["output"])["lines"]]


# Exact-boundary cases, in millionths of a tonne: a hit landing exactly on a running total,
# and a running total exactly one unit (1e-15 t) past a hit. Random inputs never get here.
BOUNDARY = [([50, 50, 50, 50], 100, h) for h in (0, 500_000_000, 999_999_999)] + [
    ([1, 2, 1], 3, 333_333_333), ([1, 1, 1, 1, 1, 1], 2, 500_000_000), ([7, 3, 5, 5], 10, 700_000_000),
    ([10, 10, 10], 10, 0), ([0, 5, 0, 5], 10, 500_000_000)]


@pytest.fixture(scope="module")
def node_result():
    if NODE is None:
        pytest.skip("node is not installed")
    rng = random.Random(7)
    draws, py = [], []
    for rep in DATA["reports"]:
        items = _items(rep)
        total = sum((i.value for i in items), Fraction(0))
        for conf in ("0.90", "0.95", "0.99"):
            for tol in ("5", "10", "17.5", "25", "30", "47.5", "100"):
                for nonce in ("console", "x"):
                    seed = f"{rep['sha256']}:{nonce}"
                    j = pps.interval_for(total * Fraction(Decimal(tol)) / 100, float(conf))
                    sel = pps.select(items, j, seed)
                    draws.append({"items": [{"key": i.key, "value": format(Decimal(i.value.numerator) / i.value.denominator, "f"),
                                             "reason": i.certain_because} for i in items],
                                  "tol": tol, "conf": float(conf), "seed": seed})
                    py.append({"interval": format(Decimal(j.numerator) / j.denominator, ".6f"),
                               "certain": [[k, w] for k, w in sel.certain], "sampled": list(sel.sampled)})
    evals = []
    for _ in range(40):
        n = rng.randint(3, 14)
        interval = Fraction(rng.randint(50, 900), 1)
        results = []
        for _ in range(n):
            book = Fraction(rng.randint(10, 2000), 7)
            taint = rng.choice([0, 0, 0, Fraction(1, 10), Fraction(1, 2), -Fraction(1, 5), 1])
            audited = None if rng.random() < 0.15 else book * (1 - taint)
            results.append(("certain" if rng.random() < 0.3 else "sampled", book, audited))
        evals.append((results, interval, rng.choice([0.9, 0.95, 0.99]), Fraction(rng.randint(100, 3000))))
    py_selects = []
    for values, j, h9 in BOUNDARY:
        with mock.patch.object(pps, "_start", lambda _seed, h9=h9: Fraction(h9, 10**9)):
            sel = pps.select([pps.Item(i + 1, Fraction(v, 10**6)) for i, v in enumerate(values)],
                             Fraction(j, 10**6), "ignored")
        py_selects.append({"certain": [[k, w] for k, w in sel.certain], "sampled": list(sel.sampled)})
    job = {"ledger": DATA["ledger"],
           "selects": [{"items": [format(Decimal(v).scaleb(-6), "f") for v in values], "j": j, "h9": h9}
                       for values, j, h9 in BOUNDARY], "texts": [r["output"] for r in DATA["reports"]] + ["", "é€nd"],
           "draws": draws,
           "evals": [{"results": [{"stratum": s, "book": float(b), "audited": None if a is None else float(a)}
                                  for s, b, a in res], "interval": float(i), "conf": c, "tolerable": float(t)}
                     for res, i, c, t in evals]}
    return {"job": job, "py_selects": py_selects, "py_draws": py, "py_evals": evals, "out": _run_node(job)}


def test_browser_emissions_equal_the_engines_for_every_ledger_row(node_result):
    assert node_result["out"]["emissions"] == [r["tco2e"] for r in DATA["ledger"]]


def test_browser_sha256_equals_python_including_non_ascii(node_result):
    texts = node_result["job"]["texts"]
    assert node_result["out"]["hashes"] == [sha(t) for t in texts]


def test_browser_sampling_draw_equals_the_engines_on_every_case(node_result):
    got, want = node_result["out"]["draws"], node_result["py_draws"]
    assert len(got) == len(want) >= 8 * 3 * 7 * 2
    for g, w in zip(got, want, strict=True):
        assert g["interval"] == w["interval"]
        assert g["certain"] == w["certain"] and g["sampled"] == w["sampled"]
    assert any(w["sampled"] for w in want), "the cases should include real sampling, not only test-everything"


def test_browser_selection_equals_the_engines_at_exact_boundaries(node_result):
    assert node_result["out"]["selects"] == node_result["py_selects"]
    assert any(w["sampled"] for w in node_result["py_selects"])


def test_browser_evaluation_equals_the_engines(node_result):
    for got, (results, interval, conf, tolerable) in zip(node_result["out"]["evals"],
                                                       node_result["py_evals"], strict=True):
        want = pps.evaluate(results, interval, conf, tolerable)
        assert got["tested"] == want.tested and got["selected"] == want.selected
        for k, v in (("projected", want.projected), ("upperOver", want.upper_over), ("upperUnder", want.upper_under)):
            assert got[k] == pytest.approx(float(v), rel=1e-9, abs=1e-9), k
        assert got["complete"] == want.complete and got["within"] == want.within


def test_browser_confidence_factors_equal_the_engines(node_result):
    want = [pps.confidence_factor(c, k) for c in (0.9, 0.95, 0.99) for k in (0, 1, 2, 3)]
    assert node_result["out"]["factors"] == pytest.approx(want, rel=1e-12)
