"""Solid material properties for finite-element conduction and stress models.

A finite-element model of a pipe wall, an insulation layer or a rock formation
needs conductivity, density, specific heat and - as soon as thermal stress is
asked for - modulus, Poisson ratio and expansion coefficient. NeqSim supplies the
fluid side; this module supplies the solid side.

Every value here is an indicative screening value with a stated basis. Project
material data sheets, the piping class and the applicable design code supersede
them, and :func:`material` records that in the returned object so the assumption
travels with the number instead of being lost.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite

# Conductivity is stored as a value at a reference temperature plus a linear
# coefficient, because over the -50 to 400 degC band that a pipe wall, an
# insulation layer and a formation actually see, the linear term captures most of
# the variation and a polynomial fit would imply an accuracy the data lacks.
_REFERENCE_TEMPERATURE_C = 20.0


@dataclass(frozen=True)
class SolidMaterial:
    """Thermal and mechanical properties of one solid layer.

    ``conductivity_temp_coeff_w_per_mk2`` is the linear temperature coefficient of
    thermal conductivity in W/(m.K) per K, applied about
    ``reference_temperature_c``. Mechanical fields are optional because an
    insulation or a formation layer is normally only carried for its thermal
    behaviour.
    """

    name: str
    category: str
    density_kg_per_m3: float
    specific_heat_j_per_kgk: float
    conductivity_w_per_mk: float
    conductivity_temp_coeff_w_per_mk2: float = 0.0
    reference_temperature_c: float = _REFERENCE_TEMPERATURE_C
    youngs_modulus_pa: float | None = None
    poisson_ratio: float | None = None
    thermal_expansion_1_per_k: float | None = None
    yield_strength_pa: float | None = None
    allowable_stress_pa: float | None = None
    max_service_temperature_c: float | None = None
    min_service_temperature_c: float | None = None
    source: str = "indicative screening value"

    def conductivity_at(self, temperature_c: float) -> float:
        """Thermal conductivity at a temperature, in W/(m.K).

        The linear model is clamped at 10 % of the reference value so an
        extrapolation far outside the fitted band can never return a zero or
        negative conductivity and silently produce an infinite resistance.
        """
        _require_finite("temperature_c", temperature_c)
        value = self.conductivity_w_per_mk + self.conductivity_temp_coeff_w_per_mk2 * (
            temperature_c - self.reference_temperature_c
        )
        return max(value, 0.1 * self.conductivity_w_per_mk)

    def thermal_diffusivity_at(self, temperature_c: float) -> float:
        """Thermal diffusivity ``k / (rho cp)`` at a temperature, in m^2/s."""
        return self.conductivity_at(temperature_c) / (
            self.density_kg_per_m3 * self.specific_heat_j_per_kgk
        )

    def volumetric_heat_capacity_j_per_m3k(self) -> float:
        """``rho cp``, the quantity that sets the transient response."""
        return self.density_kg_per_m3 * self.specific_heat_j_per_kgk

    def service_warnings(self, temperature_c: float) -> tuple[str, ...]:
        """Warn when a temperature falls outside the material's service band."""
        warnings: list[str] = []
        if (
            self.max_service_temperature_c is not None
            and temperature_c > self.max_service_temperature_c
        ):
            warnings.append(
                f"{self.name} is above its indicative service limit "
                f"({temperature_c:.0f} degC > {self.max_service_temperature_c:.0f} degC); "
                "confirm against the material data sheet."
            )
        if (
            self.min_service_temperature_c is not None
            and temperature_c < self.min_service_temperature_c
        ):
            warnings.append(
                f"{self.name} is below its indicative service limit "
                f"({temperature_c:.0f} degC < {self.min_service_temperature_c:.0f} degC); "
                "low-temperature toughness must be confirmed."
            )
        return tuple(warnings)


_LIBRARY: dict[str, SolidMaterial] = {
    "carbon-steel": SolidMaterial(
        name="carbon steel (line-pipe grade)",
        category="metal",
        density_kg_per_m3=7850.0,
        specific_heat_j_per_kgk=490.0,
        conductivity_w_per_mk=45.0,
        conductivity_temp_coeff_w_per_mk2=-0.030,
        youngs_modulus_pa=207.0e9,
        poisson_ratio=0.30,
        thermal_expansion_1_per_k=1.17e-5,
        yield_strength_pa=448.0e6,
        allowable_stress_pa=138.0e6,
        max_service_temperature_c=400.0,
        min_service_temperature_c=-46.0,
        source="Indicative API 5L X65 / ASTM A106 values; use the piping class data.",
    ),
    "stainless-316l": SolidMaterial(
        name="austenitic stainless steel 316L",
        category="metal",
        density_kg_per_m3=8000.0,
        specific_heat_j_per_kgk=500.0,
        conductivity_w_per_mk=15.0,
        conductivity_temp_coeff_w_per_mk2=0.015,
        youngs_modulus_pa=193.0e9,
        poisson_ratio=0.30,
        thermal_expansion_1_per_k=1.60e-5,
        yield_strength_pa=205.0e6,
        allowable_stress_pa=115.0e6,
        max_service_temperature_c=500.0,
        min_service_temperature_c=-196.0,
        source="Indicative ASTM A312 TP316L values; use the material data sheet.",
    ),
    "duplex-22cr": SolidMaterial(
        name="22Cr duplex stainless steel",
        category="metal",
        density_kg_per_m3=7800.0,
        specific_heat_j_per_kgk=480.0,
        conductivity_w_per_mk=15.0,
        conductivity_temp_coeff_w_per_mk2=0.012,
        youngs_modulus_pa=200.0e9,
        poisson_ratio=0.30,
        thermal_expansion_1_per_k=1.30e-5,
        yield_strength_pa=450.0e6,
        allowable_stress_pa=180.0e6,
        max_service_temperature_c=250.0,
        min_service_temperature_c=-50.0,
        source="Indicative UNS S31803 / S32205 values; NORSOK M-630 MDS governs.",
    ),
    "polyurethane-insulation": SolidMaterial(
        name="solid polyurethane subsea insulation",
        category="insulation",
        density_kg_per_m3=700.0,
        specific_heat_j_per_kgk=1500.0,
        conductivity_w_per_mk=0.17,
        conductivity_temp_coeff_w_per_mk2=0.0004,
        max_service_temperature_c=120.0,
        source="Indicative solid PU wet-insulation value; vendor data supersedes.",
    ),
    "syntactic-foam": SolidMaterial(
        name="glass-microsphere syntactic foam",
        category="insulation",
        density_kg_per_m3=600.0,
        specific_heat_j_per_kgk=1400.0,
        conductivity_w_per_mk=0.13,
        conductivity_temp_coeff_w_per_mk2=0.0003,
        max_service_temperature_c=130.0,
        source="Indicative subsea syntactic-foam value; depth rating is vendor data.",
    ),
    "mineral-wool": SolidMaterial(
        name="mineral wool (topside dry insulation)",
        category="insulation",
        density_kg_per_m3=100.0,
        specific_heat_j_per_kgk=840.0,
        conductivity_w_per_mk=0.045,
        conductivity_temp_coeff_w_per_mk2=0.0002,
        max_service_temperature_c=650.0,
        source="Indicative EN 14303 mineral-wool value at ambient mean temperature.",
    ),
    "aerogel-blanket": SolidMaterial(
        name="silica aerogel blanket",
        category="insulation",
        density_kg_per_m3=150.0,
        specific_heat_j_per_kgk=1000.0,
        conductivity_w_per_mk=0.020,
        conductivity_temp_coeff_w_per_mk2=0.00005,
        max_service_temperature_c=650.0,
        source="Indicative aerogel-blanket value; strongly compression dependent.",
    ),
    "concrete-weight-coating": SolidMaterial(
        name="concrete weight coating",
        category="coating",
        density_kg_per_m3=3040.0,
        specific_heat_j_per_kgk=880.0,
        conductivity_w_per_mk=1.60,
        source="Indicative iron-ore-aggregate weight-coating value.",
    ),
    "sandstone": SolidMaterial(
        name="sandstone formation",
        category="rock",
        density_kg_per_m3=2400.0,
        specific_heat_j_per_kgk=900.0,
        conductivity_w_per_mk=2.50,
        youngs_modulus_pa=20.0e9,
        poisson_ratio=0.25,
        thermal_expansion_1_per_k=1.0e-5,
        source="Indicative water-saturated sandstone value; log or core data supersedes.",
    ),
    "shale": SolidMaterial(
        name="shale formation",
        category="rock",
        density_kg_per_m3=2500.0,
        specific_heat_j_per_kgk=900.0,
        conductivity_w_per_mk=1.50,
        youngs_modulus_pa=15.0e9,
        poisson_ratio=0.30,
        thermal_expansion_1_per_k=1.0e-5,
        source="Indicative shale value; strongly anisotropic in practice.",
    ),
    "well-cement": SolidMaterial(
        name="class G well cement",
        category="cement",
        density_kg_per_m3=1900.0,
        specific_heat_j_per_kgk=1500.0,
        conductivity_w_per_mk=0.90,
        source="Indicative set class G cement value; slurry design supersedes.",
    ),
}


def material(name: str) -> SolidMaterial:
    """Return a library material by key.

    Raises with the available keys listed, because a silently mistyped material
    is the fastest way to produce a plausible-looking but wrong wall temperature.
    """
    key = (name or "").strip().lower()
    if key not in _LIBRARY:
        raise KeyError(
            f"unknown material '{name}'; available: {', '.join(sorted(_LIBRARY))}"
        )
    return _LIBRARY[key]


def list_materials(category: str | None = None) -> tuple[str, ...]:
    """Return the library keys, optionally filtered by category."""
    if category is None:
        return tuple(sorted(_LIBRARY))
    wanted = category.strip().lower()
    return tuple(sorted(k for k, v in _LIBRARY.items() if v.category == wanted))


def custom_material(base: str | SolidMaterial | None = None, **overrides) -> SolidMaterial:
    """Build a project-specific material, optionally starting from a library entry.

    This is the intended route for a value taken from a material data sheet: start
    from the closest library entry, override what the data sheet states, and set
    ``source`` to the document reference so the number stays traceable.
    """
    if base is None:
        required = ("name", "category", "density_kg_per_m3", "specific_heat_j_per_kgk",
                    "conductivity_w_per_mk")
        missing = [field for field in required if field not in overrides]
        if missing:
            raise ValueError(
                "without a base material these fields are required: " + ", ".join(missing)
            )
        return SolidMaterial(**overrides)

    template = material(base) if isinstance(base, str) else base
    return replace(template, **overrides)


def _require_finite(name: str, value: float | None) -> None:
    if value is None or not isfinite(float(value)):
        raise ValueError(f"{name} must be a finite number")
