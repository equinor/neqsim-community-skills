"""Convert a finite-element temperature field into thermal and pressure stress.

The reason a thermal finite-element model is run at all is usually not the
temperature - it is what the temperature does to the steel. This module closes
that loop: it turns a through-wall temperature difference into a thermal stress,
adds the Lame pressure stress, combines them, and compares the result against an
allowable with the right stress category attached.

The category matters more than the number. Pressure stress is primary: it does not
relax, and if it exceeds the allowable the wall fails. Restrained-expansion and
through-wall-gradient stresses are secondary: they are displacement-controlled and
self-limiting, so they are assessed against a range allowable (of order 3S) and
against fatigue, not against the primary membrane allowable. Comparing a thermal
stress with a primary allowable is the most common way to condemn a wall that is
perfectly acceptable - or to pass one that will crack in cyclic service.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt

from .materials import SolidMaterial

# Utilisation above this is acceptable but should be reported explicitly.
_REVIEW_UTILISATION = 0.90

# Secondary (self-limiting) stresses are assessed against a range allowable that is
# conventionally three times the primary membrane allowable.
_SECONDARY_ALLOWABLE_FACTOR = 3.0

_RESTRAINTS = ("free", "axial", "biaxial", "through_wall_gradient")


@dataclass(frozen=True)
class PressureStressResult:
    """Lame thick-wall stresses at one radius."""

    radius_m: float
    hoop_pa: float
    radial_pa: float
    axial_pa: float
    von_mises_pa: float
    thin_wall_hoop_pa: float
    thick_wall_required: bool
    assumptions: tuple[str, ...]


@dataclass(frozen=True)
class ThermalStressResult:
    """Combined thermal and pressure stress with its category and utilisation."""

    location: str
    delta_temperature_k: float
    thermal_stress_pa: float
    restraint: str
    stress_category: str
    pressure: PressureStressResult | None
    combined_von_mises_pa: float
    allowable_pa: float | None
    utilisation: float | None
    verdict: str
    warnings: tuple[str, ...]
    assumptions: tuple[str, ...]


def thermal_stress(
    material: SolidMaterial,
    *,
    delta_temperature_k: float,
    restraint: str = "axial",
) -> float:
    """Stress produced by preventing a temperature change from becoming strain.

    ``restraint`` is:

    ``free``
        Nothing restrains the expansion - zero stress. Included so the case can be
        stated rather than assumed away.
    ``axial``
        Uniaxial full restraint, ``E alpha dT``. A buried or anchored pipe run
        heated above its installation temperature.
    ``biaxial``
        Full restraint in both in-plane directions, ``E alpha dT / (1 - nu)``. A
        shell or a plate restrained by surrounding structure.
    ``through_wall_gradient``
        The self-equilibrating bending stress from a linear temperature difference
        across the wall, ``E alpha dT / (2 (1 - nu))``. This is the one a thermal
        finite-element model exists to produce, and ``delta_temperature_k`` is then
        the inner-to-outer wall temperature difference, not the process-to-ambient
        difference.
    """
    key = (restraint or "").strip().lower()
    if key not in _RESTRAINTS:
        raise ValueError("restraint must be one of " + ", ".join(_RESTRAINTS))
    _require_finite("delta_temperature_k", delta_temperature_k)

    if key == "free":
        return 0.0
    if material.youngs_modulus_pa is None or material.thermal_expansion_1_per_k is None:
        raise ValueError(
            f"material '{material.name}' carries no modulus or expansion coefficient; "
            "a thermal stress cannot be computed from it"
        )

    base = (
        material.youngs_modulus_pa
        * material.thermal_expansion_1_per_k
        * abs(delta_temperature_k)
    )
    if key == "axial":
        return base
    if material.poisson_ratio is None:
        raise ValueError(
            f"material '{material.name}' carries no Poisson ratio; a biaxial or "
            "through-wall thermal stress cannot be computed from it"
        )
    if key == "biaxial":
        return base / (1.0 - material.poisson_ratio)
    return base / (2.0 * (1.0 - material.poisson_ratio))


def pressure_stress(
    *,
    inner_radius_m: float,
    outer_radius_m: float,
    internal_pressure_pa: float,
    external_pressure_pa: float = 0.0,
    at_radius_m: float | None = None,
    closed_ends: bool = True,
) -> PressureStressResult:
    """Lame thick-wall pressure stresses, evaluated at a radius.

    Defaults to the bore, where the hoop stress is highest. The thin-wall hoop
    stress is reported alongside so the difference is visible: below a
    diameter-to-thickness ratio of about 20 the thin-wall value understates the
    bore stress and the thick-wall solution is the one to use.
    """
    _require_positive("inner_radius_m", inner_radius_m)
    _require_positive("outer_radius_m", outer_radius_m)
    if outer_radius_m <= inner_radius_m:
        raise ValueError("outer_radius_m must exceed inner_radius_m")
    radius = inner_radius_m if at_radius_m is None else float(at_radius_m)
    if not inner_radius_m <= radius <= outer_radius_m:
        raise ValueError("at_radius_m must lie inside the wall")

    a2 = inner_radius_m**2
    b2 = outer_radius_m**2
    span = b2 - a2
    membrane = (internal_pressure_pa * a2 - external_pressure_pa * b2) / span
    varying = (internal_pressure_pa - external_pressure_pa) * a2 * b2 / (span * radius**2)

    hoop = membrane + varying
    radial = membrane - varying
    axial = membrane if closed_ends else 0.0

    thickness = outer_radius_m - inner_radius_m
    mean_diameter = inner_radius_m + outer_radius_m
    thin_wall = (internal_pressure_pa - external_pressure_pa) * mean_diameter / (
        2.0 * thickness
    )
    ratio = 2.0 * outer_radius_m / thickness

    return PressureStressResult(
        radius_m=radius,
        hoop_pa=hoop,
        radial_pa=radial,
        axial_pa=axial,
        von_mises_pa=von_mises(hoop, radial, axial),
        thin_wall_hoop_pa=thin_wall,
        thick_wall_required=ratio < 20.0,
        assumptions=(
            "Lame solution for a homogeneous, isotropic, elastic thick cylinder far "
            "from an end, a nozzle or a discontinuity.",
            "Closed-end axial stress is included by default; an expansion loop, a "
            "bellows or a sliding joint removes it.",
            "No allowance for corrosion, mill tolerance or weld strength reduction.",
        ),
    )


def von_mises(sigma_1: float, sigma_2: float, sigma_3: float = 0.0) -> float:
    """Von Mises equivalent stress from three principal stresses."""
    return sqrt(
        0.5
        * (
            (sigma_1 - sigma_2) ** 2
            + (sigma_2 - sigma_3) ** 2
            + (sigma_3 - sigma_1) ** 2
        )
    )


def evaluate_wall_stress(
    material: SolidMaterial,
    *,
    location: str,
    inner_wall_temperature_c: float,
    outer_wall_temperature_c: float,
    restraint: str = "through_wall_gradient",
    inner_radius_m: float | None = None,
    outer_radius_m: float | None = None,
    internal_pressure_pa: float | None = None,
    external_pressure_pa: float = 0.0,
    allowable_stress_pa: float | None = None,
) -> ThermalStressResult:
    """Combine the finite-element temperature drop with pressure into a verdict.

    ``inner_wall_temperature_c`` and ``outer_wall_temperature_c`` are the metal
    surface temperatures the conduction model produced - not the process and
    ambient temperatures. The distinction matters: for a well-insulated line most
    of the temperature difference falls across the insulation, so the steel
    gradient, and therefore the thermal stress, is a small fraction of what the
    process-to-ambient difference would suggest.
    """
    if not location or not location.strip():
        raise ValueError("location must be a non-empty label")
    delta = inner_wall_temperature_c - outer_wall_temperature_c
    thermal = thermal_stress(material, delta_temperature_k=delta, restraint=restraint)

    pressure = None
    if internal_pressure_pa is not None:
        if inner_radius_m is None or outer_radius_m is None:
            raise ValueError(
                "supply inner_radius_m and outer_radius_m with internal_pressure_pa"
            )
        pressure = pressure_stress(
            inner_radius_m=inner_radius_m,
            outer_radius_m=outer_radius_m,
            internal_pressure_pa=internal_pressure_pa,
            external_pressure_pa=external_pressure_pa,
        )

    # The through-wall thermal stress acts in the hoop and axial directions and is
    # zero radially, so it superposes on the Lame hoop and axial components.
    if pressure is None:
        combined = thermal
    else:
        combined = von_mises(
            pressure.hoop_pa + thermal,
            pressure.radial_pa,
            pressure.axial_pa + thermal,
        )

    category = "primary_plus_secondary" if pressure is not None else "secondary"
    allowable = allowable_stress_pa or material.allowable_stress_pa
    limit = None
    utilisation = None
    verdict = "not_assessed"
    warnings: list[str] = []

    if allowable is not None:
        _require_positive("allowable stress", allowable)
        limit = allowable * _SECONDARY_ALLOWABLE_FACTOR
        utilisation = combined / limit
        if utilisation >= 1.0:
            verdict = "exceeds_allowable"
        elif utilisation >= _REVIEW_UTILISATION:
            verdict = "review"
        else:
            verdict = "acceptable"
        if pressure is not None and pressure.von_mises_pa > allowable:
            verdict = "exceeds_allowable"
            warnings.append(
                "The pressure stress alone exceeds the primary membrane allowable; "
                "that is a wall-thickness problem, not a thermal one."
            )
    else:
        warnings.append(
            "No allowable stress was supplied and the material carries none, so the "
            "stresses were computed but not assessed."
        )

    if abs(delta) < 1.0:
        warnings.append(
            f"The metal temperature difference is only {abs(delta):.2f} K, so the "
            "thermal stress is negligible; confirm the model resolved the wall."
        )
    if pressure is not None and pressure.thick_wall_required:
        warnings.append(
            "The diameter-to-thickness ratio is below 20, so the thin-wall hoop "
            "stress understates the bore stress; the Lame value is the one to use."
        )

    return ThermalStressResult(
        location=location.strip(),
        delta_temperature_k=delta,
        thermal_stress_pa=thermal,
        restraint=(restraint or "").strip().lower(),
        stress_category=category,
        pressure=pressure,
        combined_von_mises_pa=combined,
        allowable_pa=limit,
        utilisation=None if utilisation is None else round(utilisation, 4),
        verdict=verdict,
        warnings=tuple(warnings),
        assumptions=(
            "Linear elastic, temperature-independent modulus and expansion "
            "coefficient; both fall with temperature in real steels.",
            "The through-wall temperature profile is treated as linear when it is "
            "converted to a bending stress. A steep near-surface gradient from a "
            "thermal shock produces a higher peak than this.",
            f"Thermal stress is secondary and self-limiting, so it is assessed "
            f"against {_SECONDARY_ALLOWABLE_FACTOR:g}S rather than S. A cyclic duty "
            "additionally needs a fatigue assessment, which this does not perform.",
            "Stress concentration at nozzles, welds, supports and geometry changes "
            "is not included; a peak stress needs a local model.",
        ),
    )


def _require_positive(name: str, value: float | None) -> None:
    if value is None or not isfinite(float(value)) or float(value) <= 0.0:
        raise ValueError(f"{name} must be a finite positive number")


def _require_finite(name: str, value: float | None) -> None:
    if value is None or not isfinite(float(value)):
        raise ValueError(f"{name} must be a finite number")
