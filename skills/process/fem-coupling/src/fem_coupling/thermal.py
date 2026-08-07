"""Turn a NeqSim fluid state into finite-element boundary conditions.

A finite-element model does not consume a fluid. It consumes a film coefficient, a
bulk temperature, a diffusivity and a length scale. Those numbers must come from
the actual fluid at the actual condition, because conductivity, heat capacity and
viscosity - and therefore the Nusselt number - move substantially with composition
and pressure. This module pulls them from a flashed NeqSim system (or accepts them
directly, so the skill stays usable without NeqSim installed) and derives the film
coefficient, the Biot and Fourier numbers, the thermal penetration depth, and the
element size and time step that follow from them.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, log, pi, sqrt
from typing import Any

_LAMINAR_REYNOLDS = 2300.0
_TURBULENT_REYNOLDS = 3000.0

# Fully developed laminar duct flow with a constant wall temperature.
_LAMINAR_NUSSELT = 3.66

# Above this Biot number the solid cannot be treated as a single lumped
# temperature and a through-thickness finite-element model is required.
_LUMPED_BIOT_LIMIT = 0.1

# Elements per thermal penetration depth needed before a transient front is
# resolved rather than smeared.
_ELEMENTS_PER_PENETRATION_DEPTH = 4.0

# Implicit time integration is unconditionally stable but a mesh Fourier number
# far above this smears the front the model was built to capture.
_MESH_FOURIER_TARGET = 0.5


@dataclass(frozen=True)
class FemFluidState:
    """Fluid properties at one point, normally taken from a NeqSim phase.

    ``diffusion_coefficients_m2_per_s`` carries per-component molecular
    diffusivities when a species-transport model is being set up; it is empty for
    a pure heat-transfer model.
    """

    name: str
    phase: str
    temperature_c: float
    pressure_bara: float | None
    density_kg_per_m3: float
    viscosity_pa_s: float
    thermal_conductivity_w_per_mk: float
    heat_capacity_j_per_kgk: float
    velocity_m_per_s: float | None = None
    diffusion_coefficients_m2_per_s: tuple[tuple[str, float], ...] = ()

    @property
    def prandtl(self) -> float:
        """Prandtl number ``cp mu / k``."""
        return (
            self.heat_capacity_j_per_kgk
            * self.viscosity_pa_s
            / self.thermal_conductivity_w_per_mk
        )

    @property
    def thermal_diffusivity_m2_per_s(self) -> float:
        """Fluid thermal diffusivity ``k / (rho cp)``."""
        return self.thermal_conductivity_w_per_mk / (
            self.density_kg_per_m3 * self.heat_capacity_j_per_kgk
        )

    def diffusion_coefficient(self, component: str) -> float | None:
        """Return the molecular diffusivity of a component, or ``None``."""
        key = (component or "").strip().lower()
        for name, value in self.diffusion_coefficients_m2_per_s:
            if name.lower() == key:
                return value
        return None


@dataclass(frozen=True)
class FilmCoefficient:
    """Convective film coefficient and the correlation it came from."""

    h_w_per_m2k: float
    reynolds: float
    prandtl: float
    nusselt: float
    correlation: str
    warnings: tuple[str, ...]
    assumptions: tuple[str, ...]


@dataclass(frozen=True)
class FemThermalConditions:
    """Boundary conditions, dimensionless groups and discretisation targets."""

    inner_film: FilmCoefficient | None
    inner_bulk_temperature_c: float
    outer_film_coefficient_w_per_m2k: float
    outer_bulk_temperature_c: float
    wall_thickness_m: float
    solid_conductivity_w_per_mk: float
    solid_thermal_diffusivity_m2_per_s: float
    biot: float
    lumped_capacitance_valid: bool
    penetration_depth_m: float | None
    max_element_size_m: float
    recommended_time_step_s: float | None
    fourier_number: float | None
    regime: str
    warnings: tuple[str, ...]
    assumptions: tuple[str, ...]


def fluid_state_from_neqsim(
    system: Any,
    *,
    phase: str = "gas",
    velocity_m_per_s: float | None = None,
    diffusing_components: tuple[str, ...] | list[str] | None = None,
    diffusion_model: str = "Fuller-Schettler-Giddings",
) -> FemFluidState:
    """Extract a :class:`FemFluidState` from a flashed NeqSim thermodynamic system.

    ``system`` is a NeqSim ``SystemInterface`` (or anything exposing the same phase
    accessors) that has already been flashed. Physical properties are initialised
    here because thermal conductivity and viscosity are otherwise returned as zero,
    which is the single most common cause of a nonsensical film coefficient.

    When ``diffusing_components`` is given, the effective diffusion coefficients are
    read as well, which is what a species-transport finite-element model needs.
    """
    for initialiser in ("initProperties", "initPhysicalProperties"):
        try:
            getattr(system, initialiser)()
        except Exception:  # pragma: no cover - depends on the NeqSim build in use
            continue

    wanted = (phase or "").strip().lower()
    selected = None
    available: list[str] = []
    for index in range(int(system.getNumberOfPhases())):
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

    diffusivities: list[tuple[str, float]] = []
    if diffusing_components:
        diffusivities = _read_diffusion_coefficients(
            selected, tuple(diffusing_components), diffusion_model
        )

    return FemFluidState(
        name=str(getattr(system, "getFluidName", lambda: "neqsim fluid")()),
        phase=wanted,
        temperature_c=float(selected.getTemperature()) - 273.15,
        pressure_bara=_optional_float(selected, "getPressure"),
        density_kg_per_m3=float(selected.getDensity("kg/m3")),
        viscosity_pa_s=float(selected.getViscosity("kg/msec")),
        thermal_conductivity_w_per_mk=float(selected.getThermalConductivity("W/mK")),
        heat_capacity_j_per_kgk=float(selected.getCp("J/kgK")),
        velocity_m_per_s=velocity_m_per_s,
        diffusion_coefficients_m2_per_s=tuple(diffusivities),
    )


def film_coefficient(
    fluid: FemFluidState,
    *,
    hydraulic_diameter_m: float,
    velocity_m_per_s: float | None = None,
    correlation: str = "auto",
    heating: bool = False,
) -> FilmCoefficient:
    """Internal forced-convection film coefficient from a NeqSim fluid state.

    ``correlation`` is ``gnielinski`` (the default choice above Re = 3000, valid
    over a far wider Prandtl range than Dittus-Boelter), ``dittus-boelter``, or
    ``auto`` which selects Gnielinski when turbulent and the fully developed
    laminar value below Re = 2300.
    """
    _require_positive("hydraulic_diameter_m", hydraulic_diameter_m)
    _require_positive("density", fluid.density_kg_per_m3)
    _require_positive("viscosity", fluid.viscosity_pa_s)
    _require_positive("thermal conductivity", fluid.thermal_conductivity_w_per_mk)
    _require_positive("heat capacity", fluid.heat_capacity_j_per_kgk)

    velocity = velocity_m_per_s if velocity_m_per_s is not None else fluid.velocity_m_per_s
    if velocity is None:
        raise ValueError(
            "supply velocity_m_per_s, or a FemFluidState carrying velocity_m_per_s"
        )
    _require_positive("velocity_m_per_s", velocity)

    reynolds = (
        fluid.density_kg_per_m3 * velocity * hydraulic_diameter_m / fluid.viscosity_pa_s
    )
    prandtl = fluid.prandtl

    warnings: list[str] = []
    assumptions: list[str] = [
        "Fully developed internal flow with a smooth wall; an entrance region, a "
        "bend or a fitting raises the local coefficient above this value.",
        "Properties are evaluated at the bulk condition, not at the film temperature.",
    ]

    choice = (correlation or "auto").strip().lower()
    if choice == "auto":
        choice = "laminar" if reynolds < _LAMINAR_REYNOLDS else "gnielinski"

    if choice == "laminar":
        nusselt = _LAMINAR_NUSSELT
        used = "laminar fully developed (Nu = 3.66, constant wall temperature)"
        if reynolds >= _LAMINAR_REYNOLDS:
            warnings.append(
                f"Reynolds number {reynolds:.0f} is not laminar; the fully developed "
                "laminar Nusselt number underestimates the film coefficient."
            )
    elif choice == "gnielinski":
        friction = (0.79 * log(reynolds) - 1.64) ** -2
        nusselt = (
            (friction / 8.0)
            * (reynolds - 1000.0)
            * prandtl
            / (1.0 + 12.7 * sqrt(friction / 8.0) * (prandtl ** (2.0 / 3.0) - 1.0))
        )
        used = "Gnielinski with the Petukhov friction factor"
        if reynolds < _TURBULENT_REYNOLDS:
            warnings.append(
                f"Reynolds number {reynolds:.0f} is below the Gnielinski validity "
                "limit of about 3000; the correlation is being extrapolated."
            )
    elif choice in {"dittus-boelter", "dittus_boelter"}:
        exponent = 0.4 if heating else 0.3
        nusselt = 0.023 * reynolds**0.8 * prandtl**exponent
        used = f"Dittus-Boelter (n = {exponent}, {'heating' if heating else 'cooling'})"
        if not 0.6 <= prandtl <= 160.0:
            warnings.append(
                f"Prandtl number {prandtl:.2f} is outside the Dittus-Boelter validity "
                "band 0.6-160; prefer Gnielinski."
            )
    else:
        raise ValueError(
            "correlation must be 'auto', 'gnielinski', 'dittus-boelter' or 'laminar'"
        )

    if nusselt <= 0.0:
        raise ValueError(
            f"correlation returned a non-physical Nusselt number ({nusselt:.3g}); "
            "check the Reynolds and Prandtl numbers"
        )

    if _LAMINAR_REYNOLDS <= reynolds < _TURBULENT_REYNOLDS:
        warnings.append(
            f"Reynolds number {reynolds:.0f} is transitional; the film coefficient is "
            "uncertain by a factor of order two and should be carried as a range."
        )

    return FilmCoefficient(
        h_w_per_m2k=nusselt * fluid.thermal_conductivity_w_per_mk / hydraulic_diameter_m,
        reynolds=reynolds,
        prandtl=prandtl,
        nusselt=nusselt,
        correlation=used,
        warnings=tuple(warnings),
        assumptions=tuple(assumptions),
    )


def derive_thermal_conditions(
    *,
    wall_thickness_m: float,
    solid_conductivity_w_per_mk: float,
    solid_thermal_diffusivity_m2_per_s: float,
    inner_film: FilmCoefficient | float,
    inner_bulk_temperature_c: float,
    outer_film_coefficient_w_per_m2k: float,
    outer_bulk_temperature_c: float,
    transient_duration_s: float | None = None,
) -> FemThermalConditions:
    """Derive the dimensionless groups and discretisation targets for a FEM model.

    ``wall_thickness_m`` is the conduction path length: for a multilayer pipe that
    is the full steel-plus-insulation build-up, because it is the whole build-up
    that decides whether the solid can be lumped.

    ``transient_duration_s`` is the time scale of interest - a cooldown window, a
    shutdown, a start-up ramp. Supplying it produces a thermal penetration depth,
    a mesh-independent element-size target and a time step.
    """
    _require_positive("wall_thickness_m", wall_thickness_m)
    _require_positive("solid_conductivity_w_per_mk", solid_conductivity_w_per_mk)
    _require_positive("solid_thermal_diffusivity_m2_per_s", solid_thermal_diffusivity_m2_per_s)
    _require_positive(
        "outer_film_coefficient_w_per_m2k", outer_film_coefficient_w_per_m2k
    )

    film = (
        inner_film
        if isinstance(inner_film, FilmCoefficient)
        else None
    )
    h_inner = film.h_w_per_m2k if film is not None else float(inner_film)
    _require_positive("inner film coefficient", h_inner)

    warnings: list[str] = []
    assumptions: list[str] = [
        "Biot number uses the full conduction path length, so a composite wall is "
        "judged on the whole build-up rather than on the metal alone.",
    ]

    # The controlling surface coefficient is the smaller of the two: it is the one
    # that limits the heat flow and therefore sets the internal gradient.
    controlling_h = min(h_inner, outer_film_coefficient_w_per_m2k)
    biot = controlling_h * wall_thickness_m / solid_conductivity_w_per_mk
    lumped_ok = biot < _LUMPED_BIOT_LIMIT
    if lumped_ok:
        warnings.append(
            f"Biot number {biot:.3f} is below {_LUMPED_BIOT_LIMIT}; the solid is very "
            "nearly isothermal through its thickness and a lumped-capacitance model "
            "would answer the question without a finite-element mesh."
        )

    penetration = None
    time_step = None
    fourier = None
    element_size = wall_thickness_m / 10.0
    assumptions.append(
        "Steady element-size target is one tenth of the conduction path, which "
        "resolves a linear-through-thickness profile with margin."
    )

    if transient_duration_s is not None:
        _require_positive("transient_duration_s", transient_duration_s)
        # Diffusive penetration depth: how far the front has moved after the time of
        # interest. Elements coarser than this cannot represent it.
        penetration = sqrt(solid_thermal_diffusivity_m2_per_s * transient_duration_s)
        element_size = min(element_size, penetration / _ELEMENTS_PER_PENETRATION_DEPTH)
        time_step = _MESH_FOURIER_TARGET * element_size**2 / solid_thermal_diffusivity_m2_per_s
        fourier = solid_thermal_diffusivity_m2_per_s * transient_duration_s / wall_thickness_m**2
        assumptions.append(
            "Transient element size resolves the penetration depth "
            "sqrt(alpha t) with at least "
            f"{_ELEMENTS_PER_PENETRATION_DEPTH:.0f} elements."
        )
        assumptions.append(
            "Time step targets a mesh Fourier number of "
            f"{_MESH_FOURIER_TARGET}; implicit integration is stable at any step, but "
            "a much larger one smears the front."
        )
        if penetration > wall_thickness_m:
            warnings.append(
                f"Penetration depth {penetration:.3g} m exceeds the wall thickness "
                f"{wall_thickness_m:.3g} m, so the far side responds within the window "
                "of interest; the far boundary condition now matters to the answer."
            )
        if fourier is not None and fourier > 1.0:
            warnings.append(
                f"Fourier number {fourier:.2f} exceeds one; the wall is effectively at "
                "steady state over this window and a transient solve adds little."
            )

    regime = "steady" if transient_duration_s is None else "transient"

    return FemThermalConditions(
        inner_film=film,
        inner_bulk_temperature_c=inner_bulk_temperature_c,
        outer_film_coefficient_w_per_m2k=outer_film_coefficient_w_per_m2k,
        outer_bulk_temperature_c=outer_bulk_temperature_c,
        wall_thickness_m=wall_thickness_m,
        solid_conductivity_w_per_mk=solid_conductivity_w_per_mk,
        solid_thermal_diffusivity_m2_per_s=solid_thermal_diffusivity_m2_per_s,
        biot=biot,
        lumped_capacitance_valid=lumped_ok,
        penetration_depth_m=penetration,
        max_element_size_m=element_size,
        recommended_time_step_s=time_step,
        fourier_number=fourier,
        regime=regime,
        warnings=tuple(warnings + list(film.warnings if film else ())),
        assumptions=tuple(assumptions),
    )


def effective_diffusivity(
    molecular_diffusivity_m2_per_s: float,
    *,
    porosity: float,
    tortuosity: float = 2.5,
) -> tuple[float, tuple[str, ...]]:
    """Porous-medium effective diffusivity ``D_eff = phi D / tau``.

    Returns the diffusivity and the assumptions behind it. The molecular value is
    the one NeqSim computes for the actual mixture; the porosity and tortuosity are
    rock properties and must come from core data, not from this function's default.
    """
    _require_positive("molecular_diffusivity_m2_per_s", molecular_diffusivity_m2_per_s)
    _require_positive("tortuosity", tortuosity)
    if not 0.0 < porosity < 1.0:
        raise ValueError("porosity is a fraction strictly between 0 and 1")

    assumptions = (
        "Effective diffusivity uses the porosity-over-tortuosity model D_eff = "
        "phi D / tau, which assumes single-phase saturation and no surface diffusion.",
        f"Tortuosity {tortuosity:g} is a screening value; core-derived values for the "
        "actual rock differ by a factor of two or more.",
        "Molecular diffusivity comes from the NeqSim mixture model, so it already "
        "reflects composition, temperature and pressure.",
    )
    return porosity * molecular_diffusivity_m2_per_s / tortuosity, assumptions


def hydraulic_diameter_annulus(outer_diameter_m: float, inner_diameter_m: float) -> float:
    """Hydraulic diameter of an annulus, ``D_o - D_i``."""
    _require_positive("outer_diameter_m", outer_diameter_m)
    _require_positive("inner_diameter_m", inner_diameter_m)
    if inner_diameter_m >= outer_diameter_m:
        raise ValueError("inner_diameter_m must be smaller than outer_diameter_m")
    return outer_diameter_m - inner_diameter_m


def surface_area_per_length(diameter_m: float) -> float:
    """Cylindrical surface area per unit length, ``pi D``."""
    _require_positive("diameter_m", diameter_m)
    return pi * diameter_m


def _read_diffusion_coefficients(
    phase: Any, components: tuple[str, ...], model: str
) -> list[tuple[str, float]]:
    """Read effective diffusion coefficients for named components from a phase."""
    try:
        properties = phase.getPhysicalProperties()
        properties.setDiffusionCoefficientModel(model)
        phase.initPhysicalProperties()
        properties.calcEffectiveDiffusionCoefficients()
    except Exception:  # pragma: no cover - depends on the NeqSim build in use
        return []

    values: list[tuple[str, float]] = []
    for component in components:
        try:
            values.append(
                (component, float(properties.getEffectiveDiffusionCoefficient(component)))
            )
        except Exception:  # pragma: no cover - component absent or model unsupported
            continue
    return values


def _optional_float(source: Any, accessor: str) -> float | None:
    try:
        value = float(getattr(source, accessor)())
    except Exception:  # pragma: no cover - accessor absent in this NeqSim build
        return None
    return value if isfinite(value) else None


def _require_positive(name: str, value: float | None) -> None:
    if value is None or not isfinite(float(value)) or float(value) <= 0.0:
        raise ValueError(f"{name} must be a finite positive number")
