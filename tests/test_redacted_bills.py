"""Guard for data/redacted_bills/: nothing is committed that still looks like
personal data, that has no consent recorded, or that has no true consumption
figure to evaluate against. With no bills collected it checks nothing."""
import json
import re
import sys
from pathlib import Path

from carbonx.extraction.redact import residual

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from review_pack import number_pattern

DIR = Path(__file__).resolve().parents[1] / "data" / "redacted_bills"


def test_every_committed_bill_is_clean_consented_and_labelled():
    for txt in sorted(DIR.glob("*.txt")):
        meta_path = txt.with_suffix(".json")
        assert meta_path.exists(), f"{txt.name}: no sidecar"
        meta, text = json.loads(meta_path.read_text(encoding="utf-8")), txt.read_text(encoding="utf-8")
        assert residual(text) == [], f"{txt.name}: {residual(text)}"
        assert meta["consent"] is True, f"{txt.name}: no consent recorded"
        assert meta["reviewed_by"], f"{txt.name}: nobody has read the redacted text"
        kwh = meta["consumption_kwh"]
        assert isinstance(kwh, (int, float)) and kwh > 0, f"{txt.name}: no true consumption"
        assert re.search(number_pattern(float(kwh)), text), f"{txt.name}: the true consumption does not appear in the text"


def test_the_label_is_found_as_printed_even_for_a_large_figure_with_decimals():
    """A '%g' format rounds 266293.5 to six digits and would never find it in its own text."""
    for printed, kwh in (("266293.5000", 266293.5), ("1004316.0000", 1004316.0), ("193733.00", 193733.0), ("43125", 43125.0)):
        assert re.search(number_pattern(kwh), f"KWH 1.0 2.0 {printed} 7"), printed
    assert not re.search(number_pattern(266293.5), "KWH 2662935.0")      # a longer number is not a match
    assert not re.search(number_pattern(1004316.0), "10043160.0")
