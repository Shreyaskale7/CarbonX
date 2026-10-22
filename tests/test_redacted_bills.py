"""Guard for data/redacted_bills/: nothing is committed that still looks like
personal data, that has no consent recorded, or that has no true consumption
figure to evaluate against. With no bills collected it checks nothing."""
import json
import re
from pathlib import Path

from carbonx.extraction.redact import residual

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
        assert re.search(rf"(?<![\d.]){kwh:g}(?![\d])|{re.escape(f'{kwh:,.0f}')}", text), \
            f"{txt.name}: the true consumption does not appear in the text"
