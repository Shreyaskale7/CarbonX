# LLM Council transcript: CarbonX project evaluation

**Date:** 2026-09-26, about 21:00–21:20 IST
**Method:** five advisors answered independently and in parallel. Five
reviewers then assessed the anonymised answers, and a chairman synthesised
everything. All advisors, reviewers and the chairman are AI model instances,
not people.
**State of the repo at the time:** commit `5728e7c` plus uncommitted Phase 5
work (migrations 0003–0004, `engine/report.py`, 52 tests passing, a
10,000-sequence run in progress).

## Original question

> Evaluate the project like this [LLM council] for this project, and then
> fixes and improvements.

## Framed question (given to every advisor)

Evaluate this student project honestly. Is it on track to earn a top grade
(90+/100) and produce a credible research contribution? What are its weakest
points, and what should the team change, cut or add in the remaining time?

The brief each advisor received covered:

- the project (CarbonX, a bitemporal ledger for India's CCTS);
- the grading context (RVCE Experiential Learning, 14 weeks, graded under
  DBMS, AI/ML and ToC);
- the thesis (provenance, not computation);
- RQ1–RQ3 and their status, including the v22.0-dated-1-Aug-2026 finding and
  the synthetic 5.1% / 7.8% policy swing;
- what was built in week 1, and by whom (one person plus an AI assistant;
  roles blank);
- what is not built (the AI/ML component; GEI denominator; RQ1; automaton;
  workbench);
- the earlier self-assessment of 74/100;
- the stakes.

The full brief is reproduced verbatim in the advisor prompts. The facts in it
were checked against the repo before sending: `git log`, `TEAM.md` blank,
`RQ3_FINDINGS.md` unresolved, no git remote.

## Advisor responses

### The Contrarian

The biggest risk isn't technical. One person and an AI assistant built a
three-course group project in one week, and the team roles are still blank.
RVCE EL vivas grade each member separately. When examiners ask person #3 to
explain the exclusion constraints or the induction proof and they can't, the
grade collapses no matter how good the code is. Hand real ownership to each
member now, meaning each person rebuilds or extends a component themselves.

Second, the headline results measure the wrong thing. CCTS compliance is
judged on GEI, which is emissions per unit of product. Every report has
gei=null because denominator versioning isn't built. So "+5.1% / +7.8%
depending on policy" is a change in tCO2e, not a change in compliance outcome.
The plan to report "X% of entities flip compliance status" can't be done at
all: there are no entity-level Scope 1/2 splits, production data or
baselines, only synthetic numbers. Drop that claim or build the denominator
first.

Third, RQ3 has a free answer the team is ignoring: the 31 July deadline has
passed, so what BEE says and which factor version was actually applied can now
be looked up. Not having read the procedure is negligent at this point. Also,
FY2023-24, the year of the methodology break, is likely the CCTS baseline
year; excluding it as noise may throw away the most important finding.

Fourth, the AI/ML component is empty and badly planned. There are zero bills;
"held-out by DISCOM" needs many DISCOMs; learning-to-rank on injected-fault
labels is circular; and uncertainty propagation has no CEA data. Cut
learning-to-rank and the flagship uncertainty demo, and shrink ML to
extraction plus calibration on a small set of consented, redacted bills,
starting this week.

Fifth, fix the cheap credibility holes:

- The app connects as superuser, so invariant 3 isn't actually enforced
  (a one-hour fix to a non-owner role).
- Push the repo so CI runs.
- A dimensional type checker is textbook material, so the automaton needs
  mechanised safety checks (TLA+ or a model checker).

Cut the Next.js workbench.

### The First Principles Thinker

You're asking "is this on track for 90+?" The better question is what the
graders and the field will actually reward. Stripped down, CarbonX has one
real finding and one real engineering result; everything else is scope
written to satisfy three rubrics.

The real finding is RQ3: CEA v22 dated a day after the first compliance
deadline, and policy choice alone moves the figure 5-8%. That's a governance
gap, and it's the paper. The deadline has passed and entities have filed, so
RQ3 no longer needs synthetic data. Read the BEE procedure this week, then ask
3-5 ACVAs or consultants which factor version they actually applied. That is
the practitioner interviews and the RQ3 answer in one move.

The real engineering result is reproducibility under revision. It's done and
defensible; stop polishing it.

Phase 6 solves the wrong problem. CCTS obligated entities are cement kilns,
refineries and steel plants whose electricity evidence comes from HT meters,
SCADA and captive generation, not scanned DISCOM bills. LayoutLMv3 on
uncollected bills is ML for the rubric, disconnected from the thesis. A better
AI/ML component grows from data you already have: forecast the next CEA factor
version from the published generation mix, with calibrated intervals. That
directly quantifies RQ3's ambiguity: "the verifier must pick a version before
it exists" becomes "here is the forecast error of picking early".

Cut: document extraction, learning-to-rank, the Next.js workbench, and
uncertainty propagation without data. Add: denominator versioning (gei=null
means you aren't computing the CCTS metric) and the RQ1 curve.

The biggest risk is outside the code. One person built everything and TEAM.md
is blank. Split ownership by course now, with each member rebuilding and
defending one component.

### The Expansionist

The team is underselling what it already has. The asset isn't the ledger;
it's the open registry plus the v22.0 date finding. CEA's first factor for
FY2025-26 is dated 1 Aug 2026, one day after the 31 July deadline. That's a
concrete, citable gap in a live regulation, and it's already built. The first
compliance cycle has just closed, so verifiers and obligated entities are
living this problem right now, and it won't stay that timely for long.

What could be bigger:

1. **Make the registry the reference dataset.** Get the Zenodo DOI in weeks,
   not at week 14. Add a stable CSV/JSON API and a changelog that updates
   automatically when CEA publishes v23. Email it to the CEA data cell, the
   BEE CCTS team and a few ACVAs. One reply from a practitioner is worth more
   than a UI.
2. **Swap the missing bills for public filings.** Zero bills is the biggest
   risk to the AI/ML component, and a privacy problem too. SEBI's BRSR filings
   disclose Scope 1 and Scope 2 for large listed companies, many of them in
   CCTS sectors (verify the exact coverage from SEBI's circular). Extracting
   from these public PDFs gives the AI/ML component a real, redistributable
   corpus with genuine held-out splits (by company or sector instead of by
   DISCOM), and supplies the per-sector Scope 1/2 splits RQ1 needs. One pivot
   unblocks two phases.
3. **Scale up RQ3.** With Scope 2 shares from BRSR, the question becomes
   "across N real entities, policy choice flips compliance for X%". That
   result could go to a policy venue.
4. **Apply the invariant to CBAM.** Byte-reproducibility under factor revision
   is exactly what Indian steel and aluminium exporters need for EU CBAM
   embedded-emissions reporting. One paragraph in the paper.

Cut the credit lifecycle automaton, the learning-to-rank component and the
Next.js workbench to their minimum.

### The Outsider

Reading this cold, as an examiner from another department would:

- **I can't tell what you found.** There are many acronyms (bitemporal, GEI,
  CEA, BEE, ACVA, CCC, DISCOM) and no plain one-sentence result. The clearest
  idea is buried in RQ3: "the official factor for year one was published a day
  after reports were due, so nobody could have used it, and the choice changes
  the answer by up to 8%." That should be the opening line.
- **The headline number comes from synthetic data.** An outsider will ask
  "is 7.8% real, or did you pick inputs that give 7.8%?" You need at least one
  real or published entity profile, or say plainly it's an illustration.
- **The one document that answers RQ3 hasn't been read.** It's an afternoon.
  The deadline has passed, so what verifiers actually did is observable. Ask
  one.
- **"Group project, one person built it, roles blank" is the biggest grading
  risk.** In a viva, teammates who can't explain the soundness proof or the
  trigger design pull the grade down faster than any missing feature. Assign
  ownership this week, one course per person.
- **A third of the grade has nothing built.** AI/ML is empty and there are no
  bills. Cut learning-to-rank (circular labels) and the lifecycle automaton,
  and shrink AI/ML to one honest, calibrated extractor with a clear held-out
  split.
- **"Byte-reproducible" means nothing to a newcomer.** Show a before/after:
  revise the factor, rerun last year's report, get the identical hash.
- **Push the repo.** CI that has never run is not evidence.

Verdict: strong engine, weak story. Not 90+ yet.

### The Executor

Not on track for 90+ as things stand, and it isn't a code problem. What exists
is strong DB work. The AI/ML course has nothing built and zero bills: one of
three grades is at zero, and the only planned fix depends on data nobody has
started collecting.

Monday morning, in order:

1. Fill TEAM.md today; give each person one phase to own and defend.
2. Push the repo; add a remote and get CI green.
3. Read the BEE procedure: one PDF, one afternoon.
4. Start collecting bills this week from at least 3 DISCOMs, aiming for 50+
   by week 4. If you can't, switch now to pdfplumber plus a calibrated
   classifier on synthetic bills, and say so openly.
5. Build denominator versioning next; with gei=null the headline CCTS metric
   isn't computed.
6. RQ1 is the fastest real result: closed-form arithmetic once you have cited
   Scope 1/2 splits per sector, about a week.

Cut:

- learning-to-rank audit sampling (circular labels);
- correlated uncertainty for grid factors (no source data; do IPCC fuel-factor
  ranges only);
- the Next.js workbench (static HTML + FastAPI is enough);
- arXiv (a Zenodo DOI is enough).

Keep the lifecycle automaton, but small: 5 states, with safety properties
model-checked or proved by hand. That fixes "thin ToC" in about a week. Then
hold a demo every Friday, with a commit trail.

## Peer reviews

**Anonymisation map:** A = Expansionist, B = Contrarian, C = Outsider,
D = Executor, E = First Principles.

**Tally:** Strongest: **B (Contrarian), 5 of 5.** Biggest blind spot:
**A (Expansionist), 5 of 5.**

### Review 1

1. **Strongest: B.** It ties each weakness to its consequence for the grade or
   the claim. gei=null means "+7.8%" is a change in tCO2e, not in compliance.
   The superuser connection means invariant 3 isn't enforced by the database.
   It flags FY2023-24 as the likely baseline year. E comes second: the
   HT-meter/SCADA point is the sharpest challenge to the AI/ML plan.
2. **Blind spot: A.** It ignores viva/ownership risk, the null GEI and the
   superuser hole, and adds scope (a BRSR corpus, CBAM, a policy paper,
   contacting regulators) against the project's scope-creep rule. BRSR reports
   company-level Scope 1/2, not plant-level gate-to-gate intensity per
   product, so it doesn't unblock RQ1 or RQ3.
3. **All missed:** the whole headline rests on one date; check whether it is
   the document date or the publication date. AI-authorship disclosure for
   RVCE. Nobody asked for the three actual course rubrics.

### Review 2

1. **Strongest: B**, for catching the most issues that could sink the grade:
   tCO2e versus compliance, superuser, the FY2023-24 baseline, individual
   vivas, circular labels. D is a close second as an action plan.
2. **Blind spot: A.** Silent on blank roles and vivas; adds scope; wants to
   publicise v22 before anyone reads BEE.
3. **All missed:** if BEE names a fixed factor version, the one-day gap
   doesn't matter and RQ3 collapses, so the team needs a fallback story
   before reading. Verify "dated 1 Aug" against a primary source. AI
   disclosure under the academic-integrity rules is a bigger viva risk than
   any missing feature.

### Review 3

1. **Strongest: B** (every structural problem, plus the FY2023-24 baseline
   insight). E second: the HT/SCADA point, and the factor-forecasting ML idea.
2. **Blind spot: A.** All expansion; no mention of roles, vivas, GEI,
   superuser or CI. BRSR is company-level while GEI is gate-to-gate per plant.
   Ignores the whole-team-agreement rule.
3. **All missed:** AI disclosure and academic integrity. Provenance of the
   headline date: archive the primary evidence (a Wayback snapshot, the file
   metadata).

### Review 4

1. **Strongest: B**: the tCO2e-versus-compliance distinction, superuser, the
   FY2023-24 baseline, cheap concrete fixes.
2. **Blind spot: A**: expansion without grading risks; BRSR is company-level;
   CBAM is scope creep.
3. **All missed:** the finding is fragile (document versus publication date;
   a BEE-prescribed fixed or baseline factor makes RQ3 vanish). Formal AI-use
   disclosure. Nobody checked RVCE's actual per-course rubrics.

### Review 5

1. **Strongest: B.** E second, but its CEA-forecasting ML idea risks
   predicting a figure from the very data used to compute it.
2. **Blind spot: A**: ignores roles, vivas, GEI, superuser and CI; scope
   creep; BRSR is company-level.
3. **All missed:** the v22 date is unchecked against the primary record, and
   a provisional release or a fixed version set by BEE could make the gap
   moot. AI-assisted solo authorship may need formal disclosure. Every
   proposed cut needs whole-team written sign-off, plus faculty-guide
   confirmation that the reduced components still meet each course's rubric.

## Facilitator note given to the chairman

The v22.0 workbook's own DATE cell reads 2026-08-01, and CEA hosts the file
under `/wp-content/uploads/baseline/2026/09/`; WordPress paths record the
upload month. So by both the document date and the upload month, v22 appeared
after 31 July 2026. It has not been archived externally, and the
gazette/notification date is unchecked.

## Chairman's synthesis

**Current trajectory: 72/100.** The engineering is strong, but a lot is
missing: the AI/ML component doesn't exist yet, GEI (CCTS's actual compliance
metric) is null, and only one person could defend the project in a viva
today.

### Where the Council Agrees

- **The biggest risk is the team, not the code.** Four of five advisors
  raised it. One person and an AI assistant built everything, and TEAM.md is
  blank. RVCE grades each member separately in the viva. Each member must own
  one component and be able to defend it, ideally by rebuilding or extending
  part of it themselves.
- **RQ3 is the real finding and the story of the project.** The first
  official FY2025-26 factor appeared one day after the deadline. Now that the
  first reporting cycle is over, what BEE's procedure says and what verifiers
  actually applied can be checked. Not having read the BEE procedure is now
  the most expensive gap.
- **The AI/ML component is empty and planned the wrong way.** Zero bills have
  been collected. Splitting test data by DISCOM needs many DISCOMs.
  Learning-to-rank on injected faults uses circular labels. Uncertainty
  propagation has no CEA data to work from. Every advisor cut
  learning-to-rank.
- **Cut the Next.js workbench.** Four advisors said so.
- **Cheap fixes:** push the repo so CI actually runs, and state plainly that
  the 7.8% figure comes from synthetic data.

### Where the Council Clashes

- **What the AI/ML component should be.** The Contrarian, Outsider and
  Executor would keep bill extraction but shrink it to a small calibrated
  extractor, with a synthetic fallback; it maps directly onto the rubric. The
  First Principles Thinker argues that CCTS plants get their electricity data
  from HT meters and SCADA, not scanned bills, and proposes forecasting the
  next CEA factor instead. Reviewers warned that the forecast could predict a
  figure from the same data used to compute it. **Ruling:** rubric fit wins.
  Build a small, honest extractor with calibrated confidence; a forecast is
  optional.
- **The lifecycle automaton.** The Expansionist and Outsider would cut it.
  The Executor would keep a 5-state version with checked safety properties.
  The Contrarian says the dimensional type checker is textbook material, so
  ToC needs the automaton. **Ruling:** keep it small and model-checked,
  because it carries the ToC grade.
- **Expand or contract.** The Expansionist wanted BRSR filings, CBAM and a
  policy paper. Every reviewer rejected this. BRSR reports company-level
  Scope 1/2, not plant-level emissions per unit of product, so it unblocks
  neither RQ1 nor RQ3. It also breaks the project's own scope rule.

### Blind Spots the Council Caught

- **The headline finding may not survive.** If BEE fixes the factor version
  (for example, the baseline-year factor), the one-day gap does not matter and
  RQ3 collapses. Write down a fallback framing before reading the procedure.
  Archive the evidence now: a Wayback snapshot, a file hash and the workbook
  metadata. Also check the gazette date.
- **The 5.1–7.8% swing is in tCO2e, not a change in compliance.** Without the
  production denominator, "policy choice changes compliance outcome" is not
  shown.
- **FY2023-24 is probably the CCTS baseline year.** Treating its methodology
  break as noise may throw away the most important data point.
- **The app connects to Postgres as superuser.** A superuser bypasses the
  triggers and permissions that invariant 3 relies on, so the invariant is not
  actually enforced yet. Fixing it takes about an hour.
- **AI-assistance disclosure.** Heavy AI-assisted solo authorship may need
  formal disclosure under RVCE's academic-integrity rules. Undisclosed, it is
  a bigger viva risk than any missing feature.
- **Nobody has the rubrics.** Get the three course rubrics and the faculty
  guide's sign-off before cutting anything.

### The Recommendation

Stop adding breadth. Spend the next 13 weeks turning one finding and one
guarantee into something each member can defend.

1. **Week 1:** assign ownership (DBMS, AI/ML, ToC, and RQ3/report, one each);
   disclose the AI assistance; push the repo with CI green; switch the app to
   a non-owner database role; read BEE's procedure and archive the v22
   evidence.
2. **Weeks 2–4:** build denominator versioning so GEI is computed, then
   recompute the RQ3 swing as a change in GEI and in compliance status on a
   cited, realistic sector profile.
3. **Weeks 3–6:** produce the RQ1 per-sector curve from cited Scope 1/2
   splits; it is closed-form arithmetic.
4. **Weeks 2–8:** start bill collection now and build a pdfplumber extractor
   with calibrated confidence and an honest held-out split. If fewer than
   about 30 real bills arrive by week 4, switch to synthetic bills and say so.
5. **Weeks 5–8:** build a 5-state credit automaton with model-checked safety
   properties.
6. **Weeks 9–13:** a Zenodo DOI for the registry; `reproduce.sh`; a
   before/after reproducibility demo (revise a factor, rerun last year's
   report, show the identical hash); viva rehearsals where each member
   defends another member's component.

Cut learning-to-rank, the Next.js workbench, correlated grid-factor
uncertainty, arXiv, BRSR and CBAM. Record the cuts with whole-team written
sign-off.

Done this way, 88–92 is realistic.

### The One Thing to Do First

This week, read BEE's "Detailed Procedure for Compliance Mechanism under CCTS
v1.0" and record in `docs/RQ3_FINDINGS.md` which factor version it
prescribes, if any. Archive the v22 evidence alongside it. Every other
priority depends on whether RQ3 survives.
