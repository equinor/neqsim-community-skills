"""Reservoir-state proxy tables from Eclipse / OPM Flow summary results.

The functions here turn report-step summary vectors of one simulator run into the tables that the NeqSim hybrid
production model reads (``neqsim.process.fielddevelopment.hybrid.ReservoirStateProxy``): reservoir pressure, water cut,
gas-oil ratio and productivity index against a cumulative volume, per well or per drainage unit.

Nothing here runs a simulator or needs NeqSim. ``resdata`` is only imported by :meth:`SummaryData.from_file`.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

#: Cumulative quantities known to the Java proxy (``CumulativeQuantity``). ``ELAPSED_TIME`` (days) is written to
#: every table: as the second coordinate of a scenario blend it tells how fast the cumulative volume was produced.
QUANTITIES = (
    "OIL_PRODUCED",
    "WATER_PRODUCED",
    "GAS_PRODUCED",
    "LIQUID_PRODUCED",
    "WATER_INJECTED",
    "GAS_INJECTED",
    "ELAPSED_TIME",
)

#: Summary vectors a well proxy needs, and what each is used for.
WELL_VECTORS = {
    "WOPR": "oil rate (productivity index, shut-in filter)",
    "WOPT": "cumulative oil (abscissa)",
    "WBHP": "flowing bottom-hole pressure (productivity index)",
    "WWCT": "water cut",
    "WGOR": "gas-oil ratio",
}

#: Optional well vectors.
OPTIONAL_WELL_VECTORS = {
    "WTHP": "wellhead pressure (validation of lift curves)",
    "WBP9": "nine-point well block pressure (alternative reference pressure)",
    "WBP": "well block pressure (alternative reference pressure)",
    "WPI": "simulator productivity index (cross-check only)",
    "WWPT": "cumulative water",
    "WGPT": "cumulative gas",
    "WMCTL": "control mode (to see when a well is on a rate target)",
}


class SummaryData:
    """Summary vectors at the simulator time steps, keyed like Eclipse summary keys (``WOPR:A1``, ``RPR:1``)."""

    def __init__(
        self, time_days: Sequence[float], vectors: Mapping[str, Sequence[float]]
    ):
        self.time_days = np.asarray(time_days, dtype=float)
        self._vectors = {
            key: np.asarray(values, dtype=float) for key, values in vectors.items()
        }
        for key, values in self._vectors.items():
            if values.shape != self.time_days.shape:
                raise ValueError(
                    f"vector {key} has {values.size} values, time has {self.time_days.size}"
                )

    @classmethod
    def from_file(
        cls, path: str | Path, keys: Iterable[str] | None = None
    ) -> SummaryData:
        """Read the summary vectors of an Eclipse / OPM Flow run (``CASE.SMSPEC`` or the case base path).

        Every simulator time step is read, not only the report steps. ``resdata`` resamples to whole-day report
        *dates* when asked for ``report_only`` values, which shifts rates and cumulative volumes off the times the
        simulator solved (30.0 instead of 30.4375 days for a monthly step) and breaks the relation
        ``cumulative[n] = cumulative[n-1] + rate[n] * dt`` that an implicit simulator satisfies exactly.

        ``keys`` limits what is read; by default every well, group, region and field vector is loaded.
        """
        # imported here so the rest of the module works without resdata
        from resdata.summary import Summary

        summary = Summary(str(path))
        names = summary.keys()  # a resdata key list, not a dict
        wanted = (
            list(keys)
            if keys is not None
            else [k for k in names if k.split(":")[0][:1] in ("W", "G", "R", "F")]
        )
        time_days = np.asarray(summary.numpy_vector("TIME"), dtype=float)
        vectors = {}
        for key in wanted:
            if key in summary:
                vectors[key] = np.asarray(summary.numpy_vector(key), dtype=float)
        return cls(time_days, vectors)

    def has(self, key: str) -> bool:
        return key in self._vectors

    def get(self, key: str) -> np.ndarray:
        if key not in self._vectors:
            raise KeyError(
                f"summary vector {key} is not in the results; add it to the SUMMARY section and rerun"
            )
        return self._vectors[key]

    def keys(self) -> list[str]:
        return sorted(self._vectors)

    def wells(self) -> list[str]:
        """Names of the wells that have an oil rate vector."""
        return sorted(
            k.split(":", 1)[1] for k in self._vectors if k.startswith("WOPR:")
        )


def inventory(data: SummaryData, wells: Iterable[str] | None = None) -> dict:
    """Report which proxy quantities can be taken from the results, per well, and what is missing.

    Run this first on any existing simulator case: it tells whether the run has to be repeated with more
    SUMMARY vectors before a proxy can be built.
    """
    report: dict = {
        "wells": {},
        "region_pressures": [],
        "field_pressure": data.has("FPR"),
        "missing": [],
    }
    names = data.keys()  # method of SummaryData, not a dict
    report["region_pressures"] = [k for k in names if k.startswith("RPR:")]
    for well in list(wells) if wells is not None else data.wells():
        present = {v: data.has(f"{v}:{well}") for v in WELL_VECTORS}
        optional = {v: data.has(f"{v}:{well}") for v in OPTIONAL_WELL_VECTORS}
        missing = [v for v, ok in present.items() if not ok]
        pressure_sources = [f"{v}:{well}" for v in ("WBP9", "WBP") if optional[v]]
        report["wells"][well] = {
            "required": present,
            "optional": optional,
            "can_build_proxy": not missing,
            "well_pressure_sources": pressure_sources,
        }
        report["missing"].extend(f"{v}:{well}" for v in missing)
    if not report["region_pressures"] and not report["field_pressure"]:
        report["missing"].append("RPR or FPR (reservoir pressure of the drainage unit)")
    return report


@dataclass
class StateTable:
    """Proxy table of one well or drainage unit, in the column layout of ``ReservoirStateProxy.fromCsv``."""

    name: str
    abscissa: str
    columns: dict[str, np.ndarray]
    provenance: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        cumulative = self.columns["cumulative"]
        if cumulative.size < 2 or np.any(np.diff(cumulative) <= 0.0):
            raise ValueError(
                f"table {self.name}: cumulative must have at least two strictly increasing values"
            )

    @property
    def rows(self) -> int:
        return int(self.columns["cumulative"].size)

    def at(self, cumulative: float) -> dict[str, float]:
        """Interpolate every column, holding the end values outside the table (as the Java proxy does)."""
        x = self.columns["cumulative"]
        return {
            k: float(np.interp(cumulative, x, v))
            for k, v in self.columns.items()
            if k != "cumulative"
        }

    def to_csv(self, path: str | Path) -> Path:
        """Write the table for ``ReservoirStateProxy.fromCsv(name, CumulativeQuantity.<abscissa>, path)``."""
        path = Path(path)
        header = list(self.columns)
        with path.open("w", newline="", encoding="utf-8") as handle:
            handle.write(
                f"# reservoir-state proxy {self.name}; abscissa {self.abscissa}\n"
            )
            for key, value in self.provenance.items():
                handle.write(f"# {key}: {value}\n")
            writer = csv.writer(handle)
            writer.writerow(header)
            for i in range(self.rows):
                writer.writerow([repr(float(self.columns[k][i])) for k in header])
        return path


def _resolve(data: SummaryData, source) -> np.ndarray:
    """A summary key, a list of keys to add, or an array of report-step values."""
    if isinstance(source, str):
        return data.get(source)
    if isinstance(source, (list, tuple)) and source and isinstance(source[0], str):
        return np.sum([data.get(k) for k in source], axis=0)
    values = np.asarray(source, dtype=float)
    if values.shape != data.time_days.shape:
        raise ValueError("an explicit column must have one value per report step")
    return values


def _strictly_increasing(
    cumulative: np.ndarray, keep: np.ndarray, min_increment: float
) -> np.ndarray:
    """Indices of the rows kept: flagged rows whose cumulative exceeds the previous kept row."""
    indices = []
    last = -np.inf
    for i in np.flatnonzero(keep):
        if cumulative[i] > last + min_increment:
            indices.append(i)
            last = cumulative[i]
    return np.asarray(indices, dtype=int)


def well_state_table(
    data: SummaryData,
    well: str,
    pressure: str | Sequence[float],
    extra_quantities: Mapping[str, object] | None = None,
    min_rate: float = 1.0,
    min_drawdown: float = 0.5,
    initial_pressure: float | None = None,
) -> StateTable:
    """Build the proxy of one well: pressure, water cut, GOR and productivity index against its cumulative oil.

    ``pressure`` is the summary key (or report-step array) of the reservoir pressure the inflow is referred to,
    for example ``"RPR:1"`` for the well's drainage region or ``"WBP9:A1"``. The productivity index is *derived*
    as ``WOPR / (pressure - WBHP)`` so that it is consistent with that reference pressure; the simulator's own
    ``WPI`` refers to the well block and must not be combined with a region pressure.

    Rows where the well does not flow (oil rate below ``min_rate``) are dropped, because a shut-in well tells
    nothing about its state. A row at zero cumulative is added from the first flowing row, with the pressure of
    the first report step (the initial state) unless ``initial_pressure`` is given.

    ``extra_quantities`` maps a cumulative quantity name (see :data:`QUANTITIES`) to a summary key, a list of keys
    to add, or an array, for example ``{"WATER_INJECTED": "WWIT:IA"}``; scenario blending needs it.
    """
    rate = data.get(f"WOPR:{well}")
    cumulative = data.get(f"WOPT:{well}")
    bhp = data.get(f"WBHP:{well}")
    p_ref = _resolve(data, pressure)
    water_cut = data.get(f"WWCT:{well}")
    gor = data.get(f"WGOR:{well}")

    flowing = rate > min_rate
    idx = _strictly_increasing(
        cumulative, flowing, 1.0e-9 * max(float(cumulative.max()), 1.0)
    )
    if idx.size < 2:
        raise ValueError(f"well {well} has fewer than two flowing report steps")
    drawdown = p_ref[idx] - bhp[idx]
    usable = drawdown > min_drawdown
    if usable.sum() < 2:
        raise ValueError(
            f"well {well}: reference pressure {pressure!r} is not above the flowing bottom-hole pressure; "
            "choose another pressure source"
        )
    pi = np.interp(
        cumulative[idx], cumulative[idx][usable], rate[idx][usable] / drawdown[usable]
    )

    p0 = float(initial_pressure) if initial_pressure is not None else float(p_ref[0])
    columns = {
        "cumulative": np.concatenate([[0.0], cumulative[idx]]),
        "pressure": np.concatenate([[p0], p_ref[idx]]),
        "waterCut": np.clip(
            np.concatenate([[water_cut[idx][0]], water_cut[idx]]), 0.0, 0.999999
        ),
        "gor": np.concatenate([[gor[idx][0]], gor[idx]]),
        "pi": np.concatenate([[pi[0]], pi]),
        "ELAPSED_TIME": np.concatenate([[0.0], data.time_days[idx]]),
    }
    for name, source in (extra_quantities or {}).items():
        if name not in QUANTITIES:
            raise ValueError(
                f"unknown cumulative quantity {name}; use one of {QUANTITIES}"
            )
        values = _resolve(data, source)
        columns[name] = np.concatenate([[0.0], values[idx]])
    provenance = {
        "pressure_source": pressure if isinstance(pressure, str) else "explicit array",
        "productivity_index": "derived: WOPR / (pressure - WBHP), Sm3 oil/(day bar)",
        "rows_dropped_not_flowing": int((~flowing).sum()),
        "rows_with_interpolated_pi": int((~usable).sum()),
    }
    return StateTable(well, "OIL_PRODUCED", columns, provenance)


def unit_pressure_table(
    data: SummaryData,
    name: str,
    wells: Sequence[str],
    pressure: str | Sequence[float],
    extra_quantities: Mapping[str, object] | None = None,
) -> StateTable:
    """Build the pressure table of a drainage unit against the cumulative oil of all its wells.

    Wells that drain the same pressure-connected volume share its pressure, so the pressure must follow the
    production of all of them, not of each well alone. Use the region pressure of the unit (``"RPR:n"``).
    """
    cumulative = np.sum([data.get(f"WOPT:{w}") for w in wells], axis=0)
    p_ref = _resolve(data, pressure)
    keep = np.ones_like(cumulative, dtype=bool)
    idx = _strictly_increasing(
        cumulative, keep, 1.0e-9 * max(float(cumulative.max()), 1.0)
    )
    if idx.size == 0 or cumulative[idx[0]] > 0.0:
        cum = np.concatenate([[0.0], cumulative[idx]])
        pres = np.concatenate([[float(p_ref[0])], p_ref[idx]])
        elapsed = np.concatenate([[0.0], data.time_days[idx]])
        lead = True
    else:
        cum, pres, elapsed, lead = (
            cumulative[idx],
            p_ref[idx],
            data.time_days[idx],
            False,
        )
    columns = {"cumulative": cum, "pressure": pres, "ELAPSED_TIME": elapsed}
    for quantity, source in (extra_quantities or {}).items():
        if quantity not in QUANTITIES:
            raise ValueError(
                f"unknown cumulative quantity {quantity}; use one of {QUANTITIES}"
            )
        values = _resolve(data, source)[idx]
        columns[quantity] = np.concatenate([[0.0], values]) if lead else values
    provenance = {
        "pressure_source": pressure if isinstance(pressure, str) else "explicit array",
        "wells": " ".join(wells),
    }
    return StateTable(name, "OIL_PRODUCED", columns, provenance)


def performance_curve(
    data: SummaryData, well: str, min_rate: float = 1.0
) -> tuple[np.ndarray, np.ndarray]:
    """Classic performance curve of a well: oil rate against its cumulative oil, from the simulator run.

    This is the baseline the hybrid model is compared with: replaying it gives the same rate at the same
    cumulative production whatever the network does.
    """
    rate = data.get(f"WOPR:{well}")
    cumulative = data.get(f"WOPT:{well}")
    idx = _strictly_increasing(
        cumulative, rate > min_rate, 1.0e-9 * max(float(cumulative.max()), 1.0)
    )
    return np.concatenate([[0.0], cumulative[idx]]), np.concatenate(
        [[rate[idx][0]], rate[idx]]
    )


def replay_profile(
    curve: tuple[np.ndarray, np.ndarray],
    time_days: Sequence[float],
    rate_cap: float | Sequence[float] | None = None,
    substeps: int = 10,
) -> tuple[np.ndarray, np.ndarray]:
    """Integrate dNp/dt = min(q(Np), cap) for a performance curve; returns rate and cumulative at each time.

    ``rate_cap`` is a constant or one value per time (the cap that applies up to that time). The rate at a time is
    the capped curve rate at the cumulative reached; the network plays no part, which is the point of the baseline.
    """
    x, q = curve
    t = np.asarray(time_days, dtype=float)
    caps = (
        np.full(t.shape, np.inf)
        if rate_cap is None
        else np.broadcast_to(np.asarray(rate_cap, dtype=float), t.shape)
    )
    cumulative = np.zeros_like(t)
    rates = np.zeros_like(t)
    produced = 0.0
    rates[0] = min(float(np.interp(produced, x, q)), float(caps[0]))
    for i in range(1, t.size):
        dt = (t[i] - t[i - 1]) / substeps
        for _ in range(substeps):
            produced += min(float(np.interp(produced, x, q)), float(caps[i])) * dt
        cumulative[i] = produced
        rates[i] = min(float(np.interp(produced, x, q)), float(caps[i]))
    return rates, cumulative


def compare(
    reference_time: Sequence[float],
    reference: Sequence[float],
    model_time: Sequence[float],
    model: Sequence[float],
    floor: float | None = None,
) -> dict[str, float]:
    """Error of a model series against a simulator series on the simulator's report times.

    Relative errors are taken where the reference magnitude is above ``floor`` (default 1 % of its maximum), so that
    a well close to zero rate does not dominate. Returns mean and maximum absolute relative error in per cent, the
    bias in per cent and the root-mean-square error in the unit of the series.
    """
    t = np.asarray(reference_time, dtype=float)
    ref = np.asarray(reference, dtype=float)
    mod = np.interp(
        t, np.asarray(model_time, dtype=float), np.asarray(model, dtype=float)
    )
    limit = (
        floor
        if floor is not None
        else 0.01 * float(np.max(np.abs(ref))) if ref.size else 0.0
    )
    mask = np.abs(ref) > limit
    if not mask.any():
        return {
            "mean_abs_pct": float("nan"),
            "max_abs_pct": float("nan"),
            "bias_pct": float("nan"),
            "rmse": (
                float(np.sqrt(np.mean((mod - ref) ** 2))) if ref.size else float("nan")
            ),
            "points": 0,
        }
    relative = (mod[mask] - ref[mask]) / ref[mask]
    return {
        "mean_abs_pct": float(100.0 * np.mean(np.abs(relative))),
        "max_abs_pct": float(100.0 * np.max(np.abs(relative))),
        "bias_pct": float(100.0 * np.mean(relative)),
        "rmse": float(np.sqrt(np.mean((mod - ref) ** 2))),
        "points": int(mask.sum()),
    }
