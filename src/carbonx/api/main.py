"""HTTP API and the site: public pages (findings, registry, method) and the
workbench (ledger, evidence, reports). Static HTML, no build step.

    uvicorn carbonx.api.main:app --reload     # http://127.0.0.1:8000

No authentication: a local research prototype (multi-role RBAC is out of
scope). The actor recorded in the audit trail is the X-Actor header.
"""

import csv
import json
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from carbonx.db import url as database_url
from carbonx.engine import demo
from carbonx.engine.calculate import (
    calculate,
    edit_activity,
    record_activity,
    set_audit_context,
)
from carbonx.engine.exceptions import exceptions
from carbonx.engine.production import record_production
from carbonx.engine.provenance import attestation, coverage, plain, provenance
from carbonx.engine.report import EngineVersionMismatch, generate_report, regenerate
from carbonx.evidence.store import store_document
from carbonx.extraction import review
from carbonx.factors.registry import FactorNotFound, Policy
from carbonx.lifecycle import registry as credits
from carbonx.lifecycle.automaton import DELTA, TERMINAL, State, Symbol
from carbonx.materiality.assess import TRIGGERS, assess
from carbonx.uncertainty.propagate import for_report
from carbonx.units.core import DimensionError
from carbonx.units.lang import LangError, run

URL = database_url()
MAX_UPLOAD = 20 * 1024 * 1024
STATIC = Path(__file__).with_name("static")
ROOT = Path(__file__).resolve().parents[3]
FUELS = ROOT / "data" / "bee" / "fuel_factors.csv"
FIGURES = ROOT / "docs" / "figures"   # written by scripts/rq1_materiality.py, rq2_deltas.py
PAGES = {"findings", "registry", "method", "ledger", "evidence", "reports"}

app = FastAPI(title="CarbonX", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
if FIGURES.is_dir():
    app.mount("/figures", StaticFiles(directory=FIGURES), name="figures")


def connect() -> psycopg.Connection:
    """Fail fast and say why: a page must not hang because Postgres is down."""
    try:
        return psycopg.connect(URL, connect_timeout=3)
    except psycopg.OperationalError as e:
        raise HTTPException(503, "the database is not reachable; start it and "
                                 "reload this page") from e


def db() -> Iterator[psycopg.Connection]:
    # ponytail: one connection per request; add a pool if latency matters.
    with connect() as conn:  # commits on success, rolls back on error
        yield conn


Conn = Annotated[psycopg.Connection, Depends(db)]
Actor = Annotated[str, Header(alias="X-Actor")]


def _fail(e: Exception) -> HTTPException:
    if isinstance(e, psycopg.errors.ExclusionViolation):
        return HTTPException(409, "a record already exists for this facility, "
                                  "type and period: correct it instead")
    status = 404 if isinstance(e, LookupError) and not isinstance(e, FactorNotFound) else 400
    return HTTPException(status, f"{type(e).__name__}: {e}")


EXPECTED = (ValueError, LookupError, DimensionError, LangError, EngineVersionMismatch,
            psycopg.errors.ExclusionViolation)


class ActivityIn(BaseModel):
    facility_id: int
    activity_type: str = "grid_electricity"
    period_start: date
    period_end: date  # exclusive
    quantity: Decimal = Field(ge=0)
    unit: str = "kWh"
    document_id: int | None = None
    # Fuel activities ('fuel.<slug>') only: net calorific value and oxidation.
    ncv: Decimal | None = Field(default=None, gt=0)
    ncv_unit: str | None = None
    oxidation_factor: Decimal = Field(default=Decimal(1), gt=0, le=1)
    policy: Policy = Policy.VINTAGE_MATCHED
    baseline_year: str | None = None


class CorrectionIn(BaseModel):
    quantity: Decimal = Field(ge=0)
    reason: str = Field(min_length=1)
    baseline_year: str | None = None


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/{name}", include_in_schema=False)
def page(name: str) -> FileResponse:
    if name not in PAGES:
        raise HTTPException(404, "no such page")
    return FileResponse(STATIC / f"{name}.html")


@app.get("/api/factors")
def factors(conn: Conn, factor_key: str | None = None) -> list[dict[str, Any]]:
    """Without factor_key: the all-India grid series in the registry. With one:
    every published value of that series, by year and version."""
    with conn.cursor(row_factory=dict_row) as cur:
        if factor_key is None:
            return cur.execute(
                "SELECT factor_key, count(*) AS observations FROM emission_factor"
                " WHERE geography = 'IN' AND factor_key LIKE 'grid.%%'"
                " GROUP BY factor_key ORDER BY factor_key").fetchall()
        return plain(cur.execute(
            "SELECT lower(f.valid_time) AS fy_start, f.value,"
            " f.numerator_unit || '/' || f.denominator_unit AS unit,"
            " s.version_label, s.version_ordinal, s.published_on, s.source_url"
            " FROM emission_factor f JOIN factor_source s USING (source_id)"
            " WHERE f.geography = 'IN' AND f.factor_key = %s"
            " ORDER BY lower(f.valid_time), s.version_ordinal", (factor_key,)).fetchall())


class ProgramIn(BaseModel):
    program: str = Field(max_length=2000)


@app.post("/api/typecheck")
def typecheck(body: ProgramIn) -> dict[str, Any]:
    """Type-check and evaluate a program in the calculation language. A
    rejection is an answer, not a failure, so it is returned with status 200."""
    try:
        env = run(body.program)
    except (DimensionError, LangError) as e:
        return {"ok": False, "error": type(e).__name__, "message": str(e)}
    return {"ok": True, "bindings": [
        {"name": n, "exact": str(q.value), "value": f"{float(q.value):.9g}",
         "unit": q.unit.name} for n, q in env.items()]}


@app.get("/api/lifecycle")
def lifecycle() -> dict[str, Any]:
    """The credit automaton, as data: the page steps through this table."""
    return {"states": list(State), "symbols": list(Symbol), "initial": State.NONE,
            "terminal": sorted(TERMINAL),
            "delta": [{"from": s, "symbol": a, "to": t} for (s, a), t in DELTA.items()]}


@app.get("/api/facilities")
def facilities(conn: Conn) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT f.facility_id, f.name, f.state, o.org_id, o.name AS organisation"
            " FROM facility f JOIN organisation o USING (org_id)"
            " ORDER BY f.facility_id").fetchall()


@app.get("/api/fuels")
def fuels() -> list[dict[str, str]]:
    """BEE Annexure IV fuels, for activity type 'fuel.<slug>'."""
    with FUELS.open(encoding="utf-8") as fh:
        return [{"slug": r["slug"], "fuel": r["fuel"],
                 "co2e_t_per_tj": r["co2e_t_per_tj"]} for r in csv.DictReader(fh)]


@app.get("/api/policies")
def policies() -> list[str]:
    return [p.value for p in Policy]


@app.post("/api/documents")
async def upload(
    request: Request, conn: Conn, filename: str,
    doc_type: str = "electricity_bill", facility_id: int | None = None,
    x_actor: Actor = "workbench",
) -> dict[str, Any]:
    """Raw file bytes as the request body (no multipart dependency needed)."""
    data = await request.body()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, f"document larger than {MAX_UPLOAD} bytes")
    try:
        set_audit_context(conn, x_actor, None)
        d = store_document(conn, data=data, filename=filename, doc_type=doc_type,
                           facility_id=facility_id,
                           mime_type=request.headers.get("content-type"))
    except EXPECTED as e:
        raise _fail(e) from e
    return plain(d.__dict__)


@app.post("/api/activities")
def create_activity(body: ActivityIn, conn: Conn,
                    x_actor: Actor = "workbench") -> dict[str, Any]:
    try:
        # One transaction for both: an activity whose calculation fails (e.g. no
        # factor under this policy) must not be left behind. The dependency's
        # own commit cannot be relied on here: FastAPI turns HTTPException into
        # a response before the dependency exits, so it would commit.
        with conn.transaction():
            activity_id = record_activity(
                conn, facility_id=body.facility_id, activity_type=body.activity_type,
                period_start=body.period_start, period_end=body.period_end,
                quantity=body.quantity, unit=body.unit, document_id=body.document_id,
                actor=x_actor, ncv=body.ncv, ncv_unit=body.ncv_unit,
                oxidation_factor=body.oxidation_factor)
            c = calculate(conn, activity_id, body.policy,
                          baseline_year=body.baseline_year)
    except EXPECTED as e:
        raise _fail(e) from e
    return {"activity_id": activity_id, "calculation_id": c.calculation_id,
            "tco2e": format(c.tco2e, "f")}


@app.patch("/api/activities/{activity_id}")
def correct_activity(activity_id: int, body: CorrectionIn, conn: Conn,
                     x_actor: Actor = "workbench") -> dict[str, Any]:
    try:
        new_id, calcs = edit_activity(conn, activity_id, quantity=body.quantity,
                                      reason=body.reason, actor=x_actor,
                                      baseline_year=body.baseline_year)
    except EXPECTED as e:
        raise _fail(e) from e
    return {"activity_id": new_id, "calculations": [
        {"calculation_id": c.calculation_id, "policy": c.policy.value,
         "tco2e": format(c.tco2e, "f")} for c in calcs]}


@app.get("/api/emissions")
def emissions(conn: Conn, facility_id: Annotated[int | None, Query()] = None,
              ) -> list[dict[str, Any]]:
    """Current ledger: one row per current calculation."""
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute("""
            SELECT l.calculation_id, l.facility_id, f.name AS facility, l.scope,
                   lower(l.period) AS period_start, upper(l.period) AS period_end,
                   l.tco2e, a.activity_id, a.activity_type, a.quantity, a.unit,
                   p.code AS policy, a.document_id
            FROM ledger_entry l
            JOIN calculation c USING (calculation_id)
            JOIN activity a ON a.activity_id = c.activity_id
            JOIN facility f ON f.facility_id = l.facility_id
            JOIN resolution_policy p ON p.policy_id = c.policy_id
            WHERE upper_inf(l.system_time_range)
              AND (%(f)s::bigint IS NULL OR l.facility_id = %(f)s)
            ORDER BY lower(l.period), l.calculation_id""", {"f": facility_id}).fetchall()
    return plain(rows)


@app.get("/api/calculations/{calculation_id}/provenance")
def calculation_provenance(calculation_id: int, conn: Conn) -> dict[str, Any]:
    try:
        return provenance(conn, calculation_id)
    except LookupError as e:
        raise _fail(e) from e


class ReportIn(BaseModel):
    org_id: int
    compliance_year: str = "FY2025-26"
    policy: Policy = Policy.VINTAGE_MATCHED
    baseline_year: str | None = None


def _report_summary(output: str, report_id: int, sha256: str) -> dict[str, Any]:
    out = json.loads(output)
    return {"report_id": report_id, "policy": out["policy"], "as_of": out["as_of"],
            "total_tco2e": out["totals"]["total_tco2e"], "gei": out["gei"],
            "facilities": out["facilities"], "unresolved": len(out["unresolved"]),
            "sha256": sha256}


class WordIn(BaseModel):
    symbols: list[Symbol] = Field(max_length=20)


@app.post("/api/lifecycle/try")
def lifecycle_try(body: WordIn) -> dict[str, Any]:
    """Run a sequence against the database's own triggers (migration 0009), on a
    throwaway credit between two throwaway organisations. Always rolled back.
    Stops at the first move the database refuses and returns its message."""
    steps: list[dict[str, Any]] = []
    with connect() as conn:
        try:
            orgs = [conn.execute("INSERT INTO organisation (name) VALUES (%s)"
                                 " RETURNING org_id", (f"lifecycle demo {i}",)
                                 ).fetchone()[0] for i in (1, 2)]  # type: ignore[index]
            credit_id = credits.create_credit(conn, "FY2025-26", Decimal(1))
            holder = 1  # index into orgs; a transfer goes to the other one
            for symbol in body.symbols:
                try:
                    with conn.transaction():
                        moves = symbol in (Symbol.ISSUE, Symbol.TRANSFER)
                        if moves:
                            holder = 1 - holder
                        state = credits.apply(conn, credit_id, symbol,
                                              orgs[holder] if moves else None)
                except psycopg.errors.RaiseException as e:
                    message = (e.diag.message_primary or str(e)).replace(
                        f"credit {credit_id}: ", "")
                    steps.append({"symbol": symbol, "ok": False, "error": message})
                    break
                steps.append({"symbol": symbol, "ok": True, "state": state})
        finally:
            conn.rollback()
    return {"steps": steps, "accepted": all(s["ok"] for s in steps)}


@app.get("/api/reports")
def list_reports(conn: Conn) -> list[dict[str, Any]]:
    """Stored reports, newest first."""
    with conn.cursor(row_factory=dict_row) as cur:
        return plain(cur.execute(
            "SELECT r.report_id, o.name AS organisation, r.compliance_year,"
            " p.code AS policy, r.as_of, r.total_tco2e, r.gei,"
            " r.output_sha256 AS sha256 FROM report r"
            " JOIN organisation o USING (org_id)"
            " JOIN resolution_policy p USING (policy_id)"
            " ORDER BY r.report_id DESC LIMIT 100").fetchall())


@app.post("/api/reports")
def create_report(body: ReportIn, conn: Conn,
                  x_actor: Actor = "workbench") -> dict[str, Any]:
    """Generate and store a report AS OF now (immutable, hashed)."""
    try:
        set_audit_context(conn, x_actor, None)
        r = generate_report(conn, body.org_id, body.compliance_year, body.policy,
                            body.baseline_year)
    except EXPECTED as e:
        raise _fail(e) from e
    return _report_summary(r.output, r.report_id, r.sha256)


@app.get("/api/reports/{report_id}/uncertainty")
def report_uncertainty(report_id: int, conn: Conn) -> dict[str, Any]:
    """The band from published factor ranges only (IPCC 2006). Emissions whose
    factor has no published range are reported as `unquantified`, not guessed."""
    try:
        b = for_report(conn, report_id)
    except EXPECTED as e:
        raise _fail(e) from e
    return plain({"total": b.total, "low": b.low, "high": b.high,
                  "low_if_independent": b.low_if_independent,
                  "high_if_independent": b.high_if_independent,
                  "unquantified": b.unquantified, "basis": list(b.basis)})


class MaterialityIn(BaseModel):
    trigger_type: str = "factor_supersession"


@app.get("/api/materiality-triggers")
def materiality_triggers() -> list[str]:
    return sorted(TRIGGERS)


@app.post("/api/reports/{report_id}/materiality")
def report_materiality(report_id: int, body: MaterialityIn, conn: Conn,
                       x_actor: Actor = "workbench") -> dict[str, Any]:
    """Compare a stored report with the same report computed now, against the
    5% threshold, and store the assessment with a drafted disclosure."""
    try:
        a = assess(conn, report_id, body.trigger_type, actor=x_actor)
    except EXPECTED as e:
        raise _fail(e) from e
    return plain(a.__dict__)


class DemoIn(BaseModel):
    org_id: int
    compliance_year: str = "FY2025-26"


@app.post("/api/demo/reproducibility")
def demo_reproducibility(body: DemoIn) -> dict[str, Any]:
    """Invariant 1, before and after a fictional factor revision and a backdated
    correction. Runs on its own connection and is always rolled back."""
    with connect() as conn:
        try:
            return demo.run(conn, body.org_id, body.compliance_year)
        except EXPECTED as e:
            raise _fail(e) from e
        finally:
            conn.rollback()


class ProductionIn(BaseModel):
    facility_id: int
    product_code: str = Field(min_length=1)
    unit: str = "t"
    period_start: date
    period_end: date  # exclusive
    quantity: Decimal = Field(gt=0)
    document_id: int | None = None


@app.post("/api/production")
def create_production(body: ProductionIn, conn: Conn,
                      x_actor: Actor = "workbench") -> dict[str, Any]:
    """Output for a period: the denominator of emission intensity (GEI)."""
    try:
        pid = record_production(
            conn, facility_id=body.facility_id, product_code=body.product_code,
            unit=body.unit, period_start=body.period_start, period_end=body.period_end,
            quantity=body.quantity, document_id=body.document_id, actor=x_actor)
    except EXPECTED as e:
        raise _fail(e) from e
    return {"production_id": pid}


@app.get("/api/reports/{report_id}/verify")
def verify_report(report_id: int, conn: Conn) -> dict[str, Any]:
    """Regenerate a stored report AS OF its own time and compare byte for byte."""
    stored = conn.execute("SELECT output, output_sha256 FROM report WHERE report_id = %s",
                          (report_id,)).fetchone()
    if stored is None:
        raise HTTPException(404, f"no report {report_id}")
    try:
        again = regenerate(conn, report_id)
    except EXPECTED as e:
        raise _fail(e) from e
    return {"report_id": report_id, "stored_sha256": stored[1],
            "regenerated_sha256": again.sha256,
            "byte_identical": again.output == stored[0]}


@app.post("/api/documents/{document_id}/extract")
def extract(document_id: int, conn: Conn, x_actor: Actor = "workbench") -> dict[str, Any]:
    """Read consumption_kwh from a stored document. The result is queued for a
    person to confirm; it is never used on the model's authority alone."""
    try:
        set_audit_context(conn, x_actor, None)
        return plain(review.extract_document(conn, document_id))
    except EXPECTED as e:
        raise _fail(e) from e
    except ImportError as e:  # scikit-learn missing or blocked on this machine
        raise HTTPException(503, f"the bill reader cannot load here: {e}") from e


@app.get("/api/review-queue")
def review_queue(conn: Conn) -> list[dict[str, Any]]:
    """Unconfirmed extractions, least confident first."""
    return plain(review.review_queue(conn))


@app.post("/api/extractions/{extraction_id}/confirm")
def confirm_extraction(extraction_id: int, conn: Conn,
                       x_actor: Actor = "workbench") -> dict[str, Any]:
    try:
        set_audit_context(conn, x_actor, "confirmed against the document")
        review.confirm(conn, extraction_id)
    except EXPECTED as e:
        raise _fail(e) from e
    return {"extraction_id": extraction_id, "human_verified": True}


@app.get("/api/exceptions")
def exception_log(org_id: int, conn: Conn) -> list[dict[str, Any]]:
    """Conditions a verifier should look at: missing evidence, hash mismatches,
    corrections after a report, a broken audit chain, unconfirmed extractions."""
    return plain(exceptions(conn, org_id))


@app.get("/api/calculations/{calculation_id}/attestation")
def factor_attestation(calculation_id: int, conn: Conn,
                       baseline_year: str | None = None) -> dict[str, Any]:
    """Which factor version a calculation used, and the figure under every
    other resolution policy as of the same moment."""
    try:
        return attestation(conn, calculation_id, baseline_year)
    except EXPECTED as e:
        raise _fail(e) from e


@app.get("/api/coverage")
def audit_coverage(org_id: int, conn: Conn) -> dict[str, Any]:
    """Share of currently reported tCO2e with a hashed source document."""
    return coverage(conn, org_id)

