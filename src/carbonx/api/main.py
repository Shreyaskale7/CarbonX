"""HTTP API and the Phase 4 provenance page.

    uvicorn carbonx.api.main:app --reload     # http://127.0.0.1:8000

No authentication: a local research prototype (multi-role RBAC is out of
scope). The actor recorded in the audit trail is the X-Actor header.
"""

import os
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from carbonx.engine.calculate import (
    calculate,
    edit_activity,
    record_activity,
    set_audit_context,
)
from carbonx.engine.provenance import plain, provenance
from carbonx.evidence.store import store_document
from carbonx.factors.registry import FactorNotFound, Policy
from carbonx.units.core import DimensionError
from carbonx.units.lang import LangError

URL = os.environ.get(
    "DATABASE_URL", "postgresql://carbonx:carbonx@localhost:5432/carbonx"
).replace("postgresql+psycopg://", "postgresql://")
MAX_UPLOAD = 20 * 1024 * 1024
PAGE = Path(__file__).with_name("static") / "index.html"

app = FastAPI(title="CarbonX", version="0.1.0")


def db() -> Iterator[psycopg.Connection]:
    # ponytail: one connection per request; add a pool if latency matters.
    with psycopg.connect(URL) as conn:  # commits on success, rolls back on error
        yield conn


Conn = Annotated[psycopg.Connection, Depends(db)]
Actor = Annotated[str, Header(alias="X-Actor")]


def _fail(e: Exception) -> HTTPException:
    if isinstance(e, psycopg.errors.ExclusionViolation):
        return HTTPException(409, "an activity already exists for this facility, "
                                  "type and period: correct it instead")
    status = 404 if isinstance(e, LookupError) and not isinstance(e, FactorNotFound) else 400
    return HTTPException(status, f"{type(e).__name__}: {e}")


EXPECTED = (ValueError, LookupError, DimensionError, LangError,
            psycopg.errors.ExclusionViolation)


class ActivityIn(BaseModel):
    facility_id: int
    activity_type: str = "grid_electricity"
    period_start: date
    period_end: date  # exclusive
    quantity: Decimal = Field(ge=0)
    unit: str = "kWh"
    document_id: int | None = None
    policy: Policy = Policy.VINTAGE_MATCHED
    baseline_year: str | None = None


class CorrectionIn(BaseModel):
    quantity: Decimal = Field(ge=0)
    reason: str = Field(min_length=1)
    baseline_year: str | None = None


@app.get("/", include_in_schema=False)
def page() -> FileResponse:
    return FileResponse(PAGE)


@app.get("/api/facilities")
def facilities(conn: Conn) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT f.facility_id, f.name, f.state, o.org_id, o.name AS organisation"
            " FROM facility f JOIN organisation o USING (org_id)"
            " ORDER BY f.facility_id").fetchall()


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
        activity_id = record_activity(
            conn, facility_id=body.facility_id, activity_type=body.activity_type,
            period_start=body.period_start, period_end=body.period_end,
            quantity=body.quantity, unit=body.unit, document_id=body.document_id,
            actor=x_actor)
        c = calculate(conn, activity_id, body.policy, baseline_year=body.baseline_year)
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
