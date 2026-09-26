# CarbonX — project context for Claude Code

Read this before writing any code. It defines what we are building, what we are
deliberately NOT building, and the invariants that must never break.

---

## What this is

A bitemporal carbon accounting ledger for India's Carbon Credit Trading Scheme
(CCTS), where every reported emission figure is traceable to source evidence and
every historical report stays byte-reproducible when emission factors are revised.

**V-semester group Experiential Learning project, RVCE. 14 weeks.**
Graded under three courses: DBMS, AI/ML, Theory of Computation. SDG 13.
Declared outcome on the form: **product development** (not patent, never patent).

## The problem

Calculating emissions is arithmetic: `activity × emission factor`. Proving them
is not. To verify a reported figure an auditor must reconstruct which meter
reading, which invoice, which emission factor, which *version* of that factor,
who entered it, and what it was before correction. That evidence lives across
spreadsheets, PDFs and email.

**The bottleneck in carbon reporting is provenance, not computation.**

## The research questions

- **RQ1 — Materiality.** At what Scope 2 share of total emissions does grid
  emission factor revision *alone* cross the 5% rebaselining threshold that
  GHG Protocol / SBTi treat as significant? Produce the sensitivity curve per
  CCTS sector.
- **RQ2 — Signal vs noise.** Across CEA CO2 Baseline Database v2–v21, what is
  the distribution of year-on-year factor changes, and how often does it exceed
  that year's CCTS GEI reduction target?
- **RQ3 — Version ambiguity.** Compliance year FY2025-26; reports due July 2026;
  CEA v21 covers FY2024-25. Which version should a verifier apply? If BEE's
  procedure is silent, competing resolution policies produce different compliance
  outcomes on identical physical performance.

**RQ3 status is UNRESOLVED.** Someone must read BEE's "Detailed Procedure for
Compliance Mechanism under CCTS v1.0" (July 2024) and record the answer in
`docs/RQ3_FINDINGS.md` before Phase 5.

## The claim we make — and the one we do NOT

**DO say:** "Carbon accounting platforms exist and evidence lineage is a standard
enterprise feature. Our contribution is (a) an open machine-readable registry of
India's grid emission factor version history, (b) a verified reproducibility
guarantee under factor revision, and (c) a per-sector materiality sensitivity
curve."

**DO NOT say:** "We measured how much reported emissions shift from factor
revision and nobody knew this mattered." GHG Protocol *requires* base-year
recalculation and explicitly lists updated emission factors as a trigger. SBTi
sets a 5% threshold. This is standardised. Claiming novelty here is wrong and
will be caught.

**NEVER state the headline as "1.54% factor revision vs 1-3% GEI target"
without the Scope 2 qualifier.** GEI covers Scope 1 AND Scope 2 gate-to-gate.
In cement, iron & steel and refining, process emissions dominate and are
untouched by the grid factor. The honest framing is the per-sector sensitivity
curve, not a single dramatic comparison.

**NEVER describe this as a verification platform or imply it issues assurance
opinions.** It is a decision-support tool for accredited verifiers. A research
prototype. Not accredited. ACVA accreditation is a regulated status.

---

## Domain facts (verified — safe to rely on)

- CCTS compliance mechanism: GEI targets in **tCO2e per unit of product output**,
  gate-to-gate, covering Scope 1 and 2.
- FY2025-26 targets require **1–3% GEI reduction**; FY2026-27 ratchets to 2–8%.
- **2x penalty** for non-compliance.
- ~490 entities with active obligations across 7 notified sectors; 9 sectors
  notified total (aluminium, cement, chlor-alkali, fertiliser, iron & steel,
  pulp & paper, petrochemicals, petroleum refinery, textile); ~740 entities,
  >700 Mt CO2e.
- First compliance deadline was **31 July 2026**. First CCC trading expected
  ~October 2026 on IEX and PXIL. Registry operated by Grid Controller of India.
- Verification by **BEE-accredited carbon verification agency (ACVA)**;
  reasonable assurance expected for compliance entities.
- CEA CO2 Baseline Database: **v19 = 0.716 tCO2/MWh (FY2022-23)**,
  **v20 = 0.727 weighted avg w/ RE (FY2023-24)**, v21 covers FY2024-25.
  All previous versions remain published on cea.nic.in.
- GHG Protocol requires base-year recalculation on emission factor updates;
  no numeric threshold prescribed. SBTi uses **>=5% change in base year emissions**.

Anything NOT in this list must be verified from a primary source before it goes
in the report. Do not cite secondhand regulatory detail.

---

## Hard invariants — these must never break

1. **Reproducibility.** For any report R generated at transaction time T,
   re-executing R `AS OF T` at any later time T' produces byte-identical output,
   regardless of intervening factor supersessions, backdated corrections or data
   edits. Verified by property-based testing, not assertion.
2. **No in-place factor updates.** Factors are superseded, never overwritten.
   A calculation pins the factor row it used, forever.
3. **Audit trail is enforced at the database layer** via triggers, not
   application code. It must hold even if the application is wrong.
4. **Dimensional soundness.** A calculation that type-checks cannot produce a
   dimensional error. `kWh x kgCO2e/kWh -> kgCO2e` compiles;
   `kWh x kgCO2e/litre` does not.
5. **Evidence integrity.** Every source document has a SHA-256 hash recorded at
   upload. The audit log is hash-chained (each event includes the previous
   event's hash). This is tamper-EVIDENCE, not blockchain — say so explicitly.
6. **Uncertainty is never invented.** Factor uncertainty comes from published
   IPCC 2006 Vol 2 ranges. Extraction uncertainty comes from calibrated model
   confidence. If we have no empirical basis for a variance, we report a point
   estimate and say so.

---

## Scope — BUILD

| # | Component | Course |
|---|---|---|
| 1 | Bitemporal emission factor registry + version-resolution policies | DBMS |
| 2 | Denominator (production basis) versioning — intensity-aware | DBMS |
| 3 | Carbon calculation engine | — |
| 4 | Evidence store, SHA-256, hash-chained audit trail via DB triggers | DBMS |
| 5 | Materiality engine (5% threshold, auto recalculation disclosure) | DBMS |
| 6 | Dimensional type system with soundness argument | **ToC** |
| 7 | Document extraction, calibrated confidence, held-out by DISCOM | **AI/ML** |
| 8 | Correlated uncertainty propagation | **AI/ML** |
| 9 | Risk-weighted audit sampling (learning to rank) | **AI/ML** |
| 10 | Credit lifecycle automaton + proved safety properties | **ToC** |
| 11 | Verifier's workbench UI | — |
| 12 | Open CEA factor registry, released with Zenodo DOI | Deliverable |

## Scope — DO NOT BUILD

Order book. Matching engine. Price discovery. Buyer/seller roles. Composite
data-quality score. Opportunity ranking engine. Credit-readiness scoring.
Multi-role RBAC. Batch PDF reports. Scope 3. Blockchain. Live ICM registry
integration. LLM chatbot. IoT. Mobile app. Multi-tenant SaaS.

Every item above was considered and cut. The order book is cut because CCTS
trading is statutorily on IEX/PXIL, the engineering is trivial, and it is the
component most similar to a previous project (MarketOS). **Adding anything to
the BUILD list requires whole-team written agreement.** Scope creep is the
highest-likelihood failure mode.

---

## Stack

- Python 3.11+, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2
- PostgreSQL 16 + `btree_gist` (exclusion constraints on temporal ranges)
- pytest + **Hypothesis** (property-based testing — this is how invariant 1 is verified)
- pdfplumber (digital PDFs), PaddleOCR or docTR (scanned)
- transformers / LayoutLMv3 for extraction; scikit-learn, XGBoost, SHAP
- Next.js + Tailwind + Recharts (frontend)
- Docker Compose
- Zenodo (DOI), GitHub, arXiv

## Conventions

- `src/carbonx/<module>/` — one package per component above
- Type hints everywhere; `mypy --strict` on `src/carbonx/units` and `factors`
- Every DB change is an Alembic migration. Never edit a migration that has run.
- Every module gets tests. Invariant 1 gets Hypothesis tests specifically.
- `reproduce.sh` must run the whole pipeline end-to-end on sample data with one
  command. Evaluators check for this and almost nobody has it.
- No raw utility bills committed to the repo, ever. Redact before storage.
- Commit messages reference the phase: `[P3] add factor resolution policies`
