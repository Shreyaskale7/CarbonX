# Ember India electricity data: national monthly extract

`india_monthly_national.csv`: one row per month, January 2019 to November 2025.

| Column | Meaning |
|---|---|
| `month` | `YYYY-MM` |
| `generation_gwh` | total electricity generation, all India, GWh |
| `emissions_ktco2` | power-sector emissions, all India, kt CO2 |

Dividing emissions by generation gives a carbon intensity in tCO2/MWh.

## Source and licence

Derived from **Ember, "India Electricity Data"**, monthly long-format file:
`https://files.ember-energy.org/public-downloads/india_monthly_full_release_long_format.csv`

- Retrieved 2026-10-13. Ember's page gave the data as last updated 2026-01-16.
- SHA-256 of the downloaded file:
  `5874ab042dcf9f34acd5148e67853a83aedbf1909b66361355a92c5e6afaa785` (23,472,555 bytes)
- Licence: **CC BY 4.0**. Credit Ember when using this extract.
- Methodology: `https://files.ember-energy.org/public-downloads/ember_subnational_data_methodology.pdf`

## What was done to it

Only the rows for `India Total` with the variables `Total Generation` (GWh) and
`Total emissions` (ktCO2) were kept. No value was changed. The full file (all
states, fuels and capacity) is not committed; `scripts/ember_crosscheck.py`
rebuilds this extract from it when it is present in `data/raw/ember/`.

## What to know before using it

- This is Ember's **current** file. Ember revises its data, and we do not have
  the versions that were public at earlier dates.
- Ember's figures are its own calculation from Indian official statistics.
  They are an independent calculation, not an independent measurement.
- Ember's intensity is all emissions over all generation. It is not the same
  quantity as any CEA factor series; see `docs/EMBER_CROSSCHECK.md`.
