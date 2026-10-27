# Data in Brief article: content to paste into the journal's template

> **Not ready to submit.** Authors, licence, repository DOI and the declarations
> are open (marked **[ ]**), and the hand check of the data (`HAND_CHECK.csv`)
> has not been done. See "Before submitting" at the end.
>
> **How to use this file.** Data in Brief requires its own Word template
> (download it from the journal homepage; the current one is dated January 2026,
> so fetch it fresh). Copy each section below into the matching section of that
> template, keep the template's own headings and its left-hand column of the
> specifications table, and delete every instruction in it. Section order and
> the field names below follow the journal's published guidance as of October
> 2026 (the editor-in-chief's "How to write a good Data in Brief article") and
> the usual template; check both against the template you download.
>
> Rules from that guidance that this text follows, and that edits must keep:
> use the word "data" throughout; no Conclusion, Discussion or Summary section;
> avoid "study", "results" and "conclusions"; no interpretation and no claims of
> novelty in "Value of the Data"; spell out acronyms; the article must read on
> its own; every dataset described must be public.

---

## Title

**Version history of India's grid emission factors: data from 23 releases of the Central Electricity Authority CO2 Baseline Database, 2006 to 2026**

## Authors and affiliations

**[ ]** Names, ORCID iDs and corresponding author, in the template's format.
Affiliation: RV College of Engineering, Bengaluru, India.

## Abstract

The Central Electricity Authority (CEA) of India publishes grid emission factors
for the Indian power sector in its CO2 Baseline Database. Between November 2006
and August 2026 it issued 23 versions, as separate spreadsheets in three
different layouts. Each version restates some earlier financial years, so the
factor for a given year depends on the version read. This data article describes
a machine-readable record of all 23 versions: 2,071 values of eleven factor
series for financial years 2000-01 to 2025-26, each linked to the workbook,
sheet and cell it was read from, with the source address and SHA-256 checksum of
every file used. The record contains all-India values for every version and
regional values for versions 1 to 10. Values are stored as found in the
workbooks, without adjustment. The files, scripts and checks used to build the
record are provided.

**Keywords:** grid emission factor; India; Central Electricity Authority; CO2 baseline database; electricity emissions; version history; carbon accounting

## Specifications table

*(Fill only the right-hand column in the template. Keep each entry short.)*

| Field | Entry |
|---|---|
| Subject | Energy; Environmental science |
| Specific subject area | Greenhouse gas accounting: emission factors for grid electricity in India |
| Type of data | Tables (CSV), JSON; processed data compiled from published spreadsheets |
| Data collection | The 23 database workbooks and user guides published on the CEA website were downloaded on 26 September 2026. A script reads the Results sheet of each workbook, maps every row label to one of eleven factor keys, and records the value, the cell and CEA's own label. |
| Data source location | Central Electricity Authority, Ministry of Power, Government of India, New Delhi, India. Source: https://cea.nic.in/cdm-co2-baseline-database/ |
| Data accessibility | Repository name: **[ ]** Zenodo. Data identification number: **[ ]** DOI, to be minted. Direct URL: **[ ]**. Code: https://github.com/Shreyaskale7/CarbonX (directory `data/cea/`, scripts `scripts/fetch_cea.py`, `scripts/load_cea.py`, `src/carbonx/ingest/cea.py`) |
| Related research article | None. |

## Value of the Data

- The data record every value of India's grid emission factor in every published CEA version, so a factor can be retrieved as it stood when a given version was current.
- Each value is linked to its workbook, sheet and cell, and every source file has a stored SHA-256 checksum, so any value can be checked against CEA's own files.
- Organisations that calculate electricity-related emissions can use the data to document which factor series and which version a calculation used.
- Researchers can use the data to measure how published factors are restated between versions, and how CEA's different average series differ from each other.
- The files are in open formats with a machine-readable schema, and the build is deterministic, so the record can be regenerated from the same downloads.

## Background

Emissions from purchased electricity are calculated as electricity consumed
multiplied by a grid emission factor. In India the factors are published by the
Central Electricity Authority (CEA) in its CO2 Baseline Database. The database
is reissued about once a year; each issue adds the latest financial year and
republishes earlier ones. CEA keeps earlier versions online as individual
workbooks. India's Carbon Credit Trading Scheme sets emission-intensity targets
for industrial plants, and the grid factor applied is an input to such a
calculation. The data described here document the factor inputs; they do not
describe any entity's emissions.

## Data description

The data consist of the six files in Table 1. All are in the repository named in
the specifications table.

**Table 1.** Files in the dataset.

| File | Records | Content |
|---|---|---|
| `factors.csv` | 2,071 | One row per version, financial year, factor key and geography |
| `versions.csv` | 23 | One row per version: date, newest financial year covered, source addresses and checksums |
| `manifest.json` | 23 versions | Download record of every source file: address, size, retrieval time, checksum |
| `CHANGELOG.md` | 23 | For each version: years first published, values restated, series added or missing |
| `datapackage.json` | n/a | Frictionless Data schema describing the two CSV files |
| `SHA256SUMS` | n/a | Checksum of every file in the release |

**`factors.csv`** has eight columns: `version_label` (for example `v22.0`); `fy`
(financial year, for example `FY2025-26`); `factor_key` (one of eleven series,
Table 2); `geography` (`IN` for all-India, or a regional code); `value` (number
in the workbook cell, at full precision); `unit` (`tCO2/MWh`); `cell` (sheet and
cell reference, for example `Results!G36`); `cea_label` (CEA's own row label,
verbatim).

**`versions.csv`** has eleven columns: `version_label`; `version_ordinal`;
`stated_date` (the date written in the workbook); `date_precision` (`day` or
`month`); `covers_fy` (newest financial year in that version); `cea_outdated`
(whether CEA's page marks the version outdated); `workbook` (file name);
`database_url` and `database_sha256`; `user_guide_url` and `user_guide_sha256`.

**Coverage.** The data cover 26 financial years (FY2000-01 to FY2025-26) and 11
factor series. Of the 2,071 values, 884 are all-India. The remainder are
regional: five regional grids in versions 1 to 3 and two in versions 4 to 10.
From version 11 onward only all-India figures are published.

**Table 2.** Factor series (`factor_key`).

| Series | Description |
|---|---|
| `grid.weighted_avg` | Weighted average emission factor, excluding and including imports |
| `grid.weighted_avg_incl_re` | Weighted average including renewable generation, excluding and including imports |
| `grid.weighted_avg_incl_re_captive` | Weighted average including renewable generation and captive plants, excluding and including imports |
| `grid.operating_margin` | Operating margin, excluding and including imports |
| `grid.build_margin` | Build margin, excluding imports |
| `grid.combined_margin` | Combined margin, excluding and including imports |

The suffixes `.excl_imports` and `.incl_imports` complete each key; not every
series is published in every version.

**Quantities describing the data.** 186 of the 211 all-India (series, financial
year) points appear in more than one version. Between first and latest
publication these 186 differ by a median of 0.05% and by at most 4.22%; 9 of
them (4.8%) differ by more than 1%. Across all versions, each value was compared
with the newest earlier value of the same series, geography and year: 717 of
1,516 comparisons differ by more than 0.005%, the threshold used to ignore
rounding (`CHANGELOG.md`). For financial year 2025-26, the four all-India
average series in version 22 range from 0.6751 to 0.8226 tCO2/MWh.

## Experimental design, materials and methods

**Source files.** `scripts/fetch_cea.py` reads CEA's database page, downloads
each version's database file and user guide, and records the address, size,
retrieval time and SHA-256 checksum of each in `manifest.json`. Files were
retrieved on 26 September 2026. The source workbooks are not redistributed in
the dataset.

**Reading the workbooks.** `src/carbonx/ingest/cea.py` reads the `Results` sheet
of each workbook. One reader handles the three layouts found: versions 1 to 10
(regional tables); versions 11 to 18 and 21 to 22 (two blocks, excluding and
including imports); versions 19 to 20 (one block). Every row label used by CEA
is mapped explicitly to one of the eleven factor keys. A label that is not in
the mapping stops the run, so a renamed series cannot be dropped or merged
without a decision.

**Values.** The value stored is the number in the workbook cell at full
precision, not the rounded figure CEA displays. No value is adjusted,
interpolated or corrected. Each version's date is the date written in its
workbook; for five versions only a month is given, and these are recorded as the
first day of the month with `date_precision` set to `month`.

**Building the files.** `scripts/load_cea.py` writes the CSV files, and
`scripts/build_registry_release.py` builds the release archive. Rebuilding from
the same downloads gives byte-identical files and an identical archive.

**Validation.** (1) All 23 versions listed on CEA's page are present and in
order. (2) For all 23 versions, the committed CSV is compared with a fresh read
of the workbook and matches exactly in value and cell. This shows the files are
what the reader produces; it does not show that the reader selects the right
cells, which is the purpose of check (5). (3) Published headline figures are
checked, for example 0.716 tCO2/MWh for financial year 2022-23 in version 19.
(4) Before a release is built, the script checks that no row is repeated, that
every version referenced exists, that every value lies between 0 and 2 tCO2/MWh,
that every version has a source checksum, and that the counts quoted in the
documentation match the data. (5) **[ ]** A person who did not write the reader
re-derived two cells from each version directly from the workbooks, chosen by
checksum with the stored value hidden (`scripts/hand_check.py`):
**[ ] n of n agreed; state any disagreement.** *Complete this check and report
the real count before submitting.*

## Limitations

The following features of the source files affect how the data can be used.

1. Matching a series across versions is a judgement. CEA renamed some series
   between versions. The mapping is ours; the verbatim label and cell reference
   allow it to be repeated.
2. CEA publishes several average series that differ in whether imports,
   renewable generation and captive plants are included. For financial year
   2025-26 they range from 0.6751 to 0.8226 tCO2/MWh in version 22. A user must
   state which series is used.
3. Version 20 notes that build and combined margins from financial year 2023-24
   take renewable generation into account. The change of about -36% in the build
   margin that year reflects a change in CEA's method.
4. Version 20 does not include the plain weighted average.
5. For financial year 2016-17, the weighted average including imports is 0.7656
   in version 18 and 0.8237 in versions 13 to 17 and in version 22. The version
   18 value is close to the figure one row below it in the same workbook. The
   data record what the workbook contains; the value has not been corrected, and
   it is not known whether it is an error.
6. A version's date is the date written in its workbook, not a publication
   date. Version 22 is dated 1 August 2026, and CEA's server reports the file as
   last modified on 10 September 2026.
7. The unit is tonnes of CO2 per megawatt-hour. CEA reports CO2, not
   CO2-equivalent.
8. The data are compiled from CEA's published workbooks and are not an official
   CEA product. For any regulatory use, consult CEA's workbooks; the checksums
   allow a file to be compared with the one read here.

## Ethics statements

The data contain no personal data and involve no human participants or animals.
**[ ]** CEA's copyright policy (read 2026-10-27) allows reproduction free of charge
only after prior permission by email, with CEA acknowledged and the material
unaltered. Obtain that permission (draft in `docs/OUTREACH_DRAFTS.md`), then state
its terms here and in the dataset licence. Do not submit before it is in hand.

## CRediT author statement

**[ ]** One line per author, using the CRediT roles (Conceptualization, Data
curation, Formal analysis, Investigation, Methodology, Software, Validation,
Visualization, Writing - original draft, Writing - review and editing,
Supervision). Say who collected the files, who wrote the reader, who performed
the independent check of values, and who wrote the article.

## Acknowledgements

The data are compiled from publications of the Central Electricity Authority,
Ministry of Power, Government of India. **[ ]** Thank the project guide and RV
College of Engineering as appropriate, and state any funding (or "no funding").

## Declaration of competing interests

**[ ]** State, for example: "The authors declare that they have no known
competing financial interests or personal relationships that could have appeared
to influence the work reported in this article."

## Declaration of generative AI and AI-assisted technologies

**[ ]** Elsevier requires disclosure of AI use in the writing process, and RVCE
may require more. State it plainly and accurately: the project's software (the
file reader, tests and build scripts) and the drafts of this article were
developed with substantial assistance from an AI coding assistant (Claude,
Anthropic). The authors reviewed and edited the content and take full
responsibility for it. Use the journal's exact wording from its current policy.

## References

1. Central Electricity Authority, Ministry of Power, Government of India. CO2
   Baseline Database for the Indian Power Sector (versions 1.0 to 22.0).
   https://cea.nic.in/cdm-co2-baseline-database/ (files retrieved 26 September 2026).
2. **[ ]** Authors. Open registry of India's CEA grid emission factors, v1.0 to
   v22.0 (version 1.0.0). Zenodo. **[DOI to be minted]**.
3. **[ ]** Authors. CarbonX: source code and build scripts.
   https://github.com/Shreyaskale7/CarbonX.

---

## Figures

Generated from the data by `python scripts/dib_figures.py` (SVG for the
repository; `--png` writes the 4x PNGs, 3040 x 1760 pixels, for the Word
template). Place each after the paragraph that first mentions it. The files are
in `docs/figures/`; use the light versions. Captions to paste:

**Fig. 1.** Versions of the CEA CO2 Baseline Database. Each marker is one of the
23 versions, placed at the date written in its workbook (horizontal axis) and the
newest financial year it covers (vertical axis). Open markers are the five
versions whose workbook gives only a month; they are drawn at the first of that
month. Version 1.1 covers the same year as version 1.0. Source: `versions.csv`.

**Fig. 2.** Values of one all-India series (`grid.weighted_avg.incl_imports`, the
weighted average including imports) for each of the 26 financial years, across
the versions that published them. Filled markers are the latest value; open
markers are the value in the first version that published the year (shown where
a year appears in more than one version); the grey bar spans all versions of that
year. The orange marker is the largest departure of one version's value from the
other versions of its year: version 18 for financial year 2016-17 (0.7656
tCO2/MWh, against 0.8237 in the other versions). Source: `factors.csv`.

Add to the "Data description" text: "Fig. 1 shows the versions in time and Fig. 2
shows, for one series, how values differ between versions."

**Tables.** Tables 1 and 2 above, with captions.

## Before submitting

1. **Check fit with the editors.** Data in Brief's guidance says data should
   result from experiment or observation rather than computer simulation, and
   should not have been published before. These data are compiled from public
   workbooks, so ask the editorial office, before paying any fee, whether a
   compiled version history of a public source is in scope. The guidance does not
   settle it.
2. **Redistribution and licence.** Confirm CEA's terms, choose the dataset
   licence, and fill in `data/cea/release.json` (it currently has no licence and
   no authors).
3. **Repository.** All data must be public. Confirm that Zenodo is on Elsevier's
   list of supported repositories (the guidance names that list; it could not be
   read here). If it is not, Mendeley Data is free for the journal's authors and
   gives a DOI.
4. **Independent check of values.** Complete `HAND_CHECK.csv` and report the real
   count above.
5. **Fees.** DOAJ lists a charge of up to 530 USD with a waiver policy for the
   journal; confirm the current figure on the journal's pages and ask RVCE
   whether it pays.
6. **Template.** Paste into the journal's current Word template, remove every
   instruction, and leave none of its example text in the specifications table.
7. **Word check.** The guidance asks authors to avoid "study", "results",
   "conclusions", "effects", "evidence", "implications" in the title and text.
   Search the final document for them.
8. **Your own words.** The authors must be able to defend every line.
9. **Do not add analysis.** The policy findings (the two readings of "latest",
   the compliance arithmetic, the forecasting error) belong in a separate paper
   (`POLICY_PAPER_DRAFT.md`), not here.
