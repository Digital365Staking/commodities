"""Fixture is HAND-BUILT from the page text as read on 2026-10-05, not a real HTML snapshot.
Once the first real raw payload is stored, copy it here and re-run these tests."""
from pathlib import Path

import pytest

from app.parsers import nansha

HTML = (Path(__file__).parent / "fixtures" / "nansha_eastbound.html").read_text()


def test_four_service_rows():
    assert len(nansha.parse(HTML)) == 4


def test_first_row_values():
    r = nansha.parse(HTML)[0]
    assert r["liners"] == ["MSK", "MSC", "HSD", "HMM"]
    assert r["service_codes"] == ["AE11", "JADE", "SERA2", "AM2"]
    assert r["yard_closing"] == "WED/1200"
    assert len(r["ports"]) == 9 and "King Abdullah Port" in r["ports"]
    assert len(r["inbound"]) == 9
    assert len(r["outbound"]) == 9  # includes two "-" placeholders; positions are kept


def test_known_source_inconsistencies_are_preserved_not_hidden():
    rows = nansha.parse(HTML)
    assert rows[1]["outbound"] == []                      # row 2: empty outbound
    assert rows[3]["inbound"] == ["–"] * 9                # row 4: no inbound values
    assert rows[3]["service_codes"].count("FAL7") == 2    # duplicated code kept as published
    assert "Southhampton" in rows[1]["ports"]             # source spelling kept


def test_raw_cells_kept_for_audit():
    assert len(nansha.parse(HTML)[0]["raw_cells"]) == 6


def test_table_hash_ignores_page_noise_but_detects_table_edits():
    noisy = HTML.replace("{CRUMB}", "another-token-value")
    assert nansha.table_hash(HTML) == nansha.table_hash(noisy)
    edited = HTML.replace("WED/1200", "THU/1200")
    assert nansha.table_hash(HTML) != nansha.table_hash(edited)


def test_missing_table_raises():
    with pytest.raises(ValueError):
        nansha.parse("<html><body><p>maintenance</p></body></html>")
