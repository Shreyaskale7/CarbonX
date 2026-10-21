"""Build the single-file console: frontend/console.template.html + real data
-> src/carbonx/api/static/console.html (served at /console, and openable by
double-click: no server, no network, no build tools needed to view it).

    python scripts/build_console.py            # needs the sample database
    python scripts/build_console.py --template-only   # new template, the data already in the file
    python scripts/build_console.py --check    # fail unless the file is its template plus its data

Nothing in the console is typed in by hand. The data comes from:
  - the CEA registry (data/cea/*.csv): every all-India factor, by version;
  - the sample database, which `reproduce.sh` fills: reports under every policy,
    the ledger with its provenance chains, exceptions, a window of the
    hash-chained audit trail, and one stored audit sample.
The sample organisation is synthetic, and the console says so on every screen.

While building, the script re-checks what the console will later re-check in the
browser: each report's text hashes to its stored SHA-256, each audit event's
payload hashes to its stored hash and links to the one before it, and the stored
sample equals a fresh draw. A file that fails any of these is never written.
"""
import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import psycopg
import rq1_materiality
import rq3_compliance

from carbonx import db
from carbonx.engine.calculate import ENGINE_VERSION
from carbonx.engine.exceptions import exceptions
from carbonx.engine.provenance import (
    attestation,
    coverage,
    plain,
    provenance,
)
from carbonx.evidence import anchor
from carbonx.factors.registry import POLICY_DESCRIPTIONS, Policy
from carbonx.forecast import nowcast as nc
from carbonx.sampling import pps
from carbonx.uncertainty.propagate import for_report

TEMPLATE = ROOT / "frontend" / "console.template.html"
OUT = ROOT / "src" / "carbonx" / "api" / "static" / "console.html"
PLACEHOLDER = "__DATA__"
ORG_ID, FY, BASELINE = 1, "FY2025-26", "FY2023-24"
WINDOW_MAX = 40                  # most audit events shown
SAMPLE = {"confidence": Decimal("0.95"), "tolerable_pct": Decimal(30), "nonce": "console"}
CARBONX_SERIES = "grid.weighted_avg_incl_re_captive.incl_imports"
SERIES_LABELS = {
    "grid.weighted_avg.excl_imports": "Weighted average, excluding imports",
    "grid.weighted_avg.incl_imports": "Weighted average, including imports",
    "grid.weighted_avg_incl_re.excl_imports": "Weighted average with renewables, excluding imports",
    "grid.weighted_avg_incl_re.incl_imports": "Weighted average with renewables, including imports",
    "grid.weighted_avg_incl_re_captive.excl_imports":
        "Weighted average with renewables and captive, excluding imports",
    CARBONX_SERIES: "Weighted average with renewables and captive, including imports",
    "grid.operating_margin.excl_imports": "Operating margin, excluding imports",
    "grid.operating_margin.incl_imports": "Operating margin, including imports",
    "grid.build_margin.excl_imports": "Build margin, excluding imports",
    "grid.combined_margin.excl_imports": "Combined margin, excluding imports",
    "grid.combined_margin.incl_imports": "Combined margin, including imports",
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def registry() -> dict:
    with (ROOT / "data" / "cea" / "versions.csv").open(encoding="utf-8", newline="") as fh:
        versions = sorted(csv.DictReader(fh), key=lambda v: int(v["version_ordinal"]))
    order = {v["version_label"]: int(v["version_ordinal"]) for v in versions}
    points: dict[str, list[list]] = {}
    with (ROOT / "data" / "cea" / "factors.csv").open(encoding="utf-8", newline="") as fh:
        for f in csv.DictReader(fh):
            if f["geography"] == "IN":
                points.setdefault(f["factor_key"], []).append(
                    [f["fy"], f["version_label"], round(float(f["value"]), 9)])
    for pts in points.values():
        pts.sort(key=lambda p: (p[0], order[p[1]]))
    return {
        "versions": [{"label": v["version_label"], "ordinal": int(v["version_ordinal"]),
                      "stated_date": v["stated_date"], "precision": v["date_precision"],
                      "covers": v["covers_fy"]} for v in versions],
        "series": [{"key": k, "label": SERIES_LABELS[k], "used": k == CARBONX_SERIES,
                    "points": points[k]} for k in sorted(points, key=lambda k: (k != CARBONX_SERIES, k))],
    }


def materiality() -> dict:
    """The RQ1 and RQ3 arithmetic, from the same functions that write the docs."""
    value, first = rq3_compliance.load_values()
    return {
        "threshold": rq1_materiality.THRESHOLD, "targets": rq3_compliance.TARGETS,
        "kinds": [{"kind": k, "what": what, "d": float(d.rstrip("%"))}
                  for k, what, d, _ in rq1_materiality.effects()],
        "baselines": {b: [{"name": n, "used": u, "d": round(d, 6)}
                          for n, u, d in rq3_compliance.readings(value, first, b)]
                      for b in rq3_compliance.BASELINES},
        "default_baseline": rq3_compliance.DEFAULT_BASELINE,
    }


def forecast() -> dict:
    """The leakage-safe backtest of one-year-ahead nowcasts (scripts/nowcast.py)."""
    reg = nc.load(ROOT / "data" / "cea" / "factors.csv", ROOT / "data" / "cea" / "versions.csv")
    key = "grid.weighted_avg.incl_imports"
    targets, notes = nc.backtest(reg[key])
    scores = nc.score(targets)
    best = min(scores, key=lambda x: x.mae)
    return {
        "series": key, "label": SERIES_LABELS[key],
        "scores": [{"model": x.model, "n": x.n, "mae": round(x.mae, 4), "rmse": round(x.rmse, 4),
                    "bias": round(x.bias, 4), "worst": round(x.worst, 4), "beats": x.beats_naive,
                    "comparable": x.comparable, "p": round(x.p_value, 4),
                    "naive": x.model == nc.NAIVE, "best": x is best} for x in scores],
        "years": [{"fy": nc.fy(t.year), "version": t.version, "actual": t.actual,
                   "naive": t.forecasts[nc.NAIVE], "error": round(t.error(nc.NAIVE), 4)}
                  for t in targets],
        "coverage": {str(lvl): list(nc.coverage(targets, lvl)[:2]) for lvl in (0.8, 0.9)},
        "notes": notes,
    }


def reports(conn: psycopg.Connection) -> list[dict]:
    out = []
    rows = conn.execute(
        "SELECT r.report_id, p.code, r.baseline_year, r.as_of, r.output_sha256, r.output"
        " FROM report r JOIN resolution_policy p USING (policy_id) WHERE r.org_id = %s"
        " ORDER BY r.report_id", (ORG_ID,)).fetchall()
    for rid, policy, baseline, as_of, sha, output in rows:
        if _sha(output) != sha:
            sys.exit(f"report {rid}: its stored text does not hash to its stored SHA-256")
        body = json.loads(output)
        fac = body["facilities"][0]
        band = for_report(conn, rid)
        out.append({
            "id": rid, "policy": policy, "baseline_year": baseline,
            "as_of": as_of.isoformat(), "sha256": sha, "output": output,
            "total": body["totals"]["total_tco2e"], "scope1": body["totals"]["scope1_tco2e"],
            "scope2": body["totals"]["scope2_tco2e"], "gei": body["gei"], "gei_unit": fac["gei_unit"],
            "production": fac["production"], "lines": len(body["lines"]),
            "unresolved": len(body["unresolved"]),
            "band": plain({"low": band.low, "high": band.high,
                           "low_independent": band.low_if_independent,
                           "high_independent": band.high_if_independent,
                           "unquantified": band.unquantified, "unmetered": band.unmetered,
                           "basis": list(band.basis)}),
        })
    return out


def ledger(conn: psycopg.Connection) -> list[dict]:
    ids = [r[0] for r in conn.execute(
        "SELECT c.calculation_id FROM calculation c"
        " JOIN resolution_policy p USING (policy_id) JOIN activity a USING (activity_id)"
        " JOIN facility f USING (facility_id)"
        " WHERE upper_inf(c.system_time_range) AND p.code = 'VINTAGE_MATCHED' AND f.org_id = %s"
        " ORDER BY lower(a.period), a.activity_type", (ORG_ID,)).fetchall()]
    rows = []
    for cid in ids:
        p = provenance(conn, cid)
        att = attestation(conn, cid, BASELINE)
        a, c, f, d = p["activity"], p["calculation"], p["factor"], p["document"]
        rows.append({
            "calc_id": cid, "activity_id": a["activity_id"], "facility": c["facility"],
            "type": a["activity_type"], "scope": a["scope"],
            "period_start": a["period_start"], "period_end": a["period_end"],
            "quantity": a["quantity"], "unit": a["unit"], "policy": c["policy"],
            "tco2e": c["tco2e"], "corrected": a["supersedes"] is not None,
            "ncv": a["ncv"], "ncv_unit": a["ncv_unit"], "oxidation": a["oxidation_factor"],
            "recorded_at": a["recorded_at"], "computed_at": c["computed_at"],
            "supersedes": a["supersedes"], "program": c["program"], "engine": c["engine_version"],
            "doc": None if d is None else {
                "id": d["document_id"], "filename": d["filename"], "sha256": d["sha256"],
                "hash_ok": d["hash_verified"], "issuer": d["issuer"], "type": d["doc_type"]},
            "factor": {"key": f["factor_key"], "value": f["value"], "unit": f["unit"],
                       "version": f["version_label"], "published_on": f["published_on"],
                       "valid_from": f["valid_from"], "valid_to": f["valid_to"],
                       "source_url": f["source_url"], "source_sha256": f["source_file_sha256"],
                       "publisher": f["publisher"], "dataset": f["dataset_name"]},
            "history": [{"activity_id": h["activity_id"], "quantity": h["quantity"],
                         "recorded_at": h["recorded_at"], "superseded_at": h["superseded_at"]}
                        for h in p["activity_history"]],
            "audit": [{"id": e["event_id"], "table": e["entity_table"], "row": e["entity_id"],
                       "action": e["action"], "actor": e["actor"], "reason": e["reason"],
                       "at": e["occurred_at"], "hash": e["event_hash"]}
                      for e in p["audit_events"]],
            "attestation": [{"policy": x["policy"], "used": x.get("used", False),
                             "tco2e": x.get("tco2e"), "factor_value": x.get("factor_value"),
                             "version": x.get("source_version"), "factor_year": x.get("factor_year"),
                             "published_on": x.get("published_on"), "vs_pct": x.get("vs_used_pct"),
                             "unavailable": x.get("unavailable")} for x in att["alternatives"]],
        })
    return plain(rows)


def audit_window(conn: psycopg.Connection) -> dict:
    """The events from the first correction to the last stored report: the story
    the console tells, and the part of the chain a viewer can re-hash."""
    first, last = conn.execute(
        "SELECT (SELECT min(event_id) FROM audit_event WHERE reason LIKE 'meter re-read%%'),"
        " (SELECT max(event_id) FROM audit_event WHERE entity_table = 'report')").fetchone()
    if first is None or last is None or not first < last:
        sys.exit("the sample needs a correction followed by reports: see docs/FRONTEND.md")
    events = conn.execute(
        "SELECT event_id, entity_table, entity_id, action, actor, reason, occurred_at, prev_hash,"
        " event_hash, fn_audit_payload(prev_hash, entity_table, entity_id, action, old_value,"
        "   new_value, actor, reason, occurred_at)"
        " FROM audit_event WHERE event_id BETWEEN %s AND %s ORDER BY event_id",
        (first, last)).fetchall()
    if len(events) > WINDOW_MAX:
        sys.exit(f"{len(events)} audit events in the window; the console shows at most {WINDOW_MAX}")
    window = []
    for i, (eid, table, row, action, actor, reason, at, prev, h, payload) in enumerate(events):
        if _sha(payload) != h:
            sys.exit(f"audit event {eid}: its payload does not hash to its stored hash")
        if i and prev != events[i - 1][8]:
            sys.exit(f"audit event {eid}: prev_hash does not match the event before it")
        window.append({"id": eid, "table": table, "row": row, "action": action,
                       "actor": actor or "", "reason": reason or "", "at": at.isoformat(),
                       "prev": prev, "hash": h, "payload": payload})
    broken = conn.execute("SELECT * FROM fn_verify_audit_chain()").fetchone()
    total = conn.execute("SELECT count(*) FROM audit_event").fetchone()[0]
    checked = anchor.check(conn)
    return {"chain_intact": broken is None, "total_events": total, "window": window,
            "anchors": {"count": checked["anchors"], "problems": checked["problems"]}}


def sampling(conn: psycopg.Connection, report_id: int) -> dict:
    # Drawing is idempotent, as in the API: a second build reuses the stored draw.
    existing = conn.execute(
        "SELECT s.sample_id FROM audit_sample s JOIN report r USING (report_id)"
        " WHERE s.report_id = %s AND s.confidence = %s AND s.tolerable_pct = %s"
        " AND s.seed = r.output_sha256 || ':' || %s",
        (report_id, SAMPLE["confidence"], SAMPLE["tolerable_pct"], SAMPLE["nonce"])).fetchone()
    sample_id = existing[0] if existing else pps.draw(
        conn, report_id, confidence=SAMPLE["confidence"],
        tolerable_pct=SAMPLE["tolerable_pct"], nonce=SAMPLE["nonce"], actor="build_console.py")
    s = pps.summary(conn, sample_id)
    items, _ = pps.population(conn, report_id)
    fresh = pps.select(items, Fraction(s["interval_tco2e"]), s["seed"])
    stored = {(i["activity_id"], i["stratum"]) for i in s["items"]}
    again = ({(k, "certain") for k, _ in fresh.certain} | {(k, "sampled") for k in fresh.sampled})
    if stored != again:
        sys.exit("the stored sample is not what a fresh draw gives")
    return {"report_id": report_id, "sample_id": sample_id, "seed": s["seed"],
            "confidence": s["confidence"], "tolerable_pct": s["tolerable_pct"],
            "nonce": SAMPLE["nonce"], "interval": s["interval_tco2e"],
            "items": [{"activity_id": i["activity_id"], "stratum": i["stratum"]}
                      for i in s["items"]]}


def collect() -> dict:
    with psycopg.connect(db.url()) as conn:
        reps = reports(conn)
        vintage = [r for r in reps if r["policy"] == "VINTAGE_MATCHED"][-1]
        # The audit window must be read before the sample is drawn: a draw is audited too.
        trail = audit_window(conn)
        ref = sampling(conn, vintage["id"])
        conn.commit()
        cov = coverage(conn, ORG_ID)
        data = {
            "meta": {
                "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "org": conn.execute("SELECT name FROM organisation WHERE org_id = %s",
                                    (ORG_ID,)).fetchone()[0],
                "facility": conn.execute("SELECT name FROM facility WHERE org_id = %s",
                                         (ORG_ID,)).fetchone()[0],
                "fy": FY, "baseline_year": BASELINE, "engine_version": ENGINE_VERSION,
                "deadline": "2026-07-31", "synthetic": True,
                "database": "development Postgres 18.4 (compatibility mode), migrations to 0014",
            },
            "policies": [{"code": p.value, "blurb": POLICY_DESCRIPTIONS[p]} for p in Policy],
            "reports": reps, "ledger": ledger(conn), "coverage": cov,
            "exceptions": plain(exceptions(conn, ORG_ID)), "audit": trail,
            "registry": registry(), "sampling": ref,
            "materiality": materiality(), "forecast": forecast(),
        }
    return data


def _blob(data: dict) -> str:
    # Safe inside <script type="application/json">: no "</script>", no U+2028/9.
    return (json.dumps(plain(data), separators=(",", ":"), ensure_ascii=False)
            .replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def render(data: dict) -> str:
    template = TEMPLATE.read_text(encoding="utf-8")
    if template.count(PLACEHOLDER) != 1:
        sys.exit(f"the template must contain {PLACEHOLDER} exactly once")
    return template.replace(PLACEHOLDER, _blob(data))


def _from_template(built: str) -> str:
    """The template re-rendered with the data already embedded in `built`."""
    marker = '<script id="data" type="application/json">'
    start = built.index(marker) + len(marker)
    return TEMPLATE.read_text(encoding="utf-8").replace(PLACEHOLDER, built[start:built.index("</script>", start)])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="fail unless the built file is exactly the template plus its embedded data (no database)")
    ap.add_argument("--template-only", action="store_true",
                    help="re-render the template with the data already embedded (no database)")
    args = ap.parse_args()
    if args.check:
        built = OUT.read_text(encoding="utf-8")
        if PLACEHOLDER in built or '"reports":[' not in built:
            sys.exit("console.html has no data: run scripts/build_console.py")
        if _from_template(built) != built:
            sys.exit("console.html is not its template plus its data: "
                     "run scripts/build_console.py --template-only")
        print("console.html equals its template plus its embedded data")
        return
    if args.template_only:
        # Database-backed data stays as it was; what needs no database is refreshed.
        built = OUT.read_text(encoding="utf-8")
        marker = '<script id="data" type="application/json">'
        start = built.index(marker) + len(marker)
        data = json.loads(built[start:built.index("</script>", start)])
        data.update(registry=registry(), materiality=materiality(), forecast=forecast())
        html = render(data)
    else:
        html = render(collect())
    OUT.write_text(html, encoding="utf-8", newline="\n")
    print(f"console -> {OUT.relative_to(ROOT)}  ({len(html.encode()):,} bytes)")


if __name__ == "__main__":
    main()
