from __future__ import annotations

from dataclasses import dataclass
from math import sqrt


@dataclass(frozen=True)
class FireWaterDemandResult:
    """Screening fire-water demand for an area plus its dedicated objects."""

    area_demand_lpm: float
    object_demand_lpm: float
    total_demand_lpm: float
    total_demand_m3_per_h: float
    water_volume_m3: float
    foam_concentrate_m3: float
    object_to_area_ratio: float
    assumptions: tuple[str, ...]


@dataclass(frozen=True)
class DelugeLayoutResult:
    """Screening deluge nozzle net for a required density over an area."""

    required_flow_lpm: float
    flow_per_nozzle_lpm: float
    coverage_per_nozzle_m2: float
    nozzle_count_from_flow: int
    nozzle_count_from_coverage: int
    nozzle_count: int
    governing_criterion: str
    grid_spacing_m: float
    delivered_density_lpm_per_m2: float
    pressure_adequate: bool
    density_met: bool
    assumptions: tuple[str, ...]


@dataclass(frozen=True)
class MonitorScreeningResult:
    """Screening of a fire-monitor concept against a fixed-system density requirement."""

    total_flow_lpm: float
    nominal_density_lpm_per_m2: float
    drift_displacement_m: float
    wind_coverage_fraction: float
    effective_density_lpm_per_m2: float
    meets_density_still_air: bool
    meets_density_in_wind: bool
    verdict: str
    assumptions: tuple[str, ...]


class FireWaterCoverageModel:
    """Educational fire-water and deluge coverage screening.

    Public application rates only. The model answers three screening questions:

    1. how much water an area-coverage philosophy implies, and how that compares with
       protecting the individual hydrocarbon-bearing items instead;
    2. how many deluge nozzles that needs, taking the larger of the flow criterion
       (``Q = K*sqrt(p)``) and the spacing criterion (spray patterns must overlap);
    3. whether a fire-monitor concept can deliver the same density once the droplets
       are drifted downwind on an open deck.

    All results are screening indicators intended to scope a study, not a design.
    """

    #: NORSOK S-001 minimum density for process areas and equipment surfaces, (l/min)/m2.
    NORSOK_PROCESS_AREA_LPM_M2 = 10.0
    #: NORSOK S-001 minimum density for wellhead areas and riser balconies, (l/min)/m2.
    NORSOK_WELLHEAD_LPM_M2 = 20.0
    #: NFPA 15 exposure-protection density for vessel shells, (l/min)/m2 (0.25 gpm/ft2).
    NFPA15_VESSEL_EXPOSURE_LPM_M2 = 10.2
    #: Representative terminal velocity of a coarse water-monitor droplet, m/s.
    DROPLET_TERMINAL_VELOCITY_M_S = 8.0

    @staticmethod
    def _require_positive(name: str, value: float) -> None:
        if not isinstance(value, (int, float)) or value <= 0:
            raise ValueError(f"{name} must be a positive number, got {value!r}")

    @staticmethod
    def _require_non_negative(name: str, value: float) -> None:
        if not isinstance(value, (int, float)) or value < 0:
            raise ValueError(f"{name} must be zero or a positive number, got {value!r}")

    @staticmethod
    def horizontal_vessel_surface_m2(shell_outer_diameter_m: float, length_m: float) -> float:
        """Exposed surface of a horizontal drum or shell-and-tube exchanger, shell plus ends."""
        FireWaterCoverageModel._require_positive("shell_outer_diameter_m", shell_outer_diameter_m)
        FireWaterCoverageModel._require_positive("length_m", length_m)
        shell = 3.141592653589793 * shell_outer_diameter_m * length_m
        ends = 2.0 * 3.141592653589793 * shell_outer_diameter_m**2 / 4.0
        return shell + ends

    def demand(
        self,
        *,
        protected_area_m2: float,
        area_rate_lpm_per_m2: float = NORSOK_PROCESS_AREA_LPM_M2,
        objects: tuple[tuple[str, float, float], ...] = (),
        duration_min: float = 30.0,
        foam_concentrate_percent: float = 0.0,
        simultaneous_area_factor: float = 1.0,
    ) -> FireWaterDemandResult:
        """Fire-water demand for general area coverage plus dedicated object protection.

        ``objects`` is a tuple of ``(tag, surface_area_m2, rate_lpm_per_m2)``.
        """
        self._require_non_negative("protected_area_m2", protected_area_m2)
        self._require_non_negative("area_rate_lpm_per_m2", area_rate_lpm_per_m2)
        self._require_positive("duration_min", duration_min)
        self._require_non_negative("foam_concentrate_percent", foam_concentrate_percent)
        if simultaneous_area_factor < 1.0:
            raise ValueError("simultaneous_area_factor must be >= 1")

        area_demand = protected_area_m2 * area_rate_lpm_per_m2
        object_demand = 0.0
        for tag, surface, rate in objects:
            self._require_positive(f"surface area of {tag}", surface)
            self._require_positive(f"rate for {tag}", rate)
            object_demand += surface * rate

        total = (area_demand + object_demand) * simultaneous_area_factor
        volume = total * duration_min / 1000.0
        return FireWaterDemandResult(
            area_demand_lpm=area_demand,
            object_demand_lpm=object_demand,
            total_demand_lpm=total,
            total_demand_m3_per_h=total * 60.0 / 1000.0,
            water_volume_m3=volume,
            foam_concentrate_m3=volume * foam_concentrate_percent / 100.0,
            object_to_area_ratio=(object_demand / area_demand) if area_demand > 0 else float("nan"),
            assumptions=(
                "General area coverage applied over the plan area; no credit for shadowing.",
                "Dedicated object surfaces supplied by the caller; not derived from a layout.",
                "Duration is a project-basis input; NORSOK S-001 states no fire-water duration.",
            ),
        )

    def deluge_layout(
        self,
        *,
        protected_area_m2: float,
        required_density_lpm_per_m2: float,
        nozzle_k_lpm_per_sqrt_bar: float,
        nozzle_min_pressure_barg: float,
        max_spacing_m: float,
        operating_pressure_barg: float,
        coverage_efficiency: float = 1.0,
    ) -> DelugeLayoutResult:
        """Nozzle count and grid pitch, governed by the larger of flow and spacing."""
        self._require_positive("protected_area_m2", protected_area_m2)
        self._require_positive("required_density_lpm_per_m2", required_density_lpm_per_m2)
        self._require_positive("nozzle_k_lpm_per_sqrt_bar", nozzle_k_lpm_per_sqrt_bar)
        self._require_positive("nozzle_min_pressure_barg", nozzle_min_pressure_barg)
        self._require_positive("max_spacing_m", max_spacing_m)
        self._require_positive("operating_pressure_barg", operating_pressure_barg)
        if not 0.0 < coverage_efficiency <= 1.0:
            raise ValueError("coverage_efficiency must be in (0, 1]")

        required_flow = protected_area_m2 * required_density_lpm_per_m2
        q_nozzle = nozzle_k_lpm_per_sqrt_bar * sqrt(operating_pressure_barg)
        coverage = max_spacing_m**2 * coverage_efficiency
        n_flow = int(-(-required_flow // q_nozzle))
        n_cov = int(-(-protected_area_m2 // coverage))
        n = max(n_flow, n_cov)
        delivered = n * q_nozzle / protected_area_m2
        return DelugeLayoutResult(
            required_flow_lpm=required_flow,
            flow_per_nozzle_lpm=q_nozzle,
            coverage_per_nozzle_m2=coverage,
            nozzle_count_from_flow=n_flow,
            nozzle_count_from_coverage=n_cov,
            nozzle_count=n,
            governing_criterion="coverage" if n_cov > n_flow else "flow",
            grid_spacing_m=sqrt(protected_area_m2 / n),
            delivered_density_lpm_per_m2=delivered,
            pressure_adequate=operating_pressure_barg >= nozzle_min_pressure_barg,
            density_met=delivered >= required_density_lpm_per_m2,
            assumptions=(
                "Nozzle discharge follows the orifice law Q = K*sqrt(p).",
                "Coverage per nozzle is the square of the maximum permitted spacing.",
                "Square grid assumed; a real layout follows the structure and the obstructions.",
            ),
        )

    def monitor_screening(
        self,
        *,
        target_area_m2: float,
        required_density_lpm_per_m2: float,
        monitor_count: int,
        monitor_flow_lpm: float,
        wind_speed_m_s: float = 0.0,
        fall_height_m: float = 10.0,
        characteristic_dimension_m: float | None = None,
        line_of_sight_obstructed: bool = False,
        droplet_terminal_velocity_m_s: float = DROPLET_TERMINAL_VELOCITY_M_S,
    ) -> MonitorScreeningResult:
        """Density a monitor arrangement achieves, before and after wind drift."""
        self._require_positive("target_area_m2", target_area_m2)
        self._require_positive("required_density_lpm_per_m2", required_density_lpm_per_m2)
        self._require_positive("monitor_flow_lpm", monitor_flow_lpm)
        self._require_positive("fall_height_m", fall_height_m)
        self._require_positive("droplet_terminal_velocity_m_s", droplet_terminal_velocity_m_s)
        self._require_non_negative("wind_speed_m_s", wind_speed_m_s)
        if monitor_count < 1:
            raise ValueError("monitor_count must be >= 1")

        total = monitor_count * monitor_flow_lpm
        nominal = total / target_area_m2
        dim = characteristic_dimension_m if characteristic_dimension_m else sqrt(target_area_m2)
        self._require_positive("characteristic_dimension_m", dim)
        drift = fall_height_m * wind_speed_m_s / droplet_terminal_velocity_m_s
        frac = min(1.0, max(0.0, 1.0 - drift / dim))
        effective = nominal * frac

        if line_of_sight_obstructed:
            verdict = "not_suitable_shadowing"
        elif nominal < required_density_lpm_per_m2:
            verdict = "not_suitable_density"
        elif effective < required_density_lpm_per_m2:
            verdict = "marginal_wind_limited"
        else:
            verdict = "feasible_on_density"

        return MonitorScreeningResult(
            total_flow_lpm=total,
            nominal_density_lpm_per_m2=nominal,
            drift_displacement_m=drift,
            wind_coverage_fraction=frac,
            effective_density_lpm_per_m2=effective,
            meets_density_still_air=nominal >= required_density_lpm_per_m2,
            meets_density_in_wind=effective >= required_density_lpm_per_m2,
            verdict=verdict,
            assumptions=(
                "Drift displacement dx = h * u_wind / v_terminal, a screening relation.",
                "Coverage loss scales linearly with drift over the characteristic dimension.",
                "Shadowing is reported as a flag, not modelled: a monitor cannot wet what it "
                "cannot see.",
            ),
        )
