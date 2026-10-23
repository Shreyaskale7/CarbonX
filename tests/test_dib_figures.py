"""The article's two figures: what they say is what the data say. No database."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import dib_figures


def test_the_marked_outlier_is_version_18_in_financial_year_2016_17():
    fy, ver, val, rest = dib_figures.outlier(dib_figures.series_points())
    assert (fy, ver) == ("FY2016-17", "v18.0") and round(val, 4) == 0.7656 and round(rest, 4) == 0.8237


def test_figure_one_has_one_marker_per_version_and_five_open_ones():
    svg = dib_figures.figure_versions()
    assert svg.count("<circle") == 23 + 2 + 0          # 23 versions + 2 legend markers
    assert svg.count(f'fill="{dib_figures.SURFACE}" stroke="{dib_figures.BLUE}"') == 5 + 1


def test_committed_figures_equal_what_the_script_draws():
    figs = ROOT / "docs" / "figures"
    assert (figs / "dib_fig1_versions.svg").read_text(encoding="utf-8") == dib_figures.figure_versions()
    assert (figs / "dib_fig2_spread.svg").read_text(encoding="utf-8") == dib_figures.figure_spread()
