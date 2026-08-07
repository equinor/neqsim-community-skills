"""Turn a multiphase NeqSim flash into multiphase CFD boundary conditions.

A NeqSim flash already knows how much gas, oil and water there is, what each phase
weighs, how viscous it is and what the interfacial tension between them is. That is
exactly the input a multiphase CFD case needs, and it is the part most often
guessed at.

This module extracts both phases, derives the superficial and mixture quantities,
and screens which multiphase CFD model is defensible. That last step matters: a
volume-of-fluid solve on a dilute droplet mist wastes weeks, and a dispersed-phase
model on stratified flow answers the wrong question.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, pi, sqrt
from typing import Any

from .boundary import C_MU, FluidState

GRAVITY_M_PER_S2 = 9.80665

# Hinze's constant for the maximum stable droplet in turbulent break-up.
_HINZE_CONSTANT = 0.725

# Above this dispersed fraction the interface is large-scale and worth resolving.
_VOF_FRACTION = 0.10

# Below this dispersed fraction the phases are dilute enough to track as parcels.
_DILUTE_FRACTION = 0.01

# A Stokes number well below one means droplets follow the carrier flow.
_TRACER_STOKES = 0.1

_LIQUID_PHASES = ("oil", "aqueous", "liquid", "water", "wax")


@dataclass(frozen=True)
class MultiphaseState:
    """Two coexisting phases from one flash, plus the interface between them."""

    continuous: FluidState
    dispersed: FluidState
    interfacial_tension_n_per_m: float
    continuous_volume_fraction: float
    dispersed_volume_fraction: float

    @property
    def density_ratio(self) -> float:
        """Dispersed-to-continuous density ratio, which drives separation behaviour."""
        return self.dispersed.density_kg_per_m3 / self.continuous.density_kg_per_m3


@dataclass(frozen=True)
class MultiphaseBoundaryConditions:
    """Inlet state and model choice for a multiphase CFD case."""

    state: MultiphaseState
    hydraulic_diameter_m: float
    flow_area_m2: float
    superficial_continuous_velocity_m_per_s: float
    superficial_dispersed_velocity_m_per_s: float
    mixture_velocity_m_per_s: float
    mixture_density_kg_per_m3: float
    mixture_viscosity_pa_s: float
    mixture_reynolds: float
    weber: float
    froude: float
    max_stable_droplet_m: float
    stokes_number: float
    recommended_model: str
    recommended_solver: str
    model_rationale: str
    turbulent_kinetic_energy_m2_per_s2: float
    turbulent_dissipation_m2_per_s3: float
    specific_dissipation_1_per_s: float
    turbulence_intensity: float
    turbulence_length_scale_m: float
    warnings: tuple[str, ...]
    assumptions: tuple[str, ...]


def multiphase_state_from_neqsim(
    system: Any,
    *,
    continuous_phase: str | None = None,
    dispersed_phase: str | None = None,
) -> MultiphaseState:
    """Extract two phases and their interfacial tension from a flashed NeqSim system.

    By default the phase occupying the most volume is taken as continuous and the
    next largest as dispersed, which is what physically happens in a pipe. Name the
    phases explicitly when the geometry decides otherwise - for example the aqueous
    phase wetting the wall of an oil line.
    """
    try:
        system.initProperties()
    except Exception:  # pragma: no cover - depends on the NeqSim build in use
        pass

    phase_count = int(system.getNumberOfPhases())
    if phase_count < 2:
        raise ValueError(
            "a multiphase case needs at least two phases; the flash produced "
            f"{phase_count}. Use derive_boundary_conditions for single-phase flow."
        )

    entries = []
    for index in range(phase_count):
        phase = system.getPhase(index)
        name = str(phase.getPhaseTypeName()).lower()
        entries.append((name, index, _flow(phase, "m3/sec") or 0.0))

    available = ", ".join(name for name, _, _ in entries)
    ordered = sorted(entries, key=lambda entry: entry[2], reverse=True)

    continuous_entry = _select(ordered, continuous_phase, available, "continuous")
    remaining = [entry for entry in ordered if entry[1] != continuous_entry[1]]
    dispersed_entry = _select(remaining, dispersed_phase, available, "dispersed")

    total_volume = continuous_entry[2] + dispersed_entry[2]
    if total_volume <= 0.0:
        raise ValueError(
            "neither selected phase carries a volumetric flow; set a total flow rate "
            "on the fluid before flashing"
        )

    tension = _interfacial_tension(system, continuous_entry[1], dispersed_entry[1])

    return MultiphaseState(
        continuous=_state(system, continuous_entry),
        dispersed=_state(system, dispersed_entry),
        interfacial_tension_n_per_m=tension,
        continuous_volume_fraction=continuous_entry[2] / total_volume,
        dispersed_volume_fraction=dispersed_entry[2] / total_volume,
    )


def derive_multiphase_conditions(
    state: MultiphaseState,
    *,
    hydraulic_diameter_m: float,
    flow_area_m2: float | None = None,
    flow_regime: str | None = None,
    turbulence_intensity: float | None = None,
    turbulence_length_scale_m: float | None = None,
) -> MultiphaseBoundaryConditions:
    """Derive multiphase inlet quantities and screen which CFD model is defensible.

    Pass ``flow_regime`` from a dedicated flow-regime screening when it is known
    (``stratified``, ``slug``, ``annular``, ``bubble``, ``mist``); it overrides the
    fraction-based decision, which is the weaker of the two.
    """
    _require_positive("hydraulic_diameter_m", hydraulic_diameter_m)
    _require_positive("interfacial tension", state.interfacial_tension_n_per_m)

    area = flow_area_m2 if flow_area_m2 is not None else pi * hydraulic_diameter_m**2 / 4.0
    _require_positive("flow_area_m2", area)

    continuous_flow = state.continuous.volumetric_flow_m3_per_s
    dispersed_flow = state.dispersed.volumetric_flow_m3_per_s
    if not continuous_flow or not dispersed_flow:
        raise ValueError(
            "both phases need a volumetric flow; set a total flow rate on the fluid "
            "before flashing so the phase flows are defined"
        )

    superficial_continuous = continuous_flow / area
    superficial_dispersed = dispersed_flow / area
    mixture_velocity = superficial_continuous + superficial_dispersed

    fraction = state.dispersed_volume_fraction
    mixture_density = (
        fraction * state.dispersed.density_kg_per_m3
        + (1.0 - fraction) * state.continuous.density_kg_per_m3
    )
    mixture_viscosity = (
        fraction * state.dispersed.viscosity_pa_s
        + (1.0 - fraction) * state.continuous.viscosity_pa_s
    )
    reynolds = mixture_density * mixture_velocity * hydraulic_diameter_m / mixture_viscosity

    weber = (
        state.continuous.density_kg_per_m3
        * mixture_velocity**2
        * hydraulic_diameter_m
        / state.interfacial_tension_n_per_m
    )
    froude = mixture_velocity / sqrt(GRAVITY_M_PER_S2 * hydraulic_diameter_m)

    droplet = _hinze_diameter(state, mixture_velocity, hydraulic_diameter_m, reynolds)
    stokes = _stokes_number(state, droplet, mixture_velocity, hydraulic_diameter_m)

    intensity = (
        0.16 * reynolds ** (-0.125)
        if turbulence_intensity is None and reynolds >= 4000.0
        else (turbulence_intensity if turbulence_intensity is not None else 0.05)
    )
    length_scale = (
        turbulence_length_scale_m
        if turbulence_length_scale_m is not None
        else 0.07 * hydraulic_diameter_m
    )
    kinetic_energy = 1.5 * (mixture_velocity * intensity) ** 2
    dissipation = C_MU**0.75 * kinetic_energy**1.5 / length_scale

    model, solver, rationale = _recommend_model(fraction, stokes, flow_regime)

    warnings: list[str] = []
    if reynolds < 4000.0:
        warnings.append(
            f"Mixture Reynolds number {reynolds:.0f} is not fully turbulent; the "
            "turbulence inlet values and the break-up correlation do not apply."
        )
    if froude < 1.0 and flow_regime is None:
        warnings.append(
            f"Froude number {froude:.2f} is below one, so gravity dominates inertia and "
            "the phases will tend to separate. Confirm the flow regime before choosing "
            "a model on volume fraction alone."
        )
    if model == "euler_euler":
        warnings.append(
            "A dense dispersed phase needs an Euler-Euler model, which this skill does "
            "not generate. Specify it explicitly with a CFD engineer."
        )
    if model == "lagrangian":
        warnings.append(
            "A dilute dispersed phase is best handled as a single-phase carrier solve "
            "with Lagrangian parcels. This skill generates the carrier solve; the parcel "
            "cloud must be added separately."
        )

    assumptions = [
        "Phase properties, fractions and interfacial tension come from one NeqSim "
        "flash at the inlet condition; they change along the geometry.",
        "Mixture density and viscosity use the no-slip (homogeneous) volume-fraction "
        "average, so slip between the phases is not represented at the inlet.",
        "The maximum stable droplet follows the Hinze turbulent break-up correlation "
        "and is an order-of-magnitude estimate, not a measured distribution.",
    ]
    if flow_regime is None:
        assumptions.append(
            "No flow regime was supplied, so the model choice rests on volume fraction "
            "and Stokes number. A dedicated flow-regime screening is more reliable."
        )

    return MultiphaseBoundaryConditions(
        state=state,
        hydraulic_diameter_m=hydraulic_diameter_m,
        flow_area_m2=area,
        superficial_continuous_velocity_m_per_s=superficial_continuous,
        superficial_dispersed_velocity_m_per_s=superficial_dispersed,
        mixture_velocity_m_per_s=mixture_velocity,
        mixture_density_kg_per_m3=mixture_density,
        mixture_viscosity_pa_s=mixture_viscosity,
        mixture_reynolds=reynolds,
        weber=weber,
        froude=froude,
        max_stable_droplet_m=droplet,
        stokes_number=stokes,
        recommended_model=model,
        recommended_solver=solver,
        model_rationale=rationale,
        turbulent_kinetic_energy_m2_per_s2=kinetic_energy,
        turbulent_dissipation_m2_per_s3=dissipation,
        specific_dissipation_1_per_s=dissipation / (C_MU * kinetic_energy),
        turbulence_intensity=intensity,
        turbulence_length_scale_m=length_scale,
        warnings=tuple(warnings),
        assumptions=tuple(assumptions),
    )


def _recommend_model(
    dispersed_fraction: float, stokes: float, flow_regime: str | None
) -> tuple[str, str, str]:
    regime = (flow_regime or "").strip().lower()

    if regime in {"stratified", "slug", "wavy", "plug", "churn"}:
        return (
            "vof",
            "incompressibleVoF",
            f"A {regime} regime has a large-scale interface, which volume of fluid "
            "resolves directly.",
        )
    if regime in {"mist", "dispersed", "bubble"}:
        if dispersed_fraction <= _DILUTE_FRACTION or stokes < _TRACER_STOKES:
            return (
                "lagrangian",
                "incompressibleDenseParticleFluid",
                f"A {regime} regime at {100.0 * dispersed_fraction:.2f} % dispersed "
                "volume is dilute; parcels on a carrier solve are cheaper and more "
                "accurate than resolving every interface.",
            )
        return (
            "euler_euler",
            "multiphaseEuler",
            f"A {regime} regime at {100.0 * dispersed_fraction:.1f} % dispersed volume "
            "is too dense for parcels and has no resolvable interface.",
        )
    if regime == "annular":
        return (
            "vof",
            "incompressibleVoF",
            "Annular flow has a continuous wall film with a resolvable interface.",
        )

    if dispersed_fraction >= _VOF_FRACTION:
        return (
            "vof",
            "incompressibleVoF",
            f"Dispersed volume fraction {100.0 * dispersed_fraction:.1f} % is large "
            "enough that the interface is a resolvable feature.",
        )
    if dispersed_fraction <= _DILUTE_FRACTION or stokes < _TRACER_STOKES:
        return (
            "lagrangian",
            "incompressibleDenseParticleFluid",
            f"Dispersed volume fraction {100.0 * dispersed_fraction:.2f} % with Stokes "
            f"number {stokes:.3g} is dilute and largely follows the carrier flow.",
        )
    return (
        "euler_euler",
        "multiphaseEuler",
        f"Dispersed volume fraction {100.0 * dispersed_fraction:.1f} % sits between the "
        "dilute and interface-resolving limits.",
    )


def _hinze_diameter(
    state: MultiphaseState, velocity: float, diameter: float, reynolds: float
) -> float:
    """Maximum stable droplet diameter from turbulent break-up (Hinze, 1955)."""
    friction_factor = 64.0 / reynolds if reynolds < 2300.0 else 0.3164 / reynolds**0.25
    # Turbulent energy dissipation rate per unit mass in a duct.
    dissipation = friction_factor * velocity**3 / (2.0 * diameter)
    if dissipation <= 0.0:
        return float("nan")
    return (
        _HINZE_CONSTANT
        * (state.interfacial_tension_n_per_m / state.continuous.density_kg_per_m3) ** 0.6
        * dissipation ** (-0.4)
    )


def _stokes_number(
    state: MultiphaseState, droplet: float, velocity: float, diameter: float
) -> float:
    """Droplet response time relative to the flow time scale."""
    if not isfinite(droplet) or droplet <= 0.0:
        return float("nan")
    relaxation = (
        state.dispersed.density_kg_per_m3 * droplet**2 / (18.0 * state.continuous.viscosity_pa_s)
    )
    return relaxation * velocity / diameter


def _select(entries, requested, available, role):
    if requested is None:
        if not entries:
            raise ValueError(f"no phase left to act as the {role} phase")
        return entries[0]
    wanted = requested.strip().lower()
    for entry in entries:
        if entry[0] == wanted:
            return entry
    raise ValueError(f"{role} phase '{requested}' not available; phases present: {available}")


def _state(system: Any, entry) -> FluidState:
    name, index, volumetric = entry
    phase = system.getPhase(index)
    return FluidState(
        name=str(getattr(system, "getFluidName", lambda: "neqsim fluid")()),
        phase=name,
        density_kg_per_m3=float(phase.getDensity("kg/m3")),
        viscosity_pa_s=float(phase.getViscosity("kg/msec")),
        temperature_k=float(phase.getTemperature()),
        pressure_bara=float(phase.getPressure()),
        speed_of_sound_m_per_s=_optional(phase, "getSoundSpeed"),
        mass_flow_kg_per_s=_flow(phase, "kg/sec"),
        volumetric_flow_m3_per_s=volumetric or None,
    )


def _interfacial_tension(system: Any, first: int, second: int) -> float:
    getter = getattr(system, "getInterfacialTension", None)
    if getter is None:
        raise ValueError("the supplied system does not expose getInterfacialTension")
    value = float(getter(first, second))
    if not isfinite(value) or value <= 0.0:
        raise ValueError(
            "NeqSim returned no interfacial tension for this phase pair; the surface "
            "tension model may not cover it. Supply the value explicitly."
        )
    return value


def _flow(phase: Any, unit: str) -> float | None:
    method = getattr(phase, "getFlowRate", None)
    if method is None:
        return None
    try:
        value = float(method(unit))
    except Exception:  # pragma: no cover - flow not set on the system
        return None
    return value if isfinite(value) and value > 0.0 else None


def _optional(phase: Any, method_name: str) -> float | None:
    method = getattr(phase, method_name, None)
    if method is None:
        return None
    try:
        value = float(method())
    except Exception:  # pragma: no cover - property unavailable for this phase model
        return None
    return value if isfinite(value) and value > 0.0 else None


def _require_positive(name: str, value: float) -> None:
    if not isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be a positive finite number")
