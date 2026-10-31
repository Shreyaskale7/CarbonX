"""The bill redactor: it removes what it knows, keeps what extraction needs, and
fails loudly when something recognisable is left. It cannot clear a bill: a
person still reads the output (docs/BILL_COLLECTION.md). Invented bill, invented
person."""
import re

from carbonx.extraction.redact import redact, residual

BILL = """SAMPLE POWER SUPPLY COMPANY
Consumer Name : RAVI K SHETTY
Address : 14, 2nd Cross, Jayanagar
 Bengaluru 560041
Consumer No : 4410099231
Meter No: KA123456
Mobile 9845012345  Email ravi.shetty@example.com
GSTIN 29ABCDE1234F1Z5   PAN ABCDE1234F
Billing period 01/04/2025 to 30/04/2025
Previous reading 11000   Present reading 12180   Consumption (kWh) 1180
Amount payable 9,440.00
Ravi has paid by cheque
"""
ALSO = ["Ravi Shetty", "Jayanagar"]


def test_personal_data_goes_and_the_consumption_stays():
    out, found = redact(BILL, ALSO, salt=b"s")
    assert residual(out, ALSO) == []
    for secret in ("RAVI", "SHETTY", "Jayanagar", "560041", "4410099231", "KA123456",
                   "9845012345", "example.com", "29ABCDE1234F1Z5", "ABCDE1234F", "2nd Cross"):
        assert secret.lower() not in out.lower(), secret
    for kept in ("Consumption (kWh) 1180", "Present reading 12180", "01/04/2025 to 30/04/2025",
                 "9,440.00"):
        assert kept in out, kept
    assert {"email", "gstin", "pan", "mobile", "identifier", "meter", "name", "address"} <= set(found)


def test_meter_id_keeps_the_shape_the_reader_needs():
    out, _ = redact(BILL, ALSO, salt=b"s")
    assert re.search(r"Meter No: [A-Z]{2,4}\d{4,}", out)
    other, _ = redact(BILL, ALSO, salt=b"t")
    assert out != other                      # a different salt gives a different pseudonym


def test_the_same_identifier_gets_the_same_pseudonym_within_a_bill():
    out, _ = redact("Consumer No: 4410099231\nAccount No: 4410099231\n", salt=b"s")
    ids = re.findall(r"ID-[0-9a-f]{6}", out)
    assert len(ids) == 2 and ids[0] == ids[1]


def test_residual_catches_what_was_not_redacted():
    assert residual("call 9845012345") and residual("mail a@b.co") and residual("PAN ABCDE1234F")
    assert residual("Ravi paid", ["Ravi Shetty"])      # a listed word left behind
    assert residual("Consumption 1180 kWh, reading 12180") == []


def test_a_consumption_figure_is_never_taken_for_a_pin_or_phone():
    out, _ = redact("Consumption (kWh) 118000\nUnits 560041\nAmount 9845012.50\n", salt=b"s")
    assert "118000" in out and "560041" in out and "9845012.50" in out


def test_a_tan_is_removed_and_a_listed_word_is_not_cut_out_of_a_longer_word():
    out, found = redact("TAN No JDHN03184G\nPROGRAM of the RAM unit\n", ["RAM"], salt=b"s")
    assert "JDHN03184G" not in out and found["tan"] == 1
    assert "PROGRAM" in out and "[REDACTED] unit" in out          # whole words only
    assert residual(out, ["RAM"]) == []


def test_a_short_label_inside_a_word_is_not_a_label():
    out, _ = redact("(BILL FOR LARGE INDUSTRIAL/SCHEDULE HT-5 TARIFF)\nConsumer Status R\nConsumer No: 4410099231\n", salt=b"s")
    assert "SCHEDULE HT-5" in out and "Consumer Status R" in out
    assert "4410099231" not in out


def test_ocr_text_with_words_run_together_is_still_redacted_in_loose_mode():
    # invented names: OCR output runs words together and puts punctuation inside them
    ocr = "MSZENITHCOTTONSPVT.LTD..PLOTNOK41.TO44LAKEVIEW ESTATE ACMEWIDGETSPRIVATE LIMITEDM/SASHOKRAO"
    listed = ["ZENITH COTTONS", "PLOT NO K 41 TO 44", "LAKEVIEW ESTATE", "ACME WIDGETS", "ASHOK RAO"]
    plain, _ = redact(ocr, listed, salt=b"s")
    assert "ZENITH" in plain                              # whole-word matching misses merged words, which is why loose exists
    out, found = redact(ocr, listed, salt=b"s", loose=True)
    assert residual(out, listed, loose=True) == []
    for secret in ("ZENITH", "ASHOK", "ACME", "LAKEVIEW", "K41", "ESTATE"):
        assert secret.lower() not in out.lower(), (secret, out)
    assert found["listed"] > 0
