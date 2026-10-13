# Open registry of India's CEA grid emission factors, v1.0–v22.0

A machine-readable version history of the Central Electricity Authority's
*CO2 Baseline Database for the Indian Power Sector*: every factor in every
published version, each traced to the workbook cell it came from.

**2,071 factors · 23 versions (Nov 2006 – Aug 2026) · FY2000-01 to FY2025-26.**

This is a research dataset built by a student project (CarbonX, RVCE). It is
**not** an official CEA product. For any regulatory use, go to the CEA
workbooks themselves; the URLs and SHA-256 hashes below let you check that the
file you have is the one read here.

> **Not yet released.** Before publishing (for example on Zenodo), the team
> must choose a licence and confirm the terms under which data derived from
> CEA's publications may be redistributed. Neither is decided here. Authors
> and citation details are also still to be added.

## Files

| File | Rows | What it is |
|---|---|---|
| `factors.csv` | 2,071 | one row per (version, financial year, factor, geography) |
| `versions.csv` | 23 | one row per CEA version: date, year covered, source URLs and hashes |
| `manifest.json` | 23 | download record: URL, SHA-256, size, retrieval time per file |
| `CHANGELOG.md` | 23 | per version: years first published, values restated, series added or missing |

### `factors.csv`

| Column | Meaning |
|---|---|
| `version_label` | CEA version, e.g. `v22.0` |
| `fy` | Indian financial year the factor describes, e.g. `FY2025-26` (April–March) |
| `factor_key` | which factor (see below) |
| `geography` | `IN` for all-India; regional grids for older versions (see below) |
| `value` | the factor, as the full floating-point value stored in the workbook |
| `unit` | always `tCO2/MWh` (CO2, not CO2e) |
| `cell` | sheet and cell it was read from, e.g. `Results!F13` |
| `cea_label` | CEA's own row label, verbatim |

### `versions.csv`

| Column | Meaning |
|---|---|
| `version_ordinal` | sorts versions: major×10 + minor (v1.1 → 11, v22.0 → 220) |
| `stated_date` | the DATE cell in the workbook's Results sheet |
| `date_precision` | `day`, or `month` when CEA wrote only a month ("Apr 16"); then `stated_date` is the 1st |
| `covers_fy` | the newest financial year in that version's factor tables |
| `cea_outdated` | `True` where CEA's page marks the version "OUTDATED" (v1.0–v11.0) |
| `workbook` | the workbook file read (inside the zip, for older versions) |
| `database_url`, `database_sha256` | where it was downloaded from, and its hash |
| `user_guide_url`, `user_guide_sha256` | the matching user guide |

## Factor keys

`grid.<metric>.<imports>`, where `<imports>` is `excl_imports` or
`incl_imports` (CEA publishes most factors both ways: excluding and including
inter-grid imports).

| Metric | CEA's label(s) |
|---|---|
| `weighted_avg` | Weighted Average Emission Rate |
| `weighted_avg_incl_re` | Weighted Average Emission Rate Incl. RES (v18–v19 only) |
| `weighted_avg_incl_re_captive` | Grid Emission Factor (for net effective injection into grid) [v19]; Weighted Average Emission Factor (for net effective injection into grid) [v20]; Weighted Average Grid Emission Rate (Incl. RES,Captive) [v21–v22] |
| `operating_margin` | Simple Operating Margin |
| `build_margin` | Build Margin (never import-adjusted, so only `excl_imports`) |
| `combined_margin` | Combined Margin |

**Geographies.** `IN` (all-India) throughout. v1.0–v3.0 also give five regional
grids (`IN-N`, `IN-E`, `IN-S`, `IN-W`, `IN-NE`); v4.0–v10.0 give two
(`IN-NEWNE`, `IN-S`). From v11.0 only all-India figures are published.

## How it was built

1. `scripts/fetch_cea.py` reads CEA's page
   (`cea.nic.in/cdm-co2-baseline-database/`), downloads every version's
   database and user guide, and records each file's SHA-256 in `manifest.json`.
   Retrieved 2026-09-26.
2. `src/carbonx/ingest/cea.py` parses each workbook's `Results` sheet. One
   parser covers all three layout families (v1–v10 regional tables; v11–v18
   and v21–v22 two-block tables; v19–v20 a single block). Every CEA row label
   is mapped explicitly to a factor key; an unmapped label is an error, so a
   renamed factor cannot be silently dropped or merged.
3. `scripts/load_cea.py` writes these CSVs. Rebuilding from the same downloads
   gives byte-identical files.

Checks in `tests/test_cea_registry.py`: all 23 versions present and ordered;
every row unique and traceable to a cell; for all 23 versions the committed CSV
equals a fresh parse of the workbook (this needs the raw downloads, so it runs
where they are present and is skipped elsewhere, including CI); known values
match (v19 FY2022-23 = 0.716).

## Things a user of this data must know

1. **Identifying one metric across versions is a judgment.** CEA renamed
   factors. The mapping above is ours. The evidence for
   `weighted_avg_incl_re_captive`: v19's "Grid Emission Factor (for net
   effective injection into grid)" for FY2022-23 is 0.716, the same value v20
   and v22 give under their own labels. If you disagree with a mapping,
   `cea_label` and `cell` let you redo it.
2. **v19 has two "average with renewables" factors** for FY2022-23: 0.713
   ("Incl. RES") and 0.716 ("net effective injection"). They are different
   metrics, and are kept under different keys.
3. **Several "average" series exist, and they differ a lot.** For FY2025-26
   in v22 the four all-India averages range from 0.6751 to 0.8226 tCO2/MWh, a
   21.9% spread. Any use must say which series it means.
4. **CEA restates earlier years.** Each version republishes several past
   years, sometimes with changed values (FY2023-24: 0.7275 in v20, 0.7273 in
   v21, 0.7272 in v22). The same `fy` and `factor_key` therefore appear under
   several `version_label`s. That history is the point of this dataset.
5. **Method break at FY2023-24.** v20 notes that build margin and combined
   margin from FY2023-24 take renewable generation into account. The jump
   that year (build margin about −36%) is a change of method, not of the grid.
6. **`stated_date` is the date written in the workbook, not a publication
   date.** v22.0 is dated 2026-08-01, but CEA's server reports the file as
   last modified on 2026-09-10. For five versions only the month is known.
7. **Values are the workbook's stored floats.** Published tables show them
   rounded (0.727 for 0.7274926…). Round as your use requires.
8. **Unit is tCO2 per MWh.** CEA reports CO2 only, not CO2-equivalent.
9. **v20 omits the plain `weighted_avg` factor.** Its table gives only the
   net-effective-injection average. That is a gap in the source, not in the
   parser.
10. **One value in v18.0 disagrees with every other version.** For FY2016-17,
    `grid.weighted_avg.incl_imports` is 0.7656 in v18.0 (`Results!N13`), and
    0.8237 in v13.0 to v17.0 and in v22.0. The v18.0 figure is close to the
    renewables-inclusive value one row below it. It is what CEA's workbook
    contains, so it is kept. We do not know whether it is a slip. Found by
    `scripts/nowcast.py` (`docs/NOWCAST_RESULTS.md`).

## Releasing it

```
python scripts/build_registry_release.py --draft   # a bundle to inspect, in dist/
python scripts/build_registry_release.py           # the release; refuses until decided
```

The bundle holds these files plus `datapackage.json` (a Frictionless schema),
`SHA256SUMS` and `.zenodo.json`. It is deterministic, so its SHA-256 can be
quoted. Before building it the script checks the registry: no repeated rows,
every factor's version listed, units and values in range, every version with a
source hash, and the counts in this file up to date.

The script will not build a release until `release.json` names a licence and at
least one author. Those are the team's decisions; see the note at the top.

## Reproducing it

```
python scripts/fetch_cea.py     # about 67 MB from cea.nic.in, into data/raw/ (not committed)
python scripts/load_cea.py      # rebuilds factors.csv and versions.csv
```
