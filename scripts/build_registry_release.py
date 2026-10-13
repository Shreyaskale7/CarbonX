"""Package the CEA registry for release (for example on Zenodo).

    python scripts/build_registry_release.py --draft   # a bundle to inspect
    python scripts/build_registry_release.py           # refuses until the release is decided

Writes dist/<name>.zip containing the CSVs, the data card, the download
manifest, a Frictionless `datapackage.json`, `SHA256SUMS` and `.zenodo.json`.
The zip is deterministic: the same inputs give the same bytes, so its hash can
be quoted.

Two things are not this script's to decide, and it will not release without
them: the licence, and who the authors are. Both go in
data/cea/release.json. See the note in data/cea/README.md about the terms on
which data derived from CEA's publications may be redistributed.
"""
import argparse
import csv
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "cea"
META = DATA / "release.json"
DIST = ROOT / "dist"
FILES = ["README.md", "CHANGELOG.md", "factors.csv", "versions.csv", "manifest.json"]
EPOCH = (1980, 1, 1, 0, 0, 0)   # fixed timestamp: the zip must not depend on when it was built

FIELDS = {
    "factors.csv": [
        ("version_label", "string", "CEA version, e.g. v22.0"),
        ("fy", "string", "Indian financial year (April to March), e.g. FY2025-26"),
        ("factor_key", "string", "grid.<metric>.<imports>; see README.md"),
        ("geography", "string", "IN for all-India; regional grids in older versions"),
        ("value", "number", "the factor, as stored in the workbook"),
        ("unit", "string", "always tCO2/MWh"),
        ("cell", "string", "sheet and cell the value was read from"),
        ("cea_label", "string", "CEA's own row label, verbatim"),
    ],
    "versions.csv": [
        ("version_label", "string", "CEA version"),
        ("version_ordinal", "integer", "sorts versions: major x 10 + minor"),
        ("stated_date", "date", "the date written in the workbook"),
        ("date_precision", "string", "day or month"),
        ("covers_fy", "string", "newest financial year in that version"),
        ("cea_outdated", "boolean", "CEA's page marks the version OUTDATED"),
        ("workbook", "string", "workbook file read"),
        ("database_url", "string", "download URL of the database"),
        ("database_sha256", "string", "SHA-256 of the downloaded database file"),
        ("user_guide_url", "string", "download URL of the user guide"),
        ("user_guide_sha256", "string", "SHA-256 of the downloaded user guide"),
    ],
}


def rows(name: str) -> list[dict[str, str]]:
    with (DATA / name).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def validate() -> list[str]:
    """Problems that would make the release wrong. Empty means none found."""
    problems = []
    factors, versions = rows("factors.csv"), rows("versions.csv")
    for name, data in (("factors.csv", factors), ("versions.csv", versions)):
        expected = [f for f, _, _ in FIELDS[name]]
        if list(data[0]) != expected:
            problems.append(f"{name}: columns are {list(data[0])}, the schema says {expected}")
    labels = [v["version_label"] for v in versions]
    if len(set(labels)) != len(labels):
        problems.append("versions.csv: a version label is repeated")
    keys = [(f["version_label"], f["fy"], f["factor_key"], f["geography"]) for f in factors]
    if len(set(keys)) != len(keys):
        problems.append("factors.csv: a (version, fy, factor, geography) row is repeated")
    for f in factors:
        where = f"factors.csv {f['version_label']} {f['fy']} {f['factor_key']} {f['geography']}"
        if f["version_label"] not in labels:
            problems.append(f"{where}: version is not in versions.csv")
        if f["unit"] != "tCO2/MWh":
            problems.append(f"{where}: unit is {f['unit']}")
        if not 0 < float(f["value"]) < 2:   # tCO2/MWh for a national or regional grid
            problems.append(f"{where}: value {f['value']} is outside (0, 2)")
        if "!" not in f["cell"]:
            problems.append(f"{where}: no cell reference")
    for v in versions:
        if len(v["database_sha256"]) != 64:
            problems.append(f"versions.csv {v['version_label']}: no SHA-256 for the database")
    card = (DATA / "README.md").read_text(encoding="utf-8")
    for claim in (f"{len(factors):,} factors", f"{len(versions)} versions"):
        if claim not in card:
            problems.append(f"README.md does not say \"{claim}\"; its counts are out of date")
    return problems


def datapackage(meta: dict) -> dict:
    return {
        "name": meta["name"], "title": meta["title"], "version": meta["version"],
        "description": meta["description"],
        "licenses": [{"name": meta["license"]}] if meta["license"] else [],
        "contributors": [{"title": a["name"], "role": "author"} for a in meta["authors"]],
        "resources": [
            {"name": name.removesuffix(".csv"), "path": name, "format": "csv",
             "mediatype": "text/csv", "encoding": "utf-8",
             "schema": {"fields": [{"name": f, "type": t, "description": d}
                                   for f, t, d in fields]}}
            for name, fields in FIELDS.items()],
    }


def zenodo(meta: dict) -> dict:
    return {"upload_type": "dataset", "title": meta["title"], "version": meta["version"],
            "description": meta["description"], "license": meta["license"],
            "creators": [{k: a[k] for k in ("name", "affiliation", "orcid") if a.get(k)}
                         for a in meta["authors"]],
            "keywords": meta["keywords"]}


def build(draft: bool, out_dir: Path = DIST) -> Path:
    meta = json.loads(META.read_text(encoding="utf-8"))
    missing = [what for what, ok in (("a licence (\"license\")", bool(meta["license"])),
                                     ("at least one author (\"authors\")", bool(meta["authors"])))
               if not ok]
    if missing and not draft:
        sys.exit("not releasing: data/cea/release.json still needs " + " and ".join(missing)
                 + ". Use --draft to build a bundle for inspection.")
    problems = validate()
    if problems:
        sys.exit("not building: the registry failed its checks:\n  " + "\n  ".join(problems))

    def text(obj: dict) -> bytes:
        return (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode()

    contents = {name: (DATA / name).read_bytes().replace(b"\r\n", b"\n") for name in FILES}
    contents["datapackage.json"] = text(datapackage(meta))
    contents[".zenodo.json"] = text(zenodo(meta))
    contents["SHA256SUMS"] = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n"
        for name, data in sorted(contents.items())).encode()

    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{meta['name']}-{meta['version']}{'-DRAFT' if missing else ''}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(contents.items()):
            info = zipfile.ZipInfo(name, EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--draft", action="store_true",
                    help="build even though the licence or authors are not decided")
    args = ap.parse_args()
    out = build(args.draft)
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    print(f"{out.relative_to(ROOT)}  ({out.stat().st_size:,} bytes)\nsha256 {digest}")
    if "DRAFT" in out.name:
        print("DRAFT: not for publication. Fill in data/cea/release.json first.")


if __name__ == "__main__":
    main()
