"""A blind hand check of the CEA registry by a second person.

    python scripts/hand_check.py sample     # -> docs/paper/HAND_CHECK.csv (values left blank)
    python scripts/hand_check.py check      # compare what was typed with the registry

Why: every other check of the registry is our parser agreeing with itself. This
one is a person opening CEA's workbook, going to a cell, and typing what is
there. The sheet does not show the registry's value, so it cannot be copied.

The sample is two cells from each of the 23 versions, chosen by a hash of the
row, so it is the same for everyone and cannot be picked to flatter the data.
"""
import csv
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "cea"
SHEET = ROOT / "docs" / "paper" / "HAND_CHECK.csv"
PER_VERSION = 2
FIELDS = ["version", "workbook", "cell", "what_the_row_should_be", "typed_value", "checked_by",
          "note"]


def _rows() -> list[dict[str, str]]:
    with (DATA / "factors.csv").open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _key(r: dict[str, str]) -> tuple[str, str]:
    return r["version_label"], r["cell"]


def chosen() -> list[dict[str, str]]:
    """Two rows per version: the two with the smallest hash of (version, cell)."""
    by_version: dict[str, list[dict[str, str]]] = {}
    for r in _rows():
        by_version.setdefault(r["version_label"], []).append(r)
    out = []
    for rows in by_version.values():
        rows.sort(key=lambda r: hashlib.sha256("|".join(_key(r)).encode()).hexdigest())
        out += rows[:PER_VERSION]
    return out


def sample() -> None:
    with (DATA / "versions.csv").open(encoding="utf-8", newline="") as fh:
        workbook = {v["version_label"]: v["workbook"] for v in csv.DictReader(fh)}
    SHEET.parent.mkdir(parents=True, exist_ok=True)
    with SHEET.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, FIELDS, lineterminator="\n")
        w.writeheader()
        for r in chosen():
            w.writerow({"version": r["version_label"], "workbook": workbook[r["version_label"]],
                        "cell": r["cell"],
                        "what_the_row_should_be":
                            f"{r['factor_key']} | CEA label: {r['cea_label']} | {r['fy']} | "
                            f"{r['geography']}",
                        "typed_value": "", "checked_by": "", "note": ""})
    print(f"{len(chosen())} cells to check -> {SHEET.relative_to(ROOT)}\n"
          "Open each workbook (python scripts/fetch_cea.py downloads them), go to the cell,\n"
          "type the number you see into typed_value, and your name into checked_by.\n"
          "If the row is not what the sheet says it should be, say so in note.")


def check() -> None:
    truth = {_key(r): r for r in _rows()}
    with SHEET.open(encoding="utf-8", newline="") as fh:
        filled = list(csv.DictReader(fh))
    done = [r for r in filled if r["typed_value"].strip()]
    wrong = []
    for r in done:
        typed = r["typed_value"].strip()
        actual = float(truth[(r["version"], r["cell"])]["value"])
        places = len(typed.split(".")[1]) if "." in typed else 0
        # The workbook shows a rounded figure; agree to the digits the checker typed.
        if abs(float(typed) - round(actual, places)) > 0.5 * 10 ** -places:
            wrong.append(f"{r['version']} {r['cell']}: typed {typed}, registry {actual:.6f}"
                         f" ({r['checked_by'] or 'unsigned'})")
    noted = [f"{r['version']} {r['cell']}: {r['note']}" for r in filled if r["note"].strip()]
    people = sorted({r["checked_by"].strip() for r in done if r["checked_by"].strip()})
    print(f"{len(done)} of {len(filled)} cells checked by {', '.join(people) or 'nobody yet'}; "
          f"{len(done) - len(wrong)} agree, {len(wrong)} disagree")
    for line in wrong + noted:
        print("  " + line)
    if wrong:
        raise SystemExit(1)


if __name__ == "__main__":
    {"sample": sample, "check": check}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: sys.exit(__doc__))()
