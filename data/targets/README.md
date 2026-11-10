# Intensity targets and baselines

`template.csv` is the header only. **No target is pre-filled.** The notified Schedule's figures belong to
named entities, and the notification text has not been read by this project: secondary summaries say the
Schedule gives each entity a baseline output and intensity for FY2023-24 and targets for 2025-26 and
2026-27, in tCO2e per tonne of equivalent product, but those are not a source.

To load figures:

1. Read the entity's row in the notification itself (MoEFCC Greenhouse Gases Emission Intensity Target
   Rules, 2025, and the January 2026 amendment) and note the gazette number, schedule and row.
2. Add one line per facility and compliance year to a copy of `template.csv`. Use `status` = `notified`
   only for a value you read there (then `citation` and `url` are required); otherwise `assumed`.
3. `python scripts/load_targets.py yourfile.csv --dry-run`, then without `--dry-run`.

An `assumed` figure flows into every entitlement it touches with a "do not rely on this" note.
Do not commit a file of real entities' figures taken from a news article.
