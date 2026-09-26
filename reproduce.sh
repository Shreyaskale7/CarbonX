#!/usr/bin/env bash
# One command, whole pipeline, sample data. Evaluators check for this.
set -euo pipefail
echo "[1/6] database"        && alembic upgrade head
echo "[2/6] resolution policies" && python scripts/seed_policies.py
echo "[3/6] CEA factors"     && python scripts/load_cea.py --from data/raw/cea
echo "[4/6] sample facility" && python scripts/seed_sample.py
echo "[5/6] calculate"       && python -m carbonx.engine.calculate --org 1 --fy FY2025-26
echo "[6/6] report + verify" && python -m carbonx.engine.report --org 1 --fy FY2025-26 --verify
echo "done. api: uvicorn carbonx.api.main:app --reload"
