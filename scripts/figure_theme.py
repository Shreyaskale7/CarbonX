"""Every figure is written twice: `name.svg` on a light surface (for the report
and for GitHub) and `name_dark.svg` (for the site, whose default theme is dark).

The dark file is the same drawing with each colour swapped for its dark-surface
counterpart. The series colours are the dark steps of the same hues, checked
with the dataviz palette validator against the dark surface; they are not an
automatic inversion.
"""
import re
from pathlib import Path

DARK = {
    "#fcfcfb": "#1a1a19",   # chart surface
    "#0b0b0b": "#ffffff",   # primary ink
    "#52514e": "#c3c2b7",   # secondary ink
    "#898781": "#898781",   # muted: the same in both
    "#e1e0d9": "#2c2c2a",   # gridline
    "#c3c2b7": "#4a4a46",   # axis, and bands drawn in the axis colour
    "#ecebe5": "#33332f",   # shaded range behind marks
    "#2a78d6": "#3987e5",   # blue
    "#eb6834": "#d95926",   # orange
    "#1baf7a": "#199e70",   # aqua
}
_HEX = re.compile(r"#[0-9a-fA-F]{6}\b")


def dark(svg: str) -> str:
    """One pass, so a colour that is another's replacement is not swapped twice.
    An unknown colour is an error: a figure must not be half-converted."""
    return _HEX.sub(lambda m: DARK[m.group(0).lower()], svg)


def write(path: Path, svg: str) -> None:
    path.parent.mkdir(exist_ok=True)
    path.write_text(svg, encoding="utf-8", newline="\n")
    path.with_name(path.stem + "_dark.svg").write_text(dark(svg), encoding="utf-8", newline="\n")
