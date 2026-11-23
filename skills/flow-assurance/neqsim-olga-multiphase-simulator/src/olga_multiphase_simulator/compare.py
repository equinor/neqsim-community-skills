"""NeqSim-versus-OLGA comparison helpers: slug statistics from a liquid-flow trend, and a conservatism table.

Typical use::

    stats = slug_statistics(t_s, qliq_m3_s, p_pa, area_m2=0.064)
    rows = [ComparisonRow("max slug volume at riser top", "m3", neqsim=4.6, olga=stats["max_surge_volume_m3"], higher_is_worse=True)]
    print(to_markdown(rows))

The conservatism verdict compares the NeqSim SCREENING value with the OLGA value for a quantity where a higher (or lower) value is
the unsafe direction.  Neither value is "truth": OLGA is a validated-for-purpose transient code but is itself run on assumed inputs.
"""

from __future__ import annotations

import csv
import io
import math
from collections.abc import Sequence
from dataclasses import dataclass, field

__all__ = [
    "ComparisonRow",
    "compare_rows",
    "dominant_period",
    "slug_statistics",
    "to_csv",
    "to_markdown",
]


@dataclass
class ComparisonRow:
    """One NeqSim-versus-OLGA comparison line.

    :param item: what is compared
    :param unit: unit of both values
    :param neqsim: NeqSim (screening) value
    :param olga: OLGA value
    :param higher_is_worse: True when a larger value is the unsafe direction (pressure, slug volume, restart liquid peak);
        False when a smaller value is unsafe (time to hydrate, time to reach a limit, minimum temperature margin)
    :param tolerance: relative band (fraction of the OLGA value) inside which the two are called "consistent"
    :param note: free text (basis, model limits)
    """

    item: str
    unit: str
    neqsim: float
    olga: float
    higher_is_worse: bool = True
    tolerance: float = 0.25
    note: str = ""
    ratio: float = field(init=False, default=float("nan"))
    verdict: str = field(init=False, default="")

    def __post_init__(self):
        self.ratio, self.verdict = _evaluate(
            self.neqsim, self.olga, self.higher_is_worse, self.tolerance
        )


def _evaluate(neqsim: float, olga: float, higher_is_worse: bool, tolerance: float):
    if (
        olga is None
        or neqsim is None
        or any(isinstance(v, float) and math.isnan(v) for v in (olga, neqsim))
    ):
        return float("nan"), "NOT_COMPARABLE (missing value)"
    if olga == 0.0:
        if neqsim == 0.0:
            return 1.0, "CONSISTENT (both zero)"
        neqsim_more_severe = (neqsim > 0.0) if higher_is_worse else (neqsim < 0.0)
        verdict = (
            "NEQSIM CONSERVATIVE (OLGA value is zero)"
            if neqsim_more_severe
            else "NEQSIM NON-CONSERVATIVE (OLGA value is zero)"
        )
        return float("inf"), verdict
    ratio = neqsim / olga
    if abs(ratio - 1.0) <= tolerance:
        return ratio, "CONSISTENT (within +/-%d %%)" % round(tolerance * 100)
    neqsim_unsafe_side = (ratio > 1.0) if higher_is_worse else (ratio < 1.0)
    # NeqSim value sits on the SAFE side of OLGA when it is the more severe one
    if neqsim_unsafe_side:
        return ratio, "NEQSIM CONSERVATIVE (rev A more severe than OLGA)"
    return ratio, "NEQSIM NON-CONSERVATIVE (rev A less severe than OLGA)"


def compare_rows(rows: Sequence[ComparisonRow]) -> dict[str, int]:
    """Count verdicts: ``{'conservative': n, 'non_conservative': n, 'consistent': n, 'not_comparable': n}``."""
    out = {
        "conservative": 0,
        "non_conservative": 0,
        "consistent": 0,
        "not_comparable": 0,
    }
    for r in rows:
        v = r.verdict
        if v.startswith("NEQSIM CONSERVATIVE"):
            out["conservative"] += 1
        elif v.startswith("NEQSIM NON-CONSERVATIVE"):
            out["non_conservative"] += 1
        elif v.startswith("CONSISTENT"):
            out["consistent"] += 1
        else:
            out["not_comparable"] += 1
    return out


def _fmt(v: float) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "n/a"
    if abs(v) >= 1000 or (abs(v) < 0.01 and v != 0):
        return "%.3g" % v
    return "%.4g" % v


def to_markdown(rows: Sequence[ComparisonRow]) -> str:
    """Render the comparison as a Markdown table (ratio = NeqSim / OLGA)."""
    lines = [
        "| Item | Unit | NeqSim | OLGA | Ratio NeqSim/OLGA | Verdict | Note |",
        "| --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for r in rows:
        lines.append(
            "| %s | %s | %s | %s | %s | %s | %s |"
            % (
                r.item,
                r.unit,
                _fmt(r.neqsim),
                _fmt(r.olga),
                _fmt(r.ratio),
                r.verdict,
                r.note,
            )
        )
    return "\n".join(lines) + "\n"


def to_csv(rows: Sequence[ComparisonRow]) -> str:
    """Render the comparison as CSV text."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(
        [
            "item",
            "unit",
            "neqsim",
            "olga",
            "ratio_neqsim_over_olga",
            "higher_is_worse",
            "verdict",
            "note",
        ]
    )
    for r in rows:
        w.writerow(
            [
                r.item,
                r.unit,
                r.neqsim,
                r.olga,
                r.ratio,
                r.higher_is_worse,
                r.verdict,
                r.note,
            ]
        )
    return buf.getvalue()


# ------------------------------------------------------------------------------------------------ slug statistics
def dominant_period(t: Sequence[float], y: Sequence[float]) -> float:
    """Dominant oscillation period (s) of a uniformly or non-uniformly sampled signal via autocorrelation of the demeaned signal.

    :return: period in s, or ``nan`` when no clear oscillation exists (first autocorrelation peak below 0.3)
    """
    n = len(t)
    if n < 8:
        return float("nan")
    dt = (t[-1] - t[0]) / (n - 1)
    # resample to uniform grid
    grid = [t[0] + i * dt for i in range(n)]
    yu: list[float] = []
    j = 0
    for g in grid:
        while j < n - 2 and t[j + 1] < g:
            j += 1
        f = 0.0 if t[j + 1] == t[j] else (g - t[j]) / (t[j + 1] - t[j])
        yu.append(y[j] + f * (y[j + 1] - y[j]))
    m = sum(yu) / n
    z = [v - m for v in yu]
    stride = max(1, int(math.ceil(n / 1500.0)))  # keep the O(n^2) autocorrelation cheap
    if stride > 1:
        z = z[::stride]
        dt *= stride
        n = len(z)
    var = sum(v * v for v in z)
    if var <= 0:
        return float("nan")
    maxlag = n // 2
    ac = []
    for lag in range(maxlag):
        s = 0.0
        for i in range(n - lag):
            s += z[i] * z[i + lag]
        ac.append(s / var)
    # first local maximum after the first zero crossing
    k = 1
    while k < maxlag and ac[k] > 0:
        k += 1
    best, bi = 0.0, -1
    for i in range(k, maxlag - 1):
        if ac[i] >= ac[i - 1] and ac[i] >= ac[i + 1] and ac[i] > best:
            best, bi = ac[i], i
            break
    if bi < 0 or best < 0.3:
        return float("nan")
    return bi * dt


def slug_statistics(
    t_s: Sequence[float],
    q_liq_m3_s: Sequence[float],
    p_pa: Sequence[float] | None = None,
    area_m2: float = 0.064,
    t_start_s: float = 0.0,
    slug_holdup: float = 1.0,
) -> dict[str, float]:
    """Slug/surge statistics at a pipe outlet from the liquid volume-flow trend.

    The maximum surge volume is the largest liquid volume above the mean outflow accumulated over one continuous period
    (``max_{i<j} (V_j - V_i)`` with ``V = integral(q - q_mean) dt``): the separator volume needed to absorb the surge at constant
    drain rate.  Slug length is that volume over the pipe area and an assumed slug-body holdup.

    :param t_s: times in s
    :param q_liq_m3_s: liquid volume flow at the outlet, m3/s
    :param p_pa: optional pressure trend in Pa (same times) for the oscillation amplitude
    :param area_m2: pipe cross-section
    :param t_start_s: statistics are computed for t >= t_start_s (skip the start-up transient)
    :param slug_holdup: liquid holdup in the slug body used for the equivalent length
    :return: dict with ``mean_q_m3_h``, ``max_q_m3_h``, ``peak_to_mean``, ``max_surge_volume_m3``, ``slug_length_m``, ``period_s``,
        ``p_amplitude_bar`` (max-min) and ``n_points``
    """
    idx = [i for i, v in enumerate(t_s) if v >= t_start_s]
    if len(idx) < 4:
        raise ValueError("not enough samples after t_start_s")
    t = [t_s[i] for i in idx]
    q = [max(q_liq_m3_s[i], 0.0) for i in idx]
    span = t[-1] - t[0]
    vol = 0.0
    for i in range(1, len(t)):
        vol += 0.5 * (q[i] + q[i - 1]) * (t[i] - t[i - 1])
    qm = vol / span if span > 0 else 0.0
    cum = [0.0]
    for i in range(1, len(t)):
        cum.append(cum[-1] + (0.5 * (q[i] + q[i - 1]) - qm) * (t[i] - t[i - 1]))
    run_min = cum[0]
    best = 0.0
    for v in cum:
        run_min = min(run_min, v)
        best = max(best, v - run_min)
    out = {
        "mean_q_m3_h": qm * 3600.0,
        "max_q_m3_h": max(q) * 3600.0,
        "peak_to_mean": (max(q) / qm) if qm > 0 else float("nan"),
        "max_surge_volume_m3": best,
        "slug_length_m": (
            best / (area_m2 * slug_holdup) if area_m2 > 0 else float("nan")
        ),
        "period_s": dominant_period(t, q),
        "n_points": float(len(t)),
    }
    if p_pa is not None:
        p = [p_pa[i] for i in idx]
        out["p_amplitude_bar"] = (max(p) - min(p)) / 1e5
    return out
