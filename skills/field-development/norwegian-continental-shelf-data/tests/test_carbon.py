"""Tests for the public NCS carbon-cost basis and abatement screening."""

from __future__ import annotations

import math

import pytest

from norwegian_continental_shelf_data import (
    CO2_SOURCE_SPLIT_2024,
    GAS_CO2_FACTOR_KG_PER_SM3,
    POWER_FROM_SHORE_FIELDS,
    abatement_screening,
    annual_carbon_cost,
    carbon_cost_basis,
    combustion_co2_tonnes,
    emission_source_split,
)


def test_carbon_cost_basis_latest_and_specific_year():
    latest = carbon_cost_basis()
    assert latest.year >= 2025
    assert latest.co2_tax_nok_per_tonne_co2 > 0.0
    assert "norskpetroleum.no" in latest.source_url

    y2025 = carbon_cost_basis(2025)
    assert y2025.year == 2025
    assert y2025.co2_tax_nok_per_sm3_gas == pytest.approx(2.21)
    assert y2025.co2_tax_nok_per_tonne_co2 == pytest.approx(944.0)
    assert y2025.combined_co2_nok_per_tonne == pytest.approx(1825.0)
    assert y2025.nox_fund_nok_per_kg == pytest.approx(18.0)


def test_carbon_cost_basis_2026_rates():
    y2026 = carbon_cost_basis(2026)
    assert y2026.year == 2026
    assert y2026.co2_tax_nok_per_sm3_gas == pytest.approx(2.57)
    assert y2026.co2_tax_nok_per_tonne_co2 == pytest.approx(1098.0)


def test_carbon_cost_basis_unknown_year_falls_back_with_note():
    basis = carbon_cost_basis(2019)
    assert basis.year == 2025  # earliest published year
    assert "No published CO2 tax for 2019" in basis.note


def test_combustion_co2_factor_consistent_with_tax_equivalence():
    # 2.21 NOK/Sm3 gas <-> 944 NOK/tonne CO2 implies ~2.34 kg CO2/Sm3.
    assert GAS_CO2_FACTOR_KG_PER_SM3 == pytest.approx(2.34, abs=0.01)
    # 1,000,000 Sm3 gas -> 2340 tonnes CO2.
    assert combustion_co2_tonnes(1_000_000.0) == pytest.approx(2340.0)


def test_annual_carbon_cost_combined_vs_separate():
    combined = annual_carbon_cost(co2_tonnes_per_year=1000.0, year=2025)
    # Combined effective cost 1825 NOK/tonne -> 1,825,000 NOK/year.
    assert combined.combined_co2_nok_per_year == pytest.approx(1_825_000.0)
    assert combined.total_nok_per_year == pytest.approx(1_825_000.0)

    separate = annual_carbon_cost(
        co2_tonnes_per_year=1000.0, year=2025, use_combined_co2_cost=False
    )
    # Tax (944) + ETS (880) = 1824 per tonne.
    assert separate.total_nok_per_year == pytest.approx(1_824_000.0)


def test_annual_carbon_cost_includes_nox():
    cost = annual_carbon_cost(
        co2_tonnes_per_year=0.0, nox_tonnes_per_year=10.0, year=2025
    )
    # 10 t NOx * 1000 kg/t * 18 NOK/kg = 180,000 NOK/year.
    assert cost.nox_cost_nok_per_year == pytest.approx(180_000.0)
    assert cost.total_nok_per_year == pytest.approx(180_000.0)


def test_abatement_screening_attractive_measure():
    result = abatement_screening(
        measure="Waste-heat recovery",
        fuel_gas_avoided_sm3_per_year=20_000_000.0,
        capex_nok=300_000_000.0,
        gas_price_nok_per_sm3=2.0,
        horizon_years=15,
        discount_rate=0.08,
        year=2025,
    )
    assert result.co2_avoided_tonnes_per_year == pytest.approx(46_800.0)
    assert result.net_annual_saving_nok_per_year > 0.0
    assert result.simple_payback_years is not None
    assert result.npv_nok > 0.0
    assert result.verdict in {"attractive", "marginal_positive"}
    assert result.breakeven_co2_price_nok_per_tonne is not None


def test_abatement_screening_with_explicit_co2_and_added_energy_cost():
    result = abatement_screening(
        measure="Power from shore",
        co2_avoided_tonnes_per_year=200_000.0,
        capex_nok=8_000_000_000.0,
        added_energy_cost_nok_per_year=150_000_000.0,
        horizon_years=20,
        discount_rate=0.07,
        year=2025,
    )
    assert result.co2_avoided_tonnes_per_year == pytest.approx(200_000.0)
    assert result.added_energy_cost_nok_per_year == pytest.approx(150_000_000.0)
    assert isinstance(result.npv_nok, float)
    assert result.verdict in {"attractive", "marginal_positive", "review", "unattractive"}


def test_abatement_screening_requires_positive_capex():
    with pytest.raises(ValueError):
        abatement_screening(
            measure="bad", fuel_gas_avoided_sm3_per_year=1000.0, capex_nok=0.0
        )


def test_emission_source_split_2024_sums_to_one():
    split = emission_source_split(2024)
    assert split == CO2_SOURCE_SPLIT_2024
    assert math.isclose(sum(split.values()), 1.0, abs_tol=1e-3)
    assert split["turbines"] > 0.8  # turbines dominate NCS CO2


def test_emission_source_split_rejects_other_years():
    with pytest.raises(ValueError):
        emission_source_split(2023)


def test_power_from_shore_fields_listed():
    assert "Johan Sverdrup" in POWER_FROM_SHORE_FIELDS
    assert "Troll A" in POWER_FROM_SHORE_FIELDS
    assert len(POWER_FROM_SHORE_FIELDS) >= 10
