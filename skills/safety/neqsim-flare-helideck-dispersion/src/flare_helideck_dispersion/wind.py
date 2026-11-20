"""Joint wind direction x speed frequency tables and Pasquill stability rules.

A :class:`WindTable` holds the share of all hours (in percent) that the wind blows FROM
each direction sector with a speed in each speed bin. It can be loaded from JSON,
built from an hourly record of speed and direction, validated, and handed to
:mod:`flare_helideck_dispersion.study`.

All speeds are at the reference height (10 m) in m/s. Directions are the direction the
wind blows FROM, in degrees true (meteorological convention).
"""

from __future__ import annotations

import csv
import itertools
import json
import math
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

SECTOR_NAMES_16 = [
    "N",
    "NNE",
    "NE",
    "ENE",
    "E",
    "ESE",
    "SE",
    "SSE",
    "S",
    "SSW",
    "SW",
    "WSW",
    "W",
    "WNW",
    "NW",
    "NNW",
]
"""Compass names of the 16 sectors, clockwise from north."""

DEFAULT_SPEED_EDGES = (0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20)
"""Default speed-bin edges, m/s; the last bin is open ended (``>20``)."""

STABILITY_SCHEMES: dict[str, Sequence[tuple]] = {
    "conservative_stable": ((2.0, "F"), (4.0, "E"), (math.inf, "D")),
    "neutral": ((math.inf, "D"),),
    "night_stable": ((3.0, "F"), (5.0, "E"), (math.inf, "D")),
    "day_moderate": ((3.0, "B"), (5.0, "C"), (math.inf, "D")),
}
"""Pasquill class by wind speed: ``(upper speed bound, class)`` pairs.

``conservative_stable`` (default) assigns F below 2 m/s, E from 2 to 4 m/s and D
above. It keeps a lifted plume near its release height and is the stable-biased
choice for a flight-path screening. ``neutral`` assigns D to every speed. ``night_stable``
and ``day_moderate`` follow the Pasquill-Turner tables for clear night and moderate
insolation, collapsed to one class per speed range. Use the alternatives as a
sensitivity because the empirical class mix at low wind is a B/F mixture, not a single
class.
"""

StabilityScheme = str | Sequence[tuple] | Callable[[float], str]


def pasquill_by_speed(
    u10: float, scheme: StabilityScheme = "conservative_stable"
) -> str:
    """Return the Pasquill stability class for a 10 m wind speed.

    Args:
        u10: Wind speed at 10 m, m/s.
        scheme: Name in :data:`STABILITY_SCHEMES`, a sequence of
            ``(upper speed bound, class)`` pairs in ascending order, or a callable that
            maps a speed to a class letter.

    Returns:
        Class letter ``A`` to ``F``.

    Raises:
        ValueError: If the scheme name is unknown or the bounds do not cover ``u10``.
    """
    if callable(scheme):
        return str(scheme(u10))
    if isinstance(scheme, str):
        if scheme not in STABILITY_SCHEMES:
            raise ValueError(
                f"unknown stability scheme {scheme!r}; use one of {sorted(STABILITY_SCHEMES)}"
            )
        scheme = STABILITY_SCHEMES[scheme]
    for upper, cls in scheme:
        if u10 < upper:
            return cls
    raise ValueError(f"stability scheme bounds do not cover u10={u10}")


def speed_bin_labels(edges: Sequence[float] = DEFAULT_SPEED_EDGES) -> list[str]:
    """Build bin labels such as ``0-2`` ... ``>20`` from the edges.

    Args:
        edges: Ascending bin edges, m/s.

    Returns:
        One label per bin, the last one open ended.
    """

    def fmt(value: float) -> str:
        return (f"{value:g}") if value != int(value) else str(int(value))

    labels = [f"{fmt(a)}-{fmt(b)}" for a, b in itertools.pairwise(edges)]
    labels.append(f">{fmt(edges[-1])}")
    return labels


def default_representative_speeds(
    labels: Sequence[str], low_bin_speed_ms: float = 1.5, open_bin_extra_ms: float = 2.0
) -> np.ndarray:
    """Representative speed of each bin.

    The bin midpoint is used, except that the first bin (which starts at 0 m/s) uses
    ``low_bin_speed_ms`` because a Gaussian plume is not valid for speeds well below
    1 m/s and a midpoint of 1.0 m/s sits at that limit. An open-ended bin uses its lower
    edge plus ``open_bin_extra_ms``. Re-run with ``low_bin_speed_ms=1.0`` as a
    low-wind sensitivity.

    Args:
        labels: Bin labels such as ``2-4`` or ``>20``.
        low_bin_speed_ms: Speed that represents a bin starting at 0 m/s.
        open_bin_extra_ms: Added to the lower edge of an open-ended bin.

    Returns:
        Array of representative speeds, m/s.

    Raises:
        ValueError: If a label cannot be parsed.
    """
    speeds = []
    for label in labels:
        text = label.strip().replace(" ", "")
        open_match = re.fullmatch(r">=?([0-9.]+)|([0-9.]+)\+", text)
        range_match = re.fullmatch(r"([0-9.]+)[-_]([0-9.]+)", text)
        if open_match:
            lower = float(open_match.group(1) or open_match.group(2))
            speeds.append(lower + open_bin_extra_ms)
        elif range_match:
            lower, upper = float(range_match.group(1)), float(range_match.group(2))
            mid = 0.5 * (lower + upper)
            if lower == 0.0:
                mid = min(max(low_bin_speed_ms, mid), upper)
            speeds.append(mid)
        else:
            raise ValueError(f"cannot parse speed-bin label {label!r}")
    return np.array(speeds, dtype=float)


@dataclass
class WindTable:
    """Joint direction x speed frequency table.

    Attributes:
        sectors: Sector names, clockwise from north.
        sector_deg: Sector centre directions (FROM), degrees true.
        speed_bins: Speed-bin labels.
        speed_rep_ms: Representative speed of each bin, m/s.
        table_pct: Array ``(n_sectors, n_bins)`` of the share of all hours, percent.
        metadata: Free-form provenance (source, period, height, resolution).
    """

    sectors: list[str]
    sector_deg: np.ndarray
    speed_bins: list[str]
    speed_rep_ms: np.ndarray
    table_pct: np.ndarray
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Coerce arrays and validate shape.

        Raises:
            ValueError: If the shapes are inconsistent.
        """
        self.sector_deg = np.asarray(self.sector_deg, dtype=float)
        self.speed_rep_ms = np.asarray(self.speed_rep_ms, dtype=float)
        self.table_pct = np.asarray(self.table_pct, dtype=float)
        shape = (len(self.sectors), len(self.speed_bins))
        if self.table_pct.shape != shape:
            raise ValueError(
                f"table shape {self.table_pct.shape} does not match "
                f"{shape[0]} sectors x {shape[1]} bins"
            )
        if self.sector_deg.shape != (shape[0],) or self.speed_rep_ms.shape != (
            shape[1],
        ):
            raise ValueError("sector_deg / speed_rep_ms length mismatch")

    @property
    def total_pct(self) -> float:
        """Sum of the table, percent of hours."""
        return float(self.table_pct.sum())

    @property
    def sector_width_deg(self) -> float:
        """Angular width of one sector, degrees."""
        return 360.0 / len(self.sectors)

    def sector_frequency_pct(self) -> np.ndarray:
        """Share of hours per direction sector, percent."""
        return self.table_pct.sum(axis=1)

    def speed_bin_frequency_pct(self) -> np.ndarray:
        """Share of hours per speed bin, percent."""
        return self.table_pct.sum(axis=0)

    def validate(self, sum_tolerance_pct: float = 1.0) -> list[str]:
        """Validate the table and return non-fatal warnings.

        Args:
            sum_tolerance_pct: Allowed deviation of the table sum from 100 percent.

        Returns:
            List of warning strings (for example low-speed representative bins).

        Raises:
            ValueError: If values are negative or non-finite, or the table does not sum
                to 100 percent within the tolerance.
        """
        if not np.all(np.isfinite(self.table_pct)):
            raise ValueError("wind table contains non-finite values")
        if np.any(self.table_pct < 0.0):
            raise ValueError("wind table contains negative frequencies")
        if abs(self.total_pct - 100.0) > sum_tolerance_pct:
            raise ValueError(
                f"wind table sums to {self.total_pct:.3f} percent, expected 100 +/- {sum_tolerance_pct:.2f}"
            )
        warnings = []
        if np.any(np.diff(self.speed_rep_ms) <= 0.0):
            warnings.append("representative speeds are not strictly ascending")
        low = [
            label
            for label, speed in zip(self.speed_bins, self.speed_rep_ms)
            if speed < 1.0
        ]
        if low:
            warnings.append(
                f"bins {low} are represented by a speed below 1 m/s where the Gaussian "
                "plume is not valid"
            )
        return warnings

    def normalised(self) -> WindTable:
        """Return a copy rescaled so that the table sums to exactly 100 percent."""
        scale = 100.0 / self.total_pct
        return WindTable(
            list(self.sectors),
            self.sector_deg.copy(),
            list(self.speed_bins),
            self.speed_rep_ms.copy(),
            self.table_pct * scale,
            dict(self.metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable mapping with the reference layout."""
        return {
            "description": "Joint wind direction (FROM) x speed frequency, percent of hours",
            "sectors": list(self.sectors),
            "sector_deg": [float(v) for v in self.sector_deg],
            "speed_bins": list(self.speed_bins),
            "speed_rep_ms": [float(v) for v in self.speed_rep_ms],
            "table": {
                s: {
                    b: float(self.table_pct[i, k])
                    for k, b in enumerate(self.speed_bins)
                }
                for i, s in enumerate(self.sectors)
            },
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        low_bin_speed_ms: float = 1.5,
    ) -> WindTable:
        """Build a table from a mapping.

        Accepts the flat layout written by :meth:`to_dict` and the same mapping nested
        under ``joint_direction_x_speed_frequency_pct``. ``table`` is either a nested
        ``{sector: {bin: pct}}`` mapping or a list of rows.

        Args:
            data: Parsed JSON.
            low_bin_speed_ms: Representative speed of the first bin when
                ``speed_rep_ms`` is absent.

        Returns:
            The validated wind table.

        Raises:
            ValueError: If the mapping is incomplete or fails validation.
        """
        block = data.get("joint_direction_x_speed_frequency_pct", data)
        for key in ("sectors", "speed_bins", "table"):
            if key not in block:
                raise ValueError(f"wind table mapping is missing {key!r}")
        sectors = list(block["sectors"])
        bins = list(block["speed_bins"])
        raw = block["table"]
        if isinstance(raw, dict):
            table = np.array([[raw[s][b] for b in bins] for s in sectors], dtype=float)
        else:
            table = np.array(raw, dtype=float)
        width = 360.0 / len(sectors)
        sector_deg = np.array(block.get("sector_deg", np.arange(len(sectors)) * width))
        if "speed_rep_ms" in block:
            rep = np.array(block["speed_rep_ms"], dtype=float)
        else:
            rep = default_representative_speeds(bins, low_bin_speed_ms)
        meta = dict(data.get("metadata", {}) or block.get("metadata", {}))
        out = cls(sectors, sector_deg, bins, rep, table, meta)
        out.validate()
        return out

    @classmethod
    def load_json(cls, path: str | Path, low_bin_speed_ms: float = 1.5) -> WindTable:
        """Load and validate a table from a JSON file.

        Args:
            path: JSON file.
            low_bin_speed_ms: Representative speed of the first bin if absent.

        Returns:
            The wind table.
        """
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data, low_bin_speed_ms)

    def save_json(self, path: str | Path) -> None:
        """Write the table as JSON.

        Args:
            path: Output file.
        """
        Path(path).write_text(json.dumps(self.to_dict(), indent=1), encoding="utf-8")

    @classmethod
    def from_hourly(
        cls,
        speeds_ms: Iterable[float],
        directions_from_deg: Iterable[float],
        sector_count: int = 16,
        speed_edges: Sequence[float] = DEFAULT_SPEED_EDGES,
        low_bin_speed_ms: float = 1.5,
        metadata: dict[str, Any] | None = None,
    ) -> WindTable:
        """Bin an hourly record of wind speed and direction into a joint table.

        Sector ``i`` is centred on ``i * 360 / sector_count`` and spans half a sector
        either side, so north is ``348.75-11.25`` for 16 sectors. Rows with non-finite
        values are dropped and counted in the metadata.

        Args:
            speeds_ms: Wind speeds at 10 m, m/s.
            directions_from_deg: Wind directions (FROM), degrees true.
            sector_count: Number of direction sectors.
            speed_edges: Ascending bin edges, m/s; the last bin is open ended.
            low_bin_speed_ms: Representative speed of the lowest bin.
            metadata: Extra provenance to store.

        Returns:
            The wind table (sums to 100 percent).

        Raises:
            ValueError: If no valid hourly rows remain or the edges are invalid.
        """
        speed = np.asarray(list(speeds_ms), dtype=float)
        direction = np.asarray(list(directions_from_deg), dtype=float)
        if speed.shape != direction.shape:
            raise ValueError("speed and direction series differ in length")
        if sector_count < 4 or list(speed_edges) != sorted(speed_edges):
            raise ValueError("need >= 4 sectors and ascending speed edges")
        valid = np.isfinite(speed) & np.isfinite(direction) & (speed >= 0.0)
        n_dropped = int((~valid).sum())
        speed, direction = speed[valid], direction[valid]
        if speed.size == 0:
            raise ValueError("no valid hourly wind records")
        width = 360.0 / sector_count
        sector_idx = (((direction % 360.0) + 0.5 * width) // width).astype(
            int
        ) % sector_count
        bin_idx = np.digitize(speed, np.asarray(speed_edges[1:], dtype=float))
        n_bins = len(speed_edges)
        counts = np.zeros((sector_count, n_bins))
        np.add.at(counts, (sector_idx, bin_idx), 1.0)
        labels = speed_bin_labels(speed_edges)
        if sector_count == 16:
            names = list(SECTOR_NAMES_16)
        else:
            names = [f"S{round(i * width):03d}" for i in range(sector_count)]
        meta = {
            "source": "hourly record",
            "n_hours": int(speed.size),
            "n_dropped_invalid": n_dropped,
            "mean_speed_ms": float(speed.mean()),
            "reference_height_m": 10.0,
        }
        meta.update(metadata or {})
        table = counts / counts.sum() * 100.0
        return cls(
            names,
            np.arange(sector_count) * width,
            labels,
            default_representative_speeds(labels, low_bin_speed_ms),
            table,
            meta,
        )

    @classmethod
    def from_hourly_csv(
        cls,
        path: str | Path,
        speed_column: str | None = None,
        direction_column: str | None = None,
        speed_scale: float = 1.0,
        **kwargs: Any,
    ) -> WindTable:
        """Build a table from a CSV with hourly speed and direction columns.

        Column names are auto-detected from common names (for example
        ``wind_speed_10m`` and ``wind_direction_10m`` from an open weather archive) when
        not given.

        Args:
            path: CSV file with a header row.
            speed_column: Speed column name, or ``None`` to detect.
            direction_column: Direction (FROM) column name, or ``None`` to detect.
            speed_scale: Multiplier that converts the speed column to m/s.
            **kwargs: Passed to :meth:`from_hourly`.

        Returns:
            The wind table.

        Raises:
            ValueError: If a column cannot be found.
        """
        speed_names = (
            "wind_speed_10m_ms",
            "wind_speed_10m",
            "wind_speed_ms",
            "wind_speed",
            "speed_ms",
            "ws10",
            "ws",
        )
        dir_names = (
            "wind_dir_from_deg",
            "wind_direction_10m",
            "wind_direction_from_deg",
            "wind_direction",
            "wind_dir",
            "direction_deg",
            "wd10",
            "wdir",
        )
        speeds: list[float] = []
        dirs: list[float] = []
        with Path(path).open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = reader.fieldnames or []
            lower = {name.strip().lower(): name for name in fields}
            sp = speed_column or next(
                (lower[n] for n in speed_names if n in lower), None
            )
            di = direction_column or next(
                (lower[n] for n in dir_names if n in lower), None
            )
            if sp is None or di is None:
                raise ValueError(
                    f"could not detect speed/direction columns in {list(fields)}"
                )
            for row in reader:
                try:
                    speeds.append(float(row[sp]) * speed_scale)
                    dirs.append(float(row[di]))
                except (TypeError, ValueError):
                    speeds.append(float("nan"))
                    dirs.append(float("nan"))
        meta = dict(kwargs.pop("metadata", {}) or {})
        meta.setdefault("source", f"hourly csv: {Path(path).name}")
        return cls.from_hourly(speeds, dirs, metadata=meta, **kwargs)
