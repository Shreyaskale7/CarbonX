"""Dark figures are derived from the light ones and must stay in step."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import figure_theme

LIGHT = sorted(p for p in (ROOT / "docs" / "figures").glob("*.svg")
               if not p.stem.endswith("_dark"))


def test_swap_is_one_pass_and_rejects_unknown_colours():
    # secondary ink becomes #c3c2b7, which is itself the light axis colour:
    # a second pass would turn it into the dark axis colour.
    assert figure_theme.dark('fill="#52514e"') == 'fill="#c3c2b7"'
    with pytest.raises(KeyError):
        figure_theme.dark('fill="#123456"')


@pytest.mark.parametrize("light", LIGHT, ids=lambda p: p.name)
def test_committed_dark_figure_matches_its_light_one(light):
    dark = light.with_name(light.stem + "_dark.svg")
    assert dark.read_text(encoding="utf-8") == figure_theme.dark(light.read_text(encoding="utf-8"))
    assert "#fcfcfb" not in dark.read_text(encoding="utf-8")   # no light surface left
