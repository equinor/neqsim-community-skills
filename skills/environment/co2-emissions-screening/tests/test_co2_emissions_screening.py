import pytest

from co2_emissions_screening import CombustionCO2Model


def test_pure_methane_stoichiometry():
    model = CombustionCO2Model()
    result = model.evaluate(
        composition={"methane": 1.0},
        molar_flow=1.0,
    )
    # 1 mol/s CH4 -> 1 mol/s CO2 -> 0.04401 kg/s
    assert result.carbon_per_mole_fuel == pytest.approx(1.0, abs=1e-6)
    assert result.co2_mass_rate_kg_s == pytest.approx(0.04401, abs=1e-5)
    # 0.04401 kg CO2 / 0.016043 kg CH4 ~ 2.743
    assert result.specific_co2_kg_per_kg_fuel == pytest.approx(2.743, abs=2e-3)


def test_mass_flow_basis():
    model = CombustionCO2Model()
    result = model.evaluate(
        composition={"methane": 0.9, "ethane": 0.07, "propane": 0.03},
        mass_flow=1.0,
    )
    assert result.co2_mass_rate_kg_s > 0.0
    assert result.co2_mass_rate_t_per_day > 0.0


def test_inert_and_co2_handling():
    model = CombustionCO2Model()
    result = model.evaluate(
        composition={"methane": 0.8, "nitrogen": 0.1, "co2": 0.1},
        molar_flow=1.0,
    )
    # carbon per mole = 0.8 (methane) + 0.1 (CO2 carried) = 0.9
    assert result.carbon_per_mole_fuel == pytest.approx(0.9, abs=1e-6)


def test_over_limit_warning():
    model = CombustionCO2Model()
    result = model.evaluate(
        composition={"methane": 1.0},
        molar_flow=100.0,
        co2_limit_t_per_day=10.0,
    )
    assert result.emission_warning == "over-limit"


def test_requires_exactly_one_flow_basis():
    model = CombustionCO2Model()
    with pytest.raises(ValueError, match="exactly one"):
        model.evaluate(
            composition={"methane": 1.0},
            molar_flow=1.0,
            mass_flow=1.0,
        )


def test_unsupported_component_rejected():
    model = CombustionCO2Model()
    with pytest.raises(ValueError, match="unsupported component"):
        model.evaluate(
            composition={"benzene": 1.0},
            molar_flow=1.0,
        )
