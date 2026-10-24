# Use of AI assistance

**Draft record for the team to review, complete and submit as RVCE's rules
require.** Check RVCE's academic-integrity / AI-use policy and each course's
guidance, and adjust this file to whatever form they ask for. Nothing here is
a claim about what the policy permits. Last updated 2026-10-24.

## What was AI-assisted

Most of this repository was written by a team member working with an AI coding
assistant (Claude, via Claude Code), from 26 September to 24 October 2026
(68 commits, phases 0 to 10). The assistant, under the member's direction:

- wrote most of the code, migrations, tests and documentation, including the
  reproducibility property tests, the type checker, the credit automaton and its
  proof checks, the extraction pipeline, the sampling and materiality code, and
  the single-file console;
- downloaded and parsed the public CEA CO2 Baseline Database files (all
  versions), with the member's approval;
- ran the tests, the end-to-end pipeline, adversarial experiments and the
  GitHub Actions runs, and wrote the fixes when they failed;
- ran an "LLM council" evaluation of the project (`docs/council/`), whose
  advisors, reviewers and chairman were AI model instances, not people;
- drafted the two paper texts (`docs/paper/`), the Data in Brief formatting and
  its two figures (generated from the data by `scripts/dib_figures.py`), and the
  demo video (script, captions, synthesised music and rendering);
- searched the web for journal requirements, and read the editor-in-chief's
  Data in Brief guidance. Journal fees and scope statements it reports must be
  confirmed on the journals' own pages.

**Attribution in the git history.** The assistant's commits originally carried a
`Co-Authored-By: Claude` line. At the repository owner's request those lines
were removed from the commit messages before the first push to GitHub, so the
public history shows one author. That does not change what was AI-assisted, and
this file is the record of it. Do not describe the repository as written without
AI assistance.

## What was not AI-generated

- Regulatory facts in `CLAUDE.md` ("verified, safe to rely on") were supplied
  by the team.
- CEA data values come from CEA's own workbooks; every figure is traceable to
  a workbook cell (`data/cea/factors.csv`).
- The BEE procedure text quoted in `docs/RQ3_FINDINGS.md` was read by the
  assistant from one PDF. No team member has confirmed it against the notified
  text (`docs/STATUS.md`).
- No real bill, no real plant and no sector Scope 2 share has been supplied by
  anyone. All plant data is synthetic.

## What a human must still do before relying on this work

- Check each claim in the papers against its source; every `[verify]` and `[ ]`
  marker is an open item. The authors answer for the papers, not the assistant.
- Do the independent hand check of the registry (`docs/paper/HAND_CHECK.csv`):
  the current validation is largely the assistant's own code checking itself.
- State the AI use in each paper in the venue's wording (Data in Brief and
  Elsevier have a declaration section; the draft marks where).

## How the team takes ownership

See `docs/TEAM.md`: each member owns a component and must be able to explain
and defend it in the viva without the assistant.

## To complete
- [ ] RVCE policy checked; this file revised to match it
- [ ] Each member has read and agreed this record
- [ ] Disclosure submitted to faculty guides, if required
- [ ] Each paper's AI-use declaration written in the venue's wording
