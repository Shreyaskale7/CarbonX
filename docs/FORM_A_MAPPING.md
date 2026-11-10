# Mapping CarbonX to BEE's compliance forms

Written 2026-11-10; status updated the same day. A design note. **Built since it was written:**
the entitlement calculation, a cited and versioned intensity target (migration 0015), a cited and
versioned baseline record (migration 0016), a targets loader, API endpoints, and an entitlement
panel on the reports page. **Still not built:** the Form A and Form I exports, the process-emission
boundary tag, the monitoring plan, and any target values (none are pre-filled; the notification
has not been read). Source: the BEE file
`data/raw/bee/bee_ccts_compliance_procedure.pdf` (45 pages; page numbers below are
the document's own). That file carries no version label, so whether it is the July 2024 text is
**not established** (`docs/RQ3_FINDINGS.md`). Check field names against the current BEE text
before building anything.

CarbonX is a decision-support tool for accredited verifiers. It does not issue assurance
opinions and is not accredited. Nothing below produces, imitates or signs a verifier's
certificate.

## Entitlement: built, with no target values loaded

When this note was first written `src/carbonx` had no entitlement calculation: `lifecycle/registry.py`
stores a credit with a vintage year and a quantity and does not work out how many credits an entity
is owed. It is now in `src/carbonx/compliance/entitlement.py`, reading a stored report and the
target and baseline known at the report's own time. The BEE file does not say what one certificate
equals or how fractions round, so the result is a signed tCO2e-equivalent, not a certificate count.

BEE's rule (pp. 4 and 22):

> number of carbon credit certificates = (specific GHG emission notified for the respective
> compliance cycle - specific GHG emission as achieved in the respective compliance cycle)
> x production in that compliance cycle.

A positive result is certificates issued; a negative one is certificates to purchase
(p. 4, clauses (5) and (6)). The achieved intensity already exists in the calculation engine
(emissions over declared equivalent product, migration 0011). The missing input is the notified
target, which must be stored as a cited, versioned value, not typed into code.

## Form A (Annexure VI, p. 42): field mapping

| # | Form A field | CarbonX source | Status |
|---|---|---|---|
| 1-4 | Name, registration number, sector, sub-sector (marked "Auto") | entity record | add fields; BEE assigns the number |
| 5 | Accredited Carbon Verification Agency | verifier name | add as a field only |
| 6 | Form I for the previous year submitted or not | report status | add |
| 7 | Achieved specific GHG emissions, tCO2e per unit of equivalent product | calculation engine over declared equivalent product | have; withheld until every product has a conversion |
| 8 | Production (baseline) | production records | have; the label is ambiguous, read it against BEE's guidance |
| 9 | Carbon Credit Certificates issued or purchased | the entitlement formula above | **have the figure** (signed tCO2e-equivalent); no certificate count, no target values loaded |
| 10-11 | Reduction measures: year, GHG before and after, investment | none | **gap**; entity-entered, not verified by CarbonX |
| - | Undertaking, signature, seal | the entity's own | never generated |

## Form I (Annexure V, pp. 36-37): what feeds it

Annual, with one section per sector type. Main rows:

- production per product, plus "Total Equivalent Product" (tonnes);
- electricity purchased, generated, exported and total (million kWh);
- solid, liquid and gaseous fuel (million kcal);
- direct GHG energy-related, indirect GHG energy-related, **direct GHG process-related**, and
  the total direct and indirect (tCO2e);
- specific GHG emissions (tCO2e per tonne).

Form I reports process emissions as their own row. The gate-to-gate tag in
`docs/ARCHITECTURE_NEXT.md` (change 2) maps to it; without the tag CarbonX cannot fill
the energy-related and process-related rows separately.

## Form B (Annexure VII, p. 43): not ours

The accredited verifier certifies four things: the data collection under Form I, the reduction
measures in Form A, compliance with the emission norms, and the entitlement number. CarbonX can
only make those checks faster by supplying traceable evidence for each. It does not generate
Form B.

## Proposal

1. Entitlement calculation with a cited, versioned target per entity and cycle, showing the
   formula and every input.
2. Form A and Form I exports in BEE's field order, each figure with a hash pointing to its
   evidence; signature, seal and verifier fields left blank.
3. The process-emission tag (change 2), so Form I's energy-related and process-related rows
   are separate.
4. Reduction measures as an entity-entered table, labelled as not verified by CarbonX.

## Open before building

- The BEE file's version label (above).
- Pages 44-45 appear to hold further certificate forms, one referred to as "Form D". Not read
  in detail; check whether the entitlement number appears on more than one form.
- The notified target: its unit (specific GHG emission per unit of equivalent product), value
  and the year it applies to must come from the MoEFCC notification, not from a secondary summary.
- Scope: Form A and Form I output is hardening of the report component, but confirm with the
  guide. Anything beyond it goes through `docs/SCOPE_PROPOSAL.md`.
- Timing: the BEE file says Form A is due within three months of the cycle ending (p. 15).
  Secondary sources say four months or quarterly. Use the notified text.
