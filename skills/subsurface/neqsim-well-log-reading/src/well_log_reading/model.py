"""Data model for well logs read from DLIS, LIS or LAS files.

The model is format neutral: every reader returns a :class:`WellLog` holding one
or more :class:`LogFrame` objects. A frame is a set of curves sampled on one
index (measured depth or time). Units are kept as written in the file; helpers
in :mod:`well_log_reading.units` convert the depth index to metres.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .units import canonical_mnemonic, depth_factor_to_m


@dataclass
class LogCurve:
    """One logged curve (channel) in a frame."""

    name: str
    unit: str
    values: np.ndarray
    long_name: str = ""

    @property
    def canonical(self) -> str | None:
        """Canonical mnemonic (GR, RHOB, NPHI, ...) or ``None`` if unknown."""
        return canonical_mnemonic(self.name, self.unit, self.long_name)

    @property
    def is_array(self) -> bool:
        """True for array channels (images, waveforms) with more than one value per depth."""
        return self.values.ndim > 1


@dataclass
class LogFrame:
    """Curves sampled on a common index (DLIS frame, LIS DFSR or LAS file)."""

    name: str
    index_name: str
    index_unit: str
    index: np.ndarray
    curves: dict[str, LogCurve] = field(default_factory=dict)
    index_type: str = ""

    @property
    def is_depth_indexed(self) -> bool:
        """True when the index is a depth that can be converted to metres."""
        return depth_factor_to_m(self.index_unit) is not None

    def depth_curve(self) -> LogCurve | None:
        """Return the depth channel of a time-indexed frame (TDEP, DEPT), or None.

        Station and tension logs are recorded against time with depth as an
        ordinary channel; that channel then provides the depth of every sample.
        """
        if self.is_depth_indexed:
            return None
        for curve in self.curves.values():
            if (
                curve.canonical == "DEPT"
                and not curve.is_array
                and depth_factor_to_m(curve.unit)
            ):
                return curve
        return None

    @property
    def has_depth(self) -> bool:
        """True when depth in metres is available from the index or a depth channel."""
        return self.is_depth_indexed or self.depth_curve() is not None

    def depth_m(self) -> np.ndarray:
        """Return the depth of every sample in metres.

        For a depth index the index is converted. For a time index the depth
        channel (see :meth:`depth_curve`) is used; such depths need not be monotonic.

        Raises:
            ValueError: if neither the index nor a channel is a depth with a known unit.
        """
        factor = depth_factor_to_m(self.index_unit)
        if factor is not None:
            return np.asarray(self.index, dtype=float) * factor
        curve = self.depth_curve()
        if curve is not None:
            return np.asarray(curve.values, dtype=float) * depth_factor_to_m(curve.unit)
        raise ValueError(
            f"frame {self.name!r} index {self.index_name!r} has unit {self.index_unit!r}, "
            "which is not a known depth unit, and no depth channel was found; "
            "set index_unit explicitly before converting"
        )

    def curve(self, name: str) -> LogCurve:
        """Return a curve by file mnemonic or canonical mnemonic (case-insensitive).

        Raises:
            KeyError: if no curve matches, or a canonical name matches several curves.
        """
        key = name.upper()
        for curve in self.curves.values():
            if curve.name.upper() == key:
                return curve
        matches = [c for c in self.curves.values() if c.canonical == key]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            names = ", ".join(c.name for c in matches)
            raise KeyError(
                f"canonical {name!r} is ambiguous in frame {self.name!r}: {names}"
            )
        raise KeyError(f"no curve {name!r} in frame {self.name!r}")

    def to_dataframe(self, depth_in_m: bool = True):
        """Return scalar curves as a pandas DataFrame indexed by depth (or the raw index).

        Array channels are skipped; reach them through :attr:`curves`.
        """
        import pandas as pd

        if depth_in_m and self.has_depth:
            index = pd.Index(self.depth_m(), name="DEPTH_M")
        else:
            index = pd.Index(np.asarray(self.index), name=self.index_name)
        data = {
            c.name: np.asarray(c.values, dtype=float)
            for c in self.curves.values()
            if not c.is_array
        }
        return pd.DataFrame(data, index=index)

    def inventory(self) -> list[dict]:
        """Summarise every curve: unit, canonical name, valid fraction and range of data."""
        rows = []
        if self.has_depth:
            index = self.depth_m()
        else:
            index = np.asarray(self.index, dtype=float)
        for curve in self.curves.values():
            values = np.asarray(curve.values, dtype=float)
            if values.ndim == 1:
                valid = np.isfinite(values)
            else:
                valid = np.isfinite(values.reshape(values.shape[0], -1)).any(axis=1)
            row = {
                "name": curve.name,
                "canonical": curve.canonical,
                "unit": curve.unit,
                "long_name": curve.long_name,
                "dimension": list(values.shape[1:]),
                "samples": int(values.shape[0]),
                "valid_fraction": float(valid.mean()) if values.shape[0] else 0.0,
                "first_valid_index": None,
                "last_valid_index": None,
                "min": None,
                "max": None,
            }
            if valid.any():
                row["first_valid_index"] = float(np.nanmin(index[valid]))
                row["last_valid_index"] = float(np.nanmax(index[valid]))
                if values.ndim == 1:
                    row["min"] = float(np.nanmin(values))
                    row["max"] = float(np.nanmax(values))
            rows.append(row)
        return rows


@dataclass
class WellLog:
    """Everything read from one log file."""

    source_path: str
    source_format: str
    sha256: str
    well_name: str = ""
    field_name: str = ""
    company: str = ""
    frames: list[LogFrame] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def frame(self, name: str | None = None) -> LogFrame:
        """Return a frame by name, or the depth frame with most samples when ``name`` is None.

        Raises:
            KeyError: if the named frame does not exist or the file has no frames.
        """
        if not self.frames:
            raise KeyError(f"{self.source_path} contains no curve frames")
        if name is None:
            ranked = sorted(
                self.frames,
                key=lambda f: (f.is_depth_indexed, f.has_depth, f.index.size),
                reverse=True,
            )
            return ranked[0]
        for frame in self.frames:
            if frame.name == name:
                return frame
        raise KeyError(f"no frame {name!r}; available: {[f.name for f in self.frames]}")
