import pytest

from heat_exchanger_fouling_assessment import HeatExchangerFoulingModel

BASE_CASE = dict(
    area=420.0,
    design_overall_coefficient=1250.0,
    hot_mass_flow=180.0,
    hot_specific_heat=3.6,
    hot_inlet_temperature=338.15,
    hot_outlet_temperature=318.15,
    cold_mass_flow=260.0,
    cold_specific_heat=4.0,
    cold_inlet_temperature=288.15,
    cold_outlet_temperature=300.65,
    design_hot_mass_flow=220.0,
    design_cold_mass_flow=300.0,
    design_fouling_allowance=2.0e-4,
    installed_units=3,
)


def test_duty_is_reconciled_from_both_sides() -> None:
    result = HeatExchangerFoulingModel().evaluate(**BASE_CASE)

    assert result.duty_hot_kw == pytest.approx(180.0 * 3.6 * 20.0)
    assert result.duty_cold_kw == pytest.approx(260.0 * 4.0 * 12.5)
    assert result.duty_imbalance_fraction < 0.01
    assert result.duty_kw == pytest.approx(0.5 * (result.duty_hot_kw + result.duty_cold_kw))
    assert result.duty_source == "auto-mean"


def test_two_sided_normalisation_is_lower_than_one_sided() -> None:
    result = HeatExchangerFoulingModel().evaluate(**BASE_CASE)

    # Below design flow, the one-sided form scales the deposit as well as the
    # films, so it always reports the exchanger as healthier than it is.
    assert result.u_naive_one_sided_w_m2k > result.u_normalised_to_design_flow_w_m2k
    assert result.naive_optimism_percentage_points > 0.0
    assert any("one-sided" in warning for warning in result.warnings)


def test_normalisation_is_identity_at_design_flow() -> None:
    case = dict(BASE_CASE)
    case["design_hot_mass_flow"] = case["hot_mass_flow"]
    case["design_cold_mass_flow"] = case["cold_mass_flow"]

    result = HeatExchangerFoulingModel().evaluate(**case)

    assert result.u_normalised_to_design_flow_w_m2k == pytest.approx(
        result.u_measured_w_m2k, rel=1e-6
    )
    assert result.u_naive_one_sided_w_m2k == pytest.approx(result.u_measured_w_m2k, rel=1e-6)


def test_fouling_resistance_closes_the_series_resistance_balance() -> None:
    result = HeatExchangerFoulingModel().evaluate(**BASE_CASE)

    total_resistance = 1.0 / result.u_normalised_to_design_flow_w_m2k
    design_resistance = 1.0 / result.u_design_w_m2k
    assert total_resistance > design_resistance
    assert result.excess_fouling_resistance_m2k_w == pytest.approx(
        result.fouling_resistance_m2k_w - result.design_fouling_allowance_m2k_w, abs=1e-12
    )


def test_maldistribution_scan_raises_apparent_coefficient() -> None:
    result = HeatExchangerFoulingModel().evaluate(**BASE_CASE)
    scan = result.maldistribution_scan

    assert [row.units_credited for row in scan] == [3, 2, 1]
    assert scan[0].u_apparent_w_m2k < scan[1].u_apparent_w_m2k < scan[2].u_apparent_w_m2k
    assert scan[0].credited_area_m2 == pytest.approx(BASE_CASE["area"])


def test_close_approach_switches_the_coefficient_to_effectiveness_ntu() -> None:
    case = dict(BASE_CASE)
    case["cold_outlet_temperature"] = 336.0  # 2.15 K hot-end approach

    result = HeatExchangerFoulingModel().evaluate(**case)

    assert result.lmtd_reliable is False
    assert result.u_measured_basis == "effectiveness-ntu"
    assert any("close approach" in warning for warning in result.warnings)


def test_effectiveness_ntu_and_lmtd_agree_when_the_approach_is_wide() -> None:
    model = HeatExchangerFoulingModel()
    result = model.evaluate(**BASE_CASE)

    u_from_ntu = 1000.0 * result.ntu * min(180.0 * 3.6, 260.0 * 4.0) / BASE_CASE["area"]
    assert u_from_ntu == pytest.approx(result.u_measured_w_m2k, rel=0.02)


def test_capacity_limit_collapses_as_the_cold_inlet_approaches_the_set_point() -> None:
    model = HeatExchangerFoulingModel()
    wide = model.capacity_limit(
        effectiveness=0.5,
        hot_capacity_rate=648.0,
        cold_capacity_rate=1040.0,
        set_point_temperature=318.15,
        cold_inlet_temperature=288.15,
        required_duty=5000.0,
    )
    narrow = model.capacity_limit(
        effectiveness=0.5,
        hot_capacity_rate=648.0,
        cold_capacity_rate=1040.0,
        set_point_temperature=318.15,
        cold_inlet_temperature=316.15,
        required_duty=5000.0,
    )

    assert narrow.maximum_duty_kw < wide.maximum_duty_kw
    assert narrow.limited is True
    assert narrow.limit_cause == "temperature-approach"


def test_capacity_limit_is_zero_when_the_cold_inlet_exceeds_the_set_point() -> None:
    result = HeatExchangerFoulingModel().capacity_limit(
        effectiveness=0.5,
        hot_capacity_rate=648.0,
        cold_capacity_rate=1040.0,
        set_point_temperature=300.15,
        cold_inlet_temperature=303.15,
        required_duty=1000.0,
    )

    assert result.maximum_duty_kw == 0.0
    assert result.limit_cause == "cold-inlet-above-set-point"


def test_cleaning_interval_shortens_with_residual_deposit() -> None:
    model = HeatExchangerFoulingModel()
    perfect = model.cleaning_interval(
        fouling_resistance_start=2.0e-5,
        fouling_resistance_end=8.0e-5,
        elapsed_days=180.0,
        fouling_resistance_limit=1.2e-4,
    )
    partial = model.cleaning_interval(
        fouling_resistance_start=2.0e-5,
        fouling_resistance_end=8.0e-5,
        elapsed_days=180.0,
        fouling_resistance_limit=1.2e-4,
        cleaning_residual_fraction=0.5,
    )

    assert perfect.fouling_rate_m2k_w_per_day == pytest.approx(6.0e-5 / 180.0)
    assert partial.achievable_cycle_days < perfect.achievable_cycle_days
    assert perfect.cleaning_effective is True


def test_ineffective_cleaning_is_reported_rather_than_a_shorter_interval() -> None:
    result = HeatExchangerFoulingModel().cleaning_interval(
        fouling_resistance_start=2.0e-5,
        fouling_resistance_end=2.0e-4,
        elapsed_days=180.0,
        fouling_resistance_limit=1.2e-4,
        cleaning_residual_fraction=0.9,
    )

    assert result.cleaning_effective is False
    assert result.achievable_cycle_days == 0.0
    assert any("cleaning method" in warning for warning in result.warnings)


def test_rejects_temperature_cross() -> None:
    case = dict(BASE_CASE)
    case["cold_outlet_temperature"] = 345.0

    with pytest.raises(ValueError, match="temperature cross"):
        HeatExchangerFoulingModel().evaluate(**case)


def test_rejects_a_hot_stream_that_does_not_cool() -> None:
    case = dict(BASE_CASE)
    case["hot_outlet_temperature"] = case["hot_inlet_temperature"] + 1.0

    with pytest.raises(ValueError, match="hot stream must cool"):
        HeatExchangerFoulingModel().evaluate(**case)


def test_rejects_a_single_film_coefficient() -> None:
    case = dict(BASE_CASE)
    case["hot_film_coefficient"] = 6000.0

    with pytest.raises(ValueError, match="both film coefficients"):
        HeatExchangerFoulingModel().evaluate(**case)
