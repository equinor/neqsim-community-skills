"""Inflow-control device pressure drops, as OPM Flow evaluates the keywords that completor writes.

Units follow a METRIC deck: rates in reservoir m3/day per device, densities in kg/m3, viscosities in cP and
pressure drops in bar. Fractions are in-situ volume fractions of oil, water and gas at the device.

Equations (OPM Flow ``MultisegmentWellSegments``):

- AICD (``WSEGAICD``): ``dP = S * rho_mix * (rho_mix/rho_cal)^z * (mu_cal/mu_mix)^y * q^x`` with
  ``rho_mix = fo^a rho_o + fw^b rho_w + fg^c rho_g`` and ``mu_mix = fo^d mu_o + fw^e mu_w + fg^f mu_g``.
- Spiral ICD (``WSEGSICD``): ``dP = S * (rho/rho_cal)^0.75 * (mu/mu_cal)^0.25 * q^2``; the liquid viscosity is an
  emulsion viscosity switching from water-in-oil to oil-in-water around the critical water cut.
- Nozzle valve (``WSEGVALV``): ``dP = rho v^2 / (2 Cv^2)`` with ``v = q / Ac``; pipe friction is not included.
- Density-switched valve (``WSEGDENSITY``, DAR type): a valve whose area is the oil, water or gas nozzle area
  depending on the water and gas fractions. Steady screening uses the closing thresholds and ignores hysteresis.
"""

from __future__ import annotations

from dataclasses import MISSING, asdict, dataclass
from typing import Tuple, Union

SECONDS_PER_DAY = 86400.0
PA_PER_BAR = 1.0e5

Fractions = Tuple[float, float, float]


@dataclass(frozen=True)
class PhaseProperties:
    """Reservoir-condition phase properties at the device."""

    oil_density: float
    water_density: float
    gas_density: float
    oil_viscosity: float
    water_viscosity: float
    gas_viscosity: float

    def mixture_density(self, fractions: Fractions) -> float:
        fo, fw, fg = _check_fractions(fractions)
        return fo * self.oil_density + fw * self.water_density + fg * self.gas_density


@dataclass(frozen=True)
class Aicd:
    """Autonomous ICD (RCP form). ``strength`` is completor's alpha (WSEGAICD item 4)."""

    strength: float
    x: float
    y: float
    a: float = 1.0
    b: float = 1.0
    c: float = 1.0
    d: float = 1.0
    e: float = 1.0
    f: float = 1.0
    rho_cal: float = 1000.25
    mu_cal: float = 1.45
    z: float = 1.0
    kind: str = "AICD"


@dataclass(frozen=True)
class Sicd:
    """Spiral (channel) ICD. ``strength`` in bar/(rm3/day)^2."""

    strength: float
    rho_cal: float = 1000.25
    mu_cal: float = 1.45
    critical_value: float = 0.5
    width: float = 0.05
    max_visc_ratio: float = 5.0
    kind: str = "ICD"


@dataclass(frozen=True)
class Valve:
    """Nozzle ICD or valve. ``ac`` is the flow area in m2."""

    cv: float
    ac: float
    kind: str = "VALVE"


@dataclass(frozen=True)
class DensityValve:
    """Density-activated recovery (DAR) type device modelled as a switched valve."""

    cv: float
    ac_oil: float
    ac_gas: float
    ac_water: float
    wvf_low: float
    wvf_high: float
    gvf_low: float
    gvf_high: float
    kind: str = "DENSITY"

    def active_area(self, fractions: Fractions) -> Tuple[float, str]:
        """Area and state for a steady segment (closing thresholds, no hysteresis)."""
        _, fw, fg = _check_fractions(fractions)
        if fg > self.gvf_high:
            return self.ac_gas, "gas"
        if fw > self.wvf_high:
            return self.ac_water, "water"
        return self.ac_oil, "oil"


Device = Union[Aicd, Sicd, Valve, DensityValve]


def _check_fractions(fractions: Fractions) -> Fractions:
    fo, fw, fg = (float(v) for v in fractions)
    if min(fo, fw, fg) < -1e-12 or abs(fo + fw + fg - 1.0) > 1e-6:
        raise ValueError(
            f"phase fractions must be non-negative and sum to 1, got {fractions}"
        )
    return max(fo, 0.0), max(fw, 0.0), max(fg, 0.0)


def _pow(base: float, exponent: float) -> float:
    return base**exponent if base > 0.0 else 0.0


def _wio_viscosity(
    oil_viscosity: float, water_liquid_fraction: float, max_ratio: float
) -> float:
    ratio = (1.0 / (1.0 - (0.8415 / 0.7480) * water_liquid_fraction)) ** 2.5
    return oil_viscosity * min(ratio, max_ratio)


def _oiw_viscosity(
    water_viscosity: float, water_liquid_fraction: float, max_ratio: float
) -> float:
    ratio = (1.0 / (1.0 - (0.6019 / 0.6410) * (1.0 - water_liquid_fraction))) ** 2.5
    return water_viscosity * min(ratio, max_ratio)


def emulsion_viscosity(
    fo: float, fw: float, props: PhaseProperties, device: Sicd
) -> float:
    """Liquid emulsion viscosity used by the spiral ICD (OPM ``emulsionViscosity``)."""
    liquid = fo + fw
    if liquid <= 0.0:
        return 0.0
    wlf = fw / liquid
    start = device.critical_value - device.width / 2.0
    end = device.critical_value + device.width / 2.0
    if wlf <= start:
        return _wio_viscosity(props.oil_viscosity, wlf, device.max_visc_ratio)
    if wlf >= end:
        return _oiw_viscosity(props.water_viscosity, wlf, device.max_visc_ratio)
    v_start = _wio_viscosity(props.oil_viscosity, start, device.max_visc_ratio)
    v_end = _oiw_viscosity(props.water_viscosity, end, device.max_visc_ratio)
    return (v_start * (end - wlf) + v_end * (wlf - start)) / device.width


def aicd_mixture(
    device: Aicd, fractions: Fractions, props: PhaseProperties
) -> Tuple[float, float]:
    """AICD mixture density (kg/m3) and viscosity (cP)."""
    fo, fw, fg = _check_fractions(fractions)
    rho = (
        _pow(fo, device.a) * props.oil_density
        + _pow(fw, device.b) * props.water_density
        + _pow(fg, device.c) * props.gas_density
    )
    mu = (
        _pow(fo, device.d) * props.oil_viscosity
        + _pow(fw, device.e) * props.water_viscosity
        + _pow(fg, device.f) * props.gas_viscosity
    )
    return rho, mu


def pressure_drop_bar(
    device: Device, rate_rm3_day: float, fractions: Fractions, props: PhaseProperties
) -> float:
    """Pressure drop across one device for a reservoir volume rate through that device."""
    q = abs(float(rate_rm3_day))
    if q == 0.0:
        return 0.0
    fo, fw, fg = _check_fractions(fractions)
    if isinstance(device, Aicd):
        rho, mu = aicd_mixture(device, fractions, props)
        if rho <= 0.0 or mu <= 0.0:
            raise ValueError(
                "AICD mixture density and viscosity must be positive; check exponents and fractions"
            )
        return (
            device.strength
            * rho
            * (rho / device.rho_cal) ** device.z
            * (device.mu_cal / mu) ** device.y
            * q**device.x
        )
    if isinstance(device, Sicd):
        rho = props.mixture_density(fractions)
        liquid = fo + fw
        if liquid < 1e-30:
            mu = fg * props.gas_viscosity
        else:
            mu = (
                liquid * emulsion_viscosity(fo, fw, props, device)
                + fg * props.gas_viscosity
            )
        return (
            device.strength
            * (rho / device.rho_cal) ** 0.75
            * (mu / device.mu_cal) ** 0.25
            * q
            * q
        )
    if isinstance(device, (Valve, DensityValve)):
        area = (
            device.ac if isinstance(device, Valve) else device.active_area(fractions)[0]
        )
        rho = props.mixture_density(fractions)
        velocity = q / SECONDS_PER_DAY / area
        return rho * velocity * velocity / (2.0 * device.cv * device.cv) / PA_PER_BAR
    raise TypeError(f"unsupported device {type(device).__name__}")


def rate_for_pressure_drop(
    device: Device,
    dp_bar: float,
    fractions: Fractions,
    props: PhaseProperties,
    upper_rm3_day: float = 1.0e6,
) -> float:
    """Reservoir rate per device that gives ``dp_bar`` (bisection; the drop rises monotonically with rate)."""
    if dp_bar <= 0.0:
        return 0.0
    lo, hi = 0.0, 1.0
    while pressure_drop_bar(device, hi, fractions, props) < dp_bar:
        hi *= 2.0
        if hi > upper_rm3_day:
            return upper_rm3_day
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if pressure_drop_bar(device, mid, fractions, props) < dp_bar:
            lo = mid
        else:
            hi = mid
        if hi - lo <= 1e-10 * max(hi, 1.0):
            break
    return 0.5 * (lo + hi)


def single_phase_drops(
    device: Device, rate_rm3_day: float, props: PhaseProperties
) -> dict:
    """Pressure drop for pure oil, water and gas at the same rate, and the water and gas choking ratios."""
    oil = pressure_drop_bar(device, rate_rm3_day, (1.0, 0.0, 0.0), props)
    water = pressure_drop_bar(device, rate_rm3_day, (0.0, 1.0, 0.0), props)
    gas = pressure_drop_bar(device, rate_rm3_day, (0.0, 0.0, 1.0), props)
    return {
        "rate_rm3_day": rate_rm3_day,
        "dp_oil_bar": oil,
        "dp_water_bar": water,
        "dp_gas_bar": gas,
        "water_to_oil_dp_ratio": water / oil if oil > 0 else None,
        "gas_to_oil_dp_ratio": gas / oil if oil > 0 else None,
    }


def calibrate_strength(
    device: Device,
    design_rate_rm3_day: float,
    design_dp_bar: float,
    props: PhaseProperties,
    fractions: Fractions = (1.0, 0.0, 0.0),
) -> Device:
    """Return a copy of an AICD or spiral ICD whose strength gives ``design_dp_bar`` at the design rate.

    The exponents stay as given; only the strength is scaled. Use it to size a screening device from a design
    point when vendor strength is not available, and say so.
    """
    if not isinstance(device, (Aicd, Sicd)):
        raise TypeError("strength calibration applies to AICD and spiral ICD devices")
    current = pressure_drop_bar(device, design_rate_rm3_day, fractions, props)
    if current <= 0.0:
        raise ValueError("device gives no pressure drop at the design point")
    values = asdict(device)
    values["strength"] = device.strength * design_dp_bar / current
    return type(device)(**values)


DEVICE_CLASSES = {"AICD": Aicd, "ICD": Sicd, "VALVE": Valve, "DENSITY": DensityValve}


def device_from_dict(kind: str, values: dict) -> Device:
    """Build a device from a dict whose keys match the dataclass fields (``number`` and others are ignored)."""
    cls = DEVICE_CLASSES.get(kind.upper())
    if cls is None:
        raise ValueError(
            f"device type {kind} is not supported (AICD, ICD, VALVE, DENSITY)"
        )
    allowed = set(cls.__dataclass_fields__) - {"kind"}
    missing = [
        f
        for f, spec in cls.__dataclass_fields__.items()
        if f != "kind" and spec.default is MISSING and f not in values
    ]
    if missing:
        raise ValueError(f"{kind} device needs {', '.join(missing)}")
    return cls(**{k: float(v) for k, v in values.items() if k in allowed})
