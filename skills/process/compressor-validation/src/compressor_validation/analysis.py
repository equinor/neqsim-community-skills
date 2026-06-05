from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

R_GAS = 8.314  # J/(mol*K)


def _require_positive(name: str, value: float) -> None:
    if not isinstance(value, (int, float)) or not isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive finite number")


def polytropic_head(
    *,
    p_in: float,
    p_out: float,
    T_in: float,
    MW: float,
    Z: float,
    k: float,
    eta_p: float,
) -> float:
    """Polytropic head in J/kg.

    Parameters use bara for pressures, K for temperature, g/mol for molar mass,
    a dimensionless compressibility ``Z``, isentropic exponent ``k``, and
    polytropic efficiency ``eta_p`` as a fraction in (0, 1].
    """
    _require_positive("p_in", p_in)
    _require_positive("p_out", p_out)
    _require_positive("T_in", T_in)
    _require_positive("MW", MW)
    _require_positive("Z", Z)
    if not (1.0 < k < 2.0):
        raise ValueError("k (isentropic exponent) must be between 1 and 2")
    if not (0.0 < eta_p <= 1.0):
        raise ValueError("eta_p must be a fraction in (0, 1]")

    pressure_ratio = p_out / p_in
    m = (k - 1.0) / (k * eta_p)
    mw_kg = MW / 1000.0  # g/mol -> kg/mol
    return (Z * R_GAS * T_in / mw_kg) * (1.0 / m) * (pressure_ratio ** m - 1.0)


@dataclass(frozen=True)
class ChartTuning:
    """Multiplicative tuning applied to curve flow/head/efficiency and shaft power."""

    flow_mult: float = 1.0
    head_mult: float = 1.0
    eff_mult: float = 1.0
    shaft_adder_pct: float = 0.0


@dataclass(frozen=True)
class Drivetrain:
    """Simple drivetrain: gear ratio and a fractional mechanical loss."""

    gear_ratio: float = 1.0
    mechanical_loss_frac: float = 0.0

    def shaft_power(self, gas_power_W: float) -> float:
        if not (0.0 <= self.mechanical_loss_frac < 1.0):
            raise ValueError("mechanical_loss_frac must be in [0, 1)")
        return gas_power_W / (1.0 - self.mechanical_loss_frac)


def _interp_line(points: list[tuple[float, float, float]], flow: float):
    """Linear interpolation of (head, efficiency) along one speed line by flow.

    Returns ``(head, efficiency, extrapolated)``.
    """
    ordered = sorted(points, key=lambda p: p[0])
    flows = [p[0] for p in ordered]
    extrapolated = flow < flows[0] or flow > flows[-1]

    if flow <= flows[0]:
        _, head, eff = ordered[0]
        return head, eff, extrapolated
    if flow >= flows[-1]:
        _, head, eff = ordered[-1]
        return head, eff, extrapolated

    for (f0, h0, e0), (f1, h1, e1) in zip(ordered, ordered[1:]):
        if f0 <= flow <= f1:
            t = (flow - f0) / (f1 - f0)
            return h0 + t * (h1 - h0), e0 + t * (e1 - e0), extrapolated
    # Should not reach here
    _, head, eff = ordered[-1]
    return head, eff, extrapolated


@dataclass(frozen=True)
class CurveResult:
    head: float
    efficiency: float
    extrapolated: bool


class CompressorCurve:
    """Centrifugal compressor performance map: speed -> [(flow, head, eff), ...]."""

    def __init__(
        self,
        speed_lines: dict[float, list[tuple[float, float, float]]],
        tuning: ChartTuning | None = None,
    ) -> None:
        if not speed_lines:
            raise ValueError("speed_lines must not be empty")
        for speed, points in speed_lines.items():
            if len(points) < 2:
                raise ValueError(f"speed line {speed} needs at least 2 points")
        self.speed_lines = {float(s): list(pts) for s, pts in speed_lines.items()}
        self.tuning = tuning or ChartTuning()

    def _nearest_speed(self, speed: float) -> float:
        return min(self.speed_lines, key=lambda s: abs(s - speed))

    def evaluate(self, flow: float, speed: float) -> CurveResult:
        """Return tuned head and efficiency at ``flow`` (volumetric) and ``speed`` (rpm).

        Between speed lines, the nearest line is scaled by the fan laws:
        flow ~ N, head ~ N^2.
        """
        _require_positive("flow", flow)
        _require_positive("speed", speed)

        ref_speed = self._nearest_speed(speed)
        ratio = speed / ref_speed
        # Map the requested flow back onto the reference line (flow ~ N).
        ref_flow = flow / ratio
        head_ref, eff, extrapolated = _interp_line(self.speed_lines[ref_speed], ref_flow)
        # Head scales with N^2.
        head = head_ref * ratio * ratio

        t = self.tuning
        return CurveResult(
            head=head * t.head_mult,
            efficiency=min(eff * t.eff_mult, 1.0),
            extrapolated=extrapolated,
        )


def gas_power(mass_flow: float, head_J_per_kg: float, efficiency: float) -> float:
    """Gas power in W from mass flow (kg/s), polytropic head (J/kg), efficiency."""
    _require_positive("mass_flow", mass_flow)
    if not (0.0 < efficiency <= 1.0):
        raise ValueError("efficiency must be a fraction in (0, 1]")
    return mass_flow * head_J_per_kg / efficiency


@dataclass(frozen=True)
class OperatingPoint:
    measured_head: float
    curve_head: float
    head_deviation_pct: float
    efficiency: float
    gas_power_W: float
    shaft_power_W: float
    extrapolated: bool


def evaluate_operating_point(
    curve: CompressorCurve,
    *,
    flow: float,
    speed: float,
    mass_flow: float,
    p_in: float,
    p_out: float,
    T_in: float,
    MW: float,
    Z: float,
    k: float,
    tuning: ChartTuning | None = None,
    drivetrain: Drivetrain | None = None,
) -> OperatingPoint:
    """Compare a measured operating point against a performance curve.

    The curve efficiency is used to compute the measured polytropic head so that
    measured and curve heads are on a consistent efficiency basis.
    """
    if tuning is not None:
        curve = CompressorCurve(curve.speed_lines, tuning=tuning)
    drivetrain = drivetrain or Drivetrain()

    curve_result = curve.evaluate(flow=flow, speed=speed)
    measured_head = polytropic_head(
        p_in=p_in, p_out=p_out, T_in=T_in, MW=MW, Z=Z, k=k,
        eta_p=curve_result.efficiency,
    )
    deviation = (curve_result.head - measured_head) / (abs(measured_head) + 1e-12) * 100.0

    gp = gas_power(mass_flow, curve_result.head, curve_result.efficiency)
    sp = drivetrain.shaft_power(gp)
    if curve.tuning.shaft_adder_pct:
        sp *= 1.0 + curve.tuning.shaft_adder_pct / 100.0

    return OperatingPoint(
        measured_head=measured_head,
        curve_head=curve_result.head,
        head_deviation_pct=deviation,
        efficiency=curve_result.efficiency,
        gas_power_W=gp,
        shaft_power_W=sp,
        extrapolated=curve_result.extrapolated,
    )
