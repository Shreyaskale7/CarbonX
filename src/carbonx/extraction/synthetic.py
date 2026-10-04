"""Synthetic electricity bills, as text, for building and evaluating the
extraction pipeline before any real bill has been collected.

EVERYTHING HERE IS INVENTED. The issuers are fictional ("SYNTH-DISCOM-n") and
the layouts are our own, not copies of any utility's bill. Results on this data
say how the pipeline behaves; they say nothing about accuracy on real Indian
bills. When real, redacted bills arrive they replace this corpus, and the
evaluation is re-run unchanged (scripts/eval_extraction.py).

A bill is the text pdfplumber would extract from a digital PDF: lines of
tokens. Layouts differ in the things that make real bills hard:

  * what the consumption field is called, and whether it is inline or a table
  * distractor numbers: meter readings, kVAh, demand, amounts, account numbers
  * number formats (1,18,000 / 118,000 / 118000.00) and date formats
  * a multiplying factor, so consumption is not always present - previous

Layouts 1-5 are for training. Layouts 6-8 were held out, but their first
results drove changes to the model, so they are DEVELOPMENT layouts, not a
test. Layouts 9-11 were written afterwards with the model frozen, as
deliberately hard cases, and are the test:

  9   a tariff table where consumption is just "Qty" in the Energy row
  10  time-of-day slabs, where several numbers are kWh and only the total counts
  11  consumption history printed beside the current figure
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta

SEEN = (1, 2, 3, 4, 5)
DEV = (6, 7, 8)       # unseen in training, but used for error analysis: not a clean test
TEST = (9, 10, 11)    # written after the model was frozen; evaluated once


@dataclass(frozen=True)
class Bill:
    layout: int
    issuer: str
    text: str
    kwh: int               # ground truth for consumption_kwh
    period_start: date
    period_end: date
    meter_id: str


def _num(rng: random.Random, n: float, style: int | None = None) -> str:
    """One of the number styles found on bills."""
    style = rng.randrange(4) if style is None else style
    if style == 0:
        return f"{n:.0f}"
    if style == 1:
        return f"{n:,.0f}"
    if style == 2:  # Indian grouping: 1,18,000
        s = f"{n:.0f}"
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        return ",".join(([head] if head else []) + groups + [tail]) if len(s) > 3 else s
    return f"{n:.2f}"


def _date(rng: random.Random, d: date, style: int) -> str:
    return [d.strftime("%d-%m-%Y"), d.strftime("%d/%m/%Y"),
            d.strftime("%d %b %Y"), d.isoformat()][style]


def make_bill(rng: random.Random, layout: int) -> Bill:
    start = date(2025, rng.randint(1, 12), 1)
    end = (start + timedelta(days=32)).replace(day=1)
    mf = rng.choice([1, 1, 1, 20, 40, 100])
    prev = rng.randint(1_000, 900_000)
    diff = rng.randint(300, 60_000)
    pres, kwh = prev + diff, diff * mf
    kvah = round(kwh / rng.uniform(0.86, 0.99))
    demand, sanctioned = rng.randint(40, 4000), rng.choice([100, 250, 500, 1000, 5000])
    rate = rng.uniform(5.5, 9.5)
    energy, fixed = kwh * rate, sanctioned * rng.choice([150, 250, 400])
    duty = energy * 0.06
    amount = energy + fixed + duty
    arrears = rng.choice([0, 0, rng.randint(500, 90_000)])
    consumer, bill_no = rng.randint(10**9, 10**10 - 1), rng.randint(10**7, 10**8 - 1)
    meter_id = f"{rng.choice(['MTR', 'HT', 'LT', 'EM'])}{rng.randint(10**5, 10**7)}"
    ds = rng.randrange(4)
    n = lambda x: _num(rng, x)
    d = lambda x: _date(rng, x, ds)
    due = end + timedelta(days=rng.randint(10, 20))
    issuer = f"SYNTH-DISCOM-{layout}"
    head = [f"{issuer} ELECTRICITY SUPPLY (SYNTHETIC SAMPLE - NOT A REAL BILL)"]

    if layout == 1:    # inline labels, unit after the value
        lines = head + [
            f"Consumer No: {consumer}    Bill No: {bill_no}",
            f"Meter No: {meter_id}    Sanctioned Load: {sanctioned} kVA",
            f"Billing Period: {d(start)} to {d(end)}",
            f"Previous Reading: {n(prev)}    Present Reading: {n(pres)}",
            f"Multiplying Factor: {mf}",
            f"Units Consumed : {n(kwh)} kWh",
            f"Maximum Demand: {demand} kVA",
            f"Energy Charges: Rs. {n(energy)}    Fixed Charges: Rs. {n(fixed)}",
            f"Electricity Duty: Rs. {n(duty)}    Arrears: Rs. {n(arrears)}",
            f"Amount Payable: Rs. {n(amount + arrears)}    Due Date: {d(due)}",
        ]
    elif layout == 2:  # readings table, consumption is the last column
        lines = head + [
            f"Account {consumer}  Bill {bill_no}  Meter {meter_id}",
            f"From {d(start)}  To {d(end)}",
            "Previous Reading  Present Reading  MF  Units Billed",
            f"{n(prev)}  {n(pres)}  {mf}  {n(kwh)}",
            "Contract Demand  Recorded Demand  Power Factor",
            f"{sanctioned}  {demand}  {rng.uniform(0.86, 0.99):.2f}",
            "Energy Charge  Fixed Charge  Duty  Total",
            f"{n(energy)}  {n(fixed)}  {n(duty)}  {n(amount)}",
            f"Pay by {d(due)}",
        ]
    elif layout == 3:  # kWh and kVAh side by side: the classic confusion
        lines = head + [
            f"CONSUMER NUMBER {consumer}",
            f"METER SERIAL {meter_id}",
            f"BILL PERIOD {d(start)} - {d(end)}",
            f"Consumption (kVAh)        {n(kvah)}",
            f"Consumption (kWh)         {n(kwh)}",
            f"Billing Demand (kVA)      {demand}",
            f"Opening Reading {n(prev)}  Closing Reading {n(pres)}  Multiplier {mf}",
            f"Current Charges           {n(energy + fixed + duty)}",
            f"Previous Dues             {n(arrears)}",
            f"Net Payable               {n(amount + arrears)}",
            f"Due On {d(due)}",
        ]
    elif layout == 4:  # two fields per line, amount before units
        lines = head + [
            f"Service No {consumer}    Invoice No {bill_no}",
            f"Meter Id {meter_id}    Load {sanctioned} kW",
            f"Period Start {d(start)}    Period End {d(end)}",
            f"Bill Amount Rs. {n(amount)}    Billed Units {n(kwh)}",
            f"Last Read {n(prev)}    Current Read {n(pres)}",
            f"Demand Charges Rs. {n(fixed)}    Energy Charges Rs. {n(energy)}",
            f"Tax Rs. {n(duty)}    Outstanding Rs. {n(arrears)}",
            f"Last Date {d(due)}",
        ]
    elif layout == 5:  # a sentence, with the unit word after the value
        lines = head + [
            f"Ref: {bill_no} / {consumer}",
            f"Meter: {meter_id}",
            f"For the period {d(start)} to {d(end)}",
            f"Energy Consumed during the month: {n(kwh)} Units",
            f"Readings: {n(prev)} (previous), {n(pres)} (present), MF {mf}",
            f"Apparent energy: {n(kvah)} kVAh. Demand recorded: {demand} kVA.",
            f"Charges for energy Rs. {n(energy)}, fixed Rs. {n(fixed)}, duty Rs. {n(duty)}.",
            f"Please pay Rs. {n(amount + arrears)} by {d(due)}.",
        ]
    elif layout == 6:  # UNSEEN: table with different column words
        lines = head + [
            f"Connection ID {consumer}   Statement {bill_no}",
            f"Device {meter_id}",
            f"Cycle {d(start)} / {d(end)}",
            "Opening  Closing  Multiplier  Net Energy (kWh)",
            f"{n(prev)}  {n(pres)}  {mf}  {n(kwh)}",
            "Peak kVA  Allotted kVA",
            f"{demand}  {sanctioned}",
            f"Statement Value INR {n(amount)}   Carry Forward INR {n(arrears)}",
            f"Settle Before {d(due)}",
        ]
    elif layout == 7:  # UNSEEN: label and value on separate lines
        lines = head + [
            f"Customer {consumer}",
            f"Instrument {meter_id}",
            f"Service window {d(start)} .. {d(end)}",
            "Energy Drawn",
            f"{n(kwh)}",
            "kWh",
            "Meter start / stop",
            f"{n(prev)} / {n(pres)} x {mf}",
            "Reactive-adjusted energy",
            f"{n(kvah)} kVAh",
            f"Total ₹ {n(amount + arrears)} payable {d(due)}",
        ]
    elif layout == 8:  # DEV: prose, value in the middle of a sentence
        lines = head + [
            f"Dear customer {consumer}, statement {bill_no}.",
            f"Your meter {meter_id} was read on {d(end)}.",
            (f"Your electricity usage this cycle, {d(start)} to {d(end)}, was "
             f"{n(kwh)} units (kWh)."),
            f"The index moved from {n(prev)} to {n(pres)} with factor {mf}.",
            f"Your highest demand was {demand} against an allotment of {sanctioned}.",
            f"This comes to INR {n(amount)}, of which INR {n(duty)} is duty.",
            f"Kindly remit by {d(due)}.",
        ]
    elif layout == 9:  # TEST: tariff table; consumption is "Qty" in the Energy row
        lines = head + [
            f"A/c {consumer}   Doc {bill_no}   Mtr {meter_id}",
            f"Supply from {d(start)} until {d(end)}",
            "Description  Qty  Rate  Amount",
            f"Energy  {n(kwh)}  {rate:.2f}  {n(energy)}",
            f"Fixed  {sanctioned}  {fixed / sanctioned:.2f}  {n(fixed)}",
            f"Duty  {n(energy)}  0.06  {n(duty)}",
            f"Start index {n(prev)}  End index {n(pres)}  Constant {mf}",
            f"Grand Total  {n(amount + arrears)}",
            f"Remit by {d(due)}",
        ]
    elif layout == 10:  # TEST: time-of-day slabs; only the total is the answer
        peak = round(kwh * rng.uniform(0.2, 0.35))
        off = round(kwh * rng.uniform(0.2, 0.35))
        lines = head + [
            f"Consumer {consumer}  Meter {meter_id}  Bill {bill_no}",
            f"Bill period {d(start)} to {d(end)}",
            f"Peak kWh {n(peak)}",
            f"Off-Peak kWh {n(off)}",
            f"Normal kWh {n(kwh - peak - off)}",
            f"Total kWh {n(kwh)}",
            f"Total kVAh {n(kvah)}",
            f"Initial {n(prev)}  Final {n(pres)}  MF {mf}",
            f"Net amount Rs. {n(amount)}  Due {d(due)}",
        ]
    elif layout == 11:  # TEST: consumption history beside the current figure
        last_year = round(kwh * rng.uniform(0.7, 1.3))
        average = round(kwh * rng.uniform(0.8, 1.2))
        lines = head + [
            f"Customer ID {consumer}",
            f"Meter Number {meter_id}",
            f"Billing month {d(start)} - {d(end)}",
            f"Consumption for billing {n(kwh)}",
            f"Consumption same month last year {n(last_year)}",
            f"Average consumption last six months {n(average)}",
            f"Meter reading from {n(prev)} to {n(pres)}, multiplied by {mf}",
            f"Charges this month {n(energy + fixed + duty)}",
            f"Balance brought forward {n(arrears)}",
            f"Total to pay {n(amount + arrears)} before {d(due)}",
        ]
    else:
        raise ValueError(f"no layout {layout}")
    return Bill(layout, issuer, "\n".join(lines), kwh, start, end, meter_id)


def corpus(per_layout: int, layouts: tuple[int, ...], seed: int) -> list[Bill]:
    rng = random.Random(seed)
    return [make_bill(rng, layout) for layout in layouts for _ in range(per_layout)]
