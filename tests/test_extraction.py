"""Extraction pipeline: generator, candidates, baseline, model, calibration.
No database needed. All data is synthetic."""
import random

import pytest

from carbonx.extraction.extract import (
    ConsumptionModel,
    baseline,
    candidates,
    ece,
    meter_id,
    period,
)
from carbonx.extraction.synthetic import DEV, SEEN, TEST, _num, corpus, make_bill


def test_number_styles_include_indian_grouping():
    rng = random.Random(0)
    assert _num(rng, 118000, style=2) == "1,18,000"
    assert _num(rng, 1234567, style=2) == "12,34,567"
    assert _num(rng, 999, style=2) == "999"
    assert _num(rng, 118000, style=1) == "118,000"


def test_corpus_is_deterministic_and_labelled_synthetic():
    a, b = corpus(5, SEEN, seed=7), corpus(5, SEEN, seed=7)
    assert [x.text for x in a] == [x.text for x in b]
    assert all("SYNTHETIC" in x.text and x.issuer.startswith("SYNTH-") for x in a)


@pytest.mark.parametrize("layout", SEEN + DEV + TEST)
def test_the_true_value_is_always_a_candidate(layout):
    """Otherwise a layout would be unanswerable and its accuracy meaningless."""
    rng = random.Random(layout)
    for _ in range(50):
        bill = make_bill(rng, layout)
        assert any(c.value == bill.kwh for c in candidates(bill.text)), bill.text


def test_candidates_parse_grouped_numbers_and_skip_dates():
    values = [c.value for c in candidates("Units 1,18,000 kWh on 01-04-2025 Rs. 9,500.50")]
    assert values == [118000.0, 9500.5]


def test_baseline_handles_training_layouts_and_fails_safely_elsewhere():
    assert all(baseline(b.text).value == b.kwh for b in corpus(40, SEEN, seed=1))
    for b in corpus(10, DEV + TEST, seed=2):   # no rule matches: None, not a guess
        assert baseline(b.text).value in (None, b.kwh)


@pytest.fixture(scope="module")
def model():
    bills = corpus(80, SEEN, seed=3)
    m = ConsumptionModel()
    lolo = m.fit_leave_one_layout_out([b.text for b in bills], [b.kwh for b in bills],
                                      [b.layout for b in bills])
    return m, lolo


def test_model_learns_the_training_layouts(model):
    m, _ = model
    fresh = corpus(30, SEEN, seed=4)
    assert all(m.predict(b.text).value == b.kwh for b in fresh)


def test_confidence_is_a_probability_and_never_sharpened(model):
    m, lolo = model
    assert m.temperature >= 1.0          # calibration may soften, never sharpen
    assert 0.0 <= lolo <= 1.0
    for b in corpus(20, TEST, seed=5):
        raw, cal = m.predict(b.text, calibrated=False), m.predict(b.text)
        assert 0.0 <= cal.confidence <= 1.0
        assert cal.confidence <= raw.confidence + 1e-9   # softening only
        assert cal.value == raw.value                    # scaling never changes the pick


def test_ece_known_values():
    assert ece([1.0, 1.0], [True, True]) == 0.0
    assert ece([1.0, 1.0], [True, False]) == pytest.approx(0.5)   # sure, half right
    assert ece([0.5, 0.5], [True, False]) == pytest.approx(0.0)   # unsure, half right


def test_empty_document_gives_no_extraction(model):
    m, _ = model
    assert m.predict("no numbers here").value is None
    assert baseline("no numbers here").value is None


# ---- period and meter id: rules only ------------------------------------------

@pytest.mark.parametrize("line", [
    "Billing Period: 01-04-2025 to 01-05-2025",
    "From 01/04/2025  To 01/05/2025",
    "For the period 01 Apr 2025 to 01 May 2025",
    "BILL PERIOD 2025-04-01 - 2025-05-01",
])
def test_period_reads_every_date_style(line):
    from datetime import date
    assert period(f"Due Date: 20-05-2025\n{line}") == (date(2025, 4, 1), date(2025, 5, 1))


def test_period_and_meter_id_on_training_layouts_and_safe_failure():
    for b in corpus(30, SEEN, seed=9):
        assert period(b.text) == (b.period_start, b.period_end)
        assert meter_id(b.text) == b.meter_id
    assert period("no dates here") is None and meter_id("no meter here") is None
    assert period("31-02-2025 to 01-03-2025") is None      # an impossible date is not a date


def test_consumption_is_marked_as_difference_times_factor_and_a_plain_number_is_not():
    """A meter table's consumption is the reading difference times the multiplication factor. The cue fires
    on that number, on OCR that dropped decimals, and not on the readings or the factor themselves."""
    from carbonx.extraction.extract import candidates
    table = "METER-A KWH 3228.8250 2951.9530 276.8720 3000.0000 830616.0000\n"
    marked = {c.raw for c in candidates(table) if c.features["is_product"]}
    assert marked == {"830616.0000"}
    ocr = "KWH 3852.63 3658.89 193.73 1000.00 193733.00\n"                     # decimals dropped by OCR
    assert {c.raw for c in candidates(ocr) if c.features["is_product"]} == {"193733.00"}
    assert not any(c.features["is_product"] for c in candidates("Units 5000\nRate 7.5\n"))
