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
canonical JSON), Factor registry (every CEA version by year), Sampling (the
PPS draw, redone in the browser and compared with the stored one), Audit trail
(chain check, and an attempt to rewrite history). Ctrl/Cmd+K opens a command
palette; keys 1 to 6 switch views.

## Design

Dark only. Six colour tokens (canvas, surface, ink, accent, ok, bad); every
other tone is a `color-mix` of those. System fonts, tabular numerals, 4px radius,
1px rules. No icon library, no CDN, no webfonts. Reduced motion is respected.
Plain CSS was used instead of Tailwind so the file works offline.

## Browser arithmetic

The page re-implements half-even rounding, emissions, SHA-256 (`crypto.subtle`),
the PPS draw and the Stringer-bound evaluation with exact BigInt arithmetic.
`tests/test_console.py` runs that block under node against the Python engine on
hundreds of cases, including exact-boundary ones, and skips if node is missing.

## Rebuild

```bash
python scripts/build_console.py              # needs the sample database
python scripts/build_console.py --template-only   # keep the data, redo the markup
python scripts/build_console.py --check
```
