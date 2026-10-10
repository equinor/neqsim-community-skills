"""Extended-reach well screening: build-and-hold path and a Johancsik soft-string torque and drag model.

Educational, public-method screening only. Units: metres, kilonewtons, kilonewton-metres, kg/m, specific gravity.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

G = 9.81


@dataclass(frozen=True)
class DrillString:
    """Drill string and operating limits. Weights are air weights per metre."""

    name: str = "5-7/8 in DP"
    dp_kg_per_m: float = 44.0
    hwdp_kg_per_m: float = 75.0
    hwdp_length_m: float = 150.0
    bha_kg_per_m: float = 190.0
    bha_length_m: float = 90.0
    tool_joint_radius_m: float = 0.089
    torque_limit_knm: float = 55.0


@dataclass(frozen=True)
class WellEnvironment:
    """Hole and fluid basis."""

    kop_m: float = 800.0
    build_rate_deg_per_30m: float = 2.5
    mud_sg: float = 1.40
    ff_cased: float = 0.20
    ff_open: float = 0.25
    shoe_fraction: float = 0.55

    @property
    def buoyancy(self) -> float:
        return 1.0 - self.mud_sg / 7.85


@dataclass(frozen=True)
class ReachResult:
    """Torque-and-drag result for one (TVD, departure) target."""

    tvd_m: float
    departure_m: float
    md_m: float
    hold_inclination_deg: float
    erd_ratio: float
    pickup_kn: float
    slackoff_kn: float
    torque_on_bottom_knm: float
    torque_limit_knm: float
    torque_ok: bool
    slackoff_ok: bool
    limiting: str


def build_hold_profile(tvd: float, departure: float, env: WellEnvironment = WellEnvironment()) -> Optional[Tuple[float, float, float]]:
    """Return (hold inclination deg, measured depth m, build radius m) for a build-and-hold path, or None if unreachable."""
    if tvd <= env.kop_m or departure < 0.0:
        raise ValueError("tvd must exceed the kick-off point and departure must be non-negative")
    radius = 180.0 / (math.pi * env.build_rate_deg_per_30m / 30.0)

    def dep_of(inc_deg: float) -> float:
        ir = math.radians(inc_deg)
        return radius * (1.0 - math.cos(ir)) + (tvd - env.kop_m - radius * math.sin(ir)) * math.tan(ir)

    lo, hi = 0.0, 89.5
    if dep_of(hi) < departure:
        return None
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if dep_of(mid) < departure:
            lo = mid
        else:
            hi = mid
    inc = 0.5 * (lo + hi)
    ir = math.radians(inc)
    md = env.kop_m + radius * ir + (tvd - env.kop_m - radius * math.sin(ir)) / math.cos(ir)
    return inc, md, radius


def survey(tvd: float, departure: float, env: WellEnvironment = WellEnvironment(), step: float = 10.0) -> Optional[Tuple[List[float], List[float], float]]:
    """Stations (md list, inclination list in degrees) and the total measured depth."""
    profile = build_hold_profile(tvd, departure, env)
    if profile is None:
        return None
    inc_hold, md_total, radius = profile
    n = int(math.ceil(md_total / step))
    mds = [md_total * k / n for k in range(n + 1)]
    incs = [0.0 if m <= env.kop_m else min(inc_hold, math.degrees((m - env.kop_m) / radius)) for m in mds]
    return mds, incs, md_total


def _weights(mds: Sequence[float], string: DrillString) -> List[float]:
    total = mds[-1]
    out = []
    for k in range(1, len(mds)):
        mid = 0.5 * (mds[k] + mds[k - 1])
        from_bit = total - mid
        if from_bit <= string.bha_length_m:
            out.append(string.bha_kg_per_m)
        elif from_bit <= string.bha_length_m + string.hwdp_length_m:
            out.append(string.hwdp_kg_per_m)
        else:
            out.append(string.dp_kg_per_m)
    return out


def torque_and_drag(mds: Sequence[float], incs: Sequence[float], string: DrillString, env: WellEnvironment, mode: str,
                    weights: Optional[Sequence[float]] = None, preload_kn: float = 0.0) -> Tuple[float, float]:
    """Soft-string load (kN) and surface torque (kNm), integrated from the bit up.

    mode: ``pickup``, ``slackoff`` or ``rotate``. ``preload_kn`` is a tension applied at the bit (use it for capstan checks).
    """
    if mode not in ("pickup", "slackoff", "rotate"):
        raise ValueError("mode must be pickup, slackoff or rotate")
    w = list(weights) if weights is not None else _weights(mds, string)
    shoe = env.shoe_fraction * mds[-1]
    a = [math.radians(x) for x in incs]
    force = preload_kn * 1000.0
    torque = 0.0
    for k in range(len(mds) - 1, 0, -1):
        dl = mds[k] - mds[k - 1]
        wb = w[k - 1] * G * env.buoyancy
        am = 0.5 * (a[k - 1] + a[k])
        da = a[k] - a[k - 1]
        normal = abs(force * da + wb * dl * math.sin(am))
        mu = env.ff_cased if mds[k] <= shoe else env.ff_open
        force += wb * dl * math.cos(am)
        if mode == "pickup":
            force += mu * normal
        elif mode == "slackoff":
            force -= mu * normal
        else:
            torque += mu * normal * string.tool_joint_radius_m
    return force / 1000.0, torque / 1000.0


def screen_reach(tvd: float, departure: float, string: DrillString = DrillString(), env: WellEnvironment = WellEnvironment()) -> Optional[ReachResult]:
    """Torque-and-drag screening of one target. Returns None when the build-and-hold path cannot reach it."""
    s = survey(tvd, departure, env)
    if s is None:
        return None
    mds, incs, md = s
    pickup, _ = torque_and_drag(mds, incs, string, env, "pickup")
    slackoff, _ = torque_and_drag(mds, incs, string, env, "slackoff")
    _, torque = torque_and_drag(mds, incs, string, env, "rotate")
    on_bottom = 1.10 * torque
    torque_ok = on_bottom <= string.torque_limit_knm
    slack_ok = slackoff > 0.0
    limiting = "none" if torque_ok and slack_ok else ("torque" if not torque_ok else "slack-off (lock-up)")
    inc_hold = build_hold_profile(tvd, departure, env)[0]
    return ReachResult(tvd, departure, md, inc_hold, departure / tvd, pickup, slackoff, on_bottom, string.torque_limit_knm, torque_ok, slack_ok, limiting)


def reach_limit(tvd: float, string: DrillString = DrillString(), env: WellEnvironment = WellEnvironment(), step: float = 250.0,
                max_departure: float = 26000.0) -> float:
    """Largest departure (m, on a ``step`` grid) with torque within the limit and positive slack-off weight."""
    best = 0.0
    dep = step
    while dep <= max_departure:
        r = screen_reach(tvd, dep, string, env)
        if r is None:
            break
        if r.torque_ok and r.slackoff_ok:
            best = dep
        dep += step
    return best


@dataclass
class Assumptions:
    """Human-readable record of the screening basis."""

    items: List[str] = field(default_factory=lambda: [
        "Build-and-hold path, constant build rate from the kick-off point; no azimuth change or drop section.",
        "Johancsik soft-string model with Coulomb friction; tool-joint radius for torque; 10 percent added on bottom.",
        "Friction factors are calibration inputs; calibrate to the longest historic well on the same rig before using a reach.",
        "Hole cleaning, ECD, buckling and casing wear are not modelled.",
    ])
