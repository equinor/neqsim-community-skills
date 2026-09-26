"""Supply side: history, forecast and discovery profiles for every NCS entity.

* Producing fields: Sodir yearly net production (history), then a forecast.
  The forecast uses an Arps decline fitted from the peak
  (``neqsim-norwegian-continental-shelf-data`` ``fit_arps_decline`` when
  installed, with a built-in exponential fit as fallback). Fields still on
  plateau hold their last rate. Future volume is capped at Sodir remaining
  reserves.
* Discoveries: a screening build-up / plateau / decline profile sized from Sodir
  recoverable volumes. Start year is phased by maturity status.
* Enterprise or user forecasts (e.g. RNB) replace any entity's profile via
  the scenario (``forecast_overrides``).

Units: gas MSm3/d, liquid (oil + condensate) Sm3/d, both as annual averages.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

GSM3_YR_TO_MSM3_D = 1000.0 / 365.0
MSM3_YR_TO_SM3_D = 1.0e6 / 365.0
# volume factors: reserves unit -> (rate unit x days)
GAS_VOLUME_FACTOR = 1000.0   # GSm3 -> MSm3 (gas rate in MSm3/d)
LIQUID_VOLUME_FACTOR = 1.0e6  # MSm3 -> Sm3 (liquid rate in Sm3/d)

# Years after the reference year before a discovery can produce, by Sodir status.
DISCOVERY_START_OFFSET: Dict[str, Optional[int]] = {
    "Production decided": 2,
    "Approved for production": 2,
    "Production in clarification phase": 4,
    "Production likely, but unclarified": 7,
    "Production not evaluated": None,  # excluded unless explicitly included
    "Production is unlikely": None,
}

# Sodir RC -> development maturity used to label the profile
RC_LABEL = {"3F": "approved", "4F": "in planning", "5F": "likely", "7F": "not evaluated"}


@dataclass
class EntityProfile:
    entity: str
    kind: str  # "field" | "discovery"
    gas_msm3d: Dict[int, float] = field(default_factory=dict)
    liquid_sm3d: Dict[int, float] = field(default_factory=dict)
    method: Dict[str, str] = field(default_factory=dict)
    capped_by_reserves: Dict[str, bool] = field(default_factory=dict)
    start_year: Optional[int] = None

    def rate(self, year: int, medium: str) -> float:
        series = self.gas_msm3d if medium == "gas" else self.liquid_sm3d
        return series.get(year, 0.0)

    def to_dict(self) -> Dict[str, Any]:
        return {"entity": self.entity, "kind": self.kind, "start_year": self.start_year, "method": self.method,
                "capped_by_reserves": self.capped_by_reserves,
                "gas_msm3d": {str(k): round(v, 4) for k, v in sorted(self.gas_msm3d.items())},
                "liquid_sm3d": {str(k): round(v, 2) for k, v in sorted(self.liquid_sm3d.items())}}


def _exp_decline(points: List[Tuple[float, float]]) -> Optional[Tuple[float, float]]:
    """(qi at last point, decline 1/yr) from a log-linear fit of the post-peak series."""
    if len(points) < 3:
        return None
    peak = max(range(len(points)), key=lambda i: points[i][1])
    window = [(t, q) for t, q in points[peak:] if q > 0]
    if len(window) < 3:
        return None
    n = len(window)
    xs = [t for t, _ in window]
    ys = [math.log(q) for _, q in window]
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    if slope >= 0:
        return None
    return window[-1][1], -slope


def _decline_from_arps(points: List[Tuple[float, float]]) -> Optional[Tuple[float, float, str]]:
    """Effective annual decline from the community Arps fit, if available."""
    try:
        from norwegian_continental_shelf_data.decline import fit_arps_decline  # type: ignore
    except ImportError:
        fit = _exp_decline(points)
        return (fit[0], fit[1], "exponential (built-in)") if fit else None
    try:
        arps = fit_arps_decline(points, from_peak=True)
    except ValueError:
        return None
    if arps.decline_rate_per_year <= 0:
        return None
    # tangent decline at the last observed point
    t_last = points[-1][0] - arps.peak_time
    di, b = arps.decline_rate_per_year, arps.b_exponent
    d_now = di / (1.0 + b * di * t_last) if b > 0 else di
    return points[-1][1], d_now, f"arps-{arps.model} (b={b:.2f}, R2={arps.r_squared:.2f})"


def forecast_series(history: Dict[int, float], *, last_year: int, end_year: int,
                    remaining: Optional[float], volume_factor: float, min_decline: float = 0.04,
                    plateau_decline: float = 0.12, window_years: int = 10,
                    economic_limit_fraction: float = 0.02) -> Tuple[Dict[int, float], str, bool]:
    """Forecast one commodity for years ``last_year+1..end_year``.

    ``history`` maps year to average daily rate; ``remaining`` is remaining
    reserves; ``volume_factor`` converts it to rate x days (gas 1000, liquid 1e6).
    """
    pts = [(float(y), q) for y, q in sorted(history.items()) if last_year - window_years < y <= last_year]
    base = history.get(last_year, 0.0)
    if base <= 0:
        return {}, "no recent production", False
    fitted = _decline_from_arps(pts)
    if fitted:
        q0, decline, method = fitted
        decline = max(decline, min_decline)
    else:
        q0, decline, method = base, 0.0, "plateau (no decline yet)"
    budget = remaining * volume_factor if remaining and remaining > 0 else None  # rate-days available
    peak = max(history.values())
    out: Dict[int, float] = {}
    used = 0.0
    rate = q0
    capped = False
    plateau = decline == 0.0
    for year in range(last_year + 1, end_year + 1):
        if plateau and budget is not None and used > 0.6 * budget:
            plateau, decline = False, plateau_decline  # plateau ends when ~60 % of reserves are gone
            method += f" -> decline {plateau_decline:.0%}/yr"
        rate = rate if plateau else rate * math.exp(-decline)
        if rate < economic_limit_fraction * peak:
            break
        take = rate * 365.0
        if budget is not None and used + take > budget:
            left = max(budget - used, 0.0)
            capped = True
            if left > 0:
                out[year] = left / 365.0
            break
        out[year] = rate
        used += take
    return out, method, capped


def discovery_profile(recoverable: float, *, volume_factor: float, start_year: int, end_year: int,
                      plateau_fraction: float = 0.12, plateau_years: int = 4, decline: float = 0.15) -> Dict[int, float]:
    """Screening profile: one build-up year at 50 %, plateau at ``plateau_fraction``/yr, exponential decline."""
    if not recoverable or recoverable <= 0:
        return {}
    budget = recoverable * volume_factor
    plateau_rate = budget * plateau_fraction / 365.0
    out: Dict[int, float] = {}
    used, year, rate = 0.0, start_year, plateau_rate * 0.5
    phase_year = 0
    while year <= end_year and used < budget * 0.999:
        if phase_year == 1:
            rate = plateau_rate
        elif phase_year > plateau_years:
            rate *= math.exp(-decline)
        take = min(rate * 365.0, budget - used)
        if take / 365.0 < 0.02 * plateau_rate:
            break
        out[year] = take / 365.0
        used += take
        year += 1
        phase_year += 1
    return out


def build_supply(network: Any, *, reference_year: Optional[int] = None, end_year: int = 2045,
                 include_discoveries: bool = True, include_not_evaluated: bool = False,
                 overrides: Optional[Dict[str, Dict[str, Dict[str, float]]]] = None) -> Dict[str, EntityProfile]:
    """Profiles for every field and candidate discovery in an ``NcsNetwork``.

    ``reference_year`` is the last complete production year (default: snapshot
    year minus one). ``overrides`` = ``{entity: {"gas_msm3d": {year: v}, "liquid_sm3d": {...}}}``.
    """
    if reference_year is None:
        generated = str(network.snapshot.get("generated_utc", ""))[:4]
        reference_year = (int(generated) - 1) if generated.isdigit() else 2025
    profiles: Dict[str, EntityProfile] = {}
    for fid, fld in network.fields.items():
        prod = fld.get("production", {})
        gas_hist = {int(y): r.get("gas_bsm3", 0.0) * GSM3_YR_TO_MSM3_D for y, r in prod.items()
                    if int(y) <= reference_year}
        liq_hist = {int(y): (r.get("oil_msm3", 0.0) + r.get("condensate_msm3", 0.0)) * MSM3_YR_TO_SM3_D
                    for y, r in prod.items() if int(y) <= reference_year}
        res = fld.get("reserves", {})
        prof = EntityProfile(fid, "field")
        prof.gas_msm3d.update(gas_hist)
        prof.liquid_sm3d.update(liq_hist)
        g, gm, gc = forecast_series(gas_hist, last_year=reference_year, end_year=end_year,
                                    remaining=res.get("remaining_gas_bsm3"), volume_factor=GAS_VOLUME_FACTOR)
        liq_rem = (res.get("remaining_oil_msm3") or 0.0) + (res.get("remaining_condensate_msm3") or 0.0)
        lq, lm, lc = forecast_series(liq_hist, last_year=reference_year, end_year=end_year,
                                     remaining=liq_rem or None, volume_factor=LIQUID_VOLUME_FACTOR)
        prof.gas_msm3d.update(g)
        prof.liquid_sm3d.update(lq)
        prof.method = {"gas": gm, "liquid": lm, "history_to": str(reference_year)}
        prof.capped_by_reserves = {"gas": gc, "liquid": lc}
        profiles[fid] = prof

    if include_discoveries:
        for did, disc in network.discoveries.items():
            offset = DISCOVERY_START_OFFSET.get(disc.get("status"))
            if offset is None:
                if not (include_not_evaluated and disc.get("status") == "Production not evaluated"):
                    continue
                offset = 9
            res = disc.get("reserves", {})
            start = reference_year + offset
            prof = EntityProfile(did, "discovery", start_year=start)
            prof.gas_msm3d = discovery_profile(res.get("gas_bsm3") or 0.0, volume_factor=GAS_VOLUME_FACTOR,
                                               start_year=start, end_year=end_year)
            liq = (res.get("oil_msm3") or 0.0) + (res.get("condensate_msm3") or 0.0)
            prof.liquid_sm3d = discovery_profile(liq, volume_factor=LIQUID_VOLUME_FACTOR, start_year=start,
                                                 end_year=end_year)
            if not prof.gas_msm3d and not prof.liquid_sm3d:
                continue
            prof.method = {"profile": "screening build-up/plateau/decline",
                           "status": str(disc.get("status")), "rc": str(res.get("rc"))}
            profiles[did] = prof

    for entity, series in (overrides or {}).items():
        prof = profiles.setdefault(entity, EntityProfile(entity, "field"))
        for key in ("gas_msm3d", "liquid_sm3d"):
            if key in series:
                getattr(prof, key).update({int(y): float(v) for y, v in series[key].items()})
                prof.method[key.split("_")[0]] = "scenario override"
    return profiles


def total_supply(profiles: Dict[str, EntityProfile], year: int) -> Dict[str, float]:
    return {"gas_msm3d": sum(p.rate(year, "gas") for p in profiles.values()),
            "liquid_sm3d": sum(p.rate(year, "liquid") for p in profiles.values())}
