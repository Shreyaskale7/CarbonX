# RQ3: Does BEE specify which CEA factor vintage applies?

**Status: PROVISIONALLY ANSWERED (2026-09-26).** BEE gives a rule, but the
rule does not pin down a single number: it leaves the outcome open in two ways
that can be measured. Before this is cited, a member must confirm that the file
read is the notified July 2024 text (see "Provenance of the document read").

## What to read
- BEE, *Detailed Procedure for Compliance Mechanism under CCTS v1.0*, July 2024
- BEE GHG Emission calculation pro forma (the standardised monitoring template)
- The CEA notification / gazette entry for CO2 Baseline Database v22.0, if one
  exists (it would give an official release date; see below)

## The question
The compliance year is FY2025-26 and reports were due 31 July 2026. Which CEA
factor version does an ACVA apply when verifying FY2025-26 emissions?

## Evidence already in hand: when did the FY2025-26 factor appear?

Collected 2026-09-26 from primary sources. The file hash matches
`data/cea/manifest.json`.

| Evidence | v22.0 (first version covering FY2025-26) | v21.0 (covers FY2024-25) |
|---|---|---|
| DATE cell inside the workbook (`Results` sheet) | **2026-08-01** | 2025-11-01 |
| Workbook metadata `dcterms:modified` | 2026-09-09T12:15:39Z | — |
| CEA server `Last-Modified` header on the file | **Thu, 10 Sep 2026 17:47:23 GMT** | Wed, 31 Dec 2025 05:25:43 GMT |
| CEA upload path (WordPress records the upload month) | `/uploads/baseline/2026/09/` | `/uploads/baseline/2025/12/` |
| User guide `Last-Modified` | Thu, 10 Sep 2026 17:47:47 GMT | — |
| SHA-256 of the workbook | `f2341efe03d2fce4177a4a7090b8a946a5ac5ae32b41d784882d0226f2eb4860` | in manifest |

**What this shows.** By every date available, the first FY2025-26 factor did
not exist when FY2025-26 reports were due:

- the workbook's own date is one day after the deadline;
- the file was most likely made public about 10 September 2026, about 41 days
  after the deadline.

v21.0 (FY2024-25) was public since December 2025. So at the deadline, the
newest *published* factor described the previous year.

**What this does not show (verify before publishing):**
- `Last-Modified` can reflect a re-upload. An earlier release elsewhere (a
  circular, gazette or email to entities) would change the picture. Search CEA
  circulars and the gazette.
- Whether BEE's procedure makes the question moot (next section).
- Not yet archived externally. Save a Wayback Machine snapshot of the CEA page
  and both file URLs. This needs a person to do it, because submitting to an
  external archive is a public action.

## Fallback framing: written BEFORE reading the procedure

This framing is written in advance so that neither outcome is spun after the
fact.

- **If BEE prescribes a vintage rule** (for example, "the latest CEA version
  available at the time of reporting", or "the version for the baseline
  year"): RQ3's "ambiguity" framing is dead. What remains is:
  1. a validation result: CarbonX implements the prescribed rule as one of its
     four policies, and reproduces reports under it byte-for-byte;
  2. a measured cost of the rule: how far the prescribed version's factor sits
     from the eventual vintage-matched factor (from the registry: the FY2024-25
     → FY2025-26 step is −4.93% for the grid factor, before any Scope 2
     weighting);
  3. RQ2 and RQ1 carry the paper.
- **If BEE is silent:** RQ3 becomes the headline. The claim to make is exactly
  this:

  > *Competing, defensible resolution policies produce different reported
  > emissions on identical physical performance, and the vintage-matched
  > factor did not exist at the deadline.*

  Do NOT claim "entities flip compliance status" until GEI (denominator
  versioning) is built and the swing is computed on a cited, realistic sector
  profile. The policy swings in the demo (about 4.5% between VINTAGE_MATCHED
  and AS_OF_REPORT on the sample plant) are **synthetic**, and they are swings
  in tCO2e and GEI, not compliance outcomes.

## Also to verify
- **Is FY2023-24 the CCTS baseline year?** (Raised by the council.) Checked
  against the procedure on 2026-10-12: **it does not name a year** (quotes
  below, under "The baseline year and the denominator"). The year must come
  from the target notifications, which nobody on the team has read yet.
  CEA's methodology break (build and combined margins include renewables from
  FY2023-24) would then land exactly on the baseline year. That would make it
  a finding, not noise to exclude. `docs/RQ2_RESULTS.md` currently excludes
  those steps from its summary.

## Findings from the BEE procedure (read 2026-09-26)

### Provenance of the document read
- URL: `https://beeindia.gov.in/WriteReadData/L45218/7772386525993811.pdf`
  (BEE's own site; titled *Detailed Procedure for Compliance Mechanism under
  CCTS*; 45 pages).
- SHA-256: `703414782b7bc312f64374d85b23bb2b298e4d569fe9352bb3f7aa4e6f8574e9`
- **Caveat: the PDF's internal metadata gives a creation date of 2023-11-08.**
  Secondary sources say the procedure was notified on 22 July 2024. This file
  may be the notified text or a pre-notification version. Compare it with the
  notified version before citing it.
- Text was extracted with pdfplumber. The quotes below are verbatim, with the
  document's own page numbers.

### Checked again on 2026-10-31

- **The file is the one BEE publishes.** BEE's homepage lists "Detailed Procedure
  for Compliance Mechanism under CCTS [PDF] (566.09 KB)" at exactly the address
  above, and the local copy is 579,675 bytes = 566.09 KB.
- **It has no version label.** The cover carries no version or date, the page
  headers read "...under the Indian Carbon Market" (the title used by the October
  2023 draft), and the metadata date is 2023-11-08. Third-party summaries
  describe a "Version 1.0, July 2024". Whether the two are the same text is **not
  established**; a copy of the July 2024 text, if BEE hosts one, was not found.
- **Quotations re-checked word for word** against the local copy: the grid-factor
  sentence (p. 11, clause (vii)); the sentence "the emission factor shall be
  consistently applied for baseline and assessment year" (p. 8, the end of a
  clause about fuel and material factors); "baseline year" appears but no year is
  named.
- **Process emissions: the sources disagree.** The note on p. 7 says targets
  "within 2024-27" are calculated from direct energy and indirect emissions only.
  ICAP's summary of the target rules notified by MoEFCC on 8 October 2025 says the
  targets cover Scope 1 including industrial processes. Which applies is open.
- **The FY2025-26 "1 to 3%" in the project notes does not match** ICAP's summary,
  which gives sector-specific total reductions of roughly 3% to 15% over two
  years with about 40% of each due in the first. The paper no longer calls 1 and
  3% "the targets". Check the notified rules and correct `CLAUDE.md` if it is wrong.
- **Baseline year:** ICAP's summary gives FY2023-24.

### Verbatim quotes

**Grid electricity factor (p. 11, clause (vii)):**
> "For the estimation of indirect emissions from purchased electricity, the
> emissions shall be calculated by considering the latest average grid emission
> factors from CO2 baseline database for Indian Power Sector - published by the
> Central Electricity Authority. In case of dedicated power purchase agreement
> for purchased electricity, the supplier specific grid emission factors can be
> used if the obligated entity is able to provide the emission factor with
> supporting documentation verified by an independent agency."

**Consistency between baseline and assessment year (p. 8, clause (6)):**
> "The default emission factors (Type I) depending on type of fuel and
> materials will be applied for the first trajectory period. For the subsequent
> trajectory period, the emissions shall be based on actual emission factors
> (Type II) for fuel and material. However, the emission factor shall be
> consistently applied for baseline and assessment year."

**Submission timeline (p. 15, clause (1)):**
> "Every obligated entity, within three months of the conclusion of the
> compliance cycle shall submit the performance assessment document in Form 'A'
> (as per Annexure VI) covering the performance for the relevant cycle
> specifying the compliance with GHG emission intensity targets, duly verified
> together with certificate of verification in Form 'B' (as per Annexure VII)
> given by the accredited carbon verification agency"

**Which emissions count in 2024-27 (p. 7, note after the definitions of (i)
direct combustion, (ii) process and (iii) indirect emissions):**
> "Note: GHG emission intensity targets within 2024-27 for the obligated
> entities shall be calculated only on the basis of emission related to sources
> as (i) and (iii) highlighted above, subsequently targets will be calculated
> based on (i), (ii) and (iii)"

**Exported power (p. 14, clause (11)(iii)):**
> "In case of non-availability of the above data, the exported power shall be
> adjusted using the Grid average emission as published by Central Electricity
> Authority."

### The baseline year and the denominator (read 2026-10-12)

**Baseline year (p. 6, clause 3.4(1)):**
> "To establish the GHG emission intensity targets, the technical committee set
> up by the Bureau shall calculate the GHG emission intensity in the baseline
> year and the targets of GHG emissions intensity for the trajectory period for
> each compliance cycle"

**Baseline data (p. 8, clause 3.4(5)):**
> "The GHG emissions intensity shall be calculated for the baseline year from
> the verified data for that year and submitted by the obligated entity."

The phrase "baseline year" occurs four times in the 45 pages (pp. 6, 8, 16,
18). None of them says which year it is. "2023-24" does not occur at all.

**More than one product (p. 8, clause 3.4(4)):**
> "In calculating the production for the purpose of deriving the GHG emission
> intensity, where more than one product is produced, the main product or an
> equivalent product worked out from the product mix per standard practice
> prevalent in the obligated entity's sector shall be considered."

**Unit of the target (p. 4, clause (2)):**
> "shall notify the GHG Emission intensity targets in terms of tons of carbon
> dioxide equivalent (tCO2e) per unit of equivalent product"

Form I (Annexure V, p. 36) has one row per product and a "Total Equivalent
Product" row, with no conversion given.

**What this means.**
- `docs/RQ3_COMPLIANCE.md` assumes FY2023-24. This document neither supports
  nor contradicts that. The assumption stays an assumption.
- The denominator is under-determined in the same way the grid factor is: the
  procedure names "an equivalent product" and leaves the conversion to "standard
  practice" in each sector. Two plants with the same emissions and the same
  output could report different intensities by choosing "main product" or
  "equivalent product". We have not measured how much; that needs a sector's
  actual conversion practice.
- Given this clause, CarbonX has no built-in conversion formula. The entity
  declares a factor into the equivalent product for each product and year, with
  the basis it claims; "main product only" is factor 0 for the others. The
  declarations are versioned like every other input (migration 0011,
  `engine/production.py`), so a report keeps the conversion it was made with.
  Until every product of a plant has one, intensity is withheld and the report
  names the product that is missing.
- The two permitted readings give different intensities on the same data. In
  `tests/test_production.py`, a synthetic plant with 980 tCO2e, 90 t of one
  product and 20 t of another reports 10.89 tCO2e/t under "main product" and
  8.91 under tonne-for-tonne equivalence: 22% higher. That is an illustration of
  the arithmetic, not a measured sector effect.

### What the text settles, and what it leaves open

1. **Settled: the source.** The CEA CO2 Baseline Database, an "average grid
   emission factor", and the "latest" one. So RQ3 is **not "silent"**, and
   the "no rule at all" framing is dead.
2. **Open: "latest" as of when?** The text does not say whether "latest" is
   judged at the end of the compliance cycle, at submission of Form A, at
   verification, or at assessment. The registry makes the difference
   concrete:
   - At submission (three months after a financial-year cycle, around 30 Jun
     2026; or 31 Jul 2026 per CLAUDE.md), the latest *published* version was
     v21.0. Its newest factor is for FY2024-25: **0.7097** tCO2/MWh.
   - After v22.0 appeared (dated 1 Aug; on CEA's server around 10 Sep 2026),
     the latest factor is for FY2025-26: **0.6751**, which is **−4.87%**.
   - CarbonX's policies `AS_OF_REPORT` and `LATEST_AVAILABLE` are exactly
     these two readings of "latest".
3. **Open, and it matters more: which "average" series?** CEA publishes
   several all-India average series, and the procedure does not name one.
   Latest versions:

   | Version, FY | Weighted avg (excl. imports) | Weighted avg (incl. imports) | Incl. RES & captive (excl. imports) | Incl. RES & captive (incl. imports) | Spread |
   |---|---|---|---|---|---|
   | v21.0, FY2024-25 | 0.8337 | 0.8308 | 0.7117 | 0.7097 | **17.5%** |
   | v22.0, FY2025-26 | 0.8226 | 0.8182 | 0.6780 | 0.6751 | **21.9%** |

   The choice of *series* moves Scope 2 emissions by roughly 17–22%, about
   four times the version effect. Each value is traced to its workbook cell in
   `data/cea/factors.csv`. CarbonX currently uses the "incl. RES & captive,
   incl. imports" series (`ACTIVITY_TYPES` in `engine/calculate.py`). That is
   a choice, and it should be stated as one.
4. **Possibly contradictory: the consistency clause.** p. 8 (6) says "the
   emission factor shall be consistently applied for baseline and assessment
   year", but it sits in a paragraph about Type I/II **fuel and material**
   factors. If it is read to cover the grid factor, it points towards applying
   the *baseline-year* factor to both years (CarbonX's `BASELINE_FROZEN`),
   which conflicts with "latest". The text supports both readings.
5. **Deadline discrepancy to resolve.** p. 15 says "within three months of the
   conclusion of the compliance cycle"; CLAUDE.md says 31 July 2026. Check the
   target notification or later amendments. Under either date, v22.0 came
   after the deadline.

### Consequence for RQ1 (important; verify first)
Per the p. 7 note, **the 2024-27 targets exclude process emissions (ii)**. For
cement, iron & steel and refining, the first-trajectory GEI basis is then
combustion plus purchased electricity only. So the Scope 2 share *within the
target basis* is larger than a full Scope 1+2 inventory suggests, and
grid-factor revisions matter more than CLAUDE.md's caution assumes.

CLAUDE.md warns that "in cement, iron & steel and refining, process emissions
dominate and are untouched by the grid factor". That is true for total
emissions but, per this note, **not for the 2024-27 target basis**. RQ1's curve
must use the target basis. Confirm this against the notified text and the 2025
target notifications before changing CLAUDE.md.

## Verdict
- [x] **SPECIFIED, BUT UNDER-DETERMINED** (provisional, pending the provenance
      check above). The rule is "latest average grid emission factor from the
      CEA CO2 Baseline Database". It does not fix *when* "latest" is judged
      (−4.87% between the two readings for FY2025-26), or *which* average
      series applies (17–22% spread). A consistency clause may point the other
      way.

**Headline for the paper (replaces the "silent" framing):**

> *BEE's rule, "the latest average grid emission factor", does not determine a
> unique number. For the first compliance year, the two readings of "latest"
> differ by 4.9%, and the unnamed choice of series by up to 22%, on identical
> physical consumption. The FY2025-26 factor itself appeared after reports
> were due.*

## As a compliance outcome
`docs/RQ3_COMPLIANCE.md` (generated by `scripts/rq3_compliance.py`) restates the
finding in the scheme's own metric. For a plant with **no physical change**
between an assumed FY2023-24 baseline and FY2025-26, the three readings show a
GEI change of 0%, −2.45% × *s* or −7.20% × *s*, where *s* is the Scope 2 share
of the target basis. Under the last reading, a share of 14% is enough to show
a 1% reduction and 42% to show 3%, with nothing done. The baseline year and
the baseline factor are assumptions; that file lists them.

## Why this matters
If the procedure is silent, this is a governance gap in a live regulation
covering about 490 obligated entities and more than 700 Mt CO2e, under a
scheme with a 2x penalty.
