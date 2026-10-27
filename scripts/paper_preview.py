"""A two-column PDF PREVIEW of paper/main.tex, for reading before it is typeset.

    python scripts/paper_preview.py      # -> paper/main_preview.pdf   (needs playwright with Chromium)

This is not LaTeX output. It converts the subset of LaTeX that main.tex uses to HTML and prints
that with Chromium in an IEEE-like layout, so the words, numbers, tables and figures are exactly
main.tex's, but fonts, hyphenation, float placement and page breaks are not what IEEEtran gives.
Open items stay visible in red. For the submission copy, compile main.tex (Overleaf, or any TeX).
"""
import base64
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper"
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]

CSS = """
@page { size: Letter; margin: 0.75in 0.625in 0.9in; }
body { font: 9.6pt/1.18 'Times New Roman', Times, serif; margin: 0; text-align: justify; hyphens: auto; }
.banner { font: 7.5pt sans-serif; color: #a00; border: 1px solid #a00; padding: 2px 6px; margin-bottom: 8px; text-align: center; }
.head { column-span: all; text-align: center; margin-bottom: 8px; }
h1 { font-size: 20pt; line-height: 1.12; margin: 6px 0 8px; font-weight: normal; }
.authors { font-size: 10pt; }
.cols { column-count: 2; column-gap: 0.25in; }
h2 { font-size: 9.6pt; text-align: center; text-transform: uppercase; font-weight: normal; margin: 9px 0 3px; }
h3 { font-size: 9.6pt; font-style: italic; font-weight: normal; margin: 6px 0 2px; }
p { margin: 0 0 4px; text-indent: 0; }
.abs { font-weight: bold; font-size: 9pt; }
.kw { font-weight: bold; font-style: italic; font-size: 9pt; }
figure, .tbl { margin: 6px 0; break-inside: avoid; text-align: center; }
figure img { width: 100%; }
figcaption, .tcap { font-size: 8pt; text-align: justify; margin-top: 2px; }
.tcap { text-align: center; margin-bottom: 3px; text-transform: uppercase; }
table { border-collapse: collapse; width: 100%; font-size: 7.6pt; margin: 0 auto; }
th, td { padding: 1px 3px; text-align: right; border-top: 1px solid #000; }
td:first-child, th:first-child { text-align: left; }
tr:first-child th { border-top: 2px solid #000; border-bottom: 1px solid #000; }
tr:last-child td { border-bottom: 2px solid #000; }
.eq { display: flex; justify-content: space-between; align-items: center; margin: 4px 0; }
code { font: 8pt 'Cascadia Mono', Consolas, monospace; }
.v { color: #c00; font-weight: bold; }
ul { margin: 0 0 4px 14px; padding: 0; } li { margin: 0; }
.refs { font-size: 8pt; } .refs p { margin: 0 0 2px 14px; text-indent: -14px; }
"""
EQ = ("<math display='block'><mfrac><mrow><mi>&Delta;</mi><mi mathvariant='normal'>GEI</mi></mrow>"
      "<msub><mi mathvariant='normal'>GEI</mi><mi>b</mi></msub></mfrac><mo>=</mo><mi>s</mi><mo>(</mo>"
      "<mfrac><msub><mi>f</mi><mi>a</mi></msub><msub><mi>f</mi><mi>b</mi></msub></mfrac><mo>&minus;</mo><mn>1</mn><mo>)</mo></math>")


def numbers() -> dict[str, str]:
    return dict(re.findall(r"\\newcommand\{\\(\w+)\}\{([^}]*)\}", (PAPER / "numbers.tex").read_text(encoding="utf-8")))


def math(m: str) -> str:
    m = m.replace("\\,", "").replace("\\mathrm{GEI}", "GEI").replace(">", "&gt;")   # escape before any tag is added
    m = m.replace("\\Delta", "&Delta;")
    m = re.sub(r"_\{([^}]*)\}", r"<sub>\1</sub>", m)
    m = re.sub(r"_(\w)", r"<sub>\1</sub>", m)
    m = re.sub(r"(?<![&;\w/<])([A-Za-z])(?![A-Za-z;/>])", r"<i>\1</i>", m)
    return m


def inline(t: str, nums: dict, cites: dict, labels: dict) -> str:
    t = re.sub(r"\\label\{[^}]*\}", "", t)
    for k, v in nums.items():
        t = t.replace("\\" + k + "{}", v)
    t = t.replace("\\tCO{}", "tCO<sub>2</sub>").replace("\\textsubscript{2}", "<sub>2</sub>")
    t = re.sub(r"\\verify\{((?:[^{}]|\{[^{}]*\})*)\}", lambda m: f"<span class=v>[VERIFY: {html.escape(m[1].replace(chr(92) + '_', '_'))}]</span>", t)
    t = re.sub(r"\$([^$]*)\$", lambda m: math(m[1]), t)
    t = re.sub(r"\\emph\{([^}]*)\}", r"<em>\1</em>", t)
    t = re.sub(r"\\texttt\{([^}]*)\}", lambda m: "<code>" + m[1].replace("\\_", "_") + "</code>", t)
    t = re.sub(r"\\url\{([^}]*)\}", r"<code>\1</code>", t)
    t = re.sub(r"\\cite\{([^}]*)\}", lambda m: "[" + ", ".join(str(cites[k.strip()]) for k in m[1].split(",")) + "]", t)
    t = re.sub(r"\\eqref\{([^}]*)\}", lambda m: f"({labels[m[1]]})", t)
    t = re.sub(r"\\ref\{([^}]*)\}", lambda m: str(labels[m[1]]), t)
    t = t.replace("``", "&ldquo;").replace("''", "&rdquo;").replace("\\%", "%").replace("\\ldots", "&hellip;").replace("~", "&nbsp;")
    t = t.replace("\\_", "_").replace("\\&", "&amp;").replace("\\\\", "<br>").replace("$-$", "&minus;")
    return t


def image(name: str) -> str:
    import pdfplumber
    with pdfplumber.open(PAPER / name) as pdf:
        png = PAPER / (Path(name).stem + "._preview.png")
        pdf.pages[0].to_image(resolution=260).save(png)
    data = base64.b64encode(png.read_bytes()).decode()
    png.unlink()
    return f"<img src='data:image/png;base64,{data}'>"


def table(body: str, cap: str, spec_header: str, nums, cites, labels, n: int) -> str:
    parts = [p for p in re.split(r"\\hline", body) if p.strip()]
    head = [inline(c.strip(), nums, cites, labels) for c in parts[0].replace("\\\\", "").split("&")]
    rows = []
    for ln in re.findall(r"\\input\{([^}]+)\}", body):
        rows += [r for r in (PAPER / (ln + ".tex")).read_text(encoding="utf-8").splitlines()[1:] if r.strip()]
    tr = "".join("<tr>" + "".join(f"<td>{inline(c.strip(), nums, cites, labels)}</td>" for c in r.rstrip("\\ ").split("&")) + "</tr>" for r in rows)
    return (f"<div class=tbl><div class=tcap>TABLE {ROMAN[n - 1]}<br>{inline(cap, nums, cites, labels)}</div><table><tr>"
            + "".join(f"<th>{h}</th>" for h in head) + "</tr>" + tr + "</table></div>")


def build() -> str:
    tex = (PAPER / "main.tex").read_text(encoding="utf-8")
    nums = numbers()
    bib = tex[tex.index("\\begin{thebibliography}"):tex.index("\\end{thebibliography}")]
    body = tex[tex.index("\\begin{abstract}"):tex.index("\\begin{thebibliography}")]
    body = re.sub(r"(?<!\\)%.*", "", body)
    # numbering: sections, figures, tables, equation, citations by first appearance
    labels, sec, sub, fig, tab = {}, 0, 0, 0, 0
    for m in re.finditer(r"\\section\{|\\subsection\{|\\begin\{figure\}|\\begin\{table\}|\\begin\{equation\}|\\label\{([^}]+)\}", body):
        tok = m[0]
        if tok == "\\section{":
            sec, sub = sec + 1, 0
        elif tok == "\\subsection{":
            sub += 1
        elif tok == "\\begin{figure}":
            fig += 1
        elif tok == "\\begin{table}":
            tab += 1
        elif tok == "\\begin{equation}":
            pass
        else:
            key = m[1]
            labels[key] = (ROMAN[sec - 1] + (chr(64 + sub) if key.startswith("sec:") and False else "") if key.startswith("sec:") else
                           (fig if key.startswith("fig:") else (ROMAN[tab - 1] if key.startswith("tab:") else 1)))
    cites = {}
    for m in re.finditer(r"\\cite\{([^}]+)\}", body):
        for k in m[1].split(","):
            cites.setdefault(k.strip(), len(cites) + 1)
    out, sec, sub, fig, tab = [], 0, 0, 0, 0
    abstract = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", body, re.DOTALL)[1].strip()
    keywords = re.search(r"\\begin\{IEEEkeywords\}(.*?)\\end\{IEEEkeywords\}", body, re.DOTALL)[1].strip()
    main = body[body.index("\\end{IEEEkeywords}") + len("\\end{IEEEkeywords}"):]
    pos = 0
    for m in re.finditer(r"\\section\*?\{([^}]*)\}|\\subsection\{([^}]*)\}|\\begin\{figure\}.*?\\end\{figure\}|\\begin\{table\}.*?\\end\{table\}"
                         r"|\\begin\{equation\}.*?\\end\{equation\}|\\begin\{itemize\}.*?\\end\{itemize\}", main, re.DOTALL):
        para = main[pos:m.start()]
        out += [f"<p>{inline(p.strip(), nums, cites, labels)}</p>" for p in re.split(r"\n\s*\n", para) if p.strip()]
        pos, tok = m.end(), m[0]
        if tok.startswith("\\section*"):
            out.append(f"<h2>{inline(m[1], nums, cites, labels)}</h2>")
        elif tok.startswith("\\section{"):
            sec, sub = sec + 1, 0
            out.append(f"<h2>{ROMAN[sec - 1]}. {inline(m[1], nums, cites, labels)}</h2>")
        elif tok.startswith("\\subsection"):
            sub += 1
            out.append(f"<h3>{chr(64 + sub)}. {inline(m[2], nums, cites, labels)}</h3>")
        elif tok.startswith("\\begin{figure}"):
            fig += 1
            cap = re.search(r"\\caption\{((?:[^{}]|\{[^{}]*\})*)\}", tok)[1]
            figure_file = re.search(r"includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", tok)[1]
            out.append(f"<figure>{image(figure_file)}"
                       f"<figcaption>Fig. {fig}. {inline(cap, nums, cites, labels)}</figcaption></figure>")
        elif tok.startswith("\\begin{table}"):
            tab += 1
            cap = re.search(r"\\caption\{((?:[^{}]|\{[^{}]*\})*)\}", tok)[1]
            inner = re.search(r"\\begin\{tabular\}\{.*?\}\n(.*)\\end\{tabular\}", tok, re.DOTALL)[1]
            out.append(table(inner, cap, "", nums, cites, labels, tab))
        elif tok.startswith("\\begin{equation}"):
            assert "\\frac{\\Delta" in tok, "the preview knows one equation; update EQ"
            out.append(f"<div class=eq><span></span>{EQ}<span>(1)</span></div>")
        else:
            items = re.split(r"\\item", tok.replace("\\begin{itemize}", "").replace("\\end{itemize}", ""))[1:]
            out.append("<ul>" + "".join(f"<li>{inline(i.strip(), nums, cites, labels)}</li>" for i in items) + "</ul>")
    out += [f"<p>{inline(p.strip(), nums, cites, labels)}</p>" for p in re.split(r"\n\s*\n", main[pos:]) if p.strip()]
    refs = []
    items = re.findall(r"\\bibitem\{(\w+)\}(.*?)(?=\\bibitem|\Z)", bib, re.DOTALL)
    for key, text in sorted(items, key=lambda kv: cites[kv[0]]):
        refs.append(f"<p>[{cites[key]}] {inline(text.strip().replace(chr(10), ' '), nums, cites, labels)}</p>")
    title = re.search(r"\\title\{(.*)\}", tex)[1]
    return (f"<!doctype html><meta charset=utf-8><style>{CSS}</style><div class=banner>PREVIEW rendered from paper/main.tex by scripts/paper_preview.py: "
            "same words, numbers, tables and figures, but not typeset by LaTeX. Red [VERIFY] items are unresolved.</div>"
            f"<div class=head><h1>{html.escape(title)}</h1><div class=authors><span class=v>[VERIFY: authors, in order]</span><br>"
            "RV College of Engineering, Bengaluru, India</div></div><div class=cols>"
            f"<p class=abs><i>Abstract</i>&mdash;{inline(abstract, nums, cites, labels)}</p>"
            f"<p class=kw><i>Index Terms</i>&mdash;{html.escape(keywords)}</p>" + "".join(out)
            + "<h2>References</h2><div class=refs>" + "".join(refs) + "</div></div>")


def main() -> None:
    from playwright.sync_api import sync_playwright
    page_html = build()
    target = PAPER / "main_preview.pdf"
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.set_content(page_html)
        pg.pdf(path=str(target), format="Letter", print_background=True, margin={"top": "0.75in", "bottom": "0.9in", "left": "0.625in", "right": "0.625in"},
               display_header_footer=True, header_template="<span></span>",
               footer_template="<div style='font:7pt sans-serif;width:100%;text-align:center;color:#555'>PREVIEW, not typeset by LaTeX &mdash; <span class='pageNumber'></span></div>")
        b.close()
    print("wrote", target)


if __name__ == "__main__":
    sys.exit(main())
