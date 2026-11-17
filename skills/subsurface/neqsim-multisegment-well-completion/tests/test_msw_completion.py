"""Tests for the multi-segment well completion skill."""

from __future__ import annotations

import json
import math

import pytest

from msw_completion import (
    Aicd,
    DensityValve,
    PhaseProperties,
    Sicd,
    Valve,
    Zone,
    add_plain_msw,
    build_case,
    calibrate_strength,
    compare_at_same_oil,
    pressure_drop_bar,
    rate_for_pressure_drop,
    read_device_layer,
    run_completion_workflow,
    validate_design,
)
from msw_completion.__main__ import main
from msw_completion.devices import emulsion_viscosity

PROPS = PhaseProperties(
    oil_density=700.0,
    water_density=1000.0,
    gas_density=200.0,
    oil_viscosity=0.5,
    water_viscosity=0.3,
    gas_viscosity=0.03,
)

DECK = """RUNSPEC
DIMENS
  4 1 2 /
OIL
WATER
GAS
METRIC
WELLDIMS
  2 10 1 2 /
GRID
DXV
  4*100 /
DYV
  1*100 /
DZV
  2*5 /
TOPS
  2000 2001 2002 2003 /
SCHEDULE
WELSPECS
  'P1' 'G' 1 1 1* 'OIL' /
/
COMPDAT
  'P1' 1 1 2 2 'OPEN' 1* 1* 0.216 3* 'X' /
  'P1' 2 1 2 2 'OPEN' 1* 1* 0.216 3* 'X' /
  'P1' 3 1 2 2 'OPEN' 1* 1* 0.216 3* 'X' /
  'P1' 4 1 2 2 'OPEN' 1* 1* 0.216 3* 'X' /
/
WCONPROD
  'P1' 'OPEN' 'ORAT' 500 /
/
TSTEP
  10 /
END
"""

DESIGN = {
    "completion": [
        {
            "well": "P1",
            "start_md": 0,
            "end_md": 9999,
            "annulus": "GP",
            "devices_per_joint": 1,
            "device_type": "AICD",
            "device_number": 1,
            "screen_diameter_m": 0.15,
            "casing_diameter_m": 0.216,
        }
    ],
    "aicd": [
        {
            "number": 1,
            "strength": 2.0e-4,
            "x": 3.0,
            "y": 0.7,
            "a": 1.0,
            "b": 1.0,
            "c": 1.0,
            "d": 1.5,
            "e": 1.5,
            "f": 1.5,
        }
    ],
}


def test_aicd_equation_calibration_and_inverse():
    device = Aicd(strength=2.0e-4, x=3.0, y=0.7, d=1.5, e=1.5, f=1.5)
    fractions = (0.6, 0.3, 0.1)
    rho = 0.6 * 700 + 0.3 * 1000 + 0.1 * 200
    mu = 0.6**1.5 * 0.5 + 0.3**1.5 * 0.3 + 0.1**1.5 * 0.03
    expected = 2.0e-4 * rho * (rho / 1000.25) * (1.45 / mu) ** 0.7 * 4.0**3.0
    assert pressure_drop_bar(device, 4.0, fractions, PROPS) == pytest.approx(
        expected, rel=1e-12
    )
    calibrated = calibrate_strength(device, 5.0, 8.0, PROPS)
    assert pressure_drop_bar(calibrated, 5.0, (1.0, 0.0, 0.0), PROPS) == pytest.approx(
        8.0, rel=1e-12
    )
    assert rate_for_pressure_drop(
        calibrated, 8.0, (1.0, 0.0, 0.0), PROPS
    ) == pytest.approx(5.0, rel=1e-8)


def test_spiral_icd_emulsion_and_valves():
    sicd = Sicd(strength=0.01)
    oil_dp = 0.01 * (700 / 1000.25) ** 0.75 * (0.5 / 1.45) ** 0.25 * 9.0
    assert pressure_drop_bar(sicd, 3.0, (1.0, 0.0, 0.0), PROPS) == pytest.approx(
        oil_dp, rel=1e-12
    )
    below = emulsion_viscosity(0.5 + 0.025, 0.5 - 0.025, PROPS, sicd)
    inside = emulsion_viscosity(0.5, 0.5, PROPS, sicd)
    above = emulsion_viscosity(0.5 - 0.025, 0.5 + 0.025, PROPS, sicd)
    assert min(below, above) <= inside <= max(below, above)
    valve = Valve(cv=0.8, ac=2.0e-5)
    v = 10.0 / 86400.0 / 2.0e-5
    assert pressure_drop_bar(valve, 10.0, (1.0, 0.0, 0.0), PROPS) == pytest.approx(
        700 * v * v / (2 * 0.64) / 1e5
    )
    dar = DensityValve(
        cv=1.0,
        ac_oil=7e-4,
        ac_gas=1e-4,
        ac_water=1e-4,
        wvf_low=0.6,
        wvf_high=0.7,
        gvf_low=0.6,
        gvf_high=0.8,
    )
    assert dar.active_area((0.5, 0.2, 0.3))[1] == "oil"
    assert dar.active_area((0.1, 0.0, 0.9))[1] == "gas"
    assert dar.active_area((0.2, 0.8, 0.0))[1] == "water"


def test_design_validation():
    bad = {
        "completion": [
            {
                "well": "P1",
                "start_md": 10,
                "end_md": 5,
                "annulus": "XX",
                "devices_per_joint": 1,
                "device_type": "AICD",
                "device_number": 2,
            }
        ],
        "aicd": [{"number": 1, "strength": 1}],
    }
    problems = " ".join(validate_design(bad))
    assert (
        "annulus" in problems
        and "end_md" in problems
        and "device 2 is not defined" in problems
    )
    assert "missing x, y" in problems
    case = build_case(DESIGN)
    assert "WSEGAICD" in case and "'P1'" in case and "JOINTLENGTH" in case


def test_plain_msw_from_compdat_and_grid():
    deck, infos = add_plain_msw(DECK)
    assert infos == [
        {"well": "P1", "connections": 4, "top_md": 2007.5, "end_md": 2407.515}
    ]
    assert "WSEGDIMS" in deck.split("SCHEDULE")[0]
    welsegs = deck[deck.index("WELSEGS") : deck.index("COMPSEGS")]
    assert welsegs.count("/") == 6  # header, 4 segments, terminator
    compsegs = deck[deck.index("COMPSEGS") :].split("/\n/")[0]
    assert "4 1 2 1 2307.512 2407.515" in compsegs


def test_completor_writes_device_layer(tmp_path):
    pytest.importorskip("completor")
    from msw_completion import run_completor

    deck, _ = add_plain_msw(DECK)
    run = run_completor(build_case(DESIGN), deck, tmp_path / "P1_completor.DATA")
    text = (tmp_path / "P1_completor.DATA").read_text(encoding="utf-8")
    assert text.startswith("RUNSPEC")
    layer = read_device_layer(text)["P1"]
    assert layer["device_segments"] == {"AICD": 4}
    first = layer["devices"][0]
    assert first["x"] == 3.0 and first["y"] == 0.7
    assert 100.0 / 12.0 * 0.4 < first["devices"] < 100.0 / 12.0 * 1.1
    assert run["completor_version"]


def test_devices_choke_the_water_zone_at_the_same_oil():
    device = Aicd(strength=1.0e-5, x=2.0, y=0.0, b=1.0)
    props = PhaseProperties(700.0, 1500.0, 200.0, 0.5, 0.3, 0.03)
    zones = [
        Zone("oil", 50.0, 0.0, 0.0, devices=20),
        Zone("wet", 50.0, 0.6, 0.0, devices=20),
    ]
    result = compare_at_same_oil(
        zones, device, props, bare_drawdown_bar=5.0, max_drawdown_bar=50.0
    )
    assert result["oil_rate_reached"]
    assert result["oil_change_fraction"] == pytest.approx(0.0, abs=1e-5)
    assert result["water_change_fraction"] < -0.01
    assert result["extra_drawdown_bar"] > 0.0


def test_workflow_blocks_without_parameter_source_and_runs_with_it(tmp_path, capsys):
    deck = tmp_path / "P1.DATA"
    deck.write_text(DECK, encoding="utf-8")
    config = {
        "deck": str(deck),
        "out_dir": str(tmp_path / "out"),
        "design": DESIGN,
        "phase_properties": {k: getattr(PROPS, k) for k in PROPS.__dataclass_fields__},
    }
    blocked = run_completion_workflow(config)
    assert (
        blocked["status"] == "blocked" and "parameter_source" in blocked["missing"][0]
    )
    assert "completor_deck" not in blocked["outputs"]

    pytest.importorskip("completor")
    config.update(
        {
            "parameter_source": "illustrative",
            "check_rate_rm3_day": 5.0,
            "zones": [
                {
                    "name": "gas",
                    "productivity_index": 30,
                    "water_fraction": 0.0,
                    "gas_fraction": 0.7,
                    "devices": 10,
                },
                {
                    "name": "oil",
                    "productivity_index": 30,
                    "water_fraction": 0.0,
                    "gas_fraction": 0.0,
                    "devices": 10,
                },
            ],
            "screening": {
                "device": {"type": "AICD", "number": 1},
                "bare_drawdown_bar": 5,
                "max_drawdown_bar": 50,
            },
        }
    )
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    assert main(["run", str(path)]) == 0
    assert "status=ok" in capsys.readouterr().out
    evidence = json.loads(
        (tmp_path / "out" / "completion_evidence.json").read_text(encoding="utf-8")
    )
    assert evidence["device_layer"]["P1"]["device_segments"] == {"AICD": 4}
    assert any("illustrative" in w for w in evidence["warnings"])
    assert math.isfinite(evidence["device_check"]["AICD 1"]["gas_to_oil_dp_ratio"])
    assert (tmp_path / "out" / "device_curves.png").exists()


def test_neqsim_phase_properties():
    pytest.importorskip("neqsim")
    from msw_completion.fluid import phase_properties_from_neqsim

    result = phase_properties_from_neqsim(
        {"methane": 0.5, "propane": 0.1, "nC10": 0.4}, 100.0, 150.0
    )
    props = result["properties"]
    assert result["phases"] == ["oil", "gas"]
    assert 900.0 < props.water_density < 1010.0
    assert props.gas_density < props.oil_density < props.water_density
