import xml.etree.ElementTree as ET

import pytest

from tie_in_pid_sketch import Element, TieInEndSketch, landing_end_oil_header, pair_sketch, render_svg, source_end_oil_export


def test_templates_are_complete():
    pair = pair_sketch("Martin Linge A", "Oseberg A")
    assert pair["source"].validate() == []
    assert pair["landing"].validate() == []


def test_svg_is_well_formed_and_contains_tags():
    svg = render_svg(source_end_oil_export("Martin Linge A", "Oseberg A"))
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    assert "XV-01*" in svg and "PL-01*" in svg and "Tie-in A" in svg
    assert "ikke tag fra kontrollert P&amp;ID" in svg


def test_existing_equipment_without_tag_gets_no_asterisk():
    svg = render_svg(landing_end_oil_header("Oseberg A", "Martin Linge A"))
    ET.fromstring(svg)
    assert "TI-B*" in svg
    assert "<text" in svg and ">*<" not in svg


def test_validate_reports_missing_safety_items():
    sk = TieInEndSketch("t", "s", "landing", [Element("tie_in", "TI")])
    findings = sk.validate()
    assert any("ESD" in f for f in findings)
    assert any("pig receiver" in f for f in findings)
    assert any("spectacle" in f for f in findings)


def test_unknown_kind_rejected():
    with pytest.raises(ValueError):
        Element("teleporter")


def test_booster_option_adds_pump():
    sk = landing_end_oil_header("A", "B", with_booster=True)
    assert [e.kind for e in sk.elements].count("pump") == 1
