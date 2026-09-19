import math

import pytest

from cfd_coupling import (
    C_MU,
    FluidState,
    derive_boundary_conditions,
    fluid_state_from_neqsim,
)


def gas_state(**overrides) -> FluidState:
    defaults = dict(
        name="wet gas",
        phase="gas",
        density_kg_per_m3=52.4,
        viscosity_pa_s=1.45e-5,
        speed_of_sound_m_per_s=395.0,
    )
    defaults.update(overrides)
    return FluidState(**defaults)


class _FakePhase:
    def __init__(self, name, density, viscosity, sound, volumetric):
        self._name = name
        self._density = density
        self._viscosity = viscosity
        self._sound = sound
        self._volumetric = volumetric

    def getPhaseTypeName(self):
        return self._name

    def getDensity(self, unit):
        assert unit == "kg/m3"
        return self._density

    def getViscosity(self, unit):
        assert unit == "kg/msec"
        return self._viscosity

    def getTemperature(self):
        return 318.15

    def getPressure(self):
        return 65.0

    def getSoundSpeed(self):
        return self._sound

    def getFlowRate(self, unit):
        return {"m3/sec": self._volumetric, "kg/sec": 33.3}[unit]


class _FakeSystem:
    def __init__(self, phases):
        self._phases = phases
        self.properties_initialised = False

    def initProperties(self):
        self.properties_initialised = True

    def getNumberOfPhases(self):
        return len(self._phases)

    def getPhase(self, index):
        return self._phases[index]


def test_kinematic_viscosity_is_the_property_openfoam_needs() -> None:
    state = gas_state()
    assert state.kinematic_viscosity_m2_per_s == pytest.approx(1.45e-5 / 52.4)


def test_velocity_follows_from_volumetric_flow_and_area() -> None:
    state = gas_state(volumetric_flow_m3_per_s=0.636)
    boundary = derive_boundary_conditions(state, hydraulic_diameter_m=0.3048)

    area = math.pi * 0.3048**2 / 4.0
    assert boundary.flow_area_m2 == pytest.approx(area)
    assert boundary.velocity_m_per_s == pytest.approx(0.636 / area)


def test_turbulence_inlet_state_is_internally_consistent() -> None:
    boundary = derive_boundary_conditions(
        gas_state(), hydraulic_diameter_m=0.3048, velocity_m_per_s=10.0
    )

    expected_k = 1.5 * (10.0 * boundary.turbulence_intensity) ** 2
    assert boundary.turbulent_kinetic_energy_m2_per_s2 == pytest.approx(expected_k)
    # omega and epsilon must describe the same turbulence state.
    assert boundary.specific_dissipation_1_per_s == pytest.approx(
        boundary.turbulent_dissipation_m2_per_s3 / (C_MU * expected_k)
    )
    assert boundary.turbulence_length_scale_m == pytest.approx(0.07 * 0.3048)


def test_high_mach_flags_compressibility_and_switches_solver() -> None:
    boundary = derive_boundary_conditions(
        gas_state(), hydraulic_diameter_m=0.10, velocity_m_per_s=200.0
    )

    assert boundary.mach == pytest.approx(200.0 / 395.0)
    assert boundary.compressibility == "compressible"
    assert boundary.recommended_solver == "compressibleFluid"
    assert any("Mach" in warning for warning in boundary.warnings)


def test_laminar_flow_disables_the_turbulence_model() -> None:
    boundary = derive_boundary_conditions(
        gas_state(density_kg_per_m3=900.0, viscosity_pa_s=0.5, speed_of_sound_m_per_s=1200.0),
        hydraulic_diameter_m=0.05,
        velocity_m_per_s=0.5,
    )

    assert boundary.flow_regime == "laminar"
    assert boundary.recommended_turbulence_model == "laminar"
    assert any("laminar" in warning for warning in boundary.warnings)


def test_missing_flow_information_is_rejected() -> None:
    with pytest.raises(ValueError, match="supply velocity_m_per_s"):
        derive_boundary_conditions(gas_state(), hydraulic_diameter_m=0.3)


def test_turbulence_intensity_must_be_a_fraction() -> None:
    with pytest.raises(ValueError, match="fraction, not a percentage"):
        derive_boundary_conditions(
            gas_state(),
            hydraulic_diameter_m=0.3,
            velocity_m_per_s=10.0,
            turbulence_intensity=5.0,
        )


def test_neqsim_extraction_selects_the_requested_phase_and_initialises_properties() -> None:
    system = _FakeSystem(
        [
            _FakePhase("gas", 52.4, 1.45e-5, 395.0, 0.64),
            _FakePhase("oil", 700.0, 5.0e-4, 1100.0, 0.01),
        ]
    )

    state = fluid_state_from_neqsim(system, phase="gas")

    assert system.properties_initialised
    assert state.density_kg_per_m3 == pytest.approx(52.4)
    assert state.volumetric_flow_m3_per_s == pytest.approx(0.64)


def test_requesting_an_absent_phase_names_what_is_available() -> None:
    system = _FakeSystem([_FakePhase("gas", 52.4, 1.45e-5, 395.0, 0.64)])

    with pytest.raises(ValueError, match="available phases: gas"):
        fluid_state_from_neqsim(system, phase="aqueous")
