# Audit sampling: which lines of a report to test

Code: `src/carbonx/sampling/pps.py`. Tables: migration `0012`. Tests:
`tests/test_sampling.py`. Workbench page: `/sampling`.

**Status in the project scope.** `CLAUDE.md` lists component 9 as
"risk-weighted audit sampling (learning to rank)". The council asked for the
learned ranker to be cut, because its labels would come from faults we inject
ourselves. This replaces the *method* and keeps the component: a statistical
sample needs no labels. The change is recorded in `docs/SCOPE_PROPOSAL.md` and
is not agreed until the team signs it.

## 1. The problem

A verifier cannot test every line of a report. Verification practice is
risk-based: understand the controls, then test a sample sized to the risk, and
test everything where the controls cannot be relied on. What is missing from a
ranked list is a way to say what the sample *shows about the whole report*.

## 2. The method

Monetary-unit sampling, a standard technique in financial audit, with tonnes of
CO2e in place of money. Each tonne in the report is equally likely to be
picked. A line is therefore picked in proportion to its size, and a result on
the sample projects to the report with a stated confidence.

1. **Interval.** `J = tolerable / factor`. The factor is the Poisson mean that
   would still produce zero errors with probability `1 − confidence` (3.00 at
   95%). `tolerable` is the largest misstatement the verifier accepts, as a
   share of the report. J is rounded down to six places, so the stored figure
   is exactly the one used. The point of this choice: if no error is found,
   the upper limit is factor × J, which is the tolerable misstatement.
2. **Certain lines.** Tested always, never sampled: any line at least J in
   size, and any line with **no source document** (an untraced figure is
   looked at, not left to chance).
3. **Sampled lines.** Every other line, one hit every J tonnes, starting at a
   point fixed by the seed. The number of hits is the tonnes left to sample
   divided by J. It never depends on how many lines happened to be certain.
   (The first version, until 2026-10-16, split a planned number of hits
   between certain and sampled lines, so every certain line took a hit away
   from the rest and widened the interval. On the sample report, at 95% and
   a 20% tolerance, it sampled 3 of the 12 documented lines at an interval of
   3,392 tCO2e; a clean result could never have supported the tolerance. This
   method's interval is 771 tCO2e, every documented line there is larger, so
   all 24 lines are tested. With
   enough undocumented lines it was worse: documented lines could be left
   neither tested nor sampled while the evaluation passed. Those samples get
   no verdict. `test_many_undocumented_lines_do_not_crowd_out_the_rest`.)
4. **Evaluation.** For each tested line the verifier records the figure the
   evidence supports. A sampled line's *taint* is (reported − audited) /
   reported. Projected misstatement is the known error in the certain lines
   plus interval × the sum of taints. The upper limit is the Stringer bound,
   which is conservative. Both limits (overstatement and understatement) are
   compared with the tolerable misstatement.

## 3. Reproducible like everything else

- The population is the **stored report's own lines**, not the live ledger.
- The seed is the report's SHA-256 plus a nonce. The start point comes from a
  hash of the seed, not from a random-number generator's hidden state.
- So anyone holding the report and the sample's settings can re-derive exactly
  which lines were selected. `test_a_sample_can_be_rederived_from_the_report_alone`
  does this.
- A sample is never changed after it is drawn, and each line receives one
  result, once. Both are enforced by triggers and column-level privileges.

## 4. What it does not do

- **It reaches no conclusion.** The page reports arithmetic: a projection and
  two limits against a tolerance the verifier chose. Whether a report can be
  relied on is the accredited verifier's judgement.
- **It does not score risk.** Lines are not ranked by a model. The only facts
  that force a line into the sample are its size and a missing document.
- **The tolerable misstatement is an input.** The default of 5% is the
  threshold used elsewhere in this project. The figure that applies to CCTS
  verification must come from BEE's verification rules; we have not read them.
- **The method is borrowed.** We found no GHG standard that prescribes
  monetary-unit sampling. ISO 14064-3 and the EU's verification rules require a
  risk-based sampling plan and leave the technique to the verifier. Using this
  one is a design choice, and should be presented as one.
- **Understatements are its weak side.** A line reported as zero cannot be
  hit, and a taint below −100% is capped. This is a known property of the
  method. Completeness (emission sources missing from the report altogether)
  needs a different test and is not covered.
- **Controls are not assessed.** In practice the confidence level is chosen
  after testing the entity's controls. Here it is simply a setting.
