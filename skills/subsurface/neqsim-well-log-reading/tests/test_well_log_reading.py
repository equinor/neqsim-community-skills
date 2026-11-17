"""Tests for the well-log reading skill (DLIS through dlisio, LAS built in)."""

from __future__ import annotations

import json

import numpy as np
import pytest

from well_log_reading import (
    canonical_mnemonic,
    depth_factor_to_m,
    depth_window_contrast,
    read_well_log,
    resample,
    scan_folder,
    to_evidence,
    zone_statistics,
)
from well_log_reading.__main__ import main

LAS_TEXT = """~VERSION INFORMATION
 VERS.                  2.0 : CWLS LOG ASCII STANDARD - VERSION 2.0
 WRAP.                   NO : ONE LINE PER DEPTH STEP
~WELL INFORMATION
 STRT.M              1500.0 : START DEPTH
 STOP.M              1502.0 : STOP DEPTH
 STEP.M                 0.5 : STEP
 NULL.              -999.25 : NULL VALUE
 COMP.         ACME ENERGY  : COMPANY
 WELL.          TEST 1/2-3  : WELL
 FLD .           DEMO FIELD : FIELD
~CURVE INFORMATION
 DEPT.M                     : 1  DEPTH
 GR  .GAPI                  : 2  GAMMA RAY
 RHOB.G/CM3                 : 3  BULK DENSITY
 GR  .GAPI                  : 4  GAMMA RAY REPEAT
~PARAMETER INFORMATION
 BHT .DEGC            95.0 : BOTTOM HOLE TEMPERATURE
~A  DEPTH     GR      RHOB    GR
 1500.0   45.0   2.45   46.0
 1500.5   50.0 -999.25   51.0
 1501.0   80.0   2.30   81.0
 1501.5   90.0   2.25   91.0
 1502.0   60.0   2.40   61.0
"""

WRAPPED_LAS = """~V
 VERS. 2.0 :
 WRAP. YES :
~W
 WELL. WRAPPED : WELL
 NULL. -999.25 :
~C
 DEPT.FT :
 GR.GAPI :
 DT.US/F :
~A
 1000.0
 20.0 100.0
 1001.0
 30.0 -999.25
"""


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_las_header_curves_nulls_and_duplicates(tmp_path):
    log = read_well_log(_write(tmp_path, "w.las", LAS_TEXT))
    assert log.source_format == "las"
    assert (log.well_name, log.field_name, log.company) == (
        "TEST 1/2-3",
        "DEMO FIELD",
        "ACME ENERGY",
    )
    frame = log.frame()
    np.testing.assert_allclose(
        frame.depth_m(), [1500.0, 1500.5, 1501.0, 1501.5, 1502.0]
    )
    assert np.isnan(frame.curve("RHOB").values[1])
    assert set(frame.curves) == {"GR", "RHOB", "GR:1"}
    assert frame.curve("RHOB").canonical == "RHOB"
    assert log.metadata["param.BHT"] == "95.0 DEGC"
    assert len(log.sha256) == 64


def test_wrapped_las_in_feet_converts_to_metres(tmp_path):
    frame = read_well_log(_write(tmp_path, "wrap.las", WRAPPED_LAS)).frame()
    np.testing.assert_allclose(frame.depth_m(), [304.8, 304.8 + 0.3048])
    assert np.isnan(frame.curve("DT").values[1])


def test_depth_units_and_mnemonics():
    assert depth_factor_to_m("0.1 in") == pytest.approx(0.00254)
    assert depth_factor_to_m("FT") == pytest.approx(0.3048)
    assert depth_factor_to_m("ms") is None
    assert canonical_mnemonic("RHOZ") == "RHOB"
    assert canonical_mnemonic("GR_1") == "GR"
    assert canonical_mnemonic("XYZ", "g/cm3") is None
    assert canonical_mnemonic("XYZ", "g/cm3", "Bulk density") == "RHOB"
    assert canonical_mnemonic("DLDN", "GM/CC", "12 BULK DENSITY") == "RHOB"
    assert canonical_mnemonic("MDIA", "g/cc", "Mud density in") is None
    assert canonical_mnemonic("GSTK", "API", "Thorium spectral gamma") is None
    assert canonical_mnemonic("XYZ", "ohmm", "Deep resistivity") == "RDEP"
    assert canonical_mnemonic("XYZ", "us/ft") is None
    assert canonical_mnemonic("WOBA") == "WOB"


def test_zone_statistics_and_event_contrast(tmp_path):
    depth = np.arange(1000.0, 1100.0, 0.5)
    rhob = np.full(depth.size, 2.50)
    rhob[(depth >= 1048) & (depth <= 1052)] = 2.10  # low-density zone at a loss event
    las = [
        "~V",
        " VERS. 2.0 :",
        " WRAP. NO :",
        "~W",
        " WELL. SYN :",
        "~C",
        " DEPT.M :",
        " RHOB.G/CM3 :",
        "~A",
    ] + [f"{d:.1f} {r:.3f}" for d, r in zip(depth, rhob)]
    frame = read_well_log(_write(tmp_path, "syn.las", "\n".join(las))).frame()

    zones = [
        {"name": "Upper", "top_m": 1000.0, "base_m": 1040.0},
        {"name": "Event", "top_m": 1048.0, "base_m": 1052.0},
    ]
    rows = {row["zone"]: row for row in zone_statistics(frame, zones, curves=["RHOB"])}
    assert rows["Upper"]["mean"] == pytest.approx(2.50)
    assert rows["Event"]["p50"] == pytest.approx(2.10)
    halves = zone_statistics(
        frame,
        [
            {"name": "a", "top_m": 1000.0, "base_m": 1050.0},
            {"name": "b", "top_m": 1050.0, "base_m": 1099.5},
        ],
        curves=["RHOB"],
    )
    assert (
        sum(row["samples_in_zone"] for row in halves) == depth.size
    )  # no double count, last kept

    contrast = depth_window_contrast(
        frame, 1050.0, half_width_m=2.0, background_m=10.0
    )[0]
    assert contrast["contrast"] == pytest.approx(-0.40)
    assert contrast["data_coverage"] == "ok"
    quiet = depth_window_contrast(frame, 1020.0, half_width_m=2.0, background_m=10.0)[0]
    assert quiet["contrast"] == pytest.approx(0.0)

    with pytest.raises(ValueError):
        zone_statistics(frame, [{"name": "bad", "top_m": 10.0, "base_m": 5.0}])

    coarse = resample(frame, 2.0)
    assert coarse.index[1] - coarse.index[0] == pytest.approx(2.0)


def _write_dlis(path, md, gr):
    dliswriter = pytest.importorskip("dliswriter")
    pytest.importorskip("dlisio")
    dlis_file = dliswriter.DLISFile()
    logical_file = dlis_file.add_logical_file()
    logical_file.add_origin(
        "ORIGIN", well_name="WELL-A", field_name="FIELD-X", company="ACME"
    )
    depth = logical_file.add_channel("DEPT", data=md, units="m")
    gamma = logical_file.add_channel("GR", data=gr, units="gAPI", long_name="Gamma ray")
    density = logical_file.add_channel("RHOZ", data=np.full(md.size, 2.4), units="kg")
    logical_file.add_frame(
        "MAIN", channels=(depth, gamma, density), index_type="BOREHOLE-DEPTH"
    )
    dlis_file.write(str(path))


def test_dlis_round_trip_through_dlisio(tmp_path):
    md = np.arange(2000.0, 2010.0, 0.5)
    gr = np.linspace(20.0, 120.0, md.size)
    gr[3] = -999.25
    path = tmp_path / "well.dlis"
    _write_dlis(path, md, gr)

    log = read_well_log(path)
    assert log.source_format == "dlis"
    assert (log.well_name, log.field_name, log.company) == ("WELL-A", "FIELD-X", "ACME")
    frame = log.frame()
    assert frame.index_name == "DEPT" and frame.index_type == "BOREHOLE-DEPTH"
    np.testing.assert_allclose(frame.depth_m(), md)
    assert np.isnan(frame.curve("GR").values[3])
    assert frame.curve("RHOB").name == "RHOZ"  # canonical lookup
    assert frame.curve("GR").long_name == "Gamma ray"

    record = to_evidence(log)
    assert (
        record["schema"] == "well_log_evidence.v1" and record["status"] == "unverified"
    )
    gr_row = next(c for c in record["frames"][0]["curves"] if c["name"] == "GR")
    assert gr_row["valid_fraction"] == pytest.approx((md.size - 1) / md.size)
    json.dumps(record)  # serialisable


def test_time_indexed_dlis_takes_depth_from_channel(tmp_path):
    dliswriter = pytest.importorskip("dliswriter")
    pytest.importorskip("dlisio")
    time_ms = np.arange(0.0, 10000.0, 1000.0)
    tdep_in = np.linspace(85000.0, 86000.0, time_ms.size)  # inches along hole
    dlis_file = dliswriter.DLISFile()
    logical_file = dlis_file.add_logical_file()
    logical_file.add_origin("ORIGIN", well_name="STATION-1")
    channels = (
        logical_file.add_channel("TIME", data=time_ms, units="ms"),
        logical_file.add_channel("TDEP", data=tdep_in, units="in"),
        logical_file.add_channel(
            "TENS", data=np.full(time_ms.size, 2000.0), units="lbf"
        ),
    )
    logical_file.add_frame("800T", channels=channels, index_type="TIME")
    path = tmp_path / "station.dlis"
    dlis_file.write(str(path))

    log = read_well_log(path)
    frame = log.frame()
    assert not frame.is_depth_indexed and frame.depth_curve().name == "TDEP"
    np.testing.assert_allclose(frame.depth_m(), tdep_in * 0.0254)
    assert any("depth taken from channel TDEP" in w for w in log.warnings)
    record = to_evidence(log)["frames"][0]
    assert record["depth_from_channel"] == "TDEP"
    assert record["depth_range_m"][0] == pytest.approx(85000.0 * 0.0254)
    rows = zone_statistics(
        frame, [{"name": "all", "top_m": 2150.0, "base_m": 2190.0}], curves=["TENS"]
    )
    assert rows[0]["n"] == time_ms.size


def test_scan_folder_reports_bad_files_and_cli(tmp_path, capsys):
    _write(tmp_path, "good.las", LAS_TEXT)
    _write(tmp_path, "bad.las", "~V\n VERS. 2.0 :\n~W\n WELL. X :\n")
    records = {
        r["source"]["path"].split("\\")[-1].split("/")[-1]: r
        for r in scan_folder(tmp_path)
    }
    assert records["good.las"]["status"] == "unverified"
    assert (
        records["bad.las"]["status"] == "error"
        and "Curve" in records["bad.las"]["error"]
    )

    out = tmp_path / "evidence.json"
    assert (
        main(
            [
                str(tmp_path / "good.las"),
                "--out",
                str(out),
                "--csv",
                str(tmp_path / "csv"),
            ]
        )
        == 0
    )
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["well_name"] == "TEST 1/2-3"
    assert (tmp_path / "csv").is_dir()


def test_missing_file_and_unknown_format(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_well_log(tmp_path / "nope.dlis")
    odd = _write(tmp_path, "data.bin", "not a log")
    with pytest.raises(ValueError, match="cannot recognise"):
        read_well_log(odd)
