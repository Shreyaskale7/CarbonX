# Anchors

`audit_chain.jsonl`, when it exists, holds copies of the audit trail's latest
hash, one line per anchor:

```
python -m carbonx.evidence.anchor record    # append the current head
python -m carbonx.evidence.anchor check     # compare every anchor with the database
```

**Why.** The hash chain shows tampering only to someone who recomputes it. A
database owner who rewrites history can recompute it too, leaving a chain that
is consistent and false. An anchor made beforehand no longer matches.
`tests/test_anchor.py` does exactly that rewrite and shows the chain's own
check passing while the anchor fails.

**What makes it worth anything.** Only where this file is kept. Commit it and
push it to a remote the database owner does not control, after each reporting
milestone. Kept only on the database server, it proves nothing.

**What it is not.** Not prevention, and not a blockchain. It does not show
what was changed, only that something before the anchored event was. It says
nothing about events after the newest anchor. A third-party timestamp on the
hash would be stronger still; that is not built.

No anchor file is committed for the development databases: each has its own
chain, and an anchor for one says nothing about another.
