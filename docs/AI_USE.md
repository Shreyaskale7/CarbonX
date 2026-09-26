# Use of AI assistance

**Draft record for the team to review, complete and submit as RVCE's rules
require.** Check RVCE's academic-integrity / AI-use policy and each course's
guidance, and adjust this file to whatever form they ask for. Nothing here is
a claim about what the policy permits.

## What was AI-assisted

Weeks 1–2 (Sep 2026): phases 0–5 were built by one team member working with
an AI coding assistant (Claude, via Claude Code). The assistant:

- wrote most of the code, migrations, tests and documentation in this
  repository, under the member's direction, commit by commit (see
  `git log`; commits carry a `Co-Authored-By: Claude` trailer);
- downloaded and parsed the public CEA CO2 Baseline Database files (all
  versions), with the member's approval;
- ran the tests, the end-to-end pipeline and adversarial experiments against
  a local Postgres;
- ran an "LLM council" evaluation of the project (`docs/council/`), whose
  advisors, reviewers and chairman were AI model instances, not people.

## What was not AI-generated

- Regulatory facts in `CLAUDE.md` ("verified, safe to rely on") were supplied
  by the team.
- CEA data values come from CEA's own workbooks; every figure is traceable to
  a workbook cell (`data/cea/factors.csv`).
- The BEE procedure has not been read by anyone yet (`docs/RQ3_FINDINGS.md`).

## How the team takes ownership

See `docs/TEAM.md`: each member owns a component and must be able to explain
and defend it in the viva without the assistant.

## To complete
- [ ] RVCE policy checked; this file revised to match it
- [ ] Each member has read and agreed this record
- [ ] Disclosure submitted to faculty guides, if required
