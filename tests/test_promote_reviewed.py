"""The promotion gate: a person's sign-off is necessary but not sufficient. No database."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import promote_reviewed as pr
import review_pack as rp

GOOD = "JODHPUR VIDYUT VITRAN NIGAM LIMITED\nBilling Month 202508\nMTR123456 KWH 2490.9450 2156.1730 334.7720 3000.0000 1004316.0000 1004316.0000\n"


def make(directory: Path, bill_id: str, text: str = GOOD, **meta) -> None:
    sidecar = {"id": bill_id, "consent": True, "consumption_kwh": 1004316.0, "label_status": "verified",
               "consumer_group": "A", "billing_month": "202508", "label_basis": "test", "reviewed_by": None}
    sidecar.update(meta)
    (directory / f"{bill_id}.txt").write_text(text, encoding="utf-8")
    (directory / f"{bill_id}.json").write_text(json.dumps(sidecar), encoding="utf-8")


def test_a_clean_consented_reviewed_bill_is_promoted_with_the_reviewers_name(tmp_path):
    src, dest = tmp_path / "src", tmp_path / "dest"
    src.mkdir()
    make(src, "ok")
    done, refused = pr.promote({"reviewer": "A. Reviewer", "reviewed_on": "2026-11-06", "accepted": ["ok"]}, src, dest)
    assert done == ["ok"] and not refused
    meta = json.loads((dest / "ok.json").read_text(encoding="utf-8"))
    assert meta["reviewed_by"] == "A. Reviewer" and meta["reviewed_on"] == "2026-11-06"
    assert (src / "ok.txt").exists()                                   # the candidate is left where it was


def test_no_reviewer_name_means_nothing_is_promoted(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    make(src, "ok")
    with pytest.raises(SystemExit):
        pr.promote({"reviewer": "  ", "accepted": ["ok"]}, src, tmp_path / "dest")
    assert not (tmp_path / "dest").exists() or not list((tmp_path / "dest").iterdir())


@pytest.mark.parametrize("name, text, meta, why", [
    ("noconsent", GOOD, {"consent": False}, "no consent"),
    ("nolabel", GOOD, {"consumption_kwh": None}, "no labelled consumption"),
    ("flagged", GOOD, {"label_status": "flagged"}, "label status"),
    ("absent", GOOD.replace("1004316.0000", "999.0"), {}, "does not appear"),
    ("phone", GOOD + "Mobile 9845012345\n", {}, "personal data"),
    ("idnum", GOOD + "Acct 90140001\n", {}, "identifier-shaped"),
])
def test_the_gate_refuses_what_the_reviewer_may_have_missed(tmp_path, name, text, meta, why):
    src, dest = tmp_path / "src", tmp_path / "dest"
    src.mkdir()
    make(src, name, text, **meta)
    done, refused = pr.promote({"reviewer": "A. Reviewer", "accepted": [name, "missing"]}, src, dest)
    assert done == [] and why in refused[name] and refused["missing"] == "not found in the candidates folder"


def test_the_review_page_flags_a_leak_and_highlights_the_label(tmp_path):
    make(tmp_path, "leaky", GOOD + "Mobile 9845012345\n")
    page = rp.build(tmp_path)
    assert "<mark>1004316.0000</mark>" in page and "SCAN:" in page and "Download review.json" in page
