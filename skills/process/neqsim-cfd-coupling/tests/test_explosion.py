"""Tests for the explosion / dispersion workflow (no Docker needed except the opt-in verification benchmark)."""

import json
import math
import os
import shutil

import pytest
from cfd_coupling import explosion as ex
from cfd_coupling import verification as ver


# ------------------------------------------------------------------------------------------------ fail-closed readiness gate
def test_readiness_fails_closed_when_inputs_missing():
    r = ex.assess_explosion_readiness(
        {"geometry": {"source": "PDMS"}, "source": {"rate": 10}}
    )
    assert r.verdict == "not_ready"
    assert set(r.missing) == {
        "congestion",
        "ignition_location",
        "vents_confinement",
        "gas_detection",
    }
    assert any("do not report explosion results" in f for f in r.findings)


def test_readiness_assumed_inputs_are_screening_not_ready():
    full = {k: {"source": "x", "status": "assumed"} for k in ex.REQUIRED_INPUTS}
    r = ex.assess_explosion_readiness(full)
    assert r.verdict == "ready_screening" and not r.missing
    ok = {k: {"source": "x"} for k in ex.REQUIRED_INPUTS}
    assert ex.assess_explosion_readiness(ok).verdict == "ready"


# ------------------------------------------------------------------------------------------------------------------ grid helpers
@pytest.mark.parametrize("length,h0", [(10.0, 0.5), (22.5, 1.0), (3.0, 1.0)])
def test_stretched_segment_spans_length(length, h0):
    n, ratio = ex.stretched_segment(length, h0, 1.2)
    g = ratio ** (1.0 / (n - 1)) if n > 1 else 1.0
    total = h0 * (g**n - 1.0) / (g - 1.0) if n > 1 and g > 1.0 else h0 * n
    assert total == pytest.approx(length, rel=1e-3)


def test_domain_axes_and_cell_count():
    d = ex.Domain(
        fine=(0, 24, -2, 24.5, -1, 8),
        far=(0, 50, -25, 47.5, -12, 20),
        h=1.0,
        growth=1.25,
    )
    ax = d.axes()
    assert (
        ax["x"][0][0] == 0 and ax["x"][0][-1] == 50
    )  # west wall: no stretched block on the xmin side
    assert ax["y"][0][0] == -25 and ax["y"][0][-1] == 47.5
    assert d.n_cells() == math.prod(sum(a[1]) for a in ax.values())
    fine = ex.Domain(fine=d.fine, far=d.far, h=0.5, growth=1.25)
    assert fine.n_cells() > 4 * d.n_cells()


def test_gci_recovers_second_order():
    f = lambda h: 1.0 + 3.0 * h**2
    r = 2**0.5
    res = ex.gci(f(0.5), f(0.5 * r), f(0.5 * r * r), r)
    assert res["order"] == pytest.approx(2.0, abs=0.05)
    assert res["f_extrapolated"] == pytest.approx(1.0, abs=0.02)
    assert 0 < res["gci_fine"] < 0.6


def test_gci_flags_non_monotonic():
    res = ex.gci(1.0, 1.4, 1.1, 1.41)
    assert res["monotonic"] is False


def test_pressure_metrics_triangle_pulse():
    import numpy as np

    t = np.linspace(0, 0.1, 1001)
    p = 101325.0 + np.where(
        t < 0.05, 40000.0 * t / 0.05, np.clip(40000.0 * (0.1 - t) / 0.05, 0, None)
    )
    m = ex.pressure_metrics(t, p)
    assert m["peak_pa"] == pytest.approx(40000.0, rel=1e-2)
    assert m["impulse_pa_s"] == pytest.approx(0.5 * 40000.0 * 0.1, rel=2e-2)
    assert m["t_peak_s"] == pytest.approx(0.05, abs=1e-3)


# ---------------------------------------------------------------------------------------------------------- flame speed / cloud
def test_scope_laminar_speed_in_literature_range():
    lo, hi = ver.LITERATURE_RANGES["methane_stoich_laminar_burning_velocity_m_s"]
    assert lo <= ex.laminar_speed_scope("methane", 1.0) <= hi
    lo, hi = ver.LITERATURE_RANGES["propane_stoich_laminar_burning_velocity_m_s"]
    assert lo <= ex.laminar_speed_scope("propane", 1.0) <= hi
    assert (
        ex.laminar_speed_scope("methane", 0.3) == 0.0
        and ex.laminar_speed_scope("methane", 3.0) == 0.0
    )


def test_equivalent_stoich_cloud_uniform_stoich_equals_volume():
    import numpy as np

    ft = np.full(
        10,
        ex.FUELS["propane"]["afr_st"] ** -1 / (1 + ex.FUELS["propane"]["afr_st"] ** -1),
    )  # fuel mass fraction at phi = 1
    v = np.full(10, 2.0)
    out = ex.equivalent_stoich_cloud(ft, v, "propane")
    assert out["esc_volume_m3"] == pytest.approx(20.0, rel=0.02)
    assert out["flammable_volume_m3"] == pytest.approx(20.0)


def test_equivalent_stoich_cloud_lean_and_rich_weigh_less():
    import numpy as np

    afr = ex.FUELS["propane"]["afr_st"]
    ft_st = 1.0 / (1.0 + afr)
    lean = ex.equivalent_stoich_cloud(
        np.array([0.8 * ft_st]), np.array([1.0]), "propane"
    )["esc_volume_m3"]
    rich = ex.equivalent_stoich_cloud(
        np.array([1.2 * ft_st]), np.array([1.0]), "propane"
    )["esc_volume_m3"]
    assert 0 < lean < 1.0 and 0 < rich < 1.0


# ---------------------------------------------------------------------------------------------------------------- case writing
def _module_spec(with_leak=False):
    obst = "FoamFile{version 2.0;format ascii;class dictionary;object obstaclesDict;}\nscale 1.0;\nverbose 0;\ng\n{\n enabled true;\n obstacles\n (\n  box { point (1 1 0); size (2 2 2); }\n );\n}\n"
    dom = ex.Domain(fine=(0, 10, 0, 10, 0, 5), far=(0, 20, -5, 15, -3, 9), h=1.0)
    spec = ex.PdrCaseSpec(
        name="t",
        domain=dom,
        obstacles_dict=obst,
        fuel="propane",
        cloud=ex.Cloud((0, 0, 0), (5, 10, 5)),
        ignition=ex.Ignition((3, 5, 2.5)),
        monitor_points={"a": (2, 5, 2)},
        wall_panel_points={"wall": [(0.25, 2, 2), (0.25, 8, 2)]},
        n_outer=3,
    )
    if with_leak:
        spec.leak = ex.LeakSource((4, 4, 1), (1, 0, 0), 5.0, 3000.0)
        spec.wind = ex.Wind(speed=5.0, face="xmax")
        spec.ignition = None
        spec.cloud = None
    return spec


def test_write_case_tree_explosion(tmp_path):
    case = ex.write_case(_module_spec(), tmp_path / "c")
    for rel in (
        "system/PDRblockMeshDict",
        "system/PDRsetFieldsDict",
        "system/setFieldsDict",
        "system/topoSetDict",
        "system/controlDict",
        "constant/combustionProperties",
        "constant/thermophysicalProperties",
        "constant/PDRProperties",
        "geometry/obstaclesDict",
        "0.orig/p",
        "0.orig/U",
        "0.orig/ft",
        "0.orig/b",
        "system/monitorPoints.json",
    ):
        assert (case / rel).exists(), rel
    mesh = (case / "system/PDRblockMeshDict").read_text()
    assert "wallFaces { type wall; faces (0); }" in mesh
    ctrl = (case / "system/controlDict").read_text()
    assert "application PDRFoam" in ctrl and "probeLocations" in ctrl
    assert "nOuterCorrectors    3;" in (case / "system/fvSolution").read_text()
    comb = (case / "constant/combustionProperties").read_text()
    assert "ignite yes" in comb and 'fuelFile "fuels/propane"' in comb
    topo = (case / "system/topoSetDict").read_text()
    assert "fluidCells" in topo and "leakZone" not in topo
    mons = json.loads((case / "system/monitorPoints.json").read_text())
    assert set(mons) == {"a", "wall_00", "wall_01"}


def test_write_case_dispersion_has_leak_sources_and_wind(tmp_path):
    spec = _module_spec(with_leak=True)
    spec.solver = "r5PDRFoam"
    case = ex.write_case(spec, tmp_path / "d")
    fvo = (case / "constant/fvOptions").read_text()
    assert (
        "scalarSemiImplicitSource" in fvo
        and "vectorSemiImplicitSource" in fvo
        and "leakZone" in fvo
    )
    assert (
        "ft (5 0)" in fvo
        and "(3000 0 0)" in fvo
        and "ha (" in fvo
        and "rho (" not in fvo
    )
    assert "leakZone" in (case / "system/topoSetDict").read_text()
    assert (
        "inlet" in (case / "0.orig/U").read_text()
        and "(-5 0 0)" in (case / "0.orig/U").read_text()
    )
    assert "ignite no" in (case / "constant/combustionProperties").read_text()


def test_fuel_enthalpy_is_formation_inclusive_and_sign_correct():
    hm = ex.fuel_absolute_enthalpy("methane", 288.15)
    hp = ex.fuel_absolute_enthalpy("propane", 288.15)
    # JANAF absolute enthalpy of methane at 288 K: about -4.7 MJ/kg (heat of formation -74.9 kJ/mol / 16.04 g/mol + sensible)
    assert -5.0e6 < hm < -4.3e6
    assert (
        -2.8e6 < hp < -2.2e6
    )  # propane: -104.7 kJ/mol / 44.1 g/mol, plus sensible heat


def test_ramped_leak_writes_table_and_enthalpy_source(tmp_path):
    spec = _module_spec(with_leak=True)
    spec.solver = "r5PDRFoam"
    spec.leak.ramp_s = 3.0
    fvo = (ex.write_case(spec, tmp_path / "r") / "constant/fvOptions").read_text()
    assert "explicit table ((0 0) (3 5))" in fvo
    assert "ha { explicit table" in fvo
    assert "table ((0 (0 0 0)) (3 (3000 0 0)))" in fvo


def test_wind_inlet_script_is_written_with_fixed_value_velocity(tmp_path):
    spec = _module_spec(with_leak=True)
    spec.solver = "r5PDRFoam"
    case = ex.write_case(spec, tmp_path / "w")
    sh = (case / "system/inletPatch.sh").read_text()
    assert "0/U" in sh and "fixedValue" in sh and "(-5 0 0)" in sh
    assert "sh system/inletPatch.sh" in " ".join(
        ex.explosion_commands(1, solver="r5PDRFoam", dispersion=True, inlet_patch=True)
    )


def test_laminar_speed_fit_anchored_to_scope_stoichiometric_value():
    assert abs(ex.laminar_speed_scope("methane", 1.0) - 0.35) < 0.03
    assert abs(ex.laminar_speed_scope("propane", 1.0) - 0.45) < 0.04
    assert (
        ex.laminar_speed_scope("methane", 0.3) == 0.0
        and ex.laminar_speed_scope("methane", 2.5) == 0.0
    )
    assert ex.laminar_speed_scope("methane", 0.7) < ex.laminar_speed_scope(
        "methane", 1.0
    )


def test_closed_vessel_spec_is_fully_walled():
    spec = ex.closed_vessel_case(h=0.1)
    assert spec.patches_wall_faces == (0, 1, 2, 3, 4, 5)
    assert spec.domain.n_cells() == 1000


# ------------------------------------------------------------------------------------------------------------------ verification
def test_aicc_methane_matches_literature_range():
    pytest.importorskip("scipy")
    lo, hi = ver.LITERATURE_RANGES["methane_stoich_AICC_pressure_ratio_298K"]
    r = ver.aicc_isochoric({"CH4": 1.0}, 298.15, 101325.0)
    assert lo <= r["P_ratio"] <= hi
    assert 2500 < r["T_ad_K"] < 2750


def test_verify_closed_vessel_status_bands():
    pytest.importorskip("scipy")
    ref = ver.aicc_isochoric({"CH4": 1.0}, 288.15, 1e5)["P_ratio"]
    assert ver.verify_closed_vessel(ref * 0.95)["status"] == "pass"
    assert ver.verify_closed_vessel(ref * 0.85)["status"] == "caution"
    assert ver.verify_closed_vessel(ref * 0.6)["status"] == "fail"


@pytest.mark.skipif(
    os.environ.get("CFD_RUN_DOCKER") != "1" or shutil.which("docker") is None,
    reason="opt-in: set CFD_RUN_DOCKER=1 with Docker and the OpenFOAM image",
)
def test_closed_vessel_pdrfoam_benchmark(tmp_path):
    """Runs PDRFoam on a 1 m3 closed vessel (10 cm cells, about 1 min) and checks the peak pressure against the independent AICC value."""
    pytest.importorskip("scipy")
    spec = ex.closed_vessel_case("v1", h=0.1)
    case = ex.write_case(spec, tmp_path / "v1")
    ex.docker_run(case, ex.explosion_commands(1), cpus=2)
    t, p = ex.read_probes(case, "p")
    res = ver.verify_closed_vessel(float(p[:, 0].max() / 1e5))
    assert res["status"] in ("pass", "caution"), res
