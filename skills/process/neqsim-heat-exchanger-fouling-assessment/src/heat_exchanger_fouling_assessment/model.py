"""Heat-exchanger performance and fouling assessment from an operating snapshot.

Public, educational reduction of a measured duty and four terminal temperatures
into an overall coefficient, a fouling resistance, and the capacity limit that
the degraded exchanger imposes on the plant.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite, log

# Exponent of the Dittus-Boelter style film correlation h ~ G^0.8.
FILM_FLOW_EXPONENT = 0.8
# Terminal temperature difference below which the LMTD becomes sensitive to
# small temperature-measurement errors and effectiveness-NTU is preferred.
CLOSE_APPROACH_K = 3.0


@dataclass(frozen=True)
class MaldistributionRow:
    """Apparent coefficient when only part of the installed area is credited."""

    units_credited: int
    credited_area_m2: float
    u_apparent_w_m2k: float
    performance_ratio: float


@dataclass(frozen=True)
class FoulingAssessmentResult:
    duty_kw: float
    duty_source: str
    duty_hot_kw: float
    duty_cold_kw: float
    duty_imbalance_fraction: float
    lmtd_k: float
    lmtd_reliable: bool
    effectiveness: float
    ntu: float
    capacity_ratio: float
    u_measured_w_m2k: float
    u_measured_basis: str
    u_design_w_m2k: float
    u_normalised_to_design_flow_w_m2k: float
    u_naive_one_sided_w_m2k: float
    naive_optimism_percentage_points: float
    performance_ratio: float
    fouling_resistance_m2k_w: float
    design_fouling_allowance_m2k_w: float
    excess_fouling_resistance_m2k_w: float
    condition: str
    maldistribution_scan: tuple[MaldistributionRow, ...]
    warnings: tuple[str, ...]
    assumptions: tuple[str, ...]
    neqsim_available: bool


@dataclass(frozen=True)
class CapacityLimitResult:
    maximum_duty_kw: float
    duty_margin_kw: float
    limited: bool
    limit_cause: str
    cold_inlet_temperature: float
    set_point_temperature: float
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class CleaningIntervalResult:
    fouling_rate_m2k_w_per_day: float
    days_to_limit: float
    residual_fouling_resistance_m2k_w: float
    achievable_cycle_days: float
    cleaning_effective: bool
    warnings: tuple[str, ...]


class HeatExchangerFoulingModel:
    """Educational heat-exchanger condition and fouling assessment."""

    def __init__(
        self,
        *,
        fouled_performance_ratio: float = 0.85,
        heavily_fouled_performance_ratio: float = 0.60,
        duty_imbalance_tolerance: float = 0.10,
    ) -> None:
        if not 0.0 < heavily_fouled_performance_ratio < fouled_performance_ratio <= 1.0:
            raise ValueError(
                "require 0 < heavily_fouled_performance_ratio < "
                "fouled_performance_ratio <= 1"
            )
        if not 0.0 < duty_imbalance_tolerance <= 1.0:
            raise ValueError("duty_imbalance_tolerance must be in the interval (0, 1]")
        self.fouled_performance_ratio = fouled_performance_ratio
        self.heavily_fouled_performance_ratio = heavily_fouled_performance_ratio
        self.duty_imbalance_tolerance = duty_imbalance_tolerance

    # ------------------------------------------------------------------
    # Main assessment
    # ------------------------------------------------------------------
    def evaluate(
        self,
        *,
        area: float,
        design_overall_coefficient: float,
        hot_mass_flow: float,
        hot_specific_heat: float,
        hot_inlet_temperature: float,
        hot_outlet_temperature: float,
        cold_mass_flow: float,
        cold_specific_heat: float,
        cold_inlet_temperature: float,
        cold_outlet_temperature: float,
        design_hot_mass_flow: float | None = None,
        design_cold_mass_flow: float | None = None,
        design_fouling_allowance: float = 0.0,
        wall_resistance: float = 0.0,
        hot_film_coefficient: float | None = None,
        cold_film_coefficient: float | None = None,
        hot_film_resistance_fraction: float = 0.5,
        lmtd_correction_factor: float = 1.0,
        duty_source: str = "auto",
        installed_units: int = 1,
    ) -> FoulingAssessmentResult:
        """Reduce one operating snapshot to a coefficient and a fouling resistance."""
        self._require_positive("area", area)
        self._require_positive("design_overall_coefficient", design_overall_coefficient)
        self._require_positive("hot_mass_flow", hot_mass_flow)
        self._require_positive("hot_specific_heat", hot_specific_heat)
        self._require_positive("cold_mass_flow", cold_mass_flow)
        self._require_positive("cold_specific_heat", cold_specific_heat)
        for name, value in (
            ("hot_inlet_temperature", hot_inlet_temperature),
            ("hot_outlet_temperature", hot_outlet_temperature),
            ("cold_inlet_temperature", cold_inlet_temperature),
            ("cold_outlet_temperature", cold_outlet_temperature),
        ):
            self._require_positive(name, value)
        self._require_non_negative("design_fouling_allowance", design_fouling_allowance)
        self._require_non_negative("wall_resistance", wall_resistance)
        self._require_fraction("hot_film_resistance_fraction", hot_film_resistance_fraction)
        self._require_unit_interval("lmtd_correction_factor", lmtd_correction_factor)
        if installed_units < 1:
            raise ValueError("installed_units must be at least 1")
        if hot_outlet_temperature >= hot_inlet_temperature:
            raise ValueError("hot stream must cool: hot_outlet < hot_inlet")
        if cold_outlet_temperature <= cold_inlet_temperature:
            raise ValueError("cold stream must heat: cold_outlet > cold_inlet")
        if hot_inlet_temperature <= cold_inlet_temperature:
            raise ValueError("hot_inlet_temperature must exceed cold_inlet_temperature")
        if duty_source not in ("auto", "hot", "cold", "mean"):
            raise ValueError("duty_source must be auto, hot, cold, or mean")

        warnings: list[str] = []

        capacity_hot = hot_mass_flow * hot_specific_heat
        capacity_cold = cold_mass_flow * cold_specific_heat
        duty_hot = capacity_hot * (hot_inlet_temperature - hot_outlet_temperature)
        duty_cold = capacity_cold * (cold_outlet_temperature - cold_inlet_temperature)
        duty, resolved_source = self._reconcile_duty(duty_hot, duty_cold, duty_source)
        imbalance = abs(duty_hot - duty_cold) / (0.5 * (duty_hot + duty_cold))
        if imbalance > self.duty_imbalance_tolerance:
            warnings.append(
                "duty imbalance {:.1%} exceeds tolerance; one side is derived, "
                "not measured".format(imbalance)
            )

        delta_hot_end = hot_inlet_temperature - cold_outlet_temperature
        delta_cold_end = hot_outlet_temperature - cold_inlet_temperature
        if delta_hot_end <= 0.0 or delta_cold_end <= 0.0:
            raise ValueError(
                "temperature cross: counter-current terminal differences must be positive"
            )
        lmtd = self._lmtd(delta_hot_end, delta_cold_end)
        lmtd_reliable = min(delta_hot_end, delta_cold_end) >= CLOSE_APPROACH_K
        if not lmtd_reliable:
            warnings.append(
                "close approach ({:.2f} K); LMTD is sensitive to temperature error, "
                "effectiveness-NTU used for the coefficient".format(
                    min(delta_hot_end, delta_cold_end)
                )
            )

        capacity_min = min(capacity_hot, capacity_cold)
        capacity_ratio = capacity_min / max(capacity_hot, capacity_cold)
        duty_maximum = capacity_min * (hot_inlet_temperature - cold_inlet_temperature)
        effectiveness = duty / duty_maximum
        if effectiveness >= 1.0:
            raise ValueError(
                "effectiveness >= 1: the snapshot violates the second law, "
                "check flows, specific heats, and temperatures"
            )
        ntu = self._ntu_counter_current(effectiveness, capacity_ratio)

        u_lmtd = 1000.0 * duty / (area * lmtd_correction_factor * lmtd)
        u_ntu = 1000.0 * ntu * capacity_min / area
        if lmtd_reliable:
            u_measured, u_basis = u_lmtd, "lmtd"
        else:
            u_measured, u_basis = u_ntu, "effectiveness-ntu"

        hot_ratio = self._flow_ratio(hot_mass_flow, design_hot_mass_flow)
        cold_ratio = self._flow_ratio(cold_mass_flow, design_cold_mass_flow)
        hot_film, cold_film = self._design_films(
            design_overall_coefficient,
            design_fouling_allowance,
            wall_resistance,
            hot_film_coefficient,
            cold_film_coefficient,
            hot_film_resistance_fraction,
        )

        # Only the two convective films respond to flow. A deposit is a fixed
        # conduction resistance, so it is held out of the normalisation.
        film_resistance_now = 1.0 / (hot_film * hot_ratio**FILM_FLOW_EXPONENT) + 1.0 / (
            cold_film * cold_ratio**FILM_FLOW_EXPONENT
        )
        fouling_resistance = 1.0 / u_measured - film_resistance_now - wall_resistance
        if fouling_resistance < 0.0:
            warnings.append(
                "negative fouling resistance: the measured coefficient exceeds the "
                "clean-film estimate, so the design film split or the instrument "
                "basis should be revisited"
            )
        film_resistance_design = 1.0 / hot_film + 1.0 / cold_film
        u_normalised = 1.0 / (
            film_resistance_design + wall_resistance + max(fouling_resistance, 0.0)
        )
        # The common error: scaling the whole coefficient, fouling included.
        u_naive = u_measured * (1.0 / hot_ratio) ** FILM_FLOW_EXPONENT

        performance_ratio = u_normalised / design_overall_coefficient
        naive_ratio = u_naive / design_overall_coefficient
        naive_optimism = 100.0 * (naive_ratio - performance_ratio)
        if abs(naive_optimism) >= 1.0:
            warnings.append(
                "one-sided flow normalisation would report {:.0f} % of design against "
                "{:.0f} % for the two-sided form".format(
                    100.0 * naive_ratio, 100.0 * performance_ratio
                )
            )

        excess_fouling = fouling_resistance - design_fouling_allowance
        condition = self._condition(performance_ratio, excess_fouling)
        scan = self._maldistribution_scan(
            duty=duty,
            area=area,
            installed_units=installed_units,
            lmtd=lmtd,
            lmtd_correction_factor=lmtd_correction_factor,
            design_overall_coefficient=design_overall_coefficient,
        )

        return FoulingAssessmentResult(
            duty_kw=round(duty, 3),
            duty_source=resolved_source,
            duty_hot_kw=round(duty_hot, 3),
            duty_cold_kw=round(duty_cold, 3),
            duty_imbalance_fraction=round(imbalance, 4),
            lmtd_k=round(lmtd, 4),
            lmtd_reliable=lmtd_reliable,
            effectiveness=round(effectiveness, 4),
            ntu=round(ntu, 4),
            capacity_ratio=round(capacity_ratio, 4),
            u_measured_w_m2k=round(u_measured, 2),
            u_measured_basis=u_basis,
            u_design_w_m2k=round(design_overall_coefficient, 2),
            u_normalised_to_design_flow_w_m2k=round(u_normalised, 2),
            u_naive_one_sided_w_m2k=round(u_naive, 2),
            naive_optimism_percentage_points=round(naive_optimism, 2),
            performance_ratio=round(performance_ratio, 4),
            fouling_resistance_m2k_w=round(fouling_resistance, 8),
            design_fouling_allowance_m2k_w=round(design_fouling_allowance, 8),
            excess_fouling_resistance_m2k_w=round(excess_fouling, 8),
            condition=condition,
            maldistribution_scan=scan,
            warnings=tuple(warnings),
            assumptions=(
                "Public, educational screening reduction of one operating snapshot.",
                "Counter-current terminal differences; a correction factor must be "
                "supplied for multi-pass or cross-flow arrangements.",
                "Films scale as G^0.8; fouling and wall resistances are flow independent.",
                "Constant specific heats over the duty range.",
                "A vendor design coefficient usually already contains a fouling "
                "allowance, so the shortfall is fouling in excess of design margin.",
                "Move to validated NeqSim heat-exchanger classes and qualified review.",
            ),
            neqsim_available=find_spec("neqsim") is not None,
        )

    # ------------------------------------------------------------------
    # Capacity translation
    # ------------------------------------------------------------------
    def capacity_limit(
        self,
        *,
        effectiveness: float,
        hot_capacity_rate: float,
        cold_capacity_rate: float,
        set_point_temperature: float,
        cold_inlet_temperature: float,
        required_duty: float = 0.0,
    ) -> CapacityLimitResult:
        """Maximum duty of a fixed-rate loop that must hold a supply set point."""
        self._require_fraction("effectiveness", effectiveness)
        self._require_positive("hot_capacity_rate", hot_capacity_rate)
        self._require_positive("cold_capacity_rate", cold_capacity_rate)
        self._require_positive("set_point_temperature", set_point_temperature)
        self._require_positive("cold_inlet_temperature", cold_inlet_temperature)
        self._require_non_negative("required_duty", required_duty)

        warnings: list[str] = []
        capacity_min = min(hot_capacity_rate, cold_capacity_rate)
        approach = set_point_temperature - cold_inlet_temperature
        if approach <= 0.0:
            return CapacityLimitResult(
                maximum_duty_kw=0.0,
                duty_margin_kw=round(-required_duty, 3),
                limited=True,
                limit_cause="cold-inlet-above-set-point",
                cold_inlet_temperature=cold_inlet_temperature,
                set_point_temperature=set_point_temperature,
                warnings=(
                    "the cold inlet is at or above the set point; no duty can be "
                    "transferred at this set point regardless of exchanger condition",
                ),
            )

        denominator = 1.0 - effectiveness * capacity_min / hot_capacity_rate
        if denominator <= 0.0:
            warnings.append(
                "denominator non-positive: the hot stream cannot be held at the set "
                "point for any duty with this effectiveness and capacity rate"
            )
            maximum_duty = float("inf")
        else:
            maximum_duty = effectiveness * capacity_min * approach / denominator

        limited = isfinite(maximum_duty) and maximum_duty < required_duty
        cause = "temperature-approach" if limited else "not-limited"
        if limited:
            warnings.append(
                "duty limited by the available temperature difference, not by a "
                "valve or a pump"
            )
        return CapacityLimitResult(
            maximum_duty_kw=round(maximum_duty, 3) if isfinite(maximum_duty) else maximum_duty,
            duty_margin_kw=(
                round(maximum_duty - required_duty, 3) if isfinite(maximum_duty) else maximum_duty
            ),
            limited=limited,
            limit_cause=cause,
            cold_inlet_temperature=cold_inlet_temperature,
            set_point_temperature=set_point_temperature,
            warnings=tuple(warnings),
        )

    # ------------------------------------------------------------------
    # Cleaning planning
    # ------------------------------------------------------------------
    def cleaning_interval(
        self,
        *,
        fouling_resistance_start: float,
        fouling_resistance_end: float,
        elapsed_days: float,
        fouling_resistance_limit: float,
        cleaning_residual_fraction: float = 0.0,
    ) -> CleaningIntervalResult:
        """Cleaning cycle implied by two fouling resistances and a clean-up quality."""
        self._require_non_negative("fouling_resistance_start", fouling_resistance_start)
        self._require_non_negative("fouling_resistance_end", fouling_resistance_end)
        self._require_positive("elapsed_days", elapsed_days)
        self._require_positive("fouling_resistance_limit", fouling_resistance_limit)
        if not 0.0 <= cleaning_residual_fraction < 1.0:
            raise ValueError("cleaning_residual_fraction must be in the interval [0, 1)")

        warnings: list[str] = []
        rate = (fouling_resistance_end - fouling_resistance_start) / elapsed_days
        if rate <= 0.0:
            warnings.append(
                "non-positive fouling rate between the two snapshots; no interval can "
                "be projected from this pair"
            )
            return CleaningIntervalResult(
                fouling_rate_m2k_w_per_day=round(rate, 12),
                days_to_limit=float("inf"),
                residual_fouling_resistance_m2k_w=0.0,
                achievable_cycle_days=float("inf"),
                cleaning_effective=True,
                warnings=tuple(warnings),
            )

        days_to_limit = max(fouling_resistance_limit - fouling_resistance_end, 0.0) / rate
        residual = cleaning_residual_fraction * fouling_resistance_end
        effective = residual < fouling_resistance_limit
        if effective:
            cycle = (fouling_resistance_limit - residual) / rate
        else:
            cycle = 0.0
            warnings.append(
                "the clean leaves more deposit than the limit allows; a shorter "
                "interval cannot recover the duty, the cleaning method must change"
            )
        return CleaningIntervalResult(
            fouling_rate_m2k_w_per_day=round(rate, 12),
            days_to_limit=round(days_to_limit, 2),
            residual_fouling_resistance_m2k_w=round(residual, 8),
            achievable_cycle_days=round(cycle, 2),
            cleaning_effective=effective,
            warnings=tuple(warnings),
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    @staticmethod
    def _reconcile_duty(duty_hot: float, duty_cold: float, duty_source: str):
        if duty_source == "hot":
            return duty_hot, "hot"
        if duty_source == "cold":
            return duty_cold, "cold"
        if duty_source == "mean":
            return 0.5 * (duty_hot + duty_cold), "mean"
        return 0.5 * (duty_hot + duty_cold), "auto-mean"

    @staticmethod
    def _lmtd(delta_hot_end: float, delta_cold_end: float) -> float:
        if abs(delta_hot_end - delta_cold_end) < 1.0e-6 * max(delta_hot_end, delta_cold_end):
            return 0.5 * (delta_hot_end + delta_cold_end)
        return (delta_hot_end - delta_cold_end) / log(delta_hot_end / delta_cold_end)

    @staticmethod
    def _ntu_counter_current(effectiveness: float, capacity_ratio: float) -> float:
        if capacity_ratio >= 1.0 - 1.0e-9:
            return effectiveness / (1.0 - effectiveness)
        numerator = (effectiveness - 1.0) / (effectiveness * capacity_ratio - 1.0)
        return log(numerator) / (capacity_ratio - 1.0)

    @staticmethod
    def _flow_ratio(measured: float, design: float | None) -> float:
        if design is None:
            return 1.0
        if design <= 0.0 or not isfinite(design):
            raise ValueError("design mass flows must be finite and positive")
        return measured / design

    @classmethod
    def _design_films(
        cls,
        design_overall_coefficient: float,
        design_fouling_allowance: float,
        wall_resistance: float,
        hot_film_coefficient: float | None,
        cold_film_coefficient: float | None,
        hot_film_resistance_fraction: float,
    ) -> tuple[float, float]:
        if hot_film_coefficient is not None and cold_film_coefficient is not None:
            cls._require_positive("hot_film_coefficient", hot_film_coefficient)
            cls._require_positive("cold_film_coefficient", cold_film_coefficient)
            return hot_film_coefficient, cold_film_coefficient
        if hot_film_coefficient is not None or cold_film_coefficient is not None:
            raise ValueError("supply both film coefficients or neither")
        film_resistance = 1.0 / design_overall_coefficient - wall_resistance
        film_resistance -= design_fouling_allowance
        if film_resistance <= 0.0:
            raise ValueError(
                "the design fouling allowance and wall resistance consume the whole "
                "design resistance; supply film coefficients explicitly"
            )
        return (
            1.0 / (hot_film_resistance_fraction * film_resistance),
            1.0 / ((1.0 - hot_film_resistance_fraction) * film_resistance),
        )

    @staticmethod
    def _maldistribution_scan(
        *,
        duty: float,
        area: float,
        installed_units: int,
        lmtd: float,
        lmtd_correction_factor: float,
        design_overall_coefficient: float,
    ) -> tuple[MaldistributionRow, ...]:
        rows = []
        unit_area = area / installed_units
        for credited in range(installed_units, 0, -1):
            credited_area = unit_area * credited
            u_apparent = 1000.0 * duty / (credited_area * lmtd_correction_factor * lmtd)
            rows.append(
                MaldistributionRow(
                    units_credited=credited,
                    credited_area_m2=round(credited_area, 4),
                    u_apparent_w_m2k=round(u_apparent, 2),
                    performance_ratio=round(u_apparent / design_overall_coefficient, 4),
                )
            )
        return tuple(rows)

    def _condition(self, performance_ratio: float, excess_fouling: float) -> str:
        if performance_ratio < self.heavily_fouled_performance_ratio:
            return "heavily-fouled"
        if performance_ratio < self.fouled_performance_ratio:
            return "fouled"
        if excess_fouling > 0.0:
            return "within-allowance"
        return "clean"

    @staticmethod
    def _require_finite(name: str, value: float) -> None:
        if not isfinite(value):
            raise ValueError(f"{name} must be finite")

    @classmethod
    def _require_positive(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value <= 0.0:
            raise ValueError(f"{name} must be positive")

    @classmethod
    def _require_non_negative(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value < 0.0:
            raise ValueError(f"{name} must not be negative")

    @classmethod
    def _require_fraction(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value <= 0.0 or value >= 1.0:
            raise ValueError(f"{name} must be in the interval (0, 1)")

    @classmethod
    def _require_unit_interval(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value <= 0.0 or value > 1.0:
            raise ValueError(f"{name} must be in the interval (0, 1]")
