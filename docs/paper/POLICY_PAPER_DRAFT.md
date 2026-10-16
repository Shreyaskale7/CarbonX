# One rule, several numbers: how India's carbon market fixes the grid emission factor

> **DRAFT for the team to rewrite. Not for submission as it stands.**
> A short policy-analysis paper built only from this project's generated
> results; the file each figure comes from is named beside it. Statements
> marked **[verify]** are not yet backed by a primary source read for this
> project. Everything quoted from BEE rests on one PDF whose internal date
> (8 November 2023) precedes the reported notification; **until a team member
> confirms it against the notified text, none of this can be submitted.**
> Every percentage about the grid factor applies to the Scope 2 share of an
> entity's target basis, not to its total; the paper must say so wherever the
> numbers appear.

**Authors:** to be decided. **Affiliation:** RV College of Engineering, Bengaluru.

## Abstract

India's Carbon Credit Trading Scheme sets plants targets for emission intensity:
tonnes of CO2e per unit of product. For purchased electricity the compliance
procedure prescribes "the latest average grid emission factor" from the Central
Electricity Authority's CO2 Baseline Database. Using an open record of every
version of that database, we show that the rule does not determine one number.
For the first compliance year, FY2025-26, the two readings of "latest" differ by
4.87%, and CEA's four all-India average series differ by up to 21.9%. The factor
for FY2025-26 is dated one day after reports were due. For a plant whose target
basis is a share *s* purchased electricity, these choices alone move its
reported intensity by up to 7.2% × *s* with no physical change. The procedure
leaves the product denominator similarly open for plants with several products.
We find that last year's factor misses the new one by about 2% a year, that no
simple forecast does better, and that an independent monthly estimate may. We
propose four clarifications that would make the reported figure unique.

## 1. Introduction

Calculating a plant's emissions is multiplication: activity times an emission
factor. Verifying them means knowing which factor, and which version of it, was
used. **[cite]** The GHG Protocol already requires a base year
to be recalculated when emission factors change, and SBTi treats a change of 5%
or more as significant. That factor revisions can matter is therefore not new.
What is new is a compliance scheme whose rule for choosing the factor admits
several readings, at a time when the factor is changing by about the size of
the targets.

The scheme's first targets require reductions in emission intensity of 1 to 3%
for FY2025-26 **[cite the target notification]**. Section 4 shows that
the choices this paper is about are of the same size for plants that buy much of
their electricity.

## 2. What the rule says

The compliance procedure (p. 11, clause (vii)):

> "the emissions shall be calculated by considering the latest average grid
> emission factors from CO2 baseline database for Indian Power Sector -
> published by the Central Electricity Authority."

Three things are left open:

1. **Latest as of when:** the end of the compliance year, the date reports are
   due, or the date of verification.
2. **Which average:** CEA publishes several all-India averages, which differ in
   whether imports, renewable generation and captive plants are included.
3. **Consistency with the baseline:** p. 8, clause (6) requires that "the
   emission factor shall be consistently applied for baseline and assessment
   year", in a paragraph about fuel and material factors. Read as covering the
   grid factor too, it points to applying the baseline year's factor in both
   years, which conflicts with "latest".

For plants with more than one product, the denominator is also open: "the main
product or an equivalent product worked out from the product mix per standard
practice prevalent in the obligated entity's sector" (p. 8, clause 3.4(4)), with
no conversion given. The procedure does not name the baseline year.

## 3. Data

An open, machine-readable record of all 23 versions of the CEA database
(2006 to 2026): 2,071 factor values, each traced to its workbook cell, with the
hash of every source file (`data/cea/`; a separate data paper describes it).
Reproduction: `bash reproduce.sh`.

## 4. Findings

**4.1 When was the FY2025-26 factor published?** Version 22.0, the first to
cover FY2025-26, is dated 1 August 2026 in its own workbook, one day after the
31 July 2026 deadline; CEA's server reports the file as last modified on
10 September 2026 (`docs/RQ3_FINDINGS.md`). At the deadline, the newest
published factor was for FY2024-25: 0.7097 tCO2/MWh. Once version 22 appeared,
the newest was 0.6751, which is 4.87% lower. Both are "the latest".

**4.2 Which average?** For FY2025-26, version 22's four all-India averages run
from 0.6751 to 0.8226 tCO2/MWh, a spread of 21.9% (17.5% in version 21). The
series question is about four times larger than the timing question
(`docs/RQ3_FINDINGS.md`).

**4.3 What it does to a plant's intensity.** Hold a plant's fuel, electricity and
production fixed between the baseline year and FY2025-26. Its intensity still
changes by *s* × the change in the factor applied, where *s* is the Scope 2
share of the target basis (`docs/RQ3_COMPLIANCE.md`, with FY2023-24 assumed as
the baseline year):

| Reading of the rule | Factor change | Share that shows a 1% reduction | Share that shows a 3% reduction |
|---|---|---|---|
| Same factor as the baseline year | 0% | never | never |
| "Latest" when reports were due | −2.45% | 41% | never |
| "Latest" once FY2025-26 is published | −7.20% | 14% | 42% |

Under the third reading, a plant with 42% of its target basis in purchased
electricity shows the full 3% reduction without changing anything; under the
first it shows none. The choice of series alone moves a total by more than 5%
once the Scope 2 share exceeds 23% (`docs/RQ1_RESULTS.md`).

**4.4 How large are yearly changes?** In the longest all-India series, 18 of 25
first-published year-on-year changes exceeded 1% and 4 exceeded 3%
(`docs/RQ2_RESULTS.md`). These are the same size as the targets.

**4.5 Can the missing year be predicted?** Using only what CEA had published
before each year first appeared, last year's factor missed the new one by 1.99%
on average over 20 years, and drift, trend and autoregressive models did no
better (`docs/NOWCAST_RESULTS.md`). Scaling last year's factor by the change in
Ember's independent monthly estimate missed by 1.36% against 2.62% over 8 cases,
and by 0.52% against 3.82% for the renewables-inclusive series, but on two cases
and with Ember's current rather than archived data (`docs/EMBER_CROSSCHECK.md`).
Once published, CEA restates a year by a median of 0.05%: which year's factor is
used matters far more than which version of it.

**4.6 The denominator.** For an invented plant emitting 980 tCO2e with 90 t of
one product and 20 t of another, "main product only" gives 10.89 tCO2e/t and
tonne-for-tonne equivalence gives 8.91, a difference of 22%. This illustrates the
arithmetic only; the size in any real sector depends on its conversion practice,
which we have not measured.

## 5. What would make the number unique

1. **Name the series.** One of CEA's averages, by its exact title.
2. **Fix the vintage.** For example: the factor for the compliance year, as
   published in the first version that covers it, with a stated fallback if it
   is not published by the reporting date.
3. **Record the version.** Require Form A to state the CEA version and series
   used, so a verifier can reproduce the figure.
4. **Publish equivalence factors** per sector, or require each entity's factors
   and their basis to be declared and verified.

These are suggestions for discussion, made from the text alone. **[verify]**
whether later BEE guidance, FAQs or target notifications already settle any of
them; if so, the paper changes from "the rule is open" to "the rule was open in
the procedure and was later settled by X".

## 6. Limitations

- **One PDF.** The procedure read may not be the notified text.
- **The baseline year is assumed** (FY2023-24) for section 4.3.
- **No real plant.** All effects are per Scope 2 share; we have no cited sector
  shares of the target basis, so we cannot place any sector on the curve.
- **We do not know what verifiers actually applied** in the first cycle.
- **The forecast results rest on about twenty values,** and the Ember result on
  eight.
- **This is not a verification of any entity's compliance.**

## Before this can be submitted

1. Confirm the BEE text and the baseline year from primary sources.
2. Replace every [verify] with a citation or remove the claim.
3. Read later BEE guidance and the target notifications (section 5 depends on it).
4. If possible, cite each sector's Scope 2 share of the target basis.
5. State the use of AI assistance as the venue and RVCE require.
6. Rewrite in your own words, and keep the Scope 2 qualifier next to every
   percentage.
