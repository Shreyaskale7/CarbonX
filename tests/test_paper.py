"""The IEEE paper's claim to be reproducible, made checkable. No database.

1. Every committed number and table equals what the data give.
2. Those numbers agree with the independently generated docs (RQ1, RQ2, RQ3, nowcast),
   so the paper, the docs and the console cannot say different things.
3. paper/main.tex contains no figure of its own: numbers come only from macros.
4. The LaTeX is sound as far as can be checked without compiling: balanced braces,
   matched environments, every citation, reference, macro and file resolves.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import paper_build as pb

PAPER = ROOT / "paper"
TEX = (PAPER / "main.tex").read_text(encoding="utf-8")
DOCS = ROOT / "docs"


def table_rows(markdown: str, first_cell: str) -> list[str]:
    return [ln for ln in markdown.splitlines() if ln.startswith("| " + first_cell)]


def test_committed_numbers_and_tables_equal_what_the_data_give():
    for path, text in pb.outputs(pb.compute()).items():
        assert path.read_text(encoding="utf-8") == text, path.name


def test_figures_exist_for_every_includegraphics():
    for name in re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", TEX):
        assert (PAPER / name).exists(), name


def test_the_numbers_agree_with_the_generated_docs():
    res = pb.compute()
    n = res["n"]
    rq2 = (DOCS / "RQ2_RESULTS.md").read_text(encoding="utf-8")
    cells = [c.strip() for c in table_rows(rq2, pb.HEADLINE)[0].strip("|").split("|")]
    # factor | FYs | steps | median | max | >1% | >3% | median revision | max revision
    assert (cells[2], cells[3], cells[4], cells[5], cells[6], cells[7], cells[8]) == (
        n["nSteps"], n["medStep"] + "%", n["maxStep"] + "%", f"{n['nOverOne']}/{n['nSteps']}",
        f"{n['nOverThree']}/{n['nSteps']}", n["medRev"] + "%", n["maxRev"] + "%")
    for key, row in zip(pb.LONG_SERIES, res["tables"]["tab_steps"].splitlines(), strict=True):      # the whole step table
        d = [c.strip() for c in table_rows(rq2, key)[0].strip("|").split("|")]
        want = [c.strip().replace("\\%", "%") for c in row.rstrip("\\ ").split("&")]
        assert [want[1], want[2], want[3], f"{want[4]}/{want[1]}", f"{want[5]}/{want[1]}", want[6]] == [
            d[2], d[3], d[4], d[5], d[6], d[7]], key
    rq1 = (DOCS / "RQ1_RESULTS.md").read_text(encoding="utf-8")
    assert f"| series | spread of CEA's four average series, v22 FY2025-26 | {n['effectSeries']}% | {n['shareSeries']}% |" in rq1
    assert f"-{n['effectLatest']}%" in rq1 and f"-{n['effectRevision']}%" in rq1
    rq3 = (DOCS / "RQ3_COMPLIANCE.md").read_text(encoding="utf-8")
    for want in (f"-{n['dDeadline']}% | {n['shNeeded1Deadline']}% |", f"-{n['dAfter']}% | {n['shNeeded1After']}% | {n['shNeeded3After']}% |"):
        assert want in rq3, want
    nowcast = (DOCS / "NOWCAST_RESULTS.md").read_text(encoding="utf-8")
    assert f"wrong by {n['naiveMAE']}% on average** (RMSE {n['naiveRMSE']}%, worst -{n['naiveWorst']}%)" in nowcast
    assert f"contained {n['covEighty']} of {n['covEightyOf']} later values, the 90% band {n['covNinety']} of {n['covNinetyOf']}" in nowcast
    assert f"band {n['bandLow']} to {n['bandHigh']}" in nowcast and f"published {n['bandPublished']}" in nowcast
    for row in res["tables"]["tab_nowcast"].splitlines():
        model = row.split(" & ")[0]
        assert f"| {model} |" in nowcast


ALLOWED = re.compile(r"SHA-256|\b(?:19|20)\d{2}\b")


def body_text() -> str:
    """The prose of main.tex: no comments, no \\verify notes, no bibliography, no markup arguments."""
    text = TEX[TEX.index(r"\begin{document}"):TEX.index(r"\begin{thebibliography}")]
    text = re.sub(r"(?<!\\)%.*", "", text)
    text = re.sub(r"\\verify\{(?:[^{}]|\{[^{}]*\})*\}", "", text)
    text = re.sub(r"\\begin\{tabular\}\{.*", "", text)
    text = re.sub(r"\\(?:cite|label|ref|eqref|input|url|includegraphics(?:\[[^\]]*\])?|begin|end)\{[^}]*\}", "", text)
    return text


def test_main_tex_has_no_literal_figures():
    text = ALLOWED.sub("", body_text())
    bad = re.findall(r"\d+[.,]\d+|\d{2,}|\d\s*\\%", text)
    assert not bad, f"literal numbers in main.tex (use a macro from numbers.tex): {bad}"


def test_latex_is_consistent_without_compiling():
    stripped = re.sub(r"(?<!\\)%.*", "", TEX)
    plain = re.sub(r"\\[{}]", "", stripped)
    assert plain.count("{") == plain.count("}"), "unbalanced braces"
    begins, ends = re.findall(r"\\begin\{(\w+\*?)\}", stripped), re.findall(r"\\end\{(\w+\*?)\}", stripped)
    assert sorted(begins) == sorted(ends)
    bib = set(re.findall(r"\\bibitem\{(\w+)\}", TEX))
    cited = {k.strip() for group in re.findall(r"\\cite\{([^}]+)\}", TEX) for k in group.split(",")}
    assert cited == bib, cited ^ bib
    labels = set(re.findall(r"\\label\{([\w:]+)\}", TEX))
    refs = set(re.findall(r"\\(?:ref|eqref)\{([\w:]+)\}", TEX))
    assert refs <= labels, refs - labels
    defined = set(re.findall(r"\\newcommand\{\\(\w+)\}", (PAPER / "numbers.tex").read_text(encoding="utf-8")))
    defined |= set(re.findall(r"\\newcommand\{\\(\w+)\}", TEX))
    used = set(re.findall(r"\\([A-Za-z]+)\{\}", stripped))
    assert used <= defined, f"undefined macros: {used - defined}"
    for name in re.findall(r"\\input\{([^}]+)\}", TEX):
        assert (PAPER / (name if name.endswith(".tex") else name + ".tex")).exists(), name
    assert r"\documentclass[conference]{IEEEtran}" in TEX


def test_every_macro_in_the_text_comes_from_the_generated_file_or_is_declared():
    stripped = re.sub(r"(?<!\\)%.*", "", TEX)
    numbers = set(re.findall(r"\\newcommand\{\\(\w+)\}", (PAPER / "numbers.tex").read_text(encoding="utf-8")))
    assert {"nVersions", "gapReadings", "spreadTwoTwo", "naiveMAE", "shaFactors"} <= numbers
    assert not (numbers & set(re.findall(r"\\newcommand\{\\(\w+)\}", stripped))), "a generated macro is redefined by hand"


def test_every_generated_table_row_has_as_many_cells_as_its_tabular_has_columns():
    for name in re.findall(r"\\input\{tables/(\w+)\}", TEX):
        before = TEX[:TEX.index("\\input{tables/" + name + "}")]
        spec = re.findall(r"\\begin\{tabular\}\{(.*)\}", before)[-1]
        columns = len(re.findall(r"p\{[^}]*\}|[lrc]", re.sub(r"@\{\}", "", spec)))
        for row in (PAPER / "tables" / f"{name}.tex").read_text(encoding="utf-8").splitlines()[1:]:
            assert row.count("&") + 1 == columns and row.rstrip().endswith("\\\\"), (name, row)
