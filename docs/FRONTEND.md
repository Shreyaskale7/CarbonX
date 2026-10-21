# The console

`/console` (file: `src/carbonx/api/static/console.html`) is the verifier's
workbench: one self-contained HTML file with no network access, built from real
output of the engine, the database and the CEA registry. It opens by
double-click as well as from the server.

## What it is, and is not

- It is a **snapshot**. `scripts/build_console.py` runs the engine against the
  sample database, embeds the result as JSON, and checks it on the way in
  (report hashes, audit hash links, stored sample equals a fresh draw).
- The plant, bills and quantities are **synthetic**. The CEA registry is real.
- The correction dialog is a **preview**: nothing is stored.
- "Re-hash" hashes the stored report text in the browser. It does not
  regenerate the report from the database.
- Research prototype. It does not verify emissions or issue assurance.

## Views

Overview (headline figures, reproducibility check), Ledger (every figure back to
its bill, factor row and audit events), Reports (re-hash, compare two, download
canonical JSON), Factor registry (every CEA version by year), Materiality (RQ1
and RQ3: a slider for the Scope 2 share of the target basis, and what each kind
of factor change and each reading of BEE's rule does at that share), Forecast
(the leakage-safe backtest of one-year-ahead factor nowcasts; proposed scope,
unsigned), Sampling (the PPS draw, redone in the browser and compared with the
stored one), Audit trail (chain check, and an attempt to rewrite history).
Ctrl/Cmd+K opens a command palette; keys 1 to 8 switch views.

Materiality and Forecast are computed by the same functions that write
`docs/RQ1_RESULTS.md`, `docs/RQ3_COMPLIANCE.md` and `docs/NOWCAST_RESULTS.md`
(`rq1_materiality.effects`, `rq3_compliance.readings`, `carbonx.forecast.nowcast`),
not re-implemented. No sector is placed on the Materiality curve: no cited sector
shares exist yet. Uncertainty bands are in the Reports view; the bill-extraction
review queue is not in the console (it needs uploaded documents; see the
workbench pages).

## Design

Dark only. Six colour tokens (canvas, surface, ink, accent, ok, bad); every
other tone is a `color-mix` of those. System fonts, tabular numerals, 4px radius,
1px rules. No icon library, no CDN, no webfonts. Reduced motion is respected.
Plain CSS was used instead of Tailwind so the file works offline.

## Browser arithmetic

The page re-implements half-even rounding, emissions, SHA-256 (`crypto.subtle`),
the PPS draw and the Stringer-bound evaluation with exact BigInt arithmetic.
`tests/test_console.py` runs that block under node against the Python engine on
hundreds of cases, including exact-boundary ones, and skips if node is missing. The
materiality arithmetic and its formatter are compared at every whole-number share,
including values that sit exactly on a rounding tie, where JavaScript's `toFixed`
and Python's `format` disagree. Another test fails if the embedded registry,
materiality or forecast data differs from what the code produces now.

## Rebuild

```bash
python scripts/build_console.py              # needs the sample database
python scripts/build_console.py --template-only   # redo the markup; refreshes the registry,
                                                  # materiality and forecast, keeps the database data
python scripts/build_console.py --check
```
