"""Seed a SYNTHETIC organisation, facility, FY2025-26 electricity, fuel and production.

Everything here is invented: no real entity, no real bill (the repo never
holds real utility bills). The "bill" is a generated text file whose first
line says it is synthetic, stored and hashed like any other evidence.
Idempotent: does nothing if the sample organisation already exists.
"""
from datetime import date
from decimal import Decimal

import psycopg

from carbonx import db
from carbonx.engine.calculate import record_activity, set_audit_context
from carbonx.engine.production import record_production
from carbonx.evidence.store import store_document

URL = db.url()
ORG = "Sample Aluminium Works (SYNTHETIC)"
# Synthetic monthly grid consumption, kWh, April 2025 to March 2026.
MONTHLY_KWH = [1_180_000, 1_205_000, 1_150_000, 1_120_000, 1_135_000, 1_160_000,
               1_190_000, 1_210_000, 1_240_000, 1_255_000, 1_230_000, 1_265_000]
# Synthetic aluminium output, tonnes: about 14 MWh of electricity per tonne
# (order of magnitude for primary smelting), with made-up monthly variation.
MONTHLY_TONNES = [84.2, 86.5, 81.9, 80.3, 81.4, 82.6, 85.1, 86.7, 88.4, 89.9, 87.6, 90.8]
# Synthetic natural gas for furnaces, tonnes, with a made-up but plausible NCV.
# It gives the sample a Scope 1 stream, so GEI covers combustion as BEE's
# 2024-27 basis does, and the report has a factor with a published range.
MONTHLY_GAS_T = [41, 43, 40, 39, 40, 41, 42, 43, 45, 46, 44, 46]
GAS_NCV_GJ_PER_T = Decimal("48.0")

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
        record_activity(conn, facility_id=facility_id, activity_type="fuel.natural_gas",
                        period_start=start, period_end=end,
                        quantity=Decimal(MONTHLY_GAS_T[month]), unit="t",
                        ncv=GAS_NCV_GJ_PER_T, ncv_unit="GJ/t", actor="seed_sample.py",
                        reason="synthetic sample data (no evidence document)")
        record_production(conn, facility_id=facility_id, product_code="aluminium_ingot",
                          unit="t", period_start=start, period_end=end,
                          quantity=Decimal(str(MONTHLY_TONNES[month])),
                          actor="seed_sample.py", reason="synthetic sample data")
    print(f"seeded org {org_id}, facility {facility_id}, {len(MONTHLY_KWH)} monthly "
          "electricity, gas and production records, all synthetic")
