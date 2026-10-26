import math

import pytest

from h2s_partitioning import (
    SeparatorStage,
    conversion_factor_curve,
    h2s_partial_pressure_kpa,
    is_sour_service,
    make_wellstream,
    recombine_to_gor_and_h2s,
    run_train,
    separator_gor_and_gas_h2s,
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


def test_recombination_matches_gor_and_h2s_from_wrong_start(neqsim_available):
    stage = STAGES[0]
    truth = make_wellstream(water_mol_fraction=0.2, h2s_mol_fraction=3.0e-4)
    gor_true, y_true = separator_gor_and_gas_h2s(truth, stage)
    wrong = make_wellstream(water_mol_fraction=0.2, h2s_mol_fraction=2.0e-5)
    res = recombine_to_gor_and_h2s(wrong, stage, gor_true, y_true)
    assert res.converged, res.warnings
    gor_chk, y_chk = separator_gor_and_gas_h2s(res.fluid, stage)
    assert gor_chk == pytest.approx(gor_true, rel=1e-3)
    assert y_chk == pytest.approx(y_true, rel=1e-3)
    assert res.wellstream_h2s_mol_fraction == pytest.approx(3.0e-4, rel=0.05)


def test_recombination_rejects_bad_input(neqsim_available):
    fluid = make_wellstream(water_mol_fraction=0.2, h2s_mol_fraction=1.0e-5)
    with pytest.raises(ValueError):
        recombine_to_gor_and_h2s(fluid, STAGES[0], -1.0, 1.0e-4)
    with pytest.raises(ValueError):
        recombine_to_gor_and_h2s(fluid, STAGES[0], 100.0, 0.9)
