# Uncertainty propagation: what is quantified, what is not, and why

Code: `src/carbonx/uncertainty/propagate.py`. Tests: `tests/test_uncertainty.py`.
This is component 8 of CLAUDE.md, in the reduced form the council proposed:
fuel factors only, from published ranges.

    python -m carbonx.uncertainty.propagate --report 7

## 1. What counts as uncertainty here (invariant 6)

Uncertainty is never invented. Each source is used only if it is published or
measured:

| Source | Used? | Why |
|---|---|---|
| Fuel emission factors | **Yes, for 50 of 53 fuels** | IPCC 2006 (Vol. 2, Table 2.2) publishes 95% limits for each default CO2 factor |
| Three coal factors (other bituminous, sub-bituminous, lignite) | **No: point estimates** | BEE's value differs from IPCC's default (`docs/BEE_VS_IPCC.md`), so IPCC's range describes a different central value |
| Grid emission factor (CEA) | **No: point estimate** | CEA publishes no uncertainty. Its version-to-version movement is a separate matter (RQ2, RQ3) |
| Extraction confidence | **No** | not calibrated on unseen layouts (`docs/EXTRACTION.md`) |
| Activity data (meter and weighbridge error), NCV | **No** | no measured error is recorded with an activity |
| CH4 and N2O in the CO2e factor | carried with no range | under 1% of the factor for fossil fuels; IPCC's ranges for them are wide |

A report line whose factor has no range adds no width to the band. Its
emissions are reported separately as "no published range", so the reader can
see how much of the total is a point estimate.

## 2. Correlation: the reason this module exists

Lines that use the same factor row are wrong together. If the default diesel
factor is 2% too high, every diesel line in the report is 2% too high. Their
uncertainties add **linearly**. Treating them as independent and adding in
quadrature understates the band.

- **Within one factor:** fully correlated. The band on that factor's total
  emissions C_f is C_f × u_f.
- **Between factors:** treated as independent, combined in quadrature.

      width = sqrt( Σ over factors (C_f × u_f)² )

- **Lower and upper sides** are propagated separately, because IPCC's ranges
  are asymmetric. This is the usual first-order method (IPCC "Approach 1"). It
  is an approximation, not an exact interval.

**The difference is measurable.** For three equal facilities burning one fuel
with a ±4% factor range, the correlated band is ±4% of the total; the
independent treatment gives ±4%/√3 = ±2.3%. The correlated band is wider by
exactly √3 (`test_lines_sharing_a_factor_add_linearly`). In general, for n
equal lines on one factor, the independent treatment understates the band by
a factor of √n.

The module reports both, so the understatement is visible, not hidden.

## 3. Is a 2% GEI improvement distinguishable from zero?

The build plan expected the answer "possibly not". For fuel factors, the
argument points the other way, and the reason is correlation again.

- **Year-on-year, the same default factor is used in both years.** BEE's
  procedure requires it: "the emission factor shall be consistently applied
  for baseline and assessment year" (p. 8, clause (6)). So whatever the true
  factor is, the error is common to both years. For a plant burning one fuel,
  the *ratio* of this year's GEI to the baseline's does not depend on the
  factor at all. With several fuels, only a change in the fuel mix lets
  factor error into the ratio, weighted by how much the mix moved.
- **So fuel-factor uncertainty widens the absolute figure, not the measured
  change.** A plant's Scope 1 total may be uncertain by several percent
  (natural gas −3.2% / +3.9%; coking coal −7.7% / +6.8%), and a 2% improvement
  against its own baseline can still be real.
- **The grid factor has no such protection.** It changes every year, and
  under "latest" a different value is applied to the baseline and the
  assessment year. That movement does not cancel: it lands directly in the
  measured change. RQ2 measures it (every comparable year-on-year step in
  the grid factor exceeded 1%; the latest was −4.93%).

This is an argument from how the calculation is structured, not a measurement
on real plant data. It should be stated that way.

**Where the absolute band does matter:** comparing two entities that burn
different fuels, checking a figure against an absolute cap, and reconciling
against an independent estimate.

## 4. Limits

- **Only the emission factor is covered.** Activity data and NCV usually
  carry real measurement error, and none of it is recorded. The band is
  therefore a lower bound on the true uncertainty.
- **Independence between factors is assumed.** IPCC's defaults for related
  fuels were derived from overlapping data, so some correlation between
  factors is likely and is ignored.
- **IPCC's ranges are global defaults**, not specific to Indian fuels. Indian
  coal in particular varies widely in quality.
- **The band is not part of a report's hash.** It is computed from the
  report's stored output and the immutable factor rows it pinned, so it is
  reproducible, but it is rendered in floating point, not exact arithmetic.
- **Not run against a database yet.** The arithmetic is tested; reading a
  stored report (`for_report`) is not.
