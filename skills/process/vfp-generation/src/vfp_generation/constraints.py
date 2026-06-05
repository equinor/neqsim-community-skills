"""Compressor constraint classification for VFP generation.

Pure-Python reproduction of the PASS / WARN / FAIL classification used when
building Eclipse VFPPROD lift-curve tables. No third-party dependencies.
"""
from __future__ import annotations


def classify_value(
    value: float,
    limit: float,
    threshold_mode: str = "margin_pct",
    pass_at: float | None = None,
    warn_at: float | None = None,
    fail_at: float | None = None,
) -> str:
    """Classify a constraint value as ``PASS`` / ``WARN`` / ``FAIL``.

    Parameters
    ----------
    value:
        Measured value (power MW, speed RPM, margin %, casing capacity, ...).
    limit:
        Reference limit (driver max MW, chart max RPM, max casing capacity, ...).
    threshold_mode:
        How ``pass_at`` / ``warn_at`` / ``fail_at`` are interpreted:

        - ``"factor"``: compare ``value`` to ``limit * factor``.
        - ``"offset"``: compare ``value`` to ``limit - offset``.
        - ``"margin_pct"``: ``value`` *is* a margin percent; higher is safer.
    pass_at, warn_at, fail_at:
        Threshold values whose meaning depends on ``threshold_mode``.

    Returns
    -------
    str
        ``"PASS"``, ``"WARN"`` or ``"FAIL"``.
    """
    if threshold_mode == "factor":
        _pass = (pass_at if pass_at is not None else 1.00) * limit
        _fail = (fail_at if fail_at is not None else 1.05) * limit
        if value <= _pass:
            return "PASS"
        if value < _fail:
            return "WARN"
        return "FAIL"

    if threshold_mode == "offset":
        _pass = limit - (pass_at if pass_at is not None else 1.0)
        _fail = limit - (fail_at if fail_at is not None else 0.0)
        if value <= _pass:
            return "PASS"
        if value < _fail:
            return "WARN"
        return "FAIL"

    # margin_pct (default): value is the margin %, higher = safer
    _pass = pass_at if pass_at is not None else 15.0
    _fail = fail_at if fail_at is not None else 5.0
    if value > _pass:
        return "PASS"
    if value > _fail:
        return "WARN"
    return "FAIL"


# Default thresholds per constraint name: (mode, pass_at, warn_at, fail_at).
# Covers the eight constraint types handled by the VFP generator.
DEFAULT_THRESHOLDS: dict[str, tuple[str, float, float, float]] = {
    "motor_power":           ("offset",     1.0,  0.5,  0.0),
    "discharge_temperature": ("offset",     10.0, 0.0,  0.0),
    "surge_margin":          ("margin_pct", 10.0, 5.0,  5.0),
    "stonewall_margin":      ("margin_pct", 5.0,  0.0,  0.0),
    "pipe_velocity":         ("margin_pct", 15.0, 5.0,  0.0),
    "scrubber_k_value":      ("margin_pct", 20.0, 5.0,  0.0),
    "chart_envelope":        ("factor",     1.00, 1.02, 1.03),
    "max_casing_capacity":   ("factor",     1.00, 1.00, 1.00),
}


def get_thresholds(
    name: str,
    overrides: tuple[str | None, float | None, float | None, float | None] | None = None,
) -> tuple[str, float, float, float]:
    """Return ``(mode, pass_at, warn_at, fail_at)`` for a constraint name.

    Falls back to :data:`DEFAULT_THRESHOLDS`, then to a generic margin default.
    ``overrides`` may supply any subset of the four fields (use ``None`` to keep
    the default for that field).
    """
    defaults = DEFAULT_THRESHOLDS.get(name, ("margin_pct", 15.0, 5.0, 5.0))
    if overrides is None:
        return defaults
    mode = overrides[0] if overrides[0] is not None else defaults[0]
    p = overrides[1] if overrides[1] is not None else defaults[1]
    w = overrides[2] if overrides[2] is not None else defaults[2]
    f = overrides[3] if overrides[3] is not None else defaults[3]
    return (mode, p, w, f)


def classify_named(name: str, value: float, limit: float) -> str:
    """Convenience: classify ``value`` against ``limit`` using a constraint's
    default thresholds looked up by ``name``."""
    mode, p, w, f = get_thresholds(name)
    return classify_value(value, limit, mode, p, w, f)
