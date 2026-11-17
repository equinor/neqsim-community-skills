"""Tests for the SEG-Y reading skill (segyio)."""

from __future__ import annotations

import json

import numpy as np
import pytest

segyio = pytest.importorskip("segyio")

from segy_seismic_reading import (
    extract_fence,
    inspect_segy,
    read_crossline,
    read_inline,
    read_slice,
    save_section_png,
    scan_folder,
    to_evidence,
    trace_at_xy,
    write_cube,
)
from segy_seismic_reading.__main__ import main

ILINES = np.arange(100, 106)
XLINES = np.arange(200, 208)
NS = 40


def _cube():
    """Every trace holds il*1000 + xl so the trace identity is visible in the data."""
    value = ILINES[:, None] * 1000.0 + XLINES[None, :]
    return np.repeat(value[:, :, None], NS, axis=2) + np.arange(NS)[None, None, :] * 0.0


@pytest.fixture()
def cube_path(tmp_path):
    return write_cube(
        tmp_path / "cube.sgy", _cube(), ILINES, XLINES, sample_interval_ms=4.0,
        origin=(450000.0, 6780000.0), bin_size=(25.0, 12.5),
        text="SYNTHETIC CUBE\nCRS ED50 UTM ZONE 31N EPSG:23031\nTWT TIME IN MS",
    )


def test_inspect_geometry_coordinates_and_hints(cube_path):
    geometry = inspect_segy(cube_path)
    assert geometry.structured and geometry.header_bytes == (189, 193)
    assert geometry.trace_count == ILINES.size * XLINES.size
    assert geometry.sample_interval == pytest.approx(4.0)
    assert geometry.samples[-1] == pytest.approx(4.0 * (NS - 1))
    assert geometry.bbox["xmin"] == pytest.approx(450000.0)
    assert geometry.bbox["xmax"] == pytest.approx(450000.0 + 25.0 * (XLINES.size - 1))
    assert geometry.bbox["ymax"] == pytest.approx(6780000.0 + 12.5 * (ILINES.size - 1))
    assert geometry.bin_spacing == {"crossline_step": pytest.approx(25.0), "inline_step": pytest.approx(12.5)}
    assert geometry.coordinate_scalars == [-100]
    assert geometry.coordinate_unit == "m"
    assert geometry.crs_hints == {"epsg": "23031", "utm_zone": "31N", "datum": "ED50"}
    assert geometry.domain.startswith("time")
    assert geometry.amplitude["max"] == pytest.approx(ILINES[-1] * 1000.0 + XLINES[-1])

    record = to_evidence(geometry)
    assert record["schema"] == "seismic_dataset_evidence.v1" and record["status"] == "unverified"
    assert record["survey"]["inline_range"] == [100, 105]
    json.dumps(record)


def test_inline_crossline_slice_and_nearest_trace(cube_path):
    inline = read_inline(cube_path, 102)
    np.testing.assert_allclose(inline.data[:, 0], 102000.0 + XLINES)
    crossline = read_crossline(cube_path, 205)
    np.testing.assert_allclose(crossline.data[:, 0], ILINES * 1000.0 + 205)
    slice_, used = read_slice(cube_path, 9.0)
    assert used == pytest.approx(8.0) and slice_.shape == (ILINES.size, XLINES.size)

    trace, samples, info = trace_at_xy(cube_path, 450000.0 + 3 * 25.0 + 4.0, 6780000.0 + 2 * 12.5 - 3.0)
    assert (info["inline"], info["crossline"]) == (102, 203)
    assert info["snap_distance"] == pytest.approx(5.0)
    assert trace[0] == pytest.approx(102203.0) and samples.size == NS

    with pytest.raises(ValueError, match="not in survey"):
        read_inline(cube_path, 999)


def test_fence_snaps_inside_and_blanks_outside_survey(cube_path, tmp_path):
    start = (450000.0, 6780000.0 + 2 * 12.5)
    end = (450000.0 + 7 * 25.0 + 200.0, 6780000.0 + 2 * 12.5)  # runs 200 m past the survey edge
    fence = extract_fence(cube_path, [start, end], spacing=25.0)
    inside = fence.snap_distance <= 37.5
    expected = 102000.0 + XLINES[np.minimum(np.arange(inside.sum()), XLINES.size - 1)]
    np.testing.assert_allclose(fence.data[inside, 0], expected)
    assert np.isnan(fence.data[~inside]).all() and (~inside).sum() >= 6
    assert fence.distance[-1] == pytest.approx(375.0)

    png = save_section_png(fence, tmp_path / "fence.png")
    assert png.stat().st_size > 1000


def test_rotated_grid_coordinates(tmp_path):
    path = write_cube(tmp_path / "rot.sgy", _cube(), ILINES, XLINES, 4.0,
                      origin=(1000.0, 2000.0), bin_size=(25.0, 25.0), rotation_deg=90.0)
    _trace, _samples, info = trace_at_xy(path, 1000.0, 2000.0 + 25.0)  # one bin along rotated x
    assert (info["inline"], info["crossline"]) == (100, 201)
    assert info["snap_distance"] == pytest.approx(0.0, abs=0.02)


def test_unstructured_file_falls_back(tmp_path):
    path = tmp_path / "line2d.sgy"
    spec = segyio.spec()
    spec.samples = np.arange(10) * 2.0
    spec.format = 5
    spec.tracecount = 5
    with segyio.create(str(path), spec) as handle:
        for i in range(5):
            handle.header[i] = {segyio.TraceField.CDP_X: 100 * i, segyio.TraceField.CDP_Y: 0,
                                segyio.TraceField.SourceGroupScalar: 1}
            handle.trace[i] = np.full(10, float(i), dtype=np.float32)
        handle.bin.update(hdt=2000, hns=10, format=5)
    geometry = inspect_segy(path)
    assert not geometry.structured and geometry.inlines is None
    assert any("unstructured" in w for w in geometry.warnings)
    fence = extract_fence(path, [(0.0, 0.0), (400.0, 0.0)], spacing=100.0)
    np.testing.assert_allclose(fence.data[:, 0], [0, 1, 2, 3, 4])
    with pytest.raises(ValueError, match="no inline geometry"):
        read_inline(path, 1)


def test_prestack_file_is_flagged_and_sections_use_one_offset(tmp_path):
    path = tmp_path / "gathers.sgy"
    spec = segyio.spec()
    spec.ilines, spec.xlines, spec.offsets = [1, 2], [10, 11, 12], [100, 200]
    spec.samples = np.arange(5) * 4.0
    spec.format = 5
    spec.sorting = 2
    with segyio.create(str(path), spec) as handle:
        trace = 0
        for il in spec.ilines:
            for xl in spec.xlines:
                for off in spec.offsets:
                    handle.header[trace] = {segyio.TraceField.INLINE_3D: il,
                                            segyio.TraceField.CROSSLINE_3D: xl,
                                            segyio.TraceField.offset: off}
                    handle.trace[trace] = np.full(5, il * 1000.0 + xl + off / 1000.0, dtype=np.float32)
                    trace += 1
        handle.bin.update(hdt=4000, hns=5, format=5)
    geometry = inspect_segy(path)
    assert geometry.offsets == [100, 200]
    assert any("pre-stack" in w for w in geometry.warnings)
    np.testing.assert_allclose(read_inline(path, 2).data[:, 0], [2010.1, 2011.1, 2012.1], rtol=1e-6)
    np.testing.assert_allclose(read_crossline(path, 11, offset=200).data[:, 0], [1011.2, 2011.2], rtol=1e-6)


def test_scan_and_cli(cube_path, tmp_path):
    (tmp_path / "broken.segy").write_bytes(b"\x00" * 100)
    records = scan_folder(tmp_path)
    statuses = sorted(r["status"] for r in records)
    assert statuses == ["error", "unverified"]
    out = tmp_path / "evidence.json"
    assert main([str(cube_path), "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["trace_count"] == ILINES.size * XLINES.size
