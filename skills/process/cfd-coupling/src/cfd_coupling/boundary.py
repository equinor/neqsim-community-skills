"""Turn a NeqSim fluid state into CFD boundary conditions.

CFD needs density, viscosity, a velocity and a consistent turbulence inlet state.
Those numbers must come from the actual fluid at the actual condition, not from
water tables or a generic gas. This module pulls them from a flashed NeqSim system
(or accepts them directly, so the skill stays usable without NeqSim installed) and
derives the inlet turbulence quantities, the flow regime, the compressibility class
and the solver that follows from them.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, pi, sqrt
from typing import Any

# Standard k-epsilon model constant.
C_MU = 0.09

# Above this Mach number an incompressible solver is no longer defensible.
_COMPRESSIBLE_MACH = 0.3

# Turbulent length scale as a fraction of hydraulic diameter, standard practice.
_LENGTH_SCALE_FRACTION = 0.07

_LAMINAR_REYNOLDS = 2300.0
_TURBULENT_REYNOLDS = 4000.0


@dataclass(frozen=True)
class FluidState:
    """Fluid properties at one point, normally taken from a NeqSim phase."""

    name: str
    phase: str
    density_kg_per_m3: float
    viscosity_pa_s: float
    temperature_k: float | None = None
    pressure_bara: float | None = None
    speed_of_sound_m_per_s: float | None = None
    mass_flow_kg_per_s: float | None = None
    volumetric_flow_m3_per_s: float | None = None

    @property
    def kinematic_viscosity_m2_per_s(self) -> float:
        """Kinematic viscosity, the property an incompressible solver actually uses."""
        return self.viscosity_pa_s / self.density_kg_per_m3


@dataclass(frozen=True)
class CfdBoundaryConditions:
    """Inlet state, transport properties and solver class for a CFD case."""

    fluid: FluidState
    velocity_m_per_s: float
    hydraulic_diameter_m: float
    flow_area_m2: float
    reynolds: float
    mach: float | None
    flow_regime: str
    compressibility: str
    turbulence_intensity: float
    turbulence_length_scale_m: float
    turbulent_kinetic_energy_m2_per_s2: float
    turbulent_dissipation_m2_per_s3: float
    specific_dissipation_1_per_s: float
    recommended_turbulence_model: str
    recommended_solver: str
    warnings: tuple[str, ...]
    assumptions: tuple[str, ...]


def fluid_state_from_neqsim(system: Any, *, phase: str = "gas") -> FluidState:
    """Extract a :class:`FluidState` from a flashed NeqSim thermodynamic system.

    ``system`` is a NeqSim ``SystemInterface`` (or anything exposing the same phase
    accessors) that has already been flashed. ``initProperties`` is invoked here
    because transport properties are otherwise returned as zero, which is the most
    common cause of a nonsensical CFD viscosity.
    """
    try:
        system.initProperties()
    except Exception:  # pragma: no cover - depends on the NeqSim build in use
        pass

    wanted = (phase or "").strip().lower()
    phase_count = int(system.getNumberOfPhases())
    selected = None
    available: list[str] = []
    for index in range(phase_count):
        candidate = system.getPhase(index)
        name = str(candidate.getPhaseTypeName()).lower()
        available.append(name)
        if name == wanted:
            selected = candidate
            break

    if selected is None:
        raise ValueError(
            f"phase '{phase}' not present after the flash; available phases: "
            f"{', '.join(available) or 'none'}"
        )

    return FluidState(
        name=str(getattr(system, "getFluidName", lambda: "neqsim fluid")()),
        phase=wanted,
        density_kg_per_m3=float(selected.getDensity("kg/m3")),
        viscosity_pa_s=float(selected.getViscosity("kg/msec")),
        temperature_k=float(selected.getTemperature()),
        pressure_bara=float(selected.getPressure()),
        speed_of_sound_m_per_s=_optional_float(selected, "getSoundSpeed"),
        mass_flow_kg_per_s=_optional_flow(selected, "kg/sec"),
        volumetric_flow_m3_per_s=_optional_flow(selected, "m3/sec"),
    )


def derive_boundary_conditions(
    fluid: FluidState,
    *,
    hydraulic_diameter_m: float,
    flow_area_m2: float | None = None,
    velocity_m_per_s: float | None = None,
    volumetric_flow_m3_per_s: float | None = None,
    turbulence_intensity: float | None = None,
    turbulence_length_scale_m: float | None = None,
) -> CfdBoundaryConditions:
    """Derive inlet velocity, turbulence state and solver class for a CFD case.

    Supply the velocity directly, or a volumetric flow, or rely on the flow carried
    on the :class:`FluidState` itself. When ``flow_area_m2`` is omitted a circular
    cross-section of ``hydraulic_diameter_m`` is assumed.
    """
    _require_positive("hydraulic_diameter_m", hydraulic_diameter_m)
    _require_positive("density", fluid.density_kg_per_m3)
    _require_positive("viscosity", fluid.viscosity_pa_s)

    area = flow_area_m2 if flow_area_m2 is not None else pi * hydraulic_diameter_m**2 / 4.0
    _require_positive("flow_area_m2", area)

    warnings: list[str] = []
    assumptions: list[str] = [
        "Fluid properties come from the actual fluid at the actual condition; "
        "generic tables are not a substitute.",
    ]

    if velocity_m_per_s is None:
        flow = volumetric_flow_m3_per_s
        if flow is None:
            flow = fluid.volumetric_flow_m3_per_s
        if flow is None:
            raise ValueError(
                "supply velocity_m_per_s, volumetric_flow_m3_per_s, or a FluidState "
                "carrying volumetric_flow_m3_per_s"
            )
        _require_positive("volumetric flow", flow)
        velocity = flow / area
        assumptions.append(
            "Inlet velocity is the area-averaged bulk velocity from the volumetric "
            "flow; a uniform inlet profile is imposed."
        )
    else:
        _require_positive("velocity_m_per_s", velocity_m_per_s)
        velocity = velocity_m_per_s

    if flow_area_m2 is None:
        assumptions.append("A circular cross-section was assumed for the flow area.")

    reynolds = fluid.density_kg_per_m3 * velocity * hydraulic_diameter_m / fluid.viscosity_pa_s

    if reynolds < _LAMINAR_REYNOLDS:
        regime = "laminar"
        warnings.append(
            f"Reynolds number {reynolds:.0f} is laminar; a turbulence model and the "
            "turbulence inlet values below do not apply."
        )
    elif reynolds < _TURBULENT_REYNOLDS:
        regime = "transitional"
        warnings.append(
            f"Reynolds number {reynolds:.0f} is transitional; standard RANS models are "
            "calibrated for fully turbulent flow and will be unreliable here."
        )
    else:
        regime = "turbulent"

    if turbulence_intensity is None:
        # Fully developed pipe-flow correlation; only meaningful when turbulent.
        intensity = 0.16 * reynolds ** (-0.125) if reynolds >= _TURBULENT_REYNOLDS else 0.05
        assumptions.append(
            "Inlet turbulence intensity from the fully developed pipe correlation "
            "I = 0.16 Re^(-1/8); override it when the upstream fitting is known."
        )
    else:
        _require_positive("turbulence_intensity", turbulence_intensity)
        if turbulence_intensity > 1.0:
            raise ValueError("turbulence_intensity is a fraction, not a percentage")
        intensity = turbulence_intensity

    if turbulence_length_scale_m is None:
        length_scale = _LENGTH_SCALE_FRACTION * hydraulic_diameter_m
        assumptions.append(
            "Turbulent length scale taken as 0.07 x hydraulic diameter, the usual "
            "fully developed duct-flow value."
        )
    else:
        _require_positive("turbulence_length_scale_m", turbulence_length_scale_m)
        length_scale = turbulence_length_scale_m

    kinetic_energy = 1.5 * (velocity * intensity) ** 2
    dissipation = C_MU**0.75 * kinetic_energy**1.5 / length_scale
    specific_dissipation = dissipation / (C_MU * kinetic_energy)

    mach = None
    compressibility = "incompressible"
    if fluid.speed_of_sound_m_per_s and fluid.speed_of_sound_m_per_s > 0.0:
        mach = velocity / fluid.speed_of_sound_m_per_s
        if mach > _COMPRESSIBLE_MACH:
            compressibility = "compressible"
            warnings.append(
                f"Mach number {mach:.2f} exceeds {_COMPRESSIBLE_MACH}; density variation "
                "is significant and an incompressible solver is not defensible."
            )
    else:
        assumptions.append(
            "Speed of sound was not available, so compressibility could not be "
            "checked; confirm the Mach number before using an incompressible solver."
        )

    if regime == "laminar":
        turbulence_model = "laminar"
    else:
        turbulence_model = "kOmegaSST"
        assumptions.append(
            "k-omega SST is the default RANS choice for wall-bounded flow with "
            "adverse pressure gradients; it still under-predicts peaks in strongly "
            "separated or unsteady flow."
        )

    solver = "incompressibleFluid" if compressibility == "incompressible" else "compressibleFluid"

    return CfdBoundaryConditions(
        fluid=fluid,
        velocity_m_per_s=velocity,
        hydraulic_diameter_m=hydraulic_diameter_m,
        flow_area_m2=area,
        reynolds=reynolds,
        mach=mach,
        flow_regime=regime,
        compressibility=compressibility,
        turbulence_intensity=intensity,
        turbulence_length_scale_m=length_scale,
        turbulent_kinetic_energy_m2_per_s2=kinetic_energy,
        turbulent_dissipation_m2_per_s3=dissipation,
        specific_dissipation_1_per_s=specific_dissipation,
        recommended_turbulence_model=turbulence_model,
        recommended_solver=solver,
        warnings=tuple(warnings),
        assumptions=tuple(assumptions),
    )


def _optional_float(source: Any, method_name: str) -> float | None:
    method = getattr(source, method_name, None)
    if method is None:
        return None
    try:
        value = float(method())
    except Exception:  # pragma: no cover - property unavailable for this phase model
        return None
    return value if isfinite(value) and value > 0.0 else None


def _optional_flow(source: Any, unit: str) -> float | None:
    method = getattr(source, "getFlowRate", None)
    if method is None:
        return None
    try:
        value = float(method(unit))
    except Exception:  # pragma: no cover - flow not set on the system
        return None
    return value if isfinite(value) and value > 0.0 else None


def _require_positive(name: str, value: float) -> None:
    if not isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be a positive finite number")


def friction_velocity(fluid: FluidState, velocity_m_per_s: float, reynolds: float) -> float:
    """Friction velocity from Blasius smooth-wall friction, used for y+ sizing."""
    _require_positive("velocity", velocity_m_per_s)
    _require_positive("reynolds", reynolds)
    friction_factor = 64.0 / reynolds if reynolds < _LAMINAR_REYNOLDS else 0.3164 / reynolds**0.25
    return velocity_m_per_s * sqrt(friction_factor / 8.0)
