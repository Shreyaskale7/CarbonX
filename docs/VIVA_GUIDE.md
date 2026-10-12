# Viva guide: a five-minute demo and the questions to expect

For the team. `docs/TEAM.md` says who owns what; this file is what each owner
should be able to show and answer. Every answer points at the file that backs
it. If you cannot find the answer in that file, you are not ready on that
question yet.

Rehearse the demo on the machine you will present on, the day before. On
2026-10-06 and 2026-10-12 Windows Application Control on the development laptop
blocked the bundled Postgres and parts of scikit-learn; see "If the demo
machine fails" at the end.

## The demo (about five minutes, no terminal after the first command)

Start: `bash reproduce.sh`, then `uvicorn carbonx.api.main:app`, then open
http://127.0.0.1:8000. Everything below is clicks.

| # | Page | Do | Say |
|---|---|---|---|
| 1 | Home | Press **Regenerate and compare** | "This report was stored earlier. We just recomputed it as of its own time and the hash is identical. That is the guarantee the project is about." |
| 2 | Ledger | Click any tCO2e figure | "One figure, walked back: facility, activity, source document and its hash, the exact factor row and CEA file it came from, the typed calculation, and the audit trail." |
| 3 | Ledger | In the same panel, point at **The same activity under each factor policy** | "Same meter reading, four defensible readings of the rule, different tonnes. The difference is policy alone." |
| 4 | Ledger | **Correct** a quantity, give a reason | "The old row is closed, not edited. It is still there under 'Before correction', and the reason is in the audit trail." |
| 5 | Reports | **Run the demonstration** | "A factor revision and a backdated correction arrive. A new report changes. The old report, regenerated, does not. Then it is all rolled back." |
| 6 | Reports | **Details** on a report | "The uncertainty band uses only published IPCC ranges. Most of this total has no published range, and we say so instead of inventing one." |
| 7 | How it works | **Wrong factor unit**, then the lifecycle buttons and **Ask the database** | "The calculation language refuses kWh times kg per litre before computing anything. The credit lifecycle is refused by the database itself, not by the page." |
| 8 | Findings | Scroll to **The same plant, three outcomes** | "This is the research result: BEE's rule names a factor but does not fix a number." |

State once, early: the sample plant is synthetic, the tool is a research
prototype, and it supports accredited verifiers; it does not verify.

## Questions to expect

### DBMS

**Why two time axes?** Valid time is when a fact was true (the financial year
a factor describes). Transaction time is when the system learned it. A report
must answer "what did we know then", which needs the second axis.
`db/schema.sql`, `src/carbonx/factors/registry.py`.

**How does the database stop two factors claiming the same year?** A GiST
exclusion constraint over factor key, geography, valid time and transaction
time. It needs `btree_gist`. `db/schema.sql`, `tests/test_factor_registry.py`.

**Why triggers and not application checks?** So the rule holds when the
application is wrong. The application connects as `carbonx_app`, which owns no
tables and cannot disable triggers. Migration `0005`,
`test_app_role_cannot_bypass_the_database_rules`.

**Can a DBA still break it?** Yes. The owner and any superuser can. Say so
before you are asked. `docs/ADVERSARIAL_LOG.md`, attempt 12.

**What is the hash chain, and is it a blockchain?** Each audit event stores the
hash of the previous one, so altering history is detectable. It is tamper
evidence. It is not a blockchain: one writer, no consensus.

**How do you know reports reproduce?** Not by assertion: 10,000 generated
operation sequences, each ending with every report regenerated and compared
byte for byte, plus two-connection tests for the commit-time race.
`tests/test_reproducibility.py`, `docs/ADVERSARIAL_LOG.md`. Know the limits:
that run was on the development Postgres, and in one transaction.

**What broke on the way?** Have one ready. The best is the commit-time race:
a report could miss a row another transaction had stamped but not committed.
Fixed by taking transaction time under a global lock (migration `0003`).

**Why is that global lock acceptable?** It is not, at scale. It is a prototype
shortcut; partitioning by organisation is the upgrade path. Say that.

### Theory of Computation

**What is the grammar, and why LL(1)?** Five productions, in the docstring of
`src/carbonx/units/lang.py`. One token of lookahead decides every choice; be
able to show it for `atom`. The lexer's token language is regular.

**What exactly is proved?** If a program type-checks, evaluating it never
hits a dimension error, and each binding has its declared dimension.
`docs/TYPE_SOUNDNESS.md`, sections 4 and 5. Dimensions are vectors of six
integer exponents; multiplication adds them.

**Where does the guarantee stop?** Eight documented escape hatches, section 6
of the same file. It checks dimensions, not that you picked the right factor.

**Is `kWh × kg/litre` an error?** The product is well formed. The error is
declaring the result to be tonnes of CO2e. Get this right; the build plan
originally had it wrong.

**The automaton: states, alphabet, what is proved?** Five states, four
symbols, seven transitions. P1: surrendered and retired are absorbing. P2: a
live credit has exactly one holder. P3: conservation. `docs/LIFECYCLE.md`.
P2 is an inductive invariant; be able to do the inductive step for `transfer`.

**Is the model checker a proof?** No. It checks small instances exhaustively
and gives shortest counterexamples for mutated tables. The proof is the
hand-written induction. It is not machine-verified.

### AI/ML

**What does the model do?** It picks which number on a bill is the
consumption, by scoring candidates with logistic regression on position-free
features. `src/carbonx/extraction/extract.py`, `docs/EXTRACTION.md`.

**What are the results?** On unseen test layouts: 33.3% against a rule
baseline of 0%. Confidence is **not** calibrated there (ECE 0.347).
`docs/EXTRACTION_RESULTS.md`. Do not round this up.

**Why report a weak number?** Because the first model scored 0% at 99.6%
confidence on a new layout, and finding that is the result. Layouts 6 to 8
became development data once they were used for error analysis; 9 to 11 were
written afterwards and scored once. Explain why that split is the honest one.

**Is the data real?** No. Every bill is synthetic. Real, redacted bills are
still to be collected. Say it first.

**So how is the model used?** Its output is never used on its own authority.
Every value waits in a review queue, least confident first, for a person.

**What is correlated uncertainty?** Lines that share one emission factor are
wrong together, so their ranges add linearly; different factors combine in
quadrature. Treating lines as independent understates the band.
`docs/UNCERTAINTY.md`, `tests/test_uncertainty.py`.

**What is the nowcast, and what did it find?** Predicting a year's grid factor
before CEA publishes it. "Use last year's value" missed by 1.99% on average over
20 years, and drift, trend and AR(1) models did no better. `docs/NOWCAST.md`,
`docs/NOWCAST_RESULTS.md`.

**How do you know the backtest does not cheat?** The vintage rule: each forecast
uses only values from CEA versions published before the target year first
appeared. Be able to explain why using the latest restated values would leak.
A test fails if the rule is broken.

**Why such simple models?** About twenty yearly values. Anything tunable would be
fitted to noise. A null result with an honest evaluation is the finding.

**Why not predict from generation data?** CEA computes the factor from it, so
that is accounting done early, not forecasting.

**Why no uncertainty for the grid factor?** CEA publishes none, and invariant
6 forbids inventing one. The nowcast band is the uncertainty of a guess made
before publication, which is a different thing; keep the two apart.

### Research

**What is the contribution?** An open, machine-readable history of India's
grid emission factor; a tested reproducibility guarantee under revision; and a
per-share sensitivity result. Not "nobody knew factor revisions matter": GHG
Protocol already requires recalculation and SBTi sets 5%.

**What did you find?** BEE's rule says "the latest average grid emission
factor". Two readings of "latest" differ by 4.87% for FY2025-26; CEA's four
average series differ by 17 to 22%; the FY2025-26 factor is dated one day
after reports were due. `docs/RQ3_FINDINGS.md`.

**Does that change anyone's compliance?** We do not claim that. We show the
arithmetic per Scope 2 share, with the baseline year assumed.
`docs/RQ3_COMPLIANCE.md`. Always attach the Scope 2 qualifier: in cement and
steel most emissions are untouched by the grid factor.

**What is unverified?** The BEE PDF's status as the notified text; the
baseline year; per-sector Scope 2 shares. `docs/STATUS.md` lists them.

**How was AI used?** Answer from `docs/AI_USE.md`, completed and agreed by the
team, consistent with RVCE's policy. Do not improvise this one.

## If the demo machine fails

- **Database will not start.** After a reboot, `python scripts/dev_pg.py env`
  waits for recovery and retries. If Windows reports that `postgres.exe` was
  blocked by policy, the bundled Postgres cannot run on that machine. Use a
  PostgreSQL 16 installed from postgresql.org or Docker instead, set
  `DATABASE_URL` and `MIGRATION_DATABASE_URL`, and run `reproduce.sh`. That is
  also the real target, with the real extensions.
- **scikit-learn blocked.** The site still runs; only "Read consumption from
  it" fails, with a clear message. Skip that step and say why.
- **Nothing runs.** Show `docs/figures/`, `docs/RQ3_COMPLIANCE.md` and the CI
  run on GitHub. This is one reason to push the repository before the viva.
