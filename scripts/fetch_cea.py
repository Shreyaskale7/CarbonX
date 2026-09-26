"""Download every CEA CO2 Baseline Database version and its user guide.

Scrapes the CEA landing page for links rather than guessing URLs (they drift:
v20 lives under /2021/03/, v16's link text has no version number). Files go to
data/raw/cea/v<label>/ (gitignored); data/cea/manifest.json records each file's
URL, SHA-256, size and retrieval time and IS committed: it is the provenance
record for the open registry. Re-running skips files already downloaded.

    python scripts/fetch_cea.py            # databases + user guides
    python scripts/fetch_cea.py --no-guides
"""
import argparse
import hashlib
import json
import re
import time
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

import requests

PAGE = "https://cea.nic.in/cdm-co2-baseline-database/?lang=en"
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "cea"
MANIFEST = ROOT / "data" / "cea" / "manifest.json"


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text = ""

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href, self._text = dict(attrs).get("href"), ""

    def handle_data(self, data):
        if self._href:
            self._text += data

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            self.links.append((" ".join(self._text.split()), self._href))
            self._href = None


def versions(html: str) -> dict[str, dict]:
    """{'22.0': {'database': url, 'user_guide': url, 'outdated': bool}, ...}.

    Link order on the page is: 'Version N' heading, then its files. The draft
    release is skipped: it was never a published version.
    """
    parser = _Links()
    parser.feed(html)
    found: dict[str, dict] = {}
    current = None
    for text, href in parser.links:
        if m := re.fullmatch(r"Version (\d+\.\d+)", text):
            current = found.setdefault(m[1], {})
        elif text.startswith("Draft"):
            current = None
        elif current is not None and "OUTDATED" in text:
            current["outdated"] = True
        if current is None:
            continue
        if "Emission Database" in text and re.search(r"\.(xlsx|zip)$", href):
            current["database"] = href
        elif text.startswith("User Guide") and href.lower().endswith(".pdf"):
            current["user_guide"] = href
    return found


def ordinal(label: str) -> int:
    """'22.0' -> 220, '1.1' -> 11. Orders versions; labels alone collide."""
    major, minor = label.split(".")
    return int(major) * 10 + int(minor)


def fetch(url: str, dest: Path) -> dict:
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(1, 6):  # cea.nic.in drops long transfers
            try:
                r = requests.get(url, timeout=120)
                r.raise_for_status()
                break
            except requests.RequestException:
                if attempt == 5:
                    raise
                time.sleep(5 * attempt)
        dest.write_bytes(r.content)  # only complete bodies ever reach disk
    data = dest.read_bytes()
    return {
        "url": url,
        "file": dest.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "retrieved_at": datetime.fromtimestamp(
            dest.stat().st_mtime, UTC).isoformat(timespec="seconds"),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-guides", action="store_true")
    args = ap.parse_args()

    found = versions(requests.get(PAGE, timeout=60).text)
    manifest = []
    for label, links in sorted(found.items(), key=lambda kv: ordinal(kv[0])):
        entry = {"version_label": f"v{label}", "version_ordinal": ordinal(label),
                 "outdated": links.get("outdated", False)}
        for kind in ("database", "user_guide"):
            if kind == "user_guide" and args.no_guides:
                continue
            if url := links.get(kind):
                dest = RAW / f"v{label}" / url.rsplit("/", 1)[1]
                entry[kind] = fetch(url, dest)
                print(f"v{label:5} {kind:10} {entry[kind]['bytes'] / 1e6:6.2f} MB")
            else:
                print(f"v{label:5} {kind:10} NOT LISTED")
        manifest.append(entry)

    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(
        {"page": PAGE, "versions": manifest}, indent=2) + "\n", encoding="utf-8",
        newline="\n")
    print(f"{len(manifest)} versions -> {MANIFEST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
