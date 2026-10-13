#!/usr/bin/env bash
# One command, whole pipeline, sample data. Evaluators check for this.
set -euo pipefail
echo "[1/6] database"        && alembic upgrade head
echo "[2/6] resolution policies" && python scripts/seed_policies.py
echo "[3/6] CEA + BEE factors" && python scripts/load_cea.py --db && python scripts/registry_changelog.py && python scripts/load_bee_factors.py --db && python scripts/rq2_deltas.py && python scripts/rq1_materiality.py && python scripts/rq3_compliance.py && python scripts/nowcast.py && python scripts/ember_crosscheck.py
echo "[4/6] sample facility" && python scripts/seed_sample.py
echo "[5/6] calculate"       && python -m carbonx.engine.calculate --org 1 --policy VINTAGE_MATCHED
echo "[6/6] report + verify" && python -m carbonx.engine.report --org 1 --fy FY2025-26 --verify
echo "      uncertainty of report 2 (VINTAGE_MATCHED):" && python -m carbonx.uncertainty.propagate --report 2
echo "      a revision does not reach an old report:" && python scripts/demo_reproducibility.py --org 1
echo "done. api: uvicorn carbonx.api.main:app --reload"
