import math

import pytest

from h2s_partitioning import (
    SeparatorStage,
    conversion_factor_curve,
    h2s_partial_pressure_kpa,
    is_sour_service,
    make_wellstream,
    run_train,
    water_mole_fraction,
    wellstream_h2s_from_separator_gas,
)

STAGES = [SeparatorStage(70.0, 10.0, "HP"), SeparatorStage(60.0, 2.0, "LP")]


def test_pure_helpers():
    assert h2s_partial_pressure_kpa(1.0e-4, 10.0) == pytest.approx(0.1)
    assert is_sour_service(5.0e-4, 10.0)
    assert not is_sour_service(1.0e-5, 10.0)
    wf = water_mole_fraction(1000.0, 1000.0)
    assert 0.98 < wf < 1.0
    with pytest.raises(ValueError):
        water_mole_fraction(-1.0, 10.0)


@pytest.fixture(scope="module")
def neqsim_available():
    pytest.importorskip("neqsim")


def test_train_closes_h2s_balance(neqsim_available):
    fluid = make_wellstream(water_mol_fraction=0.3, h2s_mol_fraction=1.0e-4)
    res = run_train(fluid, STAGES)
    total = res.to_gas_fraction + res.to_oil_fraction + res.to_water_fraction
    assert total == pytest.approx(1.0, abs=0.02)
    assert res.to_gas_fraction > res.to_water_fraction
    assert res.stages[0].gas_h2s_ppmv > 0


def test_wellstream_back_calculation_round_trip(neqsim_available):
    z_true = 2.0e-4
    fluid = make_wellstream(water_mol_fraction=0.3, h2s_mol_fraction=z_true)
    y = run_train(fluid, STAGES).stages[0].gas_h2s_ppmv
    res = wellstream_h2s_from_separator_gas(fluid, STAGES, y, stage_index=0)
    assert res.wellstream_h2s_mol_fraction == pytest.approx(z_true, rel=1e-3)
    assert res.conversion_factor == pytest.approx(z_true * 1.0e6 / y, rel=1e-3)


def test_more_water_pulls_h2s_out_of_gas(neqsim_available):
    curve = conversion_factor_curve(None, STAGES, [0.05, 0.3, 0.6])
    factors = [f for _, f in curve]
    assert all(math.isfinite(f) and 0.0 < f < 1.0 for f in factors)
    assert factors[0] > factors[1] > factors[2]


def test_unreachable_measurement_raises(neqsim_available):
    fluid = make_wellstream(water_mol_fraction=0.2, h2s_mol_fraction=1.0e-5)
    with pytest.raises(ValueError):
        wellstream_h2s_from_separator_gas(fluid, STAGES, 1.0e9)
