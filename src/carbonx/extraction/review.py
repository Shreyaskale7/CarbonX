"""Store extractions and queue them for human review.

The model's confidence ranks right from wrong on unseen layouts but is not a
calibrated probability (docs/EXTRACTION.md). So an extraction is never used
on its own authority: it waits in the review queue, least confident first,
until a person confirms it.

The model here is trained on SYNTHETIC bills (there are no real ones yet).
MODEL_VERSION says so, and is stored with every extraction.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import psycopg
from psycopg.rows import dict_row

from carbonx.extraction.synthetic import SEEN, corpus

# The model (scikit-learn) is imported where it is used, so the queue, the
# confirm step and the rest of the API work on a machine where it cannot load.
if TYPE_CHECKING:
    from carbonx.extraction.extract import ConsumptionModel

MODEL_VERSION = "consumption-lr-synthetic-v1"


@lru_cache(maxsize=1)
def model() -> ConsumptionModel:
    """Trained once per process, on the synthetic training layouts."""
    bills = corpus(240, SEEN, seed=20260926)
    from carbonx.extraction.extract import ConsumptionModel
    m = ConsumptionModel()
    m.fit_leave_one_layout_out([b.text for b in bills], [b.kwh for b in bills],
                               [b.layout for b in bills])
    return m


def document_text(conn: psycopg.Connection, document_id: int) -> str:
    row = conn.execute("SELECT storage_path, mime_type, filename FROM source_document"
                       " WHERE document_id = %s", (document_id,)).fetchone()
    if row is None:
        raise LookupError(f"no document {document_id}")
    path, mime, filename = Path(row[0]), row[1] or "", row[2]
    if "pdf" in mime or filename.lower().endswith(".pdf"):
        from carbonx.extraction.extract import text_from_pdf
        return text_from_pdf(path)
    return path.read_text(encoding="utf-8", errors="replace")


def extract_document(conn: psycopg.Connection, document_id: int) -> dict[str, Any]:
    """Run the model on a stored document and record what it read."""
    e = model().predict(document_text(conn, document_id))
    with conn.cursor(row_factory=dict_row) as cur:
        row = cur.execute(
            "INSERT INTO extraction_result (document_id, field_name, raw_value,"
            " parsed_value, unit, confidence, model_version)"
            " VALUES (%s, 'consumption_kwh', %s, %s, 'kWh', %s, %s)"
            " RETURNING extraction_id, document_id, field_name, raw_value, parsed_value,"
            " unit, confidence, model_version, human_verified",
            (document_id, e.raw, e.value,
             None if e.confidence is None else round(e.confidence, 4), MODEL_VERSION),
        ).fetchone()
    assert row is not None
    return row


def review_queue(conn: psycopg.Connection, limit: int = 50) -> list[dict[str, Any]]:
    """Unconfirmed extractions, least confident first."""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT e.extraction_id, e.document_id, d.filename, e.field_name,"
            " e.raw_value, e.parsed_value, e.unit, e.confidence, e.model_version,"
            " e.created_at FROM extraction_result e"
            " JOIN source_document d USING (document_id)"
            " WHERE NOT e.human_verified"
            " ORDER BY e.confidence ASC NULLS FIRST, e.extraction_id LIMIT %s",
            (limit,)).fetchall()


def confirm(conn: psycopg.Connection, extraction_id: int) -> None:
    """A person has checked this value against the document."""
    done = conn.execute("UPDATE extraction_result SET human_verified = TRUE"
                        " WHERE extraction_id = %s RETURNING extraction_id",
                        (extraction_id,)).fetchone()
    if done is None:
        raise LookupError(f"no extraction {extraction_id}")
