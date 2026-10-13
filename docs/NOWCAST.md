# Nowcasting the grid factor, and how CEA revises it

Code: `src/carbonx/forecast/nowcast.py`. Results, generated from the registry:
`docs/NOWCAST_RESULTS.md`. Tests: `tests/test_nowcast.py`.

**Status in the project scope.** This is proposed as the replacement for
component 9 (learning-to-rank audit sampling) in `docs/SCOPE_PROPOSAL.md`. It
is built, but it is not in the agreed BUILD list until the team signs.

## 1. Why this exists

BEE's rule says to use "the latest average grid emission factor". When reports
for a financial year are due, CEA has usually not published that year's
factor, so "the latest" is the previous year's. That is a forecast: it predicts
this year's factor by last year's. RQ3 found the rule ambiguous. This module
measures what the ambiguity costs, on real data:

1. How wrong is "use last year's value", year after year?
2. Does any simple model do better?
3. Can the error be bounded in advance, from the errors seen so far?
4. Separately: once CEA publishes a year, how much does it later restate it?

Questions 1 to 3 are about which **year's** factor is applied. Question 4 is
about which **version** of a year's factor is applied. Comparing them says
which of RQ3's two ambiguities is the larger.

## 2. Data

The CEA registry already in this repository (`data/cea/factors.csv`): about 25
financial years, 23 versions, all-India factors. It is real and every value
traces to a workbook cell. No synthetic data is used.

Each version republishes only about five recent years. So the registry is a
**revision triangle**: for each year, a sequence of values as successive
versions restated it.

## 3. The vintage rule

To predict the first-published value of year *t*, the forecaster may use only
values from versions published **before** the version that first published
*t*. For each earlier year that means the newest value among those earlier
versions.

Without this rule a backtest would feed each forecast with numbers CEA had not
yet published, including later corrections of earlier years, and would look
better than anything a real reporter could have done. `as_known` implements
the rule. `test_as_known_never_sees_the_target_version_or_later` and the
check inside `test_real_registry_naive_is_not_beaten` fail if it is broken;
this was confirmed by breaking it on purpose.

A year is used as a target only when it is a true one-year-ahead case: the
previous year was already published, and at least five consecutive earlier
years were known. Years that fail this are listed in the results, not dropped
silently.

## 4. Models

| Model | Idea |
|---|---|
| Naive | Last year's value. This is what the rule's "latest" reading does. |
| Drift | Last value plus the average yearly change so far. |
| Recent drift | Last value plus the average of the last three changes. |
| Linear trend | A straight line through the history, extended one year. |
| AR(1) on changes | Does this year's change predict next year's? |

All five are closed-form and have no settings to tune. That is deliberate.
There are about twenty targets. A model with tunable parts, chosen by how well
it backtests, would be fitted to those twenty numbers and its score would mean
nothing. For the same reason, five models is already enough to produce one
"significant" result by chance; the results say so next to the p-values.

## 5. Evaluation

- **Rolling origin.** Each year is predicted from its own past only; the
  history grows by one year each time.
- **Error** is in percent of the published value. Reported: mean absolute
  error, root mean square error, bias, and the worst year.
- **Against naive:** the number of years with a smaller absolute error, and an
  exact two-sided sign test on that count.
- **Bands.** For year *t*, take the ratios published/nowcast from the years
  before *t* and scale the nowcast by their quantiles. No distribution is
  assumed. Coverage is then counted on the years the band was not built from.
  A band is drawn only once eight earlier errors exist.

## 6. Revisions

For each year, each later version that republished it gives one revision,
measured from the first-published value. The results table groups them by how
many restatements later they occurred, and separately compares first with
latest.

## 7. Limits

- **Twenty yearly values.** The backtest can show that nothing simple beats
  the naive forecast. It cannot show that nothing could. It can detect only a
  large difference between models.
- **Coverage is counted on about a dozen years.** "10 of 12" is consistent
  with an 80% band and with a fairly wide range of other true rates.
- **The band is not an uncertainty of the published factor.** It describes a
  guess made before publication. `carbonx.uncertainty` does not use it, and
  invariant 6 is unchanged: CEA publishes no uncertainty for its factors.
- **The series CarbonX calculates with is too short.** It first appeared in
  version 19. Its nowcast band borrows the percentage errors of the longer
  plain weighted average. That is an assumption and is labelled as one.
- **No outside predictors in the backtest.** Generation-mix data would predict
  the factor well, because CEA computes the factor from it. That would be
  reproducing an accounting identity early, not forecasting, so it is left out
  of the models above. It is tried separately and labelled as what it is:
  `docs/EMBER_CROSSCHECK.md` scales last year's CEA factor by the change in
  Ember's independently calculated intensity. On the few cases available that
  did better than the naive nowcast, most clearly for the renewables-inclusive
  series (two cases). It is an early indicator worth testing properly, not a
  result.
- **Method changes are in the data.** CEA's series definitions shift over
  time. The build and combined margins have a known break in FY2023-24 and are
  not used here. Smaller undocumented changes may sit inside the series that
  are used.
- **The Scope 2 qualifier applies.** A 2% error in the grid factor is a 2%
  error in an entity's emission intensity only if all of its target basis is
  purchased electricity.
