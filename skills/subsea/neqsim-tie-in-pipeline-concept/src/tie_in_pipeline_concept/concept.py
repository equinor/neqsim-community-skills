"""One call that chains candidate ranking, seabed profile, hydraulics and wall thickness."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from .candidates import rank_candidates
from .profile import build_profile, profile_statistics
from .sizing import OilProperties, PipelineDesignBasis, size_pipeline


def run_concept(
    source: dict[str, object],
    landing: dict[str, object],
    props: OilProperties,
    rates_sm3d: dict[str, float],
    design_case: str,
    turndown_case: str,
    hosts: Iterable[dict[str, object]] | None = None,
    feeds_into: dict[str, Sequence[str]] | None = None,
    terminal_hosts: Iterable[str] | None = None,
    basis_overrides: dict[str, float] | None = None,
    fetch: Callable[[str], dict] | None = None,
    cache_path: Path | None = None,
    spacing_km: float = 0.5,
) -> dict[str, object]:
    """Screen a new export line from ``source`` to ``landing``.

    Args:
        source: mapping with ``name``, ``lat``, ``lon`` of the source facility.
        landing: mapping with ``name``, ``lat``, ``lon`` of the chosen landing facility.
        props: stabilised dry-oil properties.
        rates_sm3d: named rate cases in Sm3/d.
        design_case: key of the design rate.
        turndown_case: key of the minimum rate.
        hosts: optional hosts for the candidate ranking.
        feeds_into: optional existing feeder map for the ranking.
        terminal_hosts: optional hosts with a trunk to the terminal.
        basis_overrides: field values of :class:`PipelineDesignBasis` to override, for example the arrival pressure.
        fetch: injectable depth fetch function.
        cache_path: optional depth cache file.
        spacing_km: profile spacing.

    Returns:
        Dictionary with ``candidates``, ``profile``, ``statistics``, ``sizing``, ``basis`` and ``assumptions``.
    """
    profile = build_profile((float(source["lon"]), float(source["lat"])),
                            (float(landing["lon"]), float(landing["lat"])), spacing_km, fetch, cache_path)
    stats = profile_statistics(profile)
    basis = PipelineDesignBasis(length_m=profile.length_km * 1000.0)
    basis.net_elevation_m = profile.depth_m[0] - profile.depth_m[-1]
    basis.max_water_depth_m = max(profile.depth_m)
    for key, value in (basis_overrides or {}).items():
        if not hasattr(basis, key):
            raise ValueError(f"unknown design basis field: {key}")
        setattr(basis, key, value)
    sizing = size_pipeline(props, basis, rates_sm3d, design_case, turndown_case)
    ranking = []
    if hosts is not None:
        ranking = [c.__dict__ for c in rank_candidates(source, hosts, feeds_into, terminal_hosts)]
    return {
        "candidates": ranking,
        "profile": {"kp_km": profile.kp_km, "lon": profile.lon, "lat": profile.lat, "depth_m": profile.depth_m},
        "statistics": stats,
        "sizing": sizing,
        "basis": {k: v for k, v in basis.__dict__.items() if k != "standard_wt_mm"},
        "assumptions": [
            "Straight great-circle corridor, no obstacle avoidance; EMODnet DTM depths.",
            "Dry stabilised oil, single phase; water removal and stabilisation happen upstream.",
            "Friction by Haaland, temperature by exponential decay with a constant overall U.",
            "Wall thickness by a hand implementation of DNV-ST-F101 containment and collapse only.",
            "Free span, on-bottom stability, buckling, fatigue, installation and surge are not assessed.",
        ],
    }
