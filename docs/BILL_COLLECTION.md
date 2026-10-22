# Collecting real bills: checklist

One page for whoever gathers bills. The extraction model has only ever seen
invented bills (`docs/EXTRACTION.md`); real ones are the largest gap in the
project. Do not skip a step: a leaked bill cannot be taken back.

## What we need

- **30 or more bills**, from **at least 3 different utilities** (DISCOMs). One
  utility is held out of training and used as the test, so the count of
  *utilities* matters more than the count of bills.
- Mostly **digital PDFs** (text can be selected). A few phone photos or scans are
  useful, but scans need OCR, which is not built, so they are not usable yet.
- Different **layouts and tariffs** (home, commercial, industrial). Not 30 copies
  of one format.
- Each bill must show the billing period and the units (kWh) consumed.

## Before you take a bill

- [ ] The person it belongs to **agreed**, knowing it will be redacted and used
      in a college research project. Write who agreed and when. Without this, do
      not use the bill.
- [ ] It is not a bill you could only get by logging in as someone else.
- [ ] You told them the project is a prototype, not accredited, and issues no
      assurance opinions.

## Handling

1. Keep the original **only on your own machine** in `data/bills/`. That folder
   is git-ignored. Never email, upload or commit the original.
2. Dry run the redactor and read every line of the output:

   ```bash
   python scripts/redact_bill.py data/bills/YOURFILE.pdf --discom BESCOM --also "Owner Name" --also "Street Name"
   ```

   `--also` takes the owner's name, street, employer and anything else that
   identifies them. Repeat it as needed. The tool also removes labelled names,
   addresses, account and consumer numbers, phones, emails, GSTIN, PAN and PIN
   codes, and replaces meter ids with a made-up one.
3. **It cannot find a name or address that has no label.** Look for those
   yourself. If something is left, add it with `--also` and run again. If the
   tool says STOP, fix that first.
4. Only when the printed text is clean, add `--write`.
5. Open the new `data/redacted_bills/<id>.json` and fill in, by hand:
   - `consent`: `true`, only if step 1 of "Before you take a bill" is done
   - `consumption_kwh`: the true figure, read from the **original** bill
   - `tariff_category`: as printed
   - `reviewed_by`: your name (someone read the redacted text)
   - `notes`: anything odd about the layout
6. `pytest tests/test_redacted_bills.py` must pass. It refuses a bill that still
   looks like personal data, has no consent, has no reviewer, or whose true
   consumption does not appear in the text.
7. Commit the `.txt` and `.json` only. Check `git status` shows no PDF.

## Not allowed

- Raw bills, screenshots or photos in the repo, in chat, or in an issue.
- Bills from people who did not agree.
- Guessing `consumption_kwh`. If you cannot read it from the original, leave the
  bill out.
- Describing results on these bills as accuracy for Indian electricity bills in
  general. Report the count of bills and utilities beside every number.

## After collecting

Say how many bills and how many utilities you have. The evaluation on real bills
(`scripts/eval_extraction.py` currently reads only the synthetic corpus) still
has to be written to read `data/redacted_bills/`; that is the next build once
there are bills to test against.
