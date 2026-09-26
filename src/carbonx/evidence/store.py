"""Evidence store: every source document is hashed (SHA-256) at upload.

Files are stored under their hash in EVIDENCE_DIR (gitignored: no raw bills in
the repo, ever). The same bytes uploaded twice are the same document row, by
the UNIQUE (sha256) constraint. This is tamper-evidence: a later mismatch
between a file and its recorded hash is detectable, not preventable.
"""

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import psycopg

EVIDENCE_DIR = Path(os.environ.get(
    "CARBONX_EVIDENCE_DIR", Path(__file__).resolve().parents[3] / "data" / "evidence"))
DOC_TYPES = {"electricity_bill", "fuel_invoice", "meter_reading", "production_log"}


@dataclass(frozen=True)
class Document:
    document_id: int
    filename: str
    sha256: str
    uploaded_at: datetime
    created: bool  # False when these exact bytes were already stored


def store_document(
    conn: psycopg.Connection, *, data: bytes, filename: str, doc_type: str,
    facility_id: int | None = None, issuer: str | None = None,
    mime_type: str | None = None, redacted: bool = False,
) -> Document:
    if doc_type not in DOC_TYPES:
        raise ValueError(f"doc_type must be one of {sorted(DOC_TYPES)}")
    if not data:
        raise ValueError("empty document")
    digest = hashlib.sha256(data).hexdigest()
    path = EVIDENCE_DIR / digest[:2] / digest
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        tmp.write_bytes(data)
        tmp.replace(path)  # atomic: no half-written evidence under a real hash

    row = conn.execute(
        "INSERT INTO source_document (facility_id, doc_type, filename,"
        " storage_path, sha256, mime_type, issuer, redacted)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
        " ON CONFLICT (sha256) DO NOTHING"
        " RETURNING document_id, filename, sha256, uploaded_at",
        (facility_id, doc_type, Path(filename).name, str(path), digest,
         mime_type, issuer, redacted),
    ).fetchone()
    if row:
        return Document(*row, created=True)
    row = conn.execute(
        "SELECT document_id, filename, sha256, uploaded_at FROM source_document"
        " WHERE sha256 = %s", (digest,)).fetchone()
    assert row is not None
    return Document(*row, created=False)


def verify_document(conn: psycopg.Connection, document_id: int) -> bool:
    """Does the stored file still hash to the value recorded at upload?"""
    row = conn.execute("SELECT storage_path, sha256 FROM source_document"
                       " WHERE document_id = %s", (document_id,)).fetchone()
    if row is None:
        raise LookupError(f"no document {document_id}")
    path = Path(row[0])
    return path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == row[1]
