"""NORSOK M-506 Rev. 2 (June 2005) bare-steel CO2 corrosion rate.

NeqSim provides the correlation as ``neqsim.process.corrosion.NorsokM506Rev2``
(added after NeqSim 3.29.0). :func:`rate_mm_per_year` and :func:`fugacity_bar`
call that class when the installed NeqSim has it, and otherwise use the
reference port below, which implements the same published equations
(sections 5.2 and 8.1, Tables 1 and 2) and is tested against the Java class.

:func:`assess_rate` wraps the correlation for profile use: inputs outside the
validity ranges are moved to the nearest bound and flagged instead of raising.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

TEMPERATURE_C = (5.0, 15.0, 20.0, 40.0, 60.0, 80.0, 90.0, 120.0, 150.0)
RATE_CONSTANT = (0.42, 1.59, 4.762, 8.927, 10.695, 9.949, 6.250, 7.770, 5.203)

RANGES = {
    "temperature_c": (5.0, 150.0),
    "fugacity_bar": (0.1, 10.0),
    "ph": (3.5, 6.5),
    "shear_pa": (1.0, 150.0),
}

_JAVA_CLASS = "neqsim.process.corrosion.NorsokM506Rev2"
_java = None
_java_checked = False


def _java_rev2():
    """The NeqSim class when installed and available, else None."""
    global _java, _java_checked
    if _java_checked:
        return _java
    _java_checked = True
    try:
        import jpype

        if not jpype.isJVMStarted():
            from neqsim import jneqsim  # noqa: F401  (starts the JVM)
        _java = jpype.JClass(_JAVA_CLASS)
    except Exception:  # noqa: BLE001 - not installed, or older NeqSim
        _java = None
    return _java


def engine_name() -> str:
    """Which implementation :func:`rate_mm_per_year` uses."""
    if _java_rev2() is not None:
        return "NeqSim NorsokM506Rev2 (Java)"
    return "Python port of NORSOK M-506 Rev. 2 (installed NeqSim lacks NorsokM506Rev2)"


def _require(value: float, name: str) -> None:
    low, high = RANGES[name]
    if not math.isfinite(value) or value < low or value > high:
        raise ValueError(f"{name} must be between {low} and {high}: {value}")


def fugacity_bar_reference(
    temperature_c: float, total_pressure_bara: float, gas_co2_mole_fraction: float
) -> float:
    """Section 8.1 CO2 fugacity (Python reference)."""
    _require(temperature_c, "temperature_c")
    if not 1.0 <= total_pressure_bara <= 1000.0:
        raise ValueError(f"total pressure must be 1-1000 bara: {total_pressure_bara}")
    if not 0.0 <= gas_co2_mole_fraction <= 1.0:
        raise ValueError("gas CO2 mole fraction must be 0-1")
    exponent = min(250.0, total_pressure_bara) * (
        0.0031 - 1.4 / (temperature_c + 273.15)
    )
    return gas_co2_mole_fraction * total_pressure_bara * 10.0**exponent


def _ph_factor(knot: int, ph: float) -> float:
    if knot <= 3 and ph < 4.6:
        return 2.0676 - 0.2309 * ph
    if knot == 0:
        return 4.342 + ph * (-1.051 + 0.0708 * ph)
    if knot == 1:
        return 4.986 + ph * (-1.191 + 0.0708 * ph)
    if knot in (2, 3):
        return 5.1885 + ph * (-1.2353 + 0.0708 * ph)
    if knot == 4:
        if ph < 4.6:
            return 1.836 - 0.1818 * ph
        return 15.444 + ph * (-6.1291 + ph * (0.8204 - 0.0371 * ph))
    if knot == 5:
        return 2.6727 - 0.3636 * ph if ph < 4.6 else 331.68 * math.exp(-1.2618 * ph)
    if knot == 6:
        if ph < 4.57:
            return 3.1355 - 0.4673 * ph
        return 21254.0 * math.exp(-2.1811 * ph) if ph < 5.62 else 0.4014 - 0.0538 * ph
    if knot == 7:
        if ph < 4.3:
            return 1.5375 - 0.125 * ph
        return 5.9757 - 1.157 * ph if ph < 5.0 else 0.546125 - 0.071225 * ph
    if ph < 3.8:
        return 1.0
    return 17.634 + ph * (-7.0945 + 0.715 * ph) if ph < 5.0 else 0.037


def _knot_rate(knot: int, fugacity: float, ph: float, shear_factor: float) -> float:
    return (
        RATE_CONSTANT[knot]
        * fugacity ** (0.36 if knot < 2 else 0.62)
        * (1.0 if knot == 0 else shear_factor)
        * _ph_factor(knot, ph)
    )


def rate_mm_per_year_reference(
    temperature_c: float,
    co2_fugacity_bar: float,
    in_situ_ph: float,
    wall_shear_pa: float,
) -> float:
    """Section 5.2 bare-steel rate, mm/year (Python reference)."""
    _require(temperature_c, "temperature_c")
    _require(co2_fugacity_bar, "fugacity_bar")
    _require(in_situ_ph, "ph")
    _require(wall_shear_pa, "shear_pa")
    upper = 0
    while TEMPERATURE_C[upper] < temperature_c:
        upper += 1
    shear = (wall_shear_pa / 19.0) ** (0.146 + 0.0324 * math.log10(co2_fugacity_bar))
    upper_rate = _knot_rate(upper, co2_fugacity_bar, in_situ_ph, shear)
    if temperature_c == TEMPERATURE_C[upper]:
        return upper_rate
    lower = upper - 1
    fraction = (temperature_c - TEMPERATURE_C[lower]) / (
        TEMPERATURE_C[upper] - TEMPERATURE_C[lower]
    )
    lower_rate = _knot_rate(lower, co2_fugacity_bar, in_situ_ph, shear)
    return lower_rate + fraction * (upper_rate - lower_rate)


def fugacity_bar(
    temperature_c: float, total_pressure_bara: float, gas_co2_mole_fraction: float
) -> float:
    """CO2 fugacity, bar: NeqSim class when available, else the reference."""
    java = _java_rev2()
    if java is not None:
        return float(
            java.fugacityBar(
                float(temperature_c),
                float(total_pressure_bara),
                float(gas_co2_mole_fraction),
            )
        )
    return fugacity_bar_reference(
        temperature_c, total_pressure_bara, gas_co2_mole_fraction
    )


def rate_mm_per_year(
    temperature_c: float,
    co2_fugacity_bar: float,
    in_situ_ph: float,
    wall_shear_pa: float,
) -> float:
    """Bare-steel rate, mm/year: NeqSim class when available, else the reference."""
    java = _java_rev2()
    if java is not None:
        return float(
            java.rateMmPerYear(
                float(temperature_c),
                float(co2_fugacity_bar),
                float(in_situ_ph),
                float(wall_shear_pa),
            )
        )
    return rate_mm_per_year_reference(
        temperature_c, co2_fugacity_bar, in_situ_ph, wall_shear_pa
    )


@dataclass
class RateAssessment:
    """Rate at one point, with the inputs actually used and any range flags."""

    rate_mm_y: float
    co2_fugacity_bar: float
    temperature_c: float
    ph: float
    wall_shear_pa: float
    flags: list[str] = field(default_factory=list)

    @property
    def upper_bound_only(self) -> bool:
        """True when CO2 fugacity was below the range (rate is an upper bound)."""
        return any(flag.startswith("fugacity below") for flag in self.flags)


def _clamp(value: float, name: str, label: str, flags: list[str]) -> float:
    low, high = RANGES[name]
    if value < low:
        flags.append(f"{label} below range ({value:.3g} < {low:g}); used {low:g}")
        return low
    if value > high:
        flags.append(f"{label} above range ({value:.3g} > {high:g}); used {high:g}")
        return high
    return value


def assess_rate(
    temperature_c: float,
    total_pressure_bara: float,
    gas_co2_mole_fraction: float,
    in_situ_ph: float,
    wall_shear_pa: float,
) -> RateAssessment:
    """Rev. 2 rate for profile use, with out-of-range inputs flagged.

    Out-of-range temperature, pH and shear are moved to the nearest bound.
    CO2 fugacity below 0.1 bar is evaluated at 0.1 bar, so the rate is an
    upper bound; above 10 bar it is evaluated at 10 bar.
    """
    flags: list[str] = []
    t = _clamp(temperature_c, "temperature_c", "temperature", flags)
    p = min(max(total_pressure_bara, 1.0), 1000.0)
    fugacity = fugacity_bar(t, p, min(max(gas_co2_mole_fraction, 0.0), 1.0))
    return _rate_from_fugacity(
        temperature_c, t, fugacity, in_situ_ph, wall_shear_pa, flags
    )


def assess_rate_at_fugacity(
    temperature_c: float,
    co2_fugacity_bar: float,
    in_situ_ph: float,
    wall_shear_pa: float,
) -> RateAssessment:
    """Rev. 2 rate from a known CO2 fugacity (e.g. from an equation of state)."""
    flags: list[str] = []
    t = _clamp(temperature_c, "temperature_c", "temperature", flags)
    return _rate_from_fugacity(
        temperature_c, t, co2_fugacity_bar, in_situ_ph, wall_shear_pa, flags
    )


def _rate_from_fugacity(
    temperature_c: float,
    t: float,
    fugacity: float,
    in_situ_ph: float,
    wall_shear_pa: float,
    flags: list[str],
) -> RateAssessment:
    del temperature_c
    if fugacity < RANGES["fugacity_bar"][0]:
        flags.append(
            f"fugacity below range ({fugacity:.3g} bar); rate evaluated at 0.1 bar "
            "is an upper bound"
        )
        used_fugacity = RANGES["fugacity_bar"][0]
    else:
        used_fugacity = _clamp(fugacity, "fugacity_bar", "CO2 fugacity", flags)
    ph = _clamp(in_situ_ph, "ph", "pH", flags)
    shear = _clamp(wall_shear_pa, "shear_pa", "wall shear stress", flags)
    return RateAssessment(
        rate_mm_y=rate_mm_per_year(t, used_fugacity, ph, shear),
        co2_fugacity_bar=fugacity,
        temperature_c=t,
        ph=ph,
        wall_shear_pa=shear,
        flags=flags,
    )
