# Two messages to send, and what the searches found

Written 2026-10-27. **Nothing here has been sent.** Both are drafts for the authors
to edit and send themselves; sending is theirs to decide.

## 1. CEA's copyright policy requires prior permission

CEA's current copyright policy, read on 2026-10-27 at
`https://cea.nic.in/api/websitepolicy/pdf/view/en/2` (linked from
`https://cea.nic.in/websitePolicy?lang=en`, "Copyright Policy"), is headed
"Copyright policy - Moderate". In summary: content may be reproduced free of
charge, subject to five conditions:

1. **Prior permission**, by emailing "the designated CEA contact" (the policy does
   not name one; the website policy page footer lists
   `sailesh.cea[at]gov[dot]in`, which should be confirmed as the right address);
2. reproduction **without modification that alters meaning or intent**;
3. CEA **clearly acknowledged** as the source;
4. no misleading, derogatory or inappropriate use;
5. third-party material needs its owners' permission.

Older pages and secondary sources describe a more open policy (no permission
needed). The current text above governs; do not rely on the older wording.

**What this touches.** `data/cea/factors.csv` and `versions.csv` hold numbers and
cell references taken from CEA's workbooks, with CEA's own row labels verbatim
and source URLs and checksums. The workbooks themselves are not in the
repository (`data/raw/` is ignored). Whether extracted figures need permission is
a question of law the authors cannot settle alone; the policy asks for permission,
so the safe course is to ask before the registry is deposited with a DOI, before
either paper is submitted, and ideally before the repository stays public. The
repository is public today.

### Draft email to CEA

> Subject: Request for permission to publish a version history of the CO2 Baseline Database (student research, RVCE)
>
> Dear Sir/Madam,
>
> We are students of RV College of Engineering, Bengaluru, working on a research
> project on emission accounting under India's Carbon Credit Trading Scheme,
> under the guidance of **[guide's name and designation]**.
>
> Following the copyright policy on cea.nic.in, we are writing to request
> permission to reproduce material from the CEA CO2 Baseline Database for the
> Indian Power Sector (versions 1.0 to 22.0). We have compiled the grid emission
> factor values from all published versions into one machine-readable table, each
> value with the workbook, sheet and cell it was read from, CEA's own row label
> reproduced verbatim, and the source URL and checksum of each file. Values are
> reproduced exactly as published, with no modification. We do not redistribute
> the workbooks themselves.
>
> We would like to (a) deposit this table in a public research repository with a
> DOI, (b) describe it in a data article, and (c) analyse how the factor differs
> between versions in a research paper. In all of these CEA would be
> acknowledged as the source, the table would state that it is not an official
> CEA product, and users would be directed to CEA's workbooks for any regulatory
> use.
>
> Could you please confirm (1) that we may do so, (2) the wording of
> acknowledgement you prefer, and (3) whether any licence or condition applies
> beyond the copyright policy? We would also be grateful to know if there is a
> more appropriate person to address.
>
> Thank you,
> **[names, roll numbers, institution email, phone]**

Keep the reply. If CEA agrees, record its wording in `data/cea/release.json` and
the Data in Brief ethics statement. If it declines or asks for changes, the
registry release and both papers change accordingly. If CEA does not answer,
that is not permission.

## 2. Pre-submission enquiry to the Data in Brief editorial office

Data in Brief's own guidance says data should not have been published before and
should result from experiment or observation rather than computer simulation.
These data are compiled from public workbooks, so ask before paying anything.
Use the contact on the journal's homepage (not confirmed here).

> Subject: Scope enquiry: compiled version history of a public government dataset
>
> Dear Editors,
>
> We would like to submit a data article describing a machine-readable version
> history of India's Central Electricity Authority CO2 Baseline Database: 23
> published versions (2006 to 2026), 2,071 values, each traced to the workbook
> cell it was read from, with source checksums. The values are reproduced as
> published, without correction. The original workbooks are public; the new
> contribution is the consolidated, versioned, cell-referenced record and its
> validation.
>
> Before we submit, could you tell us whether a compiled and validated version
> history of a public government dataset falls within the scope of Data in Brief,
> given the guidance that data should not be previously published and should
> derive from observation or experiment? We have written permission from
> **[CEA / pending]** to reproduce the material.
>
> Thank you,
> **[names, affiliation]**

## 3. What the searches found about real bills

**There is no suitable public dataset of real Indian electricity bills that we
could find**, and we should not take bills from the open internet.

- **Hugging Face:** no dataset of Indian electricity bills. A forum thread
  (`discuss.huggingface.co`, "Seeking Indic Document Dataset") is a request for
  one. `judicialmind/BharatEnergy-Data` is power-station generation data (CC
  BY-NC-SA 4.0, gated), not bills. A synthetic invoice set exists, but invoices,
  not electricity bills.
- **Kaggle:** "Financial Document Image Dataset" (`mehaksingal`) is described as
  "personal financial and identification documents for individuals in India"
  (bank statements, salary slips, tax returns, utility bills, cheques), 91 images
  in total, unknown how many are utility bills, no stated provenance, no
  consumption labels, login required. Using it would conflict with
  `docs/BILL_COLLECTION.md`: no consent from the people the documents belong to
  can be shown, and identification documents are the kind of personal data we
  must not copy. Not used. Another Kaggle set is tabular (modelled bills from
  appliance usage), not bills.
- **Elsewhere:** a 2024 paper reports a Spanish set of 75,000 electricity
  invoices (not Indian; availability and licence unknown). Commercial OCR vendors
  do not publish bill datasets.
- **Scraping images of other people's bills** from search engines or social media
  is not an option: it copies personal data without consent, and a result built
  on it could not be published.

**What can legitimately be done instead:**
1. **Bills from people who agree** (team, family, RVCE's estate office), redacted
   with `scripts/redact_bill.py`, as in `docs/BILL_COLLECTION.md`.
2. **Blank or sample bills that a utility publishes** on its own site to explain
   its bill (these are formats, not consumers' bills). They would add layouts
   for the synthetic generator and for the held-out-by-utility test, with the
   utility named as source. Check each site's terms; ask before downloading any.
3. Keep calling the extraction result **synthetic-only** until option 1 gives at
   least 3 utilities with 5 bills each.
