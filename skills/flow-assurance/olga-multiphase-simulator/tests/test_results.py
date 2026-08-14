from __future__ import annotations

from pathlib import Path

import pytest

from olga_multiphase_simulator import OlgaResultError, read_ppl, read_tpl


def test_tpl_header_and_branches(tpl_file: Path) -> None:
    trend = read_tpl(tpl_file)
    assert trend.metadata["engine"] == "OLGA 2025.1.0.24773"
    assert trend.metadata["kind"] == "TIME PLOT"
    assert trend.metadata["input_file"] == "demo.genkey"
    assert [(b.name, b.nsections, b.nboundaries) for b in trend.branches] == [("PIPELINE", 2, 3)]
    assert trend.time_unit == "S"


def test_tpl_catalog(tpl_file: Path) -> None:
    trend = read_tpl(tpl_file)
    assert trend.names() == ["PT", "TM"]
    pressure = trend.variables[0]
    assert pressure.unit == "PA"
    assert pressure.branch == "PIPELINE"
    assert pressure.pipe == "PIPE-1"
    assert pressure.section == "1"
    assert pressure.description == "Pressure"
    assert pressure.label() == "PT:PIPELINE:PIPE-1:NR=1"


def test_tpl_series(tpl_file: Path) -> None:
    trend = read_tpl(tpl_file)
    assert trend.time == (0.0, 10.0, 20.0)
    assert trend.series("PT") == (1.0e7, 9.5e6, 9.0e6)
    assert trend.final("TM") == pytest.approx(45.0)


def test_tpl_unknown_variable_raises(tpl_file: Path) -> None:
    with pytest.raises(KeyError):
        read_tpl(tpl_file).series("NOPE")


def test_tpl_truncated_data_raises(tmp_path: Path, tpl_file: Path) -> None:
    broken = tmp_path / "broken.tpl"
    broken.write_text(tpl_file.read_text(encoding="utf-8") + "3.0\n", encoding="utf-8")
    with pytest.raises(OlgaResultError):
        read_tpl(broken)


def test_ppl_times_and_variable_locations(ppl_file: Path) -> None:
    profile = read_ppl(ppl_file)
    assert profile.times == (0.0, 10.0)
    assert [v.name for v in profile.variables] == ["PT", "HOL"]
    assert profile.variables[0].is_boundary is True
    assert profile.variables[1].is_boundary is False


def test_ppl_profile_lengths_follow_boundary_or_section(ppl_file: Path) -> None:
    profile = read_ppl(ppl_file)
    assert len(profile.profile("PT", 0)) == 3  # nsections + 1
    assert len(profile.profile("HOL", 0)) == 2  # nsections


def test_ppl_profile_values(ppl_file: Path) -> None:
    profile = read_ppl(ppl_file)
    assert profile.profile("PT", 0) == (1.0e7, 9.0e6, 8.0e6)
    assert profile.profile("PT", -1) == (9.5e6, 8.5e6, 7.5e6)
    assert profile.profile("HOL", -1) == (0.55, 0.45)


def test_ppl_incomplete_time_block_raises(tmp_path: Path, ppl_file: Path) -> None:
    broken = tmp_path / "broken.ppl"
    broken.write_text(ppl_file.read_text(encoding="utf-8") + "2.0e+01\n1.0e+07\n", encoding="utf-8")
    with pytest.raises(OlgaResultError):
        read_ppl(broken)


def test_non_olga_file_raises(tmp_path: Path) -> None:
    path = tmp_path / "not-olga.tpl"
    path.write_text("hello\nworld\n", encoding="utf-8")
    with pytest.raises(OlgaResultError):
        read_tpl(path)
