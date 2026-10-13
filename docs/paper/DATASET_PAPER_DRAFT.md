# A version history of India's grid emission factors, 2006 to 2026

> **DRAFT for the team to rewrite. Not for submission as it stands.**
> Written as a starting text in the shape of a data descriptor (the article
> type of *Scientific Data* and *Data in Brief*). Every figure below was
> computed from `data/cea/` on 2026-10-13 and is reproducible with the scripts
> named. Statements marked **[verify]** come from general knowledge, not from a
> source read for this project, and must be checked against a primary source
> or removed. The checklist at the end lists what must be true before this
> goes anywhere.

**Authors:** to be decided by the team. **Affiliation:** RV College of
Engineering, Bengaluru. **Licence of the dataset:** to be decided.

## Abstract

India's Central Electricity Authority (CEA) publishes the grid emission factors
that companies in India use to account for purchased electricity. It has
released 23 versions of its *CO2 Baseline Database for the Indian Power Sector*
between November 2006 and August 2026. Each version restates several earlier
years, so the factor for a given year depends on which version is read. The
versions are separate spreadsheets with three different layouts and changing
labels, and no single file records how any value has moved. We present a
machine-readable history of all of them: 2,071 factor values covering financial
years 2000-01 to 2025-26, each traced to the workbook cell it was read from,
with the source URL and SHA-256 hash of every file. The dataset allows a factor
to be looked up as it stood on any publication date, and makes the size and
timing of CEA's revisions measurable. We describe how it was built and
validated, and document the irregularities a user must know about.

*(163 words. Check the venue's limit; data descriptor abstracts are short.)*

## Background and summary

Organisations that report greenhouse gas emissions calculate the emissions from
purchased electricity by multiplying consumption by a grid emission factor. In
India the reference source for that factor is CEA's CO2 Baseline Database.
**[verify: the database was created to support baseline calculations for Clean
Development Mechanism projects, and its methodology follows the CDM tool for
electricity-system emission factors.]**

The database is reissued roughly once a year. Each issue adds the latest
financial year and republishes several earlier ones, sometimes with changed
values. CEA keeps earlier versions online, but as individual workbooks. Three
practical problems follow:

1. **No revision history.** To learn how a year's factor has changed, a user
   must open every workbook that mentions it.
2. **No stable naming.** Row labels change between versions, and the same label
   does not always mean the same quantity.
3. **Several "average" factors.** CEA publishes more than one all-India average,
   under definitions that differ in whether imports, renewable generation and
   captive plants are included. For FY2025-26 the four averages in version 22
   range from 0.6751 to 0.8226 tCO2/MWh.

These matter more since India's Carbon Credit Trading Scheme began setting
emission-intensity targets for industrial plants. **[verify the scheme's rule
for the grid factor against the notified procedure; see `docs/RQ3_FINDINGS.md`.]**
A plant's reported intensity depends on the factor applied, and a factor that
differs by version, by year and by series is an input that needs a record.

This dataset is that record. It contains every factor in every published
version, with provenance to the cell.

## Methods

**Collection.** `scripts/fetch_cea.py` reads CEA's database page
(`cea.nic.in/cdm-co2-baseline-database/`), downloads each version's database
file and user guide, and records the URL, size, retrieval time and SHA-256 of
each in `manifest.json`. Files were retrieved on 2026-09-26.

**Parsing.** `src/carbonx/ingest/cea.py` reads the `Results` sheet of each
workbook. One parser handles the three layout families found: versions 1 to 10
(regional tables), versions 11 to 18 and 21 to 22 (two blocks, excluding and
including imports), and versions 19 to 20 (one block). Every row label that CEA
uses is mapped explicitly to one of eleven factor keys. A label that is not in
the mapping stops the parse, so a renamed factor cannot be dropped or merged
without a decision.

**Values.** The value stored is the number in the workbook cell at full
precision, not the rounded figure CEA prints. No value is adjusted,
interpolated or corrected.

**Versions.** Each version's date is the date written in its workbook. For five
versions only a month is given; these are recorded as the first of the month
with a flag.

`scripts/load_cea.py` writes the CSV files. Rebuilding from the same downloads
gives byte-identical output.

## Data records

The dataset will be deposited at **[Zenodo DOI, to be minted]**. It consists of:

| File | Rows | Contents |
|---|---|---|
| `factors.csv` | 2,071 | one row per version, financial year, factor and geography |
| `versions.csv` | 23 | one row per version: date, newest year covered, source URLs and hashes |
| `manifest.json` | 23 versions | download record for every source file |
| `CHANGELOG.md` | 23 | per version: years first published, values restated, series added or missing |
| `datapackage.json` | — | Frictionless schema for the two CSV files |
| `SHA256SUMS` | — | checksum of every file in the release |

Each row of `factors.csv` gives the version, the financial year, a factor key,
a geography code, the value in tCO2/MWh, the sheet and cell it was read from,
and CEA's own label for the row, verbatim.

**Coverage.** 26 financial years (FY2000-01 to FY2025-26) and 11 factor series:
the weighted average, the weighted average including renewables, the weighted
average including renewables and captive plants, the operating margin, the
build margin and the combined margin, most of them both excluding and including
imports. 884 values are all-India. The rest are regional: five regional grids
in versions 1 to 3 and two in versions 4 to 10. From version 11 only all-India
figures are published.

## Technical validation

- **Completeness.** All 23 versions listed on CEA's page are present and in
  order (`tests/test_cea_registry.py`).
- **Re-parsing.** For all 23 versions, the committed CSV is compared with a
  fresh parse of the workbook and must match exactly, value and cell. This
  shows the files are what the parser produces. It does not show the parser
  reads the right cells; that needs the independent check in the list below.
- **Known values.** Published headline figures are checked, for example
  0.716 tCO2/MWh for FY2022-23 in version 19.
- **Integrity.** Before a release is built, `scripts/build_registry_release.py`
  checks that no row is repeated, that every factor's version exists, that
  every value lies between 0 and 2 tCO2/MWh, that every version has a source
  hash, and that the counts in the documentation match the data. The release
  archive is deterministic, so its hash can be quoted.
- **Internal consistency of revisions.** `CHANGELOG.md` compares each version
  with the newest earlier value of the same factor, geography and year. Of
  1,516 such comparisons, 717 differ by more than 0.005%. For the all-India
  series, 186 of 211 year-and-series points appear in more than one version;
  between first and latest publication they moved by a median of 0.05% and at
  most 4.22%, and 4.8% of them moved by more than 1%.

## Usage notes

A user of this dataset should know the following. Each is documented with its
evidence in the dataset's README.

1. **Matching one factor across versions is a judgement.** CEA renamed factors.
   The mapping is ours; the verbatim label and cell reference let anyone redo it.
2. **The "average" series differ by up to 22%.** State which series is used.
3. **Earlier years are restated.** The same year and series appear under
   several versions. That history is the purpose of the dataset.
4. **There is a break in method at FY2023-24.** Version 20 notes that the build
   and combined margins from that year take renewable generation into account.
   The change of about −36% in the build margin that year is a change of
   method, not of the grid.
5. **Version 20 omits the plain weighted average.**
6. **One value in version 18 disagrees with every other version.** For
   FY2016-17 the weighted average including imports is 0.7656 in version 18
   and 0.8237 in versions 13 to 17 and in 22. It is close to the
   renewables-inclusive figure one row below it. We record what the workbook
   contains and do not correct it. We do not know whether it is an error.
7. **A version's date is the date in its workbook, not a publication date.**
   Version 22 is dated 1 August 2026, and CEA's server reports the file as last
   modified on 10 September 2026.
8. **The unit is tCO2 per MWh.** CEA reports CO2, not CO2-equivalent.
9. **This is not an official CEA product.** For any regulatory use, consult
   CEA's workbooks; the hashes allow a file to be checked against the one read
   here.

**Examples of use.** Looking up the factor a reporter would have had on a given
date; measuring how often and how far a year is restated; testing how well the
previous year's factor predicts the next (`docs/NOWCAST_RESULTS.md`, where it
missed by 1.99% on average over 20 years).

## Code availability

The collection, parsing, validation and release scripts are in the project
repository at **[URL, once the repository is public]**, under **[licence]**.
Python 3.11 or later; the parser depends on `openpyxl` and `xlrd`.

## Statements to complete

- **Author contributions:** who collected, who wrote the parser, who validated,
  who wrote the paper.
- **Use of AI tools:** this project was developed with substantial assistance
  from an AI coding assistant, including the parser, the tests and this draft.
  State that plainly, in the form the venue and RVCE require. The authors are
  responsible for every claim and must have checked each one.
- **Competing interests** and **funding:** to be stated.
- **Acknowledgement of the source:** CEA, Ministry of Power, Government of India.

## Before this can be submitted

1. **Redistribution.** Confirm the terms under which data derived from CEA's
   publications may be redistributed, and choose the dataset's licence. Without
   this there is no paper.
2. **Remove or verify every [verify] statement.**
3. **Have a second person re-derive a sample of values by hand** from the
   workbooks. The current validation is our own code checking itself.
4. **Check novelty.** Search for an existing compilation of CEA's version
   history before claiming this is the first. We found none; that is not the
   same as there being none.
5. **Mint the DOI** and cite it in Data Records.
6. **Rewrite it in your own words.** A descriptor must be something its authors
   can defend line by line.
7. **Do not add analysis.** A data descriptor may not test hypotheses. The
   policy findings (the two readings of "latest", the compliance arithmetic)
   belong in a separate paper.
