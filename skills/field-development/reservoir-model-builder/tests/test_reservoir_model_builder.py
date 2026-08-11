import math

import pytest

from reservoir_model_builder import (
    Parameter,
    ReservoirInputs,
    ReservoirModelBuilder,
    build_reservoir_model,
    summarize,
)


def test_headline_only_model_backs_out_in_place_volume() -> None:
    model = build_reservoir_model(
        field_name="Headline Gas",
        fluid_type="gas",
        datum_depth_m_tvdmsl=2500.0,
        recoverable_gas_Sm3=30.0e9,
    )

    assert model.data_tier == "tier-1-public-volumetric"
    assert model.volumetrics.recoverable_gas_Sm3 == pytest.approx(30.0e9)
    # GIIP = recoverable / RF, with the analogue depletion-drive recovery factor.
    assert model.volumetrics.giip_Sm3 == pytest.approx(30.0e9 / 0.75)
    assert model.parameters["recovery_factor"].provenance == "analogue"


def test_hydrostatic_pressure_and_geothermal_temperature_defaults() -> None:
    model = build_reservoir_model(
        field_name="Depth Only",
        fluid_type="oil",
        sea_area="barents_sea",
        datum_depth_m_tvdmsl=700.0,
        water_depth_m=400.0,
        recoverable_oil_Sm3=1.0e6,
    )

    pressure = model.parameters["initial_pressure_bara"]
    temperature = model.parameters["reservoir_temperature_C"]
    assert pressure.value == pytest.approx(1.01325 + 0.1050 * 700.0, abs=0.01)
    assert pressure.provenance == "derived"
    # 4 degC seabed plus 33 degC/km over the 300 m below the seabed.
    assert temperature.value == pytest.approx(4.0 + 33.0 * 0.3, abs=0.05)


def test_volumetric_calculation_from_geometry() -> None:
    model = build_reservoir_model(
        field_name="Geometry Oil",
        fluid_type="oil",
        area_km2=20.0,
        net_pay_m=30.0,
        porosity=0.30,
        water_saturation=0.20,
        oil_formation_volume_factor=1.20,
        initial_pressure_bara=200.0,
        reservoir_temperature_C=80.0,
        provenance="interpreted",
    )

    expected_hcpv = 20.0e6 * 30.0 * 0.30 * 0.80
    assert model.volumetrics.hydrocarbon_pore_volume_rm3 == pytest.approx(expected_hcpv)
    assert model.volumetrics.stoiip_Sm3 == pytest.approx(expected_hcpv / 1.20)
    assert model.volumetrics.reservoir_oil_volume_rm3 == pytest.approx(expected_hcpv)


def test_net_pay_is_not_multiplied_by_net_to_gross_twice() -> None:
    with_net_pay = build_reservoir_model(
        field_name="A",
        fluid_type="oil",
        area_km2=10.0,
        net_pay_m=20.0,
        net_to_gross=0.5,
        gross_thickness_m=40.0,
        porosity=0.25,
        water_saturation=0.25,
        initial_pressure_bara=250.0,
        reservoir_temperature_C=90.0,
    )
    with_gross = build_reservoir_model(
        field_name="B",
        fluid_type="oil",
        area_km2=10.0,
        gross_thickness_m=40.0,
        net_to_gross=0.5,
        porosity=0.25,
        water_saturation=0.25,
        initial_pressure_bara=250.0,
        reservoir_temperature_C=90.0,
    )

    assert with_net_pay.volumetrics.hydrocarbon_pore_volume_rm3 == pytest.approx(
        with_gross.volumetrics.hydrocarbon_pore_volume_rm3
    )
    assert any("double-counting" in warning for warning in with_net_pay.warnings)


def test_gas_formation_volume_factor_follows_real_gas_law() -> None:
    model = build_reservoir_model(
        field_name="Gas Bg",
        fluid_type="gas",
        giip_Sm3=50.0e9,
        initial_pressure_bara=300.0,
        reservoir_temperature_C=100.0,
        gas_compressibility_factor=0.95,
    )

    expected = 1.01325 * 0.95 * 373.15 / (288.15 * 300.0)
    assert model.parameters["gas_formation_volume_factor"].value == pytest.approx(expected)
    assert model.volumetrics.reservoir_gas_volume_rm3 == pytest.approx(50.0e9 * expected)


def test_productivity_index_from_darcy_and_derived_well_count() -> None:
    model = build_reservoir_model(
        field_name="Darcy Oil",
        fluid_type="oil",
        area_km2=25.0,
        net_pay_m=40.0,
        porosity=0.28,
        water_saturation=0.25,
        permeability_mD=500.0,
        oil_viscosity_cP=1.0,
        oil_formation_volume_factor=1.2,
        skin_factor=0.0,
        drainage_radius_m=500.0,
        wellbore_radius_m=0.108,
        initial_pressure_bara=200.0,
        reservoir_temperature_C=80.0,
        target_plateau_rate_Sm3_per_day=20000.0,
        provenance="measured",
    )

    pi = model.parameters["productivity_index_Sm3_per_day_bar"]
    re_over_rw = 500.0 / 0.108
    expected = 0.05357 * 500.0 * 40.0 / (1.0 * 1.2 * (math.log(re_over_rw) - 0.75))
    assert pi.value == pytest.approx(expected, rel=1e-9)

    per_well = pi.value * model.parameters["design_drawdown_bar"].value
    assert model.get("producer_count") == math.ceil(20000.0 / per_well)


def test_missing_deliverability_is_flagged_not_invented() -> None:
    model = build_reservoir_model(
        field_name="No Flow Data",
        fluid_type="gas",
        giip_Sm3=10.0e9,
        initial_pressure_bara=250.0,
        reservoir_temperature_C=90.0,
    )

    assert model.get("productivity_index_Sm3_per_day_bar") == 0.0
    assert any("productivity index" in warning for warning in model.warnings)
    assert model.get("producer_count") == 1


def test_drive_mechanism_inference_and_recovery_factor() -> None:
    aquifer_gas = build_reservoir_model(
        field_name="Aquifer Gas",
        fluid_type="gas",
        giip_Sm3=1.0e9,
        initial_pressure_bara=250.0,
        reservoir_temperature_C=90.0,
        aquifer_strength="strong",
    )
    injected_oil = build_reservoir_model(
        field_name="Injected Oil",
        fluid_type="oil",
        stoiip_Sm3=1.0e7,
        initial_pressure_bara=250.0,
        reservoir_temperature_C=90.0,
        injection_plan="water_injection",
    )

    assert aquifer_gas.drive_mechanism == "water_drive"
    assert aquifer_gas.parameters["recovery_factor"].value == pytest.approx(0.60)
    assert injected_oil.drive_mechanism == "water_injection"
    assert injected_oil.parameters["recovery_factor"].value == pytest.approx(0.45)
    assert injected_oil.get("injector_count") == injected_oil.get("producer_count")


def test_neqsim_spec_uses_reservoir_volumes_and_quadratic_production_index() -> None:
    model = build_reservoir_model(
        field_name="Spec Gas",
        fluid_type="gas",
        giip_Sm3=20.0e9,
        initial_pressure_bara=300.0,
        reservoir_temperature_C=100.0,
        gas_compressibility_factor=0.9,
        productivity_index_Sm3_per_day_bar=50000.0,
        target_plateau_rate_Sm3_per_day=10.0e6,
        fluid_composition={"methane": 0.9, "ethane": 0.07, "propane": 0.03},
    )
    spec = model.neqsim_spec

    bg = model.parameters["gas_formation_volume_factor"].value
    assert spec["gasVolume_Sm3"] == pytest.approx(20.0e9 * bg)
    assert spec["volumeBasis"].startswith("reservoir m3")
    assert spec["standardConditionVolumes"]["giip_Sm3"] == pytest.approx(20.0e9)
    assert spec["components"] == {"methane": 0.9, "ethane": 0.07, "propane": 0.03}
    assert len(spec["producers"]) == int(model.get("producer_count"))

    drawdown = model.parameters["design_drawdown_bar"].value
    pwf = 300.0 - drawdown
    per_well = 50000.0 * drawdown
    assert spec["wellModel"]["neqsimWellProductionIndex_MSm3_per_day_bar2"] == pytest.approx(
        (per_well / 1.0e6) / (300.0**2 - pwf**2)
    )


def test_refinement_plan_is_ranked_and_actionable() -> None:
    model = build_reservoir_model(
        field_name="Sparse",
        fluid_type="oil",
        datum_depth_m_tvdmsl=2000.0,
        recoverable_oil_Sm3=5.0e6,
    )

    names = [item.parameter for item in model.refinement_plan]
    assert "area_km2" in names
    assert "permeability_mD" in names
    scores = [item.priority_score for item in model.refinement_plan]
    assert scores == sorted(scores, reverse=True)
    assert all(item.acquisition_route for item in model.refinement_plan)


def test_refine_upgrades_provenance_tier_and_reports_changes() -> None:
    coarse = build_reservoir_model(
        field_name="Refinable",
        fluid_type="oil",
        datum_depth_m_tvdmsl=2000.0,
        recoverable_oil_Sm3=5.0e6,
    )
    refined = coarse.refine(
        {
            "area_km2": 12.0,
            "net_pay_m": 25.0,
            "porosity": 0.27,
            "water_saturation": 0.22,
            "permeability_mD": 800.0,
            "oil_formation_volume_factor": 1.18,
            "aquifer_strength": "moderate",
        },
        provenance="measured",
        reference="appraisal well logs and DST",
    )

    assert coarse.completeness < refined.completeness
    assert refined.data_tier == "tier-3-static-model"
    changed = {change["parameter"] for change in refined.changes}
    assert {"porosity", "water_saturation", "area_km2"} <= changed
    assert refined.parameters["porosity"].provenance == "measured"
    assert len(refined.refinement_plan) < len(coarse.refinement_plan)


def test_refine_keeps_the_provenance_of_earlier_data_sources() -> None:
    public = build_reservoir_model(
        field_name="Layered Sources",
        fluid_type="oil",
        datum_depth_m_tvdmsl=1800.0,
        recoverable_oil_Sm3=6.0e6,
        provenance="public-reported",
        reference="public resource statement",
    )
    with_analogue = public.refine(
        {"porosity": 0.28, "water_saturation": 0.24},
        provenance="analogue",
        reference="analogue field in the same play",
    )
    with_logs = with_analogue.refine(
        {"porosity": 0.31, "area_km2": 14.0},
        provenance="measured",
        reference="appraisal well logs",
    )

    assert with_logs.parameters["water_saturation"].provenance == "analogue"
    assert with_logs.parameters["porosity"].provenance == "measured"
    assert with_logs.parameters["porosity"].reference == "appraisal well logs"
    assert with_logs.parameters["area_km2"].provenance == "measured"


def test_cold_and_shallow_reservoir_raises_engineering_warnings() -> None:
    model = build_reservoir_model(
        field_name="Cold Shallow",
        fluid_type="oil",
        sea_area="barents_sea",
        datum_depth_m_tvdmsl=650.0,
        water_depth_m=400.0,
        recoverable_oil_Sm3=8.0e6,
    )

    joined = " ".join(model.warnings)
    assert "hydrate" in joined
    assert "Shallow reservoirs" in joined


def test_build_requires_a_way_to_size_the_reservoir() -> None:
    with pytest.raises(ValueError, match="cannot size the reservoir"):
        build_reservoir_model(
            field_name="Nothing",
            fluid_type="oil",
            initial_pressure_bara=200.0,
            reservoir_temperature_C=80.0,
        )


def test_build_requires_pressure_or_depth() -> None:
    with pytest.raises(ValueError, match="initial_pressure_bara or datum_depth"):
        build_reservoir_model(field_name="No Conditions", stoiip_Sm3=1.0e6)


def test_invalid_inputs_are_rejected() -> None:
    with pytest.raises(ValueError, match="fluid_type"):
        ReservoirInputs(field_name="X", fluid_type="steam")
    with pytest.raises(ValueError, match="aquifer_strength"):
        ReservoirInputs(field_name="X", aquifer_strength="enormous")
    with pytest.raises(ValueError, match="provenance"):
        Parameter(name="x", value=1.0, unit="-", provenance="guess")


def test_refine_rejects_unknown_fields() -> None:
    model = build_reservoir_model(
        field_name="X", fluid_type="oil", stoiip_Sm3=1.0e6, initial_pressure_bara=200.0,
        reservoir_temperature_C=80.0,
    )
    with pytest.raises(ValueError, match="unknown input field"):
        model.refine({"not_a_field": 1.0})


def test_summary_is_human_readable() -> None:
    model = build_reservoir_model(
        field_name="Summary Field",
        fluid_type="gas",
        giip_Sm3=15.0e9,
        initial_pressure_bara=280.0,
        reservoir_temperature_C=95.0,
    )
    text = summarize(model)

    assert "Summary Field" in text
    assert "data tier" in text
    assert "next data to acquire" in text


def test_builder_is_reusable_across_fields() -> None:
    builder = ReservoirModelBuilder()
    first = builder.build(
        ReservoirInputs(
            field_name="One", fluid_type="gas", giip_Sm3=1.0e9,
            initial_pressure_bara=200.0, reservoir_temperature_C=80.0,
        )
    )
    second = builder.build(
        ReservoirInputs(
            field_name="Two", fluid_type="oil", stoiip_Sm3=2.0e6,
            initial_pressure_bara=300.0, reservoir_temperature_C=110.0,
        )
    )

    assert first.field_name == "One"
    assert second.field_name == "Two"
    assert first.parameters is not second.parameters
