"""Reservoir souring screening: seawater fraction, per-well H2S correlations and mixing-zone potential.

Pure Python (standard library only). Screening-level and educational: correlations are
empirical fits to measured data, the mixing-zone model is a substrate-limited bound.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

H2S_PER_SULFATE = 34.081 / 96.06  # mg H2S per mg SO4
H2S_PER_ACETATE = 34.081 / 59.04  # mg H2S per mg acetate (1 acetate : 1 sulfate : 1 H2S)


def seawater_fraction_from_tracer(c_measured: float, c_formation: float, c_seawater: float, clip: bool = True) -> float:
    """Injected-water fraction of produced water from one conservative tracer (Cl, Mg, Br, ...).

    Linear two end-member mixing: c = f * c_sw + (1 - f) * c_fw. Do not use sulfate or barium:
    both are removed by reaction or scaling.
    """
    if math.isclose(c_seawater, c_formation):
        raise ValueError("tracer does not separate the end members")
    f = (c_measured - c_formation) / (c_seawater - c_formation)
    return min(1.0, max(0.0, f)) if clip else f


def seawater_fraction_multi_tracer(
    measured: Dict[str, float], formation: Dict[str, float], seawater: Dict[str, float]
) -> Tuple[float, float]:
    """Least-squares seawater fraction from several tracers, scaled by end-member contrast.

    Returns (fraction, rms residual in fraction units); a large residual flags a tracer that
    is not conservative or an end member that is wrong.
    """
    names = [n for n in measured if n in formation and n in seawater and not math.isclose(formation[n], seawater[n])]
    if not names:
        raise ValueError("no usable tracer common to measured, formation and seawater")
    fs = [(measured[n] - formation[n]) / (seawater[n] - formation[n]) for n in names]
    weights = [abs(seawater[n] - formation[n]) / max(abs(formation[n]), abs(seawater[n]), 1e-12) for n in names]
    wsum = sum(weights)
    f = sum(w * v for w, v in zip(weights, fs)) / wsum
    rms = math.sqrt(sum(w * (v - f) ** 2 for w, v in zip(weights, fs)) / wsum)
    return min(1.0, max(0.0, f)), rms


@dataclass
class Correlation:
    """A fitted H2S-versus-seawater-fraction correlation for one well."""

    well: str
    model: str
    params: Dict[str, float]
    n: int
    rmse: float
    r2: float
    f_min: float
    f_max: float
    aicc: float
    units: str = "ppmv"
    warnings: List[str] = field(default_factory=list)

    def predict(self, f: float) -> float:
        """Evaluate the correlation; negative values are clipped to zero."""
        return max(0.0, _MODELS[self.model][0](f, self.params))

    def to_dict(self) -> dict:
        """JSON-serialisable form for plugging into a model setup."""
        return asdict(self)


def _linear(f: float, p: Dict[str, float]) -> float:
    return p["a"] * f + p.get("b", 0.0)


def _power(f: float, p: Dict[str, float]) -> float:
    return p["a"] * max(f, 0.0) ** p["n"]


def _saturating(f: float, p: Dict[str, float]) -> float:
    return p["a"] * f / (1.0 + p["k"] * f)


def _threshold(f: float, p: Dict[str, float]) -> float:
    return p["a"] * max(f - p["f0"], 0.0)


def _mixing_zone(f: float, p: Dict[str, float]) -> float:
    # substrate limited: sulfate rises with f, donor falls with f; peak where they balance
    return p["a"] * min(f / p["f_star"], (1.0 - f) / (1.0 - p["f_star"])) if 0.0 <= f <= 1.0 else 0.0


_MODELS: Dict[str, Tuple[Callable[[float, Dict[str, float]], float], int]] = {
    "linear": (_linear, 2),
    "power": (_power, 2),
    "saturating": (_saturating, 2),
    "threshold": (_threshold, 2),
    "mixing_zone": (_mixing_zone, 2),
}


def _lstsq_1d(x: Sequence[float], y: Sequence[float], w: Sequence[float], intercept: bool) -> Tuple[float, float]:
    sw = sum(w)
    if intercept:
        mx = sum(wi * xi for wi, xi in zip(w, x)) / sw
        my = sum(wi * yi for wi, yi in zip(w, y)) / sw
        sxx = sum(wi * (xi - mx) ** 2 for wi, xi in zip(w, x))
        a = sum(wi * (xi - mx) * (yi - my) for wi, xi, yi in zip(w, x, y)) / sxx if sxx > 0 else 0.0
        return a, my - a * mx
    sxx = sum(wi * xi * xi for wi, xi in zip(w, x))
    return (sum(wi * xi * yi for wi, xi, yi in zip(w, x, y)) / sxx if sxx > 0 else 0.0), 0.0


def _sse(model: str, params: Dict[str, float], f: Sequence[float], y: Sequence[float], w: Sequence[float]) -> float:
    fn = _MODELS[model][0]
    return sum(wi * (yi - max(0.0, fn(fi, params))) ** 2 for wi, fi, yi in zip(w, f, y))


def _fit_model(model: str, f: Sequence[float], y: Sequence[float], w: Sequence[float]) -> Tuple[Dict[str, float], float]:
    if model == "linear":
        a, b = _lstsq_1d(f, y, w, True)
        params = {"a": a, "b": b}
    elif model == "power":
        best = None
        for i in range(0, 61):
            n = 0.4 + i * 0.05
            xs = [max(fi, 0.0) ** n for fi in f]
            a, _ = _lstsq_1d(xs, y, w, False)
            p = {"a": a, "n": n}
            s = _sse(model, p, f, y, w)
            if best is None or s < best[1]:
                best = (p, s)
        params = best[0]
    elif model == "saturating":
        best = None
        for i in range(0, 121):
            k = i * 0.1
            xs = [fi / (1.0 + k * fi) for fi in f]
            a, _ = _lstsq_1d(xs, y, w, False)
            p = {"a": a, "k": k}
            s = _sse(model, p, f, y, w)
            if best is None or s < best[1]:
                best = (p, s)
        params = best[0]
    elif model == "threshold":
        best = None
        fmax = max(f)
        for i in range(0, 60):
            f0 = i * 0.01 * max(fmax, 1e-9)
            xs = [max(fi - f0, 0.0) for fi in f]
            a, _ = _lstsq_1d(xs, y, w, False)
            p = {"a": a, "f0": f0}
            s = _sse(model, p, f, y, w)
            if best is None or s < best[1]:
                best = (p, s)
        params = best[0]
    elif model == "mixing_zone":
        best = None
        for i in range(2, 99):
            fs = i * 0.01
            xs = [min(fi / fs, (1.0 - fi) / (1.0 - fs)) if 0 <= fi <= 1 else 0.0 for fi in f]
            a, _ = _lstsq_1d(xs, y, w, False)
            p = {"a": a, "f_star": fs}
            s = _sse(model, p, f, y, w)
            if best is None or s < best[1]:
                best = (p, s)
        params = best[0]
    else:
        raise ValueError("unknown model %s" % model)
    return params, _sse(model, params, f, y, w)


def fit_well_correlation(
    well: str,
    f_sw: Sequence[float],
    h2s: Sequence[float],
    models: Optional[Iterable[str]] = None,
    weights: Optional[Sequence[float]] = None,
    units: str = "ppmv",
) -> Correlation:
    """Fit the candidate models to paired (seawater fraction, H2S) data and keep the best by AICc.

    weights allow forgetting of old data (see update_correlation). Needs at least 5 points.
    """
    if len(f_sw) != len(h2s):
        raise ValueError("f_sw and h2s must have equal length")
    pairs = [(float(a), float(b)) for a, b in zip(f_sw, h2s) if a is not None and b is not None and math.isfinite(a) and math.isfinite(b)]
    if len(pairs) < 5:
        raise ValueError("need at least 5 valid (f_sw, H2S) points for %s" % well)
    f = [a for a, _ in pairs]
    y = [b for _, b in pairs]
    w = [1.0] * len(pairs) if weights is None else [float(v) for v in weights][: len(pairs)]
    names = list(models) if models else list(_MODELS)
    n = len(pairs)
    sw = sum(w)
    ybar = sum(wi * yi for wi, yi in zip(w, y)) / sw
    sst = sum(wi * (yi - ybar) ** 2 for wi, yi in zip(w, y))
    best: Optional[Correlation] = None
    for m in names:
        try:
            params, sse = _fit_model(m, f, y, w)
        except ZeroDivisionError:
            continue
        k = _MODELS[m][1]
        eff_n = max(n, k + 2)
        aicc = eff_n * math.log(max(sse / sw, 1e-300)) + 2 * k + (2 * k * (k + 1)) / max(eff_n - k - 1, 1)
        cand = Correlation(
            well=well,
            model=m,
            params=params,
            n=n,
            rmse=math.sqrt(sse / sw),
            r2=1.0 - sse / sst if sst > 0 else 0.0,
            f_min=min(f),
            f_max=max(f),
            aicc=aicc,
            units=units,
        )
        if best is None or cand.aicc < best.aicc:
            best = cand
    if best is None:
        raise ValueError("no model could be fitted for %s" % well)
    if best.f_max < 0.5:
        best.warnings.append("data span f_sw up to %.2f only; extrapolation to higher seawater fraction is unreliable" % best.f_max)
    if best.r2 < 0.5:
        best.warnings.append("R2 %.2f: seawater fraction explains little of the H2S variance" % best.r2)
    return best


def update_correlation(
    previous: Optional[Correlation],
    well: str,
    f_sw: Sequence[float],
    h2s: Sequence[float],
    half_life_points: Optional[float] = None,
    **kwargs,
) -> Correlation:
    """Refit with the new data; optionally forget old points exponentially (half-life in points).

    f_sw and h2s must be time-ordered with the newest last. When previous is given, a warning
    is added if the model family or the prediction at the latest f_sw moved by more than 25 percent.
    """
    w = None
    if half_life_points:
        n = len(f_sw)
        w = [0.5 ** ((n - 1 - i) / half_life_points) for i in range(n)]
    new = fit_well_correlation(well, f_sw, h2s, weights=w, **kwargs)
    if previous is not None:
        f_ref = new.f_max
        a, b = previous.predict(f_ref), new.predict(f_ref)
        if previous.model != new.model:
            new.warnings.append("model changed from %s to %s" % (previous.model, new.model))
        if a > 0 and abs(b - a) / a > 0.25:
            new.warnings.append("prediction at f_sw=%.2f moved %.0f percent" % (f_ref, 100 * (b - a) / a))
    return new


def save_registry(correlations: Iterable[Correlation], path: str) -> None:
    """Write a per-well correlation registry as JSON."""
    data = {c.well: c.to_dict() for c in correlations}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)


def load_registry(path: str) -> Dict[str, Correlation]:
    """Read a registry written by save_registry."""
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    return {k: Correlation(**v) for k, v in raw.items()}


def mixing_zone_h2s_mg_l(
    f_sw: float,
    sulfate_sw_mg_l: float,
    donor_fw_mg_l: float,
    efficiency: float = 1.0,
    sink_fraction: float = 0.0,
    mitigation_factor: float = 1.0,
    temperature_c: Optional[float] = None,
    t_cutoff_c: float = 80.0,
    t_width_c: float = 10.0,
) -> float:
    """Substrate-limited upper bound for biogenic H2S (mg/L produced water) at seawater fraction f_sw.

    Sulfate in the mixture is f * SO4_sw, electron donor (acetate-equivalent VFA) is (1 - f) * donor_fw.
    H2S = min(0.355 * SO4, 0.577 * donor) * efficiency * (1 - sink) * mitigation * thermal factor.
    mitigation_factor scales for sulfate removal or nitrate treatment (1 = none). The thermal
    factor is a logistic cutoff around t_cutoff_c for the mixing-zone temperature.
    """
    if not 0.0 <= f_sw <= 1.0:
        raise ValueError("f_sw must be in [0, 1]")
    for name, v in (("efficiency", efficiency), ("sink_fraction", sink_fraction), ("mitigation_factor", mitigation_factor)):
        if not 0.0 <= v <= 1.0:
            raise ValueError("%s must be in [0, 1]" % name)
    so4 = f_sw * sulfate_sw_mg_l
    donor = (1.0 - f_sw) * donor_fw_mg_l
    thermal = 1.0
    if temperature_c is not None:
        thermal = 1.0 / (1.0 + math.exp((temperature_c - t_cutoff_c) / max(t_width_c / 4.0, 1e-9)))
    return min(H2S_PER_SULFATE * so4, H2S_PER_ACETATE * donor) * efficiency * (1.0 - sink_fraction) * mitigation_factor * thermal


def sulfate_balance_h2s_mg_l(sulfate_in_mg_l: float, sulfate_out_mg_l: float) -> float:
    """H2S upper bound from sulfate consumed between injected and produced water (mg/L basis)."""
    if sulfate_in_mg_l < 0 or sulfate_out_mg_l < 0:
        raise ValueError("sulfate must be non-negative")
    return max(0.0, sulfate_in_mg_l - sulfate_out_mg_l) * H2S_PER_SULFATE


def water_h2s_to_well_stream_rate(h2s_mg_l: float, water_sm3_d: float) -> float:
    """H2S mass rate in kg/d carried by produced water: mg/L times m3/d."""
    return h2s_mg_l * water_sm3_d / 1000.0


def h2s_ppmv_in_gas_from_mass_rate(h2s_kg_d: float, gas_sm3_d: float, gas_fraction_of_h2s: float = 1.0) -> float:
    """Approximate gas H2S ppmv (standard conditions) from an H2S mass rate and the share in gas.

    Uses 23.64 Sm3/kmol (15 C, 1 atm). For accuracy use the partitioning skill.
    """
    if gas_sm3_d <= 0:
        raise ValueError("gas rate must be positive")
    kmol = h2s_kg_d / 34.081
    return kmol * gas_fraction_of_h2s * 23.64 / gas_sm3_d * 1.0e6
