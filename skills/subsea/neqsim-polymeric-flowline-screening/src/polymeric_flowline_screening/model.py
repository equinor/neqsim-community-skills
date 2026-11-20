"""Screening-level checks for thermoplastic (polymeric) subsea flowlines."""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass

R_GAS = 8.314462618
SEAWATER_DENSITY = 1025.0
GRAVITY = 9.80665
MOLAR_VOLUME_NM3_PER_MOL = 0.0224140  # normal conditions, 0 C and 1 atm

Table = tuple[tuple[float, float], ...]


def interpolate(table: Table, x: float) -> tuple[float, bool]:
    """Linear interpolation on an ascending (x, y) table.

    Returns ``(value, extrapolated)``; outside the table the end value is held
    and ``extrapolated`` is True so the caller can report a data gap.
    """
    if not table:
        raise ValueError("table is empty")
    points = sorted(table)
    if x <= points[0][0]:
        return points[0][1], x < points[0][0]
    if x >= points[-1][0]:
        return points[-1][1], x > points[-1][0]
    for (x0, y0), (x1, y1) in itertools.pairwise(points):
        if x0 <= x <= x1:
            weight = (x - x0) / (x1 - x0)
            return y0 + weight * (y1 - y0), False
    raise AssertionError("unreachable")


@dataclass(frozen=True)
class PolymerGrade:
    """Polymer data supplied by the caller from the manufacturer or a qualification.

    ``long_term_strength_mpa`` is the long-term hydrostatic strength (MRS style) at
    temperature in C. ``modulus_mpa`` is the time-appropriate modulus: use the
    long-term creep modulus for a collapse check, not the short-term value.
    """

    name: str
    max_temperature_c: float
    long_term_strength_mpa: Table
    modulus_mpa: Table
    conductivity_w_mk: float
    poisson: float = 0.4

    def __post_init__(self) -> None:
        if not self.conductivity_w_mk > 0.0:
            raise ValueError("conductivity_w_mk must be positive")
        if not 0.0 < self.poisson < 0.5:
            raise ValueError("poisson must be in (0, 0.5)")


@dataclass(frozen=True)
class Permeant:
    """A gas that permeates the pressure sheath; all values are caller-supplied."""

    name: str
    partial_pressure_bar: float
    permeability_mol_m_s_pa: float
    reference_temperature_c: float
    activation_energy_kj_mol: float

    def __post_init__(self) -> None:
        if self.partial_pressure_bar < 0.0 or self.permeability_mol_m_s_pa < 0.0:
            raise ValueError(
                f"{self.name}: pressure and permeability cannot be negative"
            )


@dataclass(frozen=True)
class PolymerPipe:
    """Homogeneous polymer wall; a vendor rating table can replace the hoop formula."""

    outer_diameter_m: float
    wall_m: float
    length_m: float
    polymer: PolymerGrade
    pressure_rating_bar: Table | None = None

    def __post_init__(self) -> None:
        if not self.outer_diameter_m > 0.0 or not self.length_m > 0.0:
            raise ValueError("diameter and length must be positive")
        if not 0.0 < self.wall_m < self.outer_diameter_m / 2.0:
            raise ValueError("wall_m must be between 0 and half the outer diameter")

    @property
    def inner_diameter_m(self) -> float:
        """Inner diameter in metres."""
        return self.outer_diameter_m - 2.0 * self.wall_m

    @property
    def mean_diameter_m(self) -> float:
        """Mean wall diameter, ``D - t``."""
        return self.outer_diameter_m - self.wall_m


@dataclass(frozen=True)
class OperatingCase:
    """Operating and installation conditions for the screening."""

    internal_pressure_bar: float
    temperature_c: float
    ambient_c: float
    mass_flow_kg_s: float
    fluid_cp_j_kgk: float
    water_depth_m: float
    outer_film_w_m2k: float = 500.0
    collapse_internal_pressure_bar: float = 0.0
    installed_bend_radius_m: float | None = None
    minimum_arrival_temperature_c: float | None = None
    annulus_vent_capacity_nm3_d_km: float | None = None


@dataclass(frozen=True)
class DesignBasis:
    """Safety factors and limits; values must come from the governing code or vendor."""

    hoop_design_factor: float
    collapse_safety_factor: float
    allowable_bending_strain: float | None = None

    def __post_init__(self) -> None:
        if not 0.0 < self.hoop_design_factor <= 1.0:
            raise ValueError("hoop_design_factor must be in (0, 1]")
        if not self.collapse_safety_factor >= 1.0:
            raise ValueError("collapse_safety_factor must be at least 1")


@dataclass(frozen=True)
class Check:
    """One screening check: ``pass``, ``fail`` or ``data_gap``."""

    name: str
    status: str
    value: float | None
    limit: float | None
    unit: str
    note: str = ""

    @property
    def utilisation(self) -> float | None:
        """Value divided by limit, when both exist and the limit is positive."""
        if self.value is None or self.limit is None or self.limit <= 0.0:
            return None
        return self.value / self.limit


@dataclass(frozen=True)
class ThermalResult:
    """Steady-state thermal performance, polymer against bare steel of equal size."""

    resistance_k_m_per_w: float
    outlet_temperature_c: float
    heat_loss_kw: float
    steel_outlet_temperature_c: float


@dataclass(frozen=True)
class PermeationResult:
    """Permeation of one species through the wall, per km and per pipe."""

    species: str
    rate_nm3_per_day_per_km: float
    rate_nm3_per_day: float


@dataclass(frozen=True)
class ScreeningResult:
    """All checks, thermal and permeation results, and data gaps."""

    checks: dict[str, Check]
    thermal: ThermalResult
    permeation: tuple[PermeationResult, ...]
    data_gaps: tuple[str, ...]
    warnings: tuple[str, ...]
    overall: str


def allowable_hoop_pressure_bar(
    pipe: PolymerPipe, temperature_c: float, hoop_design_factor: float
) -> tuple[float, bool, str]:
    """Allowable internal pressure at temperature and whether it is extrapolated.

    Uses the vendor rating table when given; otherwise the thin-wall (ISO 12162
    style) relation ``P = 2 * sigma_design * t / (D - t)`` with
    ``sigma_design = long-term strength x design factor``.
    """
    if pipe.pressure_rating_bar:
        value, extrapolated = interpolate(pipe.pressure_rating_bar, temperature_c)
        return value, extrapolated, "vendor rating table"
    strength, extrapolated = interpolate(
        pipe.polymer.long_term_strength_mpa, temperature_c
    )
    sigma = strength * hoop_design_factor
    pressure_mpa = 2.0 * sigma * pipe.wall_m / pipe.mean_diameter_m
    return pressure_mpa * 10.0, extrapolated, "thin-wall hoop relation"


def collapse_pressure_bar(
    pipe: PolymerPipe, temperature_c: float
) -> tuple[float, bool]:
    """Elastic collapse of a long unsupported ring, ``2E/(1-nu^2) (t/Dm)^3``."""
    modulus, extrapolated = interpolate(pipe.polymer.modulus_mpa, temperature_c)
    ratio = pipe.wall_m / pipe.mean_diameter_m
    pressure_mpa = 2.0 * modulus / (1.0 - pipe.polymer.poisson**2) * ratio**3
    return pressure_mpa * 10.0, extrapolated


def permeability_at(species: Permeant, temperature_c: float) -> float:
    """Arrhenius-corrected permeability in mol/(m s Pa)."""
    t_k = temperature_c + 273.15
    t_ref = species.reference_temperature_c + 273.15
    exponent = (
        -species.activation_energy_kj_mol * 1000.0 / R_GAS * (1.0 / t_k - 1.0 / t_ref)
    )
    return species.permeability_mol_m_s_pa * math.exp(exponent)


def permeation_rate(
    pipe: PolymerPipe, species: Permeant, temperature_c: float
) -> PermeationResult:
    """Cylindrical-wall steady permeation of one species.

    ``Q' = 2 pi Pe dp / ln(Do/Di)`` in mol/s per metre, converted to Nm3/day.
    """
    delta_pa = species.partial_pressure_bar * 1.0e5
    per_metre = (
        2.0
        * math.pi
        * permeability_at(species, temperature_c)
        * delta_pa
        / math.log(pipe.outer_diameter_m / pipe.inner_diameter_m)
    )
    per_km = per_metre * 1000.0 * MOLAR_VOLUME_NM3_PER_MOL * 86400.0
    return PermeationResult(species.name, per_km, per_km * pipe.length_m / 1000.0)


def thermal_performance(
    pipe: PolymerPipe, case: OperatingCase, steel_conductivity_w_mk: float = 45.0
) -> ThermalResult:
    """Steady outlet temperature from a radial resistance model.

    ``R' = ln(Do/Di)/(2 pi k) + 1/(pi Do h_out)``; the comparison is a bare steel
    pipe of the same diameters, which isolates the effect of the polymer wall.
    """
    flow_capacity = case.mass_flow_kg_s * case.fluid_cp_j_kgk
    if not flow_capacity > 0.0:
        raise ValueError("mass_flow_kg_s and fluid_cp_j_kgk must be positive")
    ln_ratio = math.log(pipe.outer_diameter_m / pipe.inner_diameter_m)
    outer = 1.0 / (math.pi * pipe.outer_diameter_m * case.outer_film_w_m2k)

    def outlet(conductivity: float) -> tuple[float, float]:
        resistance = ln_ratio / (2.0 * math.pi * conductivity) + outer
        decay = math.exp(-pipe.length_m / (flow_capacity * resistance))
        return (
            resistance,
            case.ambient_c + (case.temperature_c - case.ambient_c) * decay,
        )

    resistance, outlet_c = outlet(pipe.polymer.conductivity_w_mk)
    _, steel_outlet_c = outlet(steel_conductivity_w_mk)
    return ThermalResult(
        resistance_k_m_per_w=resistance,
        outlet_temperature_c=outlet_c,
        heat_loss_kw=flow_capacity * (case.temperature_c - outlet_c) / 1000.0,
        steel_outlet_temperature_c=steel_outlet_c,
    )


def _status(passes: bool) -> str:
    return "pass" if passes else "fail"


def screen(
    pipe: PolymerPipe,
    case: OperatingCase,
    basis: DesignBasis,
    permeants: Sequence[Permeant] = (),
) -> ScreeningResult:
    """Run all screening checks for one operating case."""
    checks: dict[str, Check] = {}
    data_gaps: list[str] = []
    warnings: list[str] = []

    polymer = pipe.polymer
    checks["temperature"] = Check(
        "temperature",
        _status(case.temperature_c <= polymer.max_temperature_c),
        case.temperature_c,
        polymer.max_temperature_c,
        "C",
        "operating temperature against the polymer maximum",
    )

    allowable, extrapolated, source = allowable_hoop_pressure_bar(
        pipe, case.temperature_c, basis.hoop_design_factor
    )
    if extrapolated:
        data_gaps.append(
            "hoop strength or rating table does not cover the operating temperature"
        )
    checks["hoop_pressure"] = Check(
        "hoop_pressure",
        _status(case.internal_pressure_bar <= allowable),
        case.internal_pressure_bar,
        allowable,
        "bar",
        source,
    )

    external_bar = SEAWATER_DENSITY * GRAVITY * case.water_depth_m / 1.0e5
    net_external = external_bar - case.collapse_internal_pressure_bar
    collapse, collapse_extrapolated = collapse_pressure_bar(pipe, case.temperature_c)
    if collapse_extrapolated:
        data_gaps.append("modulus table does not cover the operating temperature")
    allowed_external = collapse / basis.collapse_safety_factor
    checks["collapse"] = Check(
        "collapse",
        _status(net_external <= allowed_external),
        net_external,
        allowed_external,
        "bar",
        "net external pressure with the line at the stated internal pressure",
    )

    if basis.allowable_bending_strain is None or case.installed_bend_radius_m is None:
        data_gaps.append("bend radius or allowable bending strain not supplied")
        checks["bend_radius"] = Check("bend_radius", "data_gap", None, None, "m")
    else:
        minimum = pipe.outer_diameter_m / (2.0 * basis.allowable_bending_strain)
        checks["bend_radius"] = Check(
            "bend_radius",
            _status(case.installed_bend_radius_m >= minimum),
            minimum,
            case.installed_bend_radius_m,
            "m",
            "minimum radius from the strain limit; limit column is the installed radius",
        )

    thermal = thermal_performance(pipe, case)
    if case.minimum_arrival_temperature_c is None:
        checks["arrival_temperature"] = Check(
            "arrival_temperature", "data_gap", thermal.outlet_temperature_c, None, "C"
        )
        data_gaps.append("minimum arrival temperature not supplied")
    else:
        checks["arrival_temperature"] = Check(
            "arrival_temperature",
            _status(thermal.outlet_temperature_c >= case.minimum_arrival_temperature_c),
            thermal.outlet_temperature_c,
            case.minimum_arrival_temperature_c,
            "C",
            "steady-state arrival; cooldown and transients are not covered",
        )

    permeation = tuple(permeation_rate(pipe, p, case.temperature_c) for p in permeants)
    total_per_km = sum(p.rate_nm3_per_day_per_km for p in permeation)
    if not permeants:
        data_gaps.append("no permeation species supplied")
        checks["permeation"] = Check("permeation", "data_gap", None, None, "Nm3/d/km")
    elif case.annulus_vent_capacity_nm3_d_km is None:
        data_gaps.append("annulus vent capacity not supplied")
        checks["permeation"] = Check(
            "permeation", "data_gap", total_per_km, None, "Nm3/d/km"
        )
    else:
        checks["permeation"] = Check(
            "permeation",
            _status(total_per_km <= case.annulus_vent_capacity_nm3_d_km),
            total_per_km,
            case.annulus_vent_capacity_nm3_d_km,
            "Nm3/d/km",
            "total permeation against the supplied vent capacity",
        )

    if thermal.outlet_temperature_c > case.temperature_c:
        warnings.append(
            "outlet warmer than inlet: check ambient and inlet temperatures"
        )
    failed = [c for c in checks.values() if c.status == "fail"]
    overall = "fail" if failed else ("incomplete" if data_gaps else "pass")
    return ScreeningResult(
        checks=checks,
        thermal=thermal,
        permeation=permeation,
        data_gaps=tuple(dict.fromkeys(data_gaps)),
        warnings=tuple(warnings),
        overall=overall,
    )
