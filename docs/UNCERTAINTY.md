# Uncertainty propagation: what is quantified, what is not, and why

Code: `src/carbonx/uncertainty/propagate.py`. Tests: `tests/test_uncertainty.py`.
This is component 8 of CLAUDE.md, in the reduced form the council proposed:
fuel factors from published ranges, plus (since 2026-10-13, a proposed
addition) activity data where a meter's calibration certificate states an
uncertainty.

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
| Activity data from a declared meter | **Yes, where the certificate states it** | the expanded uncertainty (about 95%) on the meter's calibration certificate. The database refuses a figure without the stored certificate (migration 0013) |
| Activity data with no meter, or a meter with no certificate; NCV | **No** | nothing documented to take it from |
| CH4 and N2O in the CO2e factor | carried with no range | under 1% of the factor for fossil fuels; IPCC's ranges for them are wide |

A report line whose factor has no range adds no width to the band from its
factor, and a line whose reading has no stated measurement uncertainty adds
none from its activity data. Both amounts are reported separately ("no factor
range", "no meter uncertainty"), so the reader can see how much of the total
is a point estimate in each respect.

**Why a certificate counts and an accuracy class does not.** Invariant 6 allows
published ranges and calibrated measurements. A calibration certificate states
an expanded uncertainty for that device, and we store the certificate. A
nameplate accuracy class is a maximum permissible error; turning it into a
95% interval needs an assumed distribution, which would be us inventing the
number. So only the certificate's own figure is accepted. This extends the
wording of invariant 6 in `CLAUDE.md` to a third source; that needs the team's
agreement (`docs/SCOPE_PROPOSAL.md`).

**Meters are correlated too.** All readings from one meter share its error, so
they add linearly, like lines sharing a factor. Different meters, and meters
and factors, are treated as independent.

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

- **Coverage is partial by design.** Activity data counts only where a meter
  with a stored certificate is named; NCV never does. On the sample plant no
  meter is declared, so its band is still from fuel factors alone. The band is
  a lower bound on the true uncertainty.
- **A certificate describes the meter on the day it was calibrated.** Drift
  since then, installation effects and reading errors are not in it.
- **Independence between factors is assumed.** IPCC's defaults for related
  fuels were derived from overlapping data, so some correlation between
  factors is likely and is ignored.
- **IPCC's ranges are global defaults**, not specific to Indian fuels. Indian
  coal in particular varies widely in quality.
- **The band is not part of a report's hash.** It is computed from the
  report's stored output and the immutable factor rows it pinned, so it is
  reproducible, but it is rendered in floating point, not exact arithmetic.
- **Checked on a development database only.** The arithmetic is unit-tested.
  Reading a stored report (`for_report`) was checked by hand on
  the local development Postgres (`scripts/dev_pg.py`, 2026-10-05). That is Postgres 18 in compatibility mode, not the target Postgres 16; CI (Postgres 16) ran green on 2026-10-22 and is the authority.
  It has no automated database test.
