"""Tests for seismic_structure: analytical closure volumes, I/O, velocity, grid, tracking and workflow."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

_SEGY_SRC = Path(__file__).resolve().parents[2] / "neqsim-seismic-segy-reading" / "src"
if _SEGY_SRC.is_dir() and str(_SEGY_SRC) not in sys.path:
    sys.path.insert(0, str(_SEGY_SRC))  # sibling skill; the plugin installs both together

from seismic_structure import (  # noqa: E402
    analyse_closure,
    build_layered_grid,
    calibrate_velocity,
    contact_for_volume,
    contact_sweep,
    discover,
    read_surface,
    run_structure_workflow,
    surface_from_function,
    time_to_depth,
    volumes_at_contact,
    write_irap,
    write_zmap,
)
from seismic_structure.__main__ import main  # noqa: E402
from seismic_structure.surface import Surface  # noqa: E402

Z0, A = 2000.0, 1.0e-4  # paraboloid dome: z = Z0 + A r^2 (m), edge of a 4 x 4 km grid at 2400 m


def dome(step=25.0, half=2000.0, **kwargs):
    n = int(2 * half / step) + 1
    return surface_from_function(lambda x, y: Z0 + A * (x ** 2 + y ** 2), -half, -half, step, step, n, n,
                                 name="top_dome", **kwargs)


def test_paraboloid_closure_matches_analytical_area_and_volume():
    top = dome()
    closure = analyse_closure(top)
    assert closure.closed and closure.crest_m == pytest.approx(Z0)
    assert closure.spill_m == pytest.approx(Z0 + A * 2000.0 ** 2) and closure.spill_reason == "grid edge"
    c = 2200.0
    thick = volumes_at_contact(top, closure, c)
    assert thick["area_km2"] == pytest.approx(math.pi * (c - Z0) / A / 1e6, rel=0.01)
    assert thick["grv_mm3"] == pytest.approx(math.pi * (c - Z0) ** 2 / (2 * A) / 1e6, rel=0.01)
    thin = volumes_at_contact(top, closure, c, thickness_m=50.0)
    assert thin["grv_mm3"] == pytest.approx(math.pi * 8.75e7 / 1e6, rel=0.01)
    assert thin["equivalent_thickness_m"] * thin["area_km2"] == pytest.approx(thin["grv_mm3"], rel=1e-9)

    rows = contact_sweep(top, closure, step_m=10.0, thickness_m=50.0)
    assert rows[0]["grv_mm3"] == 0.0 and rows[-1]["contact_m"] == pytest.approx(closure.spill_m)
    fit = contact_for_volume(rows, thin["grv_mm3"])
    assert fit["contact_m"] == pytest.approx(c, abs=1.0)
    assert contact_for_volume(rows, 1e9) is None


def test_saddle_spill_crest_choice_and_undefined_nodes():
    def two_domes(x, y):
        return np.minimum(2000 + A * ((x + 1000) ** 2 + y ** 2), 2050 + A * ((x - 1000) ** 2 + y ** 2))

    top = surface_from_function(two_domes, -3000, -3000, 25, 25, 241, 241)
    west = analyse_closure(top)
    assert west.crest_m == pytest.approx(2000.0)
    saddle = 2000 + A * 1125.0 ** 2  # both domes equal at x = +125 m on y = 0
    assert west.spill_m == pytest.approx(saddle, abs=0.5)
    assert west.spill_reason == "saddle into a neighbouring high" and west.spill_xy[0] > 100
    east = analyse_closure(top, near_xy=(1000.0, 0.0))
    assert east.crest_m == pytest.approx(2050.0)
    assert east.spill_m == pytest.approx(saddle, abs=0.5)

    holed = dome()
    holed.values[90:92, 80] = np.nan  # gap 250 m from the crest
    leak = analyse_closure(holed, undefined_nodes="leak")
    barrier = analyse_closure(holed, undefined_nodes="barrier")
    assert "undefined" in leak.spill_reason and leak.spill_m < 2010
    assert barrier.spill_m == pytest.approx(2400.0)

    tilted = surface_from_function(lambda x, y: 2000 + 0.1 * x, 0, 0, 25, 25, 40, 40)
    assert not analyse_closure(tilted).closed


def test_irap_zmap_round_trip_rotation_and_yflip(tmp_path):
    top = dome(step=100.0, rotation=30.0)
    top.values[3, 5] = np.nan
    back = read_surface(write_irap(top, tmp_path / "top_res.irap"), domain="depth")
    np.testing.assert_allclose(back.values, top.values, atol=1e-3)
    assert back.rotation == pytest.approx(30.0)
    probe = (150.0, -420.0)
    assert back.sample(*probe)[0] == pytest.approx(top.sample(*probe)[0], abs=1e-2)

    flipped = Surface(0.0, 1000.0, 50.0, 50.0, np.arange(20.0).reshape(4, 5), yflip=-1)
    norm = flipped.normalized()
    assert norm.yflip == 1 and norm.yori == pytest.approx(800.0)
    assert norm.sample(50.0, 800.0)[0] == pytest.approx(flipped.sample(50.0, 800.0)[0])

    flat = dome(step=100.0)
    zmap = read_surface(write_zmap(flat, tmp_path / "top.zmap"), domain="depth")
    np.testing.assert_allclose(zmap.values, flat.values, atol=1e-3)
    with pytest.raises(ValueError):
        write_zmap(top, tmp_path / "rotated.zmap")
    guessed = read_surface(write_irap(flat, tmp_path / "Top_TWT.irap"))
    assert guessed.domain == "time" and any("guessed" in n for n in guessed.notes)


def test_velocity_calibration_and_depth_conversion():
    truth = calibrate_velocity([(1000.0, 1000.0)], k=0.0)
    assert truth.v0 == pytest.approx(2000.0)
    v0, k = 1700.0, 0.6
    t = np.array([800.0, 1600.0, 2400.0, 3000.0])
    z = v0 / k * np.expm1(k * t / 2000.0)
    model = calibrate_velocity(list(zip(t, z)))
    assert model.v0 == pytest.approx(v0, rel=0.02) and model.k == pytest.approx(k, abs=0.02)
    assert model.twt(model.depth(1500.0))[()] == pytest.approx(1500.0)
    time_surface = surface_from_function(lambda x, y: 2000 + 0 * x, 0, 0, 10, 10, 3, 3, domain="time", unit="ms")
    depth = time_to_depth(time_surface, model)
    assert depth.domain == "depth" and depth.values[0, 0] == pytest.approx(float(model.depth(2000.0)))
    with pytest.raises(ValueError):
        calibrate_velocity([])


def test_layered_grid_reproduces_closure_volume_and_passes_builder_checks(tmp_path):
    top = dome(step=50.0)
    closure = analyse_closure(top)
    contact = 2200.0
    expected = volumes_at_contact(top, closure, contact, thickness_m=50.0)
    grid = build_layered_grid(top, nz=5, thickness_m=50.0, porosity=0.25, net_to_gross=0.8,
                              contact_m=contact, closure=closure)
    assert grid.summary["grv_above_contact_mm3"] == pytest.approx(expected["grv_mm3"], rel=1e-9)
    assert grid.summary["net_pore_volume_above_contact_mm3"] == pytest.approx(expected["grv_mm3"] * 0.2, rel=1e-9)
    assert "hcpv_mm3" not in grid.summary
    with_sw = build_layered_grid(top, nz=1, thickness_m=50.0, porosity=0.25, net_to_gross=0.8,
                                 contact_m=contact, closure=closure, water_saturation=0.25)
    assert with_sw.summary["hcpv_mm3"] == pytest.approx(expected["grv_mm3"] * 0.2 * 0.75, rel=1e-9)
    n = grid.nx * grid.ny * grid.nz
    assert all(len(v) == n for v in grid.keywords.values())
    tops = grid.keywords["TOPS"].reshape(grid.nz, grid.ny, grid.nx)
    assert tops[0, 40, 40] == pytest.approx(Z0) and tops[1, 40, 40] == pytest.approx(Z0 + 10.0)
    if grid.validation is not None:
        assert grid.validation["deck_writable"], grid.validation
    text = grid.write(tmp_path / "grid.grdecl").read_text(encoding="utf-8")
    assert f"DIMENS {grid.nx} {grid.ny} 5" in text and "\nTOPS\n" in text
    coarse = build_layered_grid(top, nz=2, thickness_m=50.0, coarsen=4, contact_m=contact, closure=closure)
    assert coarse.summary["grv_above_contact_mm3"] == pytest.approx(expected["grv_mm3"], rel=0.1)


def _ricker(t, f=25.0):
    a = (math.pi * f * t / 1000.0) ** 2
    return (1 - 2 * a) * np.exp(-a)


@pytest.fixture()
def dome_cube(tmp_path):
    """Synthetic cube: a peak at TWT = 1000 + 0.08 * r^2/1000 ms under a dome, 25 m bins, 4 ms."""
    segy_sections = pytest.importorskip("segy_seismic_reading.sections")
    ilines, xlines, ns = np.arange(1, 41), np.arange(101, 141), 200
    samples = np.arange(ns) * 4.0 + 800.0
    x0, y0 = 500000.0, 6700000.0
    cube = np.zeros((ilines.size, xlines.size, ns), dtype=np.float32)
    twt = np.zeros((ilines.size, xlines.size))
    for i in range(ilines.size):
        for j in range(xlines.size):
            r2 = ((j - 20) * 25.0) ** 2 + ((i - 20) * 25.0) ** 2
            twt[i, j] = 1000.0 + 0.08 * r2 / 1000.0
            cube[i, j] = _ricker(samples - twt[i, j]) + 0.3 * _ricker(samples - twt[i, j] - 60.0)
    path = segy_sections.write_cube(tmp_path / "dome.sgy", cube, ilines, xlines, 4.0, origin=(x0, y0),
                                    bin_size=(25.0, 25.0))
    # write_cube starts the time axis at 0; shift the expected times accordingly
    return path, twt - 800.0, (x0, y0)


def test_tracking_recovers_a_known_reflector(dome_cube):
    from seismic_structure import load_cube, track_horizon

    path, twt, (x0, y0) = dome_cube
    cube = load_cube(path)
    surface = track_horizon(cube, 21, 121, float(twt[20, 20]) + 6.0)
    assert surface.domain == "time" and surface.stats()["defined_fraction"] == pytest.approx(1.0)
    np.testing.assert_allclose(surface.values, twt.T, atol=0.6)
    assert (surface.xori, surface.yori) == (pytest.approx(x0), pytest.approx(y0))
    assert surface.xinc == pytest.approx(25.0) and surface.rotation == pytest.approx(0.0, abs=1e-6)
    assert surface.sample(x0 + 20 * 25.0, y0 + 20 * 25.0)[0] == pytest.approx(twt[20, 20], abs=0.6)


def test_workflow_from_seismic_with_well_seed_to_builder(dome_cube, tmp_path):
    path, twt, (x0, y0) = dome_cube
    crest_depth = 2100.0
    velocity = {"ties": [[float(twt[20, 20]), crest_depth]], "k": 0.0}
    config = {"field_name": "Dome", "fluid_type": "oil", "search_paths": [str(path)],
              "seismic": {"well": {"x": x0 + 500.0, "y": y0 + 500.0, "top_depth_m": crest_depth}},
              "velocity": velocity, "thickness_m": 40.0, "contact_m": 2130.0,
              "grid": {"nz": 4, "porosity": 0.25, "net_to_gross": 0.8, "permeability_mD": 200},
              "out_dir": str(tmp_path / "out")}
    evidence = run_structure_workflow(config)
    assert evidence["status"] == "ok", evidence["missing"]
    assert evidence["seed"]["snap_distance_m"] == pytest.approx(0.0, abs=0.1)
    assert evidence["closure"]["crest_m"] == pytest.approx(crest_depth, abs=1.0)
    assert evidence["gate_attempts"]["geometry"][-1] == {
        "source": "structure_map", "outcome": "used",
        "detail": "top tracked from seismic (screening pick, not interpretation)"}
    inputs = evidence["builder_inputs"]
    assert inputs["area_km2"] > 0 and 0 < inputs["gross_thickness_m"] <= 40.0
    for key in ("evidence_json", "top_depth_irap", "closure_map_png", "grid_grdecl"):
        assert (tmp_path / "out").joinpath(evidence["outputs"][key]).exists()
    json.loads((tmp_path / "out" / "structure_evidence.json").read_text(encoding="utf-8"))

    builder = pytest.importorskip("reservoir_model_builder")
    model = builder.build_reservoir_model(**inputs, net_to_gross=0.8, porosity=0.25, water_saturation=0.2)
    expected_hcpv = evidence["volumes"]["grv_mm3"] * 1e6 * 0.8 * 0.25 * 0.8
    assert model.volumetrics.hydrocarbon_pore_volume_rm3 == pytest.approx(expected_hcpv, rel=1e-3)
    assert model.volumetrics.stoiip_Sm3 > 0


def test_workflow_seeds_from_a_discovered_tops_file_and_ties_wells(dome_cube, tmp_path):
    path, twt, (x0, y0) = dome_cube
    folder = tmp_path / "refs"
    folder.mkdir()
    (folder / "cube.sgy").write_bytes(path.read_bytes())
    crest_depth = 2100.0
    (folder / "A-1_tops.csv").write_text(
        f"Well,X,Y,Formation,TVDSS_m\nA-1,{x0 + 500.0},{y0 + 500.0},Reservoir_Top,{crest_depth}\n"
        f"A-1,{x0 + 500.0},{y0 + 500.0},Reservoir_Base,{crest_depth + 40}\n", encoding="utf-8")
    (folder / "A-1_checkshot.csv").write_text(f"TWT_ms,Depth_m\n{twt[20, 20]:.3f},{crest_depth}\n", encoding="utf-8")
    (folder / "old_model.EGRID").write_bytes(b"\x00")
    assert len(discover([folder])["well_tops"]) == 1

    evidence = run_structure_workflow({"search_paths": [str(folder)], "thickness_m": 40.0})
    assert evidence["status"] == "ok", evidence["missing"]
    assert evidence["seed"]["from_well"]["name"] == "A-1"
    tie = evidence["well_tie_check"][0]
    assert tie["well"] == "A-1" and abs(tie["misfit_m"]) < 2.0
    assert any("edge of the mapped area" in w for w in evidence["warnings"])
    assert any("published_grid" in w and "gate record" in w for w in evidence["warnings"])
    assert all(a["source"] != "published_grid" for a in evidence["gate_attempts"]["geometry"])
    assert evidence["builder_inputs"]["field_provenance"]["area_km2"] == "derived"

    # A rerun with outputs inside the searched folder must track again, not re-read its own tracked top.
    for out_dir in (folder / "structure", folder / "elsewhere"):
        run_structure_workflow({"search_paths": [str(folder)], "thickness_m": 40.0, "out_dir": str(out_dir)})
    rerun = run_structure_workflow({"search_paths": [str(folder)], "thickness_m": 40.0})
    assert rerun["inventory"]["depth_surface"] == []
    assert rerun["builder_inputs"]["field_provenance"]["area_km2"] == "derived"

def test_workflow_flags_noise_closures(tmp_path):
    rng = np.random.default_rng(7)
    plane = surface_from_function(lambda x, y: 1500 + 0.02 * x, 0, 0, 25, 25, 60, 60)
    plane.values += rng.normal(0.0, 1.0, plane.values.shape)
    path = write_irap(plane, tmp_path / "top_noisy.irap")
    evidence = run_structure_workflow({"top_surface": str(path), "surface_domain": "depth", "thickness_m": 20.0})
    assert evidence["surface_roughness_m"] > 1.0
    flagged = [w for w in evidence["warnings"] if "map noise" in w or "picking noise" in w or "no closure" in w]
    assert flagged, evidence["warnings"]


def test_workflow_blocks_without_velocity_and_discovers_files(tmp_path, capsys):
    folder = tmp_path / "refs"
    write_irap(dome(step=100.0, domain="time", unit="ms"), folder / "Top_reservoir_twt.irap")
    (folder / "well.las").write_text("~V\n", encoding="utf-8")
    (folder / "checkshot.csv").write_text("TWT_ms,Depth_m\n1000,1000\n", encoding="utf-8")
    inventory = discover([folder])
    assert [len(inventory[k]) for k in ("time_surface", "well_logs", "well_ties")] == [1, 1, 1]

    blocked = run_structure_workflow({"search_paths": [str(folder / "Top_reservoir_twt.irap")]})
    assert blocked["status"] == "blocked" and "velocity" in blocked["missing"][0]
    ok = run_structure_workflow({"search_paths": [str(folder)], "thickness_m": 30.0})
    assert ok["status"] == "ok" and ok["velocity"]["v0_m_per_s"] == pytest.approx(2000.0)
    assert any("spill point" in w for w in ok["warnings"])

    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"search_paths": [str(tmp_path / "empty")]}), encoding="utf-8")
    assert main(["run", str(cfg)]) == 2
    assert main(["discover", str(folder), "--out", str(tmp_path / "inv.json")]) == 0
    assert "time_surface=1" in capsys.readouterr().out
