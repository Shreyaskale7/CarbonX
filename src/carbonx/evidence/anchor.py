"""Anchors: copies of the audit chain's latest hash, kept outside the database.

The hash chain makes tampering visible only to someone who recomputes it, and
a database owner who rewrites history can recompute it too, leaving a chain
that is consistent and false. An anchor closes that: it records "event N had
hash H at time T" in a file the database cannot reach. If history before N is
later rewritten, the hash at N changes and no longer matches the anchor.

    python -m carbonx.evidence.anchor record     # append the current head
    python -m carbonx.evidence.anchor check      # compare every anchor with the chain

How strong this is depends entirely on where the file lives. In a git
repository pushed to a remote the database owner does not control, it is real
evidence. On the database server's own disk it is none. Stronger still, and
not done here, is to give the hash to a third party (a public timestamp
authority, a published notice). This is tamper-evidence, not prevention, and
it is not a blockchain.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg

from carbonx import db

ANCHORS = Path(os.environ.get(
    "CARBONX_ANCHOR_FILE",
    Path(__file__).resolve().parents[3] / "anchors" / "audit_chain.jsonl"))


def head(conn: psycopg.Connection) -> dict[str, Any] | None:
    """The newest audit event, and the first event's hash as the chain's identity."""
    row = conn.execute(
        "SELECT event_id, event_hash, occurred_at,"
        " (SELECT event_hash FROM audit_event ORDER BY event_id LIMIT 1)"
        " FROM audit_event ORDER BY event_id DESC LIMIT 1").fetchone()
    if row is None:
        return None
    return {"chain": row[3], "event_id": row[0], "event_hash": row[1],
            "event_at": row[2].astimezone(UTC).isoformat()}


def record(conn: psycopg.Connection, path: Path | None = None) -> dict[str, Any]:
    """Append the current head to the anchor file. Nothing is written to the database."""
    path = path or ANCHORS
    anchor = head(conn)
    if anchor is None:
        raise LookupError("the audit trail is empty; there is nothing to anchor")
    anchor["anchored_at"] = datetime.now(UTC).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(anchor, sort_keys=True) + "\n")
    return anchor


def check(conn: psycopg.Connection, path: Path | None = None) -> dict[str, Any]:
    """Compare every anchor with the chain as it is now.

    `problems` lists anchors of this database that no longer match. Anchors
    made on another database (another first event) cannot be compared; if the
    file has anchors and none belongs to this database, that is reported too,
    because a chain rewritten from its very first event looks exactly like that.
    """
    path = path or ANCHORS
    now = head(conn)
    anchors = ([json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()] if path.exists() else [])
    mine = [a for a in anchors if now and a["chain"] == now["chain"]]
    problems = []
    for a in mine:
        row = conn.execute("SELECT event_hash FROM audit_event WHERE event_id = %s",
                           (a["event_id"],)).fetchone()
        if row is None:
            problems.append(f"event {a['event_id']}, anchored {a['anchored_at'][:10]}, "
                            "no longer exists")
        elif row[0] != a["event_hash"]:
            problems.append(f"event {a['event_id']} had hash {a['event_hash'][:12]}... when "
                            f"anchored on {a['anchored_at'][:10]}; it is now {row[0][:12]}...")
    if anchors and not mine:
        problems.append(f"none of the {len(anchors)} anchors on file belongs to this database: "
                        "either the file is another database's, or the chain was rewritten "
                        "from its first event")
    return {"anchors": len(anchors), "checked": len(mine), "problems": problems,
            "latest": max(mine, key=lambda a: a["event_id"]) if mine else None, "head": now}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["record", "check"])
    ap.add_argument("--file", type=Path, default=ANCHORS)
    args = ap.parse_args()
    with psycopg.connect(db.url()) as conn:
        if args.command == "record":
            a = record(conn, args.file)
            print(f"anchored event {a['event_id']} {a['event_hash']}\n-> {args.file}\n"
                  "Commit and push this file somewhere the database owner does not control.")
        else:
            result = check(conn, args.file)
            print(f"{result['checked']} of {result['anchors']} anchors checked")
            for p in result["problems"]:
                print("MISMATCH:", p)
            if result["problems"]:
                raise SystemExit(1)


if __name__ == "__main__":
    main()
