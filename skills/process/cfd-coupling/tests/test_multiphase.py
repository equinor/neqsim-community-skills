import math

import pytest

from cfd_coupling import (
    FluidState,
    MeshSpec,
    MultiphaseState,
    VofOpenFoamCase,
    derive_multiphase_conditions,
    multiphase_state_from_neqsim,
    read_case_results,
)


class _FakePhase:
    def __init__(self, name, density, viscosity, volumetric):
        self._name = name
        self._density = density
        self._viscosity = viscosity
        self._volumetric = volumetric

    def getPhaseTypeName(self):
        return self._name

    def getDensity(self, unit):
        return self._density

    def getViscosity(self, unit):
        return self._viscosity

    def getTemperature(self):
        return 318.15

    def getPressure(self):
        return 65.0

    def getSoundSpeed(self):
        return 395.0

    def getFlowRate(self, unit):
        return {"m3/sec": self._volumetric, "kg/sec": self._volumetric * self._density}[unit]


class _FakeSystem:
    def __init__(self, phases, tension=0.012):
        self._phases = phases
        self._tension = tension
        self.properties_initialised = False

    def initProperties(self):
        self.properties_initialised = True

    def getNumberOfPhases(self):
        return len(self._phases)

    def getPhase(self, index):
        return self._phases[index]

    def getInterfacialTension(self, first, second):
        return self._tension


def wet_gas_system(liquid_flow=0.05):
    return _FakeSystem(
        [
            _FakePhase("gas", 52.4, 1.45e-5, 0.60),
            _FakePhase("oil", 720.0, 6.0e-4, liquid_flow),
        ]
    )


def state(dispersed_fraction=0.20, tension=0.012):
    return MultiphaseState(
        continuous=FluidState(
            name="wet gas",
            phase="gas",
            density_kg_per_m3=52.4,
            viscosity_pa_s=1.45e-5,
            pressure_bara=65.0,
            volumetric_flow_m3_per_s=(1.0 - dispersed_fraction),
        ),
        dispersed=FluidState(
            name="wet gas",
            phase="oil",
            density_kg_per_m3=720.0,
            viscosity_pa_s=6.0e-4,
            pressure_bara=65.0,
            volumetric_flow_m3_per_s=dispersed_fraction,
        ),
        interfacial_tension_n_per_m=tension,
        continuous_volume_fraction=1.0 - dispersed_fraction,
        dispersed_volume_fraction=dispersed_fraction,
    )


# ----------------------------------------------------------------- extraction


def test_largest_phase_is_continuous_by_default() -> None:
    result = multiphase_state_from_neqsim(wet_gas_system())

    assert result.continuous.phase == "gas"
    assert result.dispersed.phase == "oil"
    assert result.dispersed_volume_fraction == pytest.approx(0.05 / 0.65)
    assert result.interfacial_tension_n_per_m == pytest.approx(0.012)


def test_phases_can_be_named_when_geometry_decides() -> None:
    result = multiphase_state_from_neqsim(
        wet_gas_system(), continuous_phase="oil", dispersed_phase="gas"
    )

    assert result.continuous.phase == "oil"
    assert result.dispersed.phase == "gas"
    assert result.density_ratio == pytest.approx(52.4 / 720.0)


def test_single_phase_flash_is_redirected_to_the_single_phase_path() -> None:
    system = _FakeSystem([_FakePhase("gas", 52.4, 1.45e-5, 0.6)])

    with pytest.raises(ValueError, match="derive_boundary_conditions"):
        multiphase_state_from_neqsim(system)


def test_absent_phase_is_reported_with_what_is_available() -> None:
    with pytest.raises(ValueError, match="phases present: gas, oil"):
        multiphase_state_from_neqsim(wet_gas_system(), dispersed_phase="aqueous")


def test_missing_interfacial_tension_is_rejected_rather_than_defaulted() -> None:
    system = wet_gas_system()
    system._tension = float("nan")

    with pytest.raises(ValueError, match="interfacial tension"):
        multiphase_state_from_neqsim(system)


# ------------------------------------------------------------------- derived


def test_superficial_velocities_sum_to_the_mixture_velocity() -> None:
    conditions = derive_multiphase_conditions(state(), hydraulic_diameter_m=0.3048)

    area = math.pi * 0.3048**2 / 4.0
    assert conditions.superficial_continuous_velocity_m_per_s == pytest.approx(0.8 / area)
    assert conditions.superficial_dispersed_velocity_m_per_s == pytest.approx(0.2 / area)
    assert conditions.mixture_velocity_m_per_s == pytest.approx(1.0 / area)


def test_mixture_properties_use_the_no_slip_volume_average() -> None:
    conditions = derive_multiphase_conditions(state(0.25), hydraulic_diameter_m=0.3048)

    assert conditions.mixture_density_kg_per_m3 == pytest.approx(0.25 * 720.0 + 0.75 * 52.4)
    assert any("no-slip" in note for note in conditions.assumptions)


def test_weber_and_froude_come_from_the_mixture_and_the_interface() -> None:
    conditions = derive_multiphase_conditions(state(), hydraulic_diameter_m=0.3048)

    velocity = conditions.mixture_velocity_m_per_s
    assert conditions.weber == pytest.approx(52.4 * velocity**2 * 0.3048 / 0.012)
    assert conditions.froude == pytest.approx(velocity / math.sqrt(9.80665 * 0.3048))


def test_large_dispersed_fraction_selects_volume_of_fluid() -> None:
    conditions = derive_multiphase_conditions(state(0.30), hydraulic_diameter_m=0.3048)

    assert conditions.recommended_model == "vof"
    assert conditions.recommended_solver == "incompressibleVoF"


def test_dilute_dispersed_phase_selects_lagrangian_parcels() -> None:
    conditions = derive_multiphase_conditions(state(0.002), hydraulic_diameter_m=0.3048)

    assert conditions.recommended_model == "lagrangian"
    assert any("parcel" in warning for warning in conditions.warnings)


def test_supplied_flow_regime_overrides_the_fraction_rule() -> None:
    conditions = derive_multiphase_conditions(
        state(0.002), hydraulic_diameter_m=0.3048, flow_regime="stratified"
    )

    assert conditions.recommended_model == "vof"
    assert "stratified" in conditions.model_rationale


def test_missing_flow_regime_is_declared_as_a_weaker_basis() -> None:
    conditions = derive_multiphase_conditions(state(), hydraulic_diameter_m=0.3048)

    assert any("flow-regime screening" in note for note in conditions.assumptions)


def test_phases_without_a_flow_rate_are_rejected() -> None:
    bare = MultiphaseState(
        continuous=FluidState(name="g", phase="gas", density_kg_per_m3=52.4, viscosity_pa_s=1.4e-5),
        dispersed=FluidState(name="o", phase="oil", density_kg_per_m3=720.0, viscosity_pa_s=6e-4),
        interfacial_tension_n_per_m=0.012,
        continuous_volume_fraction=0.8,
        dispersed_volume_fraction=0.2,
    )

    with pytest.raises(ValueError, match="both phases need a volumetric flow"):
        derive_multiphase_conditions(bare, hydraulic_diameter_m=0.3)


# ------------------------------------------------------------------ VOF case


def vof_case(**overrides) -> VofOpenFoamCase:
    settings = dict(
        boundary=derive_multiphase_conditions(state(0.30), hydraulic_diameter_m=0.3048),
        mesh=MeshSpec(kind="pipe", diameter_m=0.3048, length_m=3.0),
        name="vof-test",
    )
    settings.update(overrides)
    return VofOpenFoamCase(**settings)


def test_vof_case_writes_the_two_phase_tree(tmp_path) -> None:
    case_dir = tmp_path / "case"
    written = vof_case().write(case_dir)

    for expected in (
        "0/alpha.oil",
        "0/U",
        "0/p_rgh",
        "constant/g",
        "constant/phaseProperties",
        "constant/physicalProperties.oil",
        "constant/physicalProperties.gas",
        "system/setFieldsDict",
        "system/blockMeshDict",
    ):
        assert expected in written
        assert (case_dir / expected).is_file()


def test_phase_properties_carry_both_neqsim_phases_and_the_tension(tmp_path) -> None:
    case_dir = tmp_path / "case"
    vof_case().write(case_dir)

    phase_text = (case_dir / "constant" / "phaseProperties").read_text()
    oil_text = (case_dir / "constant" / "physicalProperties.oil").read_text()
    gas_text = (case_dir / "constant" / "physicalProperties.gas").read_text()

    assert "phases          (oil gas);" in phase_text
    assert "sigma           0.012;" in phase_text
    assert "rho             720;" in oil_text
    assert "rho             52.4;" in gas_text


def test_alpha_inlet_is_the_flash_phase_split(tmp_path) -> None:
    case_dir = tmp_path / "case"
    case = vof_case()
    case.write(case_dir)

    alpha_text = (case_dir / "0" / "alpha.oil").read_text()
    assert f"{case.boundary.state.dispersed_volume_fraction:.8g}" in alpha_text


def test_vof_control_is_transient_and_courant_limited(tmp_path) -> None:
    case_dir = tmp_path / "case"
    vof_case().write(case_dir)

    control = (case_dir / "system" / "controlDict").read_text()
    schemes = (case_dir / "system" / "fvSchemes").read_text()
    assert "adjustTimeStep  yes;" in control
    assert "maxAlphaCo" in control
    assert "ddtSchemes      { default Euler; }" in schemes
    assert "Gauss vanLeer" in schemes


def test_vof_commands_initialise_the_field_before_solving() -> None:
    assert vof_case().commands() == (
        "blockMesh",
        "checkMesh -constant",
        "setFields",
        "foamRun",
        "foamToVTK -latestTime",
    )


def test_legacy_flavour_uses_interfoam_and_transport_properties(tmp_path) -> None:
    case_dir = tmp_path / "legacy"
    written = vof_case(flavour="legacy").write(case_dir)

    assert "constant/transportProperties" in written
    control = (case_dir / "system" / "controlDict").read_text()
    assert "application     interFoam;" in control
    assert "solver" not in control.split("functions")[0].replace("smoothSolver", "")


def test_building_vof_for_a_dilute_mist_is_refused_with_the_reason() -> None:
    dilute = derive_multiphase_conditions(state(0.002), hydraulic_diameter_m=0.3048)

    with pytest.raises(ValueError, match="recommended 'lagrangian'"):
        vof_case(boundary=dilute)


def test_an_unrecommended_model_can_be_forced_deliberately() -> None:
    dilute = derive_multiphase_conditions(state(0.002), hydraulic_diameter_m=0.3048)

    case = vof_case(boundary=dilute, allow_unrecommended_model=True)

    assert case.dispersed_name == "oil"


def test_outlet_phase_fraction_is_read_back_and_compared(tmp_path) -> None:
    path = tmp_path / "postProcessing" / "outletDispersedFraction" / "5"
    path.mkdir(parents=True)
    (path / "surfaceFieldValue.dat").write_text("# Time  areaAverage\n5  0.0125\n")

    results = read_case_results(tmp_path)

    assert results.outlet_dispersed_fraction == pytest.approx(0.0125)
    assert any("dispersed-phase fraction" in finding for finding in results.findings)
