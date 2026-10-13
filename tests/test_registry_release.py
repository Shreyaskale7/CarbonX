"""The registry release bundle: complete, checksummed, deterministic, and not
released before the licence and authors are decided. No database."""
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_registry_release as rel


def test_the_committed_registry_passes_its_checks():
    assert rel.validate() == []


def test_no_release_without_a_licence_and_authors(tmp_path):
    meta = json.loads(rel.META.read_text(encoding="utf-8"))
    if meta["license"] and meta["authors"]:
        pytest.skip("the release has been decided")
    with pytest.raises(SystemExit, match="not releasing"):
        rel.build(draft=False, out_dir=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_draft_bundle_is_complete_checksummed_and_deterministic(tmp_path):
    first = rel.build(draft=True, out_dir=tmp_path / "a")
    second = rel.build(draft=True, out_dir=tmp_path / "b")
    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as z:
        names = set(z.namelist())
        assert {"factors.csv", "versions.csv", "manifest.json", "README.md", "CHANGELOG.md",
                "datapackage.json", ".zenodo.json", "SHA256SUMS"} == names
        for line in z.read("SHA256SUMS").decode().splitlines():
            digest, name = line.split("  ")
            assert hashlib.sha256(z.read(name)).hexdigest() == digest
        package = json.loads(z.read("datapackage.json"))
        header = z.read("factors.csv").decode().splitlines()[0].split(",")
    fields = [f["name"] for f in package["resources"][0]["schema"]["fields"]]
    assert fields == header


def test_checks_catch_a_repeated_row_and_a_stale_count(tmp_path, monkeypatch):
    for name in rel.FILES:
        shutil.copy(rel.DATA / name, tmp_path / name)
    with (tmp_path / "factors.csv").open(encoding="utf-8", newline="") as fh:
        lines = fh.read().splitlines()
    (tmp_path / "factors.csv").write_text("\n".join([*lines, lines[1]]) + "\n",
                                          encoding="utf-8", newline="\n")
    monkeypatch.setattr(rel, "DATA", tmp_path)
    problems = rel.validate()
    assert any("repeated" in p for p in problems)
    assert any("out of date" in p for p in problems)
