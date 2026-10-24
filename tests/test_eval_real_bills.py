"""The real-bill evaluation, tried on stand-ins: synthetic bills written where real
redacted ones will go. It must hold a utility out, count honestly, and refuse to
publish numbers before there is enough data. No database."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import eval_real_bills as ev

from carbonx.extraction.synthetic import DEV, corpus


def write_bills(directory: Path, utilities: int, per: int, consent: bool = True) -> None:
    bills = corpus(per, DEV[:utilities], seed=7)
    for i, b in enumerate(bills):
        bid = f"u{b.layout}-{i}"
        (directory / f"{bid}.txt").write_text(b.text, encoding="utf-8")
        (directory / f"{bid}.json").write_text(json.dumps({
            "id": bid, "discom": f"UTIL{b.layout}", "consent": consent, "reviewed_by": "tester",
            "consumption_kwh": b.kwh}), encoding="utf-8")


def test_three_utilities_are_each_held_out_and_counted(tmp_path, monkeypatch):
    write_bills(tmp_path, 3, 5)
    monkeypatch.setattr(ev, "DIR", tmp_path)
    monkeypatch.setattr(ev, "OUT", tmp_path / "out.md")
    monkeypatch.setattr(ev, "SYNTH_PER_LAYOUT", 6)
    ev.main()
    text = (tmp_path / "out.md").read_text(encoding="utf-8")
    assert "15 real bills from 3 utilities" in text
    assert all(f"| UTIL{n} | 5 |" in text for n in DEV[:3]) and "| **all** | 15 |" in text
    assert "Read the counts first" in text


def test_too_few_utilities_writes_nothing(tmp_path, monkeypatch, capsys):
    write_bills(tmp_path, 2, 8)
    monkeypatch.setattr(ev, "DIR", tmp_path)
    monkeypatch.setattr(ev, "OUT", tmp_path / "out.md")
    ev.main()
    assert not (tmp_path / "out.md").exists()
    assert "not enough real bills" in capsys.readouterr().out


def test_a_bill_without_consent_stops_the_run(tmp_path):
    write_bills(tmp_path, 3, 5, consent=False)
    with pytest.raises(SystemExit):
        ev.load(tmp_path)


def test_wilson_interval_is_wide_for_few_bills_and_brackets_the_rate():
    lo, hi = ev.wilson(5, 5)
    assert lo < 0.6 and hi == 1.0                      # five of five is not "100%"
    lo, hi = ev.wilson(50, 100)
    assert lo < 0.5 < hi and hi - lo < 0.21
    assert ev.wilson(0, 0) == (0.0, 1.0)
