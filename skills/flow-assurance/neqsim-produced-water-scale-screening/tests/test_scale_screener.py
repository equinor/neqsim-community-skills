"""Tests for the scale screener."""

from __future__ import annotations

import pytest

from produced_water_scale_screening import ProducedWaterBuilder, ScaleScreener


def _formation_water():
    return ProducedWaterBuilder().build(
        preset="formation_water_high_ba", ph=6.5, temperature_c=25.0
    )


def _seawater():
    return ProducedWaterBuilder().build(
        preset="seawater", ph=8.1, temperature_c=25.0
    )


def test_screen_returns_all_minerals() -> None:
    screening = ScaleScreener().screen(_seawater())
    salts = {r.salt for r in screening.results}
    assert salts == {"BaSO4", "SrSO4", "CaSO4", "CaCO3"}


def test_sulfate_scale_unknown_without_anion() -> None:
    # Formation water with zero sulfate cannot form sulfate scale on its own.
    screening = ScaleScreener().screen(_formation_water())
    baso4 = next(r for r in screening.results if r.salt == "BaSO4")
    assert baso4.risk == "unknown"
    assert baso4.saturation_index is None


def test_calcite_requires_ph() -> None:
    water = ProducedWaterBuilder().build(preset="seawater")  # no pH
    screening = ScaleScreener().screen(water)
    calcite = next(r for r in screening.results if r.salt == "CaCO3")
    assert calcite.risk == "unknown"


def test_mixing_incompatibility_flags_baso4() -> None:
    screener = ScaleScreener()
    results = screener.mixing_incompatibility(_formation_water(), _seawater(), steps=11)
    baso4 = next(r for r in results if r.salt == "BaSO4")
    # Mixing barium formation water with sulfate seawater must supersaturate BaSO4.
    assert baso4.worst_saturation_index is not None
    assert baso4.worst_saturation_index > 0.0
    assert baso4.risk in {"moderate", "high"}
    assert 0.0 < baso4.worst_fraction_a < 1.0


def test_corrosion_flags_co2_and_h2s() -> None:
    water = ProducedWaterBuilder().build(preset="seawater", pressure_bara=50.0)
    flags = ScaleScreener().corrosion_flags(
        water, co2_mol_percent=5.0, h2s_mol_percent=0.1
    )
    text = " ".join(flags)
    assert "CO2 partial pressure" in text
    assert "H2S partial pressure" in text


def test_corrosion_flags_skip_without_gas() -> None:
    water = ProducedWaterBuilder().build(preset="seawater")
    flags = ScaleScreener().corrosion_flags(water)
    assert any("skipped" in f for f in flags)


def test_mixing_requires_two_steps() -> None:
    with pytest.raises(ValueError):
        ScaleScreener().mixing_incompatibility(_formation_water(), _seawater(), steps=1)
