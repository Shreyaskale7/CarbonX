"""Seed a SYNTHETIC organisation, facility and FY2025-26 electricity activity.

Everything here is invented: no real entity, no real bill (the repo never
holds real utility bills). The "bill" is a generated text file whose first
line says it is synthetic, stored and hashed like any other evidence.
Idempotent: does nothing if the sample organisation already exists.
"""
import os
from datetime import date
from decimal import Decimal

import psycopg

from carbonx.engine.calculate import record_activity, set_audit_context
from carbonx.evidence.store import store_document

URL = os.environ.get(
    "DATABASE_URL", "postgresql://carbonx:carbonx@localhost:5432/carbonx"
).replace("postgresql+psycopg://", "postgresql://")
ORG = "Sample Aluminium Works (SYNTHETIC)"
# Synthetic monthly grid consumption, kWh, April 2025 to March 2026.
MONTHLY_KWH = [1_180_000, 1_205_000, 1_150_000, 1_120_000, 1_135_000, 1_160_000,
               1_190_000, 1_210_000, 1_240_000, 1_255_000, 1_230_000, 1_265_000]

with psycopg.connect(URL) as conn:
    set_audit_context(conn, "seed_sample.py", "synthetic sample data")
    if conn.execute("SELECT 1 FROM organisation WHERE name = %s", (ORG,)).fetchone():
        print("sample organisation already seeded")
        raise SystemExit(0)
    (org_id,) = conn.execute(
        "INSERT INTO organisation (name, ccts_sector, is_obligated)"
        " VALUES (%s, 'aluminium', FALSE) RETURNING org_id", (ORG,)).fetchone()
    (facility_id,) = conn.execute(
        "INSERT INTO facility (org_id, name, state, grid_region)"
        " VALUES (%s, 'Sample smelter (SYNTHETIC)', 'Odisha', 'IN') RETURNING facility_id",
        (org_id,)).fetchone()
    for month, kwh in enumerate(MONTHLY_KWH):
        y, m = (2025, 4 + month) if month < 9 else (2026, month - 8)
        start = date(y, m, 1)
        end = date(y + (m == 12), m % 12 + 1, 1)
        bill = (f"SYNTHETIC SAMPLE BILL - not a real utility bill.\n"
                f"Consumer: {ORG}\nPeriod: {start} to {end} (exclusive)\n"
                f"Grid consumption: {kwh} kWh\n").encode()
        doc = store_document(conn, data=bill, filename=f"synthetic_bill_{start:%Y_%m}.txt",
                             doc_type="electricity_bill", facility_id=facility_id,
                             issuer="SYNTHETIC", mime_type="text/plain", redacted=True)
        record_activity(conn, facility_id=facility_id, activity_type="grid_electricity",
                        period_start=start, period_end=end, quantity=Decimal(kwh),
                        unit="kWh", document_id=doc.document_id, actor="seed_sample.py",
                        reason="synthetic sample data")
    print(f"seeded org {org_id}, facility {facility_id}, {len(MONTHLY_KWH)} monthly "
          "activities with synthetic bills")
