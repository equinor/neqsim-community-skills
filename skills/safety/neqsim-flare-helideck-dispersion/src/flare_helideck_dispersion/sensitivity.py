"""Sensitivity studies: tip-inclination scan, tornado and seeded Monte Carlo.

Every evaluation re-runs the full wind sweep in the ``briggs`` plume mode with changed
model parameters and returns the flight-path peak, the conditional exceedance hours at
20 and 10 percent of the LFL, and the helideck and into-wind peaks. The helideck result
for cold, dense gas is sensitive to the tip inclination; the scan over 20 to 70 degrees
must always be reported next to the base result.

Parameters that can be varied:

* ``tilt_deg``: flare-tip inclination above horizontal.
* ``sigma0_divisor``: virtual-source spread divisor (``sigma0 = dh / divisor``).
* ``wind_exponent``: power-law exponent of the wind profile.
* ``mass_flow_scale``: multiplier on the release mass flow. For a case with a
  ``tip_override`` the jet momentum is fixed, so the scale only changes the
  concentration source term.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from .model import Release, ReleaseCase
from .receptors import Receptors
from .study import StudySettings, exceedance_pct, run_case
from .wind import WindTable

DEFAULT_RANGES: dict[str, tuple[float, float]] = {
    "tilt_deg": (40.0, 50.0),
    "sigma0_divisor": (2.0, 7.0),
    "wind_exponent": (0.08, 0.14),
    "mass_flow_scale": (0.8, 1.2),
}
"""Default low and high values of the varied parameters."""

DEFAULT_TILTS = (20.0, 25.0, 30.0, 35.0, 40.0, 55.0, 70.0)
"""Tip inclinations of the scan, degrees; the base value is added automatically."""

PARAMETER_LABELS = {
    "tilt_deg": "Tip inclination %g-%g deg (base %g)",
    "sigma0_divisor": "Initial spread sigma0 = dh/%g ... dh/%g (base %g)",
    "wind_exponent": "Wind profile exponent %g-%g (base %g)",
    "mass_flow_scale": "Release rate x%g ... x%g (base x%g)",
}


def evaluate(
    case: ReleaseCase,
    wind: WindTable,
    receptors: Receptors,
    settings: StudySettings,
    overrides: Mapping[str, float] | None = None,
) -> dict[str, float]:
    """Run the wind sweep once with parameter overrides.

    Args:
        case: Release case.
        wind: Joint wind table.
        receptors: Receptor set.
        settings: Base study settings (the ``briggs`` mode is used).
        overrides: Parameter values replacing the base ones (keys of
            :data:`DEFAULT_RANGES`).

    Returns:
        Dictionary with ``peak_any_path``, ``hours_ge20``, ``hours_ge10``,
        ``helideck_peak`` and ``into_wind_peak``.

    Raises:
        ValueError: If an override key is unknown.
    """
    overrides = dict(overrides or {})
    unknown = set(overrides) - set(DEFAULT_RANGES)
    if unknown:
        raise ValueError(f"unknown sensitivity parameters {sorted(unknown)}")
    scale = overrides.pop("mass_flow_scale", 1.0)
    params = settings.params.replace(**overrides) if overrides else settings.params
    run_settings = dataclasses.replace(settings, params=params, modes=("briggs",))
    scaled = dataclasses.replace(case, mass_flow_kg_s=case.mass_flow_kg_s * scale)
    arr = run_case(Release(scaled, params), wind, receptors, run_settings, "briggs")
    return {
        "peak_any_path": float(arr.any_path.max()),
        "hours_ge20": exceedance_pct(arr.any_path, wind, 20.0),
        "hours_ge10": exceedance_pct(arr.any_path, wind, 10.0),
        "helideck_peak": float(arr.deck.max()),
        "into_wind_peak": float(arr.into_wind.max()),
    }


def tilt_scan(
    case: ReleaseCase,
    wind: WindTable,
    receptors: Receptors,
    settings: StudySettings,
    tilts_deg: Sequence[float] = DEFAULT_TILTS,
) -> list[dict[str, float]]:
    """Scan the tip inclination and report peaks and exceedance hours.

    Args:
        case: Release case.
        wind: Joint wind table.
        receptors: Receptor set.
        settings: Base study settings.
        tilts_deg: Inclinations to evaluate, degrees; the base inclination is added.

    Returns:
        One row per inclination in ascending order.
    """
    tilts = sorted({float(t) for t in tilts_deg} | {settings.params.tilt_deg})
    rows = []
    for tilt in tilts:
        r = evaluate(case, wind, receptors, settings, {"tilt_deg": tilt})
        rows.append({"tilt_deg": tilt, **r})
    return rows


def tornado(
    case: ReleaseCase,
    wind: WindTable,
    receptors: Receptors,
    settings: StudySettings,
    ranges: Mapping[str, tuple[float, float]] | None = None,
) -> list[dict[str, Any]]:
    """One-at-a-time low/high variation of each parameter.

    Args:
        case: Release case.
        wind: Joint wind table.
        receptors: Receptor set.
        settings: Base study settings.
        ranges: Parameter ranges (defaults to :data:`DEFAULT_RANGES`).

    Returns:
        Entries sorted by decreasing swing in the exceedance of 20 percent of the LFL.
    """
    ranges = dict(ranges or DEFAULT_RANGES)
    base_values = {
        "tilt_deg": settings.params.tilt_deg,
        "sigma0_divisor": settings.params.sigma0_divisor,
        "wind_exponent": settings.params.wind_exponent,
        "mass_flow_scale": 1.0,
    }
    out = []
    for key, (lo, hi) in ranges.items():
        low = evaluate(case, wind, receptors, settings, {key: lo})
        high = evaluate(case, wind, receptors, settings, {key: hi})
        out.append(
            {
                "parameter_key": key,
                "parameter": PARAMETER_LABELS[key] % (lo, hi, base_values[key]),
                "low_input": lo,
                "high_input": hi,
                "peak_low": low["peak_any_path"],
                "peak_high": high["peak_any_path"],
                "hours20_low": low["hours_ge20"],
                "hours20_high": high["hours_ge20"],
                "hours10_low": low["hours_ge10"],
                "hours10_high": high["hours_ge10"],
                "swing_hours10": abs(high["hours_ge10"] - low["hours_ge10"]),
                "swing_hours20": abs(high["hours_ge20"] - low["hours_ge20"]),
            }
        )
    return sorted(out, key=lambda t: -t["swing_hours20"])


def _percentiles(values: np.ndarray) -> dict[str, float]:
    """Return P10, P50 and P90 of a sample."""
    return {
        "p10": float(np.percentile(values, 10)),
        "p50": float(np.percentile(values, 50)),
        "p90": float(np.percentile(values, 90)),
    }


def monte_carlo(
    case: ReleaseCase,
    wind: WindTable,
    receptors: Receptors,
    settings: StudySettings,
    n_samples: int = 100,
    seed: int = 42,
    ranges: Mapping[str, tuple[float, float]] | None = None,
) -> dict[str, Any]:
    """Uniform Monte Carlo over the parameter ranges with a fixed seed.

    Args:
        case: Release case.
        wind: Joint wind table.
        receptors: Receptor set.
        settings: Base study settings.
        n_samples: Number of samples.
        seed: Seed of the random generator (results are reproducible).
        ranges: Parameter ranges (defaults to :data:`DEFAULT_RANGES`).

    Returns:
        Dictionary with the sample count, seed and P10/P50/P90 of the outputs.
    """
    ranges = dict(ranges or DEFAULT_RANGES)
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n_samples):
        draw = {k: float(rng.uniform(*v)) for k, v in ranges.items()}
        r = evaluate(case, wind, receptors, settings, draw)
        rows.append(
            (
                r["peak_any_path"],
                r["hours_ge20"],
                r["hours_ge10"],
                r["helideck_peak"],
                r["into_wind_peak"],
            )
        )
    mc = np.array(rows)
    return {
        "monte_carlo_n": n_samples,
        "seed": seed,
        "distribution": "uniform",
        "ranges": {k: list(v) for k, v in ranges.items()},
        "peak_pct_lfl_any_path": _percentiles(mc[:, 0]),
        "hours_ge20_pct": _percentiles(mc[:, 1]),
        "hours_ge10_pct": _percentiles(mc[:, 2]),
        "helideck_peak_max_over_samples": float(mc[:, 3].max()),
        "into_wind_peak_max_over_samples": float(mc[:, 4].max()),
    }


def run_sensitivity(
    cases: Sequence[ReleaseCase],
    wind: WindTable,
    receptors: Receptors,
    settings: StudySettings,
    tilt_scan_cases: Sequence[str] | None = None,
    uncertainty_cases: Sequence[str] | None = None,
    tilts_deg: Sequence[float] = DEFAULT_TILTS,
    n_samples: int = 100,
    seed: int = 42,
    ranges: Mapping[str, tuple[float, float]] | None = None,
) -> dict[str, Any]:
    """Run the tilt scan, tornado and Monte Carlo for selected cases.

    Args:
        cases: All release cases.
        wind: Joint wind table.
        receptors: Receptor set.
        settings: Base study settings.
        tilt_scan_cases: Case names for the tilt scan (default all).
        uncertainty_cases: Case names for tornado and Monte Carlo (default all).
        tilts_deg: Tip inclinations of the scan, degrees.
        n_samples: Monte Carlo samples (0 disables Monte Carlo).
        seed: Monte Carlo seed.
        ranges: Parameter ranges.

    Returns:
        Dictionary with ``tilt_scan`` (by case) and one entry per uncertainty case
        holding ``base``, ``tornado`` and the Monte Carlo summary.
    """
    by_name = {c.name: c for c in cases}
    scan_names = list(tilt_scan_cases) if tilt_scan_cases is not None else list(by_name)
    unc_names = (
        list(uncertainty_cases) if uncertainty_cases is not None else list(by_name)
    )
    out: dict[str, Any] = {"tilt_scan": {}}
    for name in scan_names:
        out["tilt_scan"][name] = tilt_scan(
            by_name[name], wind, receptors, settings, tilts_deg
        )
    for name in unc_names:
        case = by_name[name]
        base = evaluate(case, wind, receptors, settings)
        entry: dict[str, Any] = {
            "base": {
                "peak_pct_lfl_any_path": base["peak_any_path"],
                "hours_ge20_pct": base["hours_ge20"],
                "hours_ge10_pct": base["hours_ge10"],
                "helideck_peak": base["helideck_peak"],
                "into_wind_peak": base["into_wind_peak"],
            },
            "tornado": tornado(case, wind, receptors, settings, ranges),
        }
        if n_samples > 0:
            entry.update(
                monte_carlo(case, wind, receptors, settings, n_samples, seed, ranges)
            )
        out[name] = entry
    return out
