# BEE default fuel emission factors (Annexure IV)

`fuel_factors.csv`: the 53 default ("Type I") fuel emission factors from
Annexure IV of BEE's *Detailed Procedure for Compliance Mechanism under CCTS*,
pages 34–35. Built by `scripts/load_bee_factors.py`; the PDF itself is not
committed.

| Column | Meaning |
|---|---|
| `sr_no`, `fuel` | BEE's row number and fuel name, as printed |
| `slug` | the name used in CarbonX: activity type `fuel.<slug>` |
| `co2_t_per_tj` | CO2 factor, t CO2 per TJ (printed by BEE) |
| `ch4_kg_per_tj`, `n2o_kg_per_tj` | CH4 and N2O factors, kg per TJ (printed by BEE) |
| `co2e_t_per_tj` | **derived by us**, see below |
| `page` | page of the PDF |
| `source_sha256` | SHA-256 of the PDF read |

## What is ours, not BEE's

- **`co2e_t_per_tj` is computed, not printed:**
  `co2 + (ch4 × 21 + n2o × 310) / 1000`, using the GWPs in the procedure's
  Annexure I (IPCC AR2, 100-year: CH4 = 21, N2O = 310).
- **Using CO2e for combustion is our reading.** The procedure converts GHGs to
  CO2e (section 3.2) and Annexure IV gives all three gases, but its combustion
  formula (Annexure II, equation III) is written in t CO2. CarbonX's engine
  uses the CO2e factor; the CO2-only factor is loaded alongside it
  (`fuel.<slug>.co2`). The difference is small: about 0.5% for coal.
- **Validity.** Loaded as valid from 1 April 2024 to 31 March 2027: the
  procedure (p. 8, clause (6)) applies default factors "for the first
  trajectory period".

## How combustion is calculated

BEE's formula (Annexure II, equations III and IV):

    emissions = fuel quantity × NCV × emission factor × oxidation factor

The NCV (net calorific value) and oxidation factor are measured per fuel lot
and stored on the activity. The oxidation factor defaults to 1. The
calculation is type-checked: `t × kcal/kg × tCO2e/TJ` is `tCO2e`, with exact
unit conversion (1 kcal = 4186.8 J; 1 toe = 41.868 GJ, the IEA definitions).

## Check before relying on this

1. **Document version.** The PDF read has internal metadata dated 2023-11-08,
   before the reported July 2024 notification (`docs/RQ3_FINDINGS.md`). Confirm
   the table against the notified text.
2. **Compare with IPCC 2006.** Annexure IV says Type I factors are "referred
   from IPCC Guidelines". This table has **not** been compared with IPCC's
   (Vol. 2, Table 2.2); the IPCC site was unreachable when this was built. The
   coal rows in particular should be checked.
3. **No uncertainty ranges.** BEE prints none. IPCC's published ranges are
   needed before any uncertainty is reported for fuel factors (invariant 6).
4. **Process emissions** (the carbonate table that follows in Annexure IV) are
   not loaded: 2024-27 targets exclude process emissions (p. 7 note).
