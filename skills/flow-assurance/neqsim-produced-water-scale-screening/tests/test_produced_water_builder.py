"""Tests for the produced-water builder."""

from __future__ import annotations

import math

import pytest

from produced_water_scale_screening import ProducedWaterBuilder


def test_build_from_preset_seawater() -> None:
    builder = ProducedWaterBuilder()
    water = builder.build(preset="seawater", temperature_c=25.0, ph=8.1)

    assert water.tds_mg_l > 30000.0
    assert "Na+" in water.molality
    assert water.ionic_strength_mol_kg > 0.0
    # NeqSim mapping must include water and sum to ~1.
    assert "water" in water.neqsim_components
    assert math.isclose(sum(water.neqsim_components.values()), 1.0, rel_tol=1e-9)


def test_build_from_explicit_ions() -> None:
    builder = ProducedWaterBuilder()
    water = builder.build(
        ions_mg_l={"Na+": 10000.0, "Cl-": 15400.0},
        name="brine",
    )
    assert water.name == "brine"
    # Roughly charge balanced NaCl brine.
    assert abs(water.charge_balance_error_pct) < 5.0


def test_unsupported_ion_warning() -> None:
    builder = ProducedWaterBuilder()
    water = builder.build(ions_mg_l={"Na+": 1000.0, "Cl-": 1540.0, "Ba++": 100.0})
    assert any("Ba++" in w for w in water.warnings)


def test_tds_only_input_models_nacl() -> None:
    builder = ProducedWaterBuilder()
    water = builder.build(tds_mg_l=35000.0)
    assert set(water.ions_mg_l) == {"Na+", "Cl-"}
    assert any("NaCl" in w for w in water.warnings)


def test_charge_balance_warning_triggers() -> None:
    builder = ProducedWaterBuilder()
    water = builder.build(ions_mg_l={"Na+": 10000.0, "Cl-": 100.0})
    assert any("Charge balance" in w for w in water.warnings)


def test_mix_blends_compositions() -> None:
    builder = ProducedWaterBuilder()
    a = builder.build(preset="formation_water_high_ba")
    b = builder.build(preset="seawater")
    blend = builder.mix(a, b, 0.5)
    assert blend.ions_mg_l["SO4--"] == pytest.approx(
        0.5 * a.ions_mg_l.get("SO4--", 0.0) + 0.5 * b.ions_mg_l["SO4--"]
    )


def test_invalid_inputs_raise() -> None:
    builder = ProducedWaterBuilder()
    with pytest.raises(ValueError):
        builder.build()
    with pytest.raises(ValueError):
        builder.build(preset="seawater", tds_mg_l=1000.0)
    with pytest.raises(ValueError):
        builder.build(ions_mg_l={"Na+": float("nan")})
    with pytest.raises(ValueError):
        builder.build(ions_mg_l={"Na+": -1.0})
