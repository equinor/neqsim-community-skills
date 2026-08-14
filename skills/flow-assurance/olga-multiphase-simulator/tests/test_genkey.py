from __future__ import annotations

from pathlib import Path

import pytest

from olga_multiphase_simulator import (
    apply_parameters,
    get_parameter,
    list_keywords,
    parameter_overview,
    set_parameter,
    write_variant,
)


def test_lists_keywords_and_skips_comments(genkey_text: str) -> None:
    keywords = list_keywords(genkey_text)
    assert keywords == ["OPTIONS", "FILES", "INTEGRATION", "TREND", "PIPE"]


def test_reads_scalar_value_with_unit(genkey_text: str) -> None:
    assert get_parameter(genkey_text, "INTEGRATION", "ENDTIME") == "5 h"
    assert get_parameter(genkey_text, "integration", "maxdt") == "1 s"


def test_reads_parenthesised_list_value(genkey_text: str) -> None:
    assert get_parameter(genkey_text, "FILES", "PVTFILE") == "(./demo.tab, ./water.tab)"


def test_reads_across_a_continuation_line(genkey_text: str) -> None:
    assert get_parameter(genkey_text, "PIPE", "WALL") == '"WALL-1"'
    assert get_parameter(genkey_text, "PIPE", "ROUGHNESS") == "2.8e-05 m"


def test_selects_occurrence(genkey_text: str) -> None:
    assert get_parameter(genkey_text, "PIPE", "DIAMETER", occurrence=0) == "0.2 m"
    assert get_parameter(genkey_text, "PIPE", "DIAMETER", occurrence=1) == "0.3 m"


def test_set_parameter_changes_only_the_target(genkey_text: str) -> None:
    edited = set_parameter(genkey_text, "INTEGRATION", "ENDTIME", "60 s")
    assert get_parameter(edited, "INTEGRATION", "ENDTIME") == "60 s"
    assert get_parameter(edited, "INTEGRATION", "MAXDT") == "1 s"
    assert get_parameter(edited, "INTEGRATION", "STARTTIME") == "0 s"
    assert edited.count("TREND DTPLOT=10 s") == 1


def test_commented_statement_is_not_edited(genkey_text: str) -> None:
    edited = set_parameter(genkey_text, "INTEGRATION", "ENDTIME", "60 s")
    assert "! INTEGRATION ENDTIME=99 h" in edited


def test_apply_parameters_handles_several_keywords(genkey_text: str) -> None:
    edited = apply_parameters(
        genkey_text,
        {"INTEGRATION": {"ENDTIME": "2 h", "MAXDT": "5 s"}, "TREND": {"DTPLOT": "60 s"}},
    )
    assert get_parameter(edited, "INTEGRATION", "ENDTIME") == "2 h"
    assert get_parameter(edited, "INTEGRATION", "MAXDT") == "5 s"
    assert get_parameter(edited, "TREND", "DTPLOT") == "60 s"


def test_parameter_overview(genkey_text: str) -> None:
    overview = parameter_overview(genkey_text, "OPTIONS")
    assert overview == {
        "TEMPERATURE": "WALL",
        "STEADYSTATE": "ON",
        "COMPOSITIONAL": "OFF",
    }


def test_write_variant_round_trip(tmp_path: Path, genkey_text: str) -> None:
    source = tmp_path / "base.genkey"
    source.write_text(genkey_text, encoding="utf-8")
    variant = write_variant(source, tmp_path / "case_60s.genkey", {"INTEGRATION": {"ENDTIME": "60 s"}})
    assert variant.parent == source.parent
    assert get_parameter(variant.read_text(encoding="utf-8"), "INTEGRATION", "ENDTIME") == "60 s"


def test_unknown_keyword_or_parameter_raises(genkey_text: str) -> None:
    with pytest.raises(KeyError):
        get_parameter(genkey_text, "NOSUCHKEYWORD", "X")
    with pytest.raises(KeyError):
        get_parameter(genkey_text, "INTEGRATION", "NOSUCHPARAM")
