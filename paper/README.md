# The IEEE paper

`main.tex` is an IEEE conference paper (`IEEEtran`). It contains **no number of
its own**: every figure in the text is a macro from `numbers.tex`, every table body
is a file in `tables/`, every graph is a PDF in `figs/`, and all of them are
written by one script from the open registry.

    python scripts/paper_build.py --figures    # data/cea/*.csv -> numbers.tex, tables/, figs/ (figures need matplotlib)
    python scripts/paper_build.py --check      # fails if a committed file differs from what the data give
    python scripts/paper_build.py --submit-check   # lists the open [VERIFY] items; fails while any remain
    pytest tests/test_paper.py                 # all of the above, plus agreement with docs/RQ1-3 and the nowcast

Compile with `pdflatex main && bibtex main && pdflatex main && pdflatex main`, or
upload the folder to Overleaf (it provides `IEEEtran.cls`). **This repository was
not compiled by its author's tools**: no TeX distribution was available when the
paper was drafted, so a first compile on Overleaf may show warnings to fix. The
tests check braces, environments, citations, references, macros and table
columns, not the typeset result.

## Why the numbers can be trusted, and what that does not cover

- They are computed from `data/cea/factors.csv` and `versions.csv` (their SHA-256
  prefixes are printed in the paper's Reproducibility section), by the same
  functions that write `docs/RQ1_RESULTS.md`, `RQ3_COMPLIANCE.md` and
  `NOWCAST_RESULTS.md`, and cross-checked against `docs/RQ2_RESULTS.md`.
- `tests/test_paper.py` fails if `main.tex` gains a literal number, if a
  committed table or number goes stale, or if the paper and the docs disagree.
- That makes the **numbers** reproducible. It does not make the **claims** true:
  the procedure text, the targets, the baseline year and the reference details are
  marked `\verify{...}` in red, 16 of them at the time of writing, and the paper
  cannot be submitted while any remain (`--submit-check`).

## Before submitting

1. Resolve every `\verify{}`: confirm the BEE text against the notified
   procedure, find the target notification, fix the references' details.
2. Fill the authors, ORCID iDs and the acknowledgement (including the AI-use
   wording the venue requires; see `docs/AI_USE.md`).
3. Mint the registry's DOI and cite it; settle the licence and CEA's terms.
4. Check the venue's template, page limit and reference style; this is a
   six-page-class draft.
5. Do the independent hand check of the registry (`docs/paper/HAND_CHECK.csv`).
