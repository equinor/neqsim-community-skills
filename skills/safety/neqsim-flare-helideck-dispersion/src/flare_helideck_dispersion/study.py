"""Wind sweep, helideck and flight-path exposure, and conditional exceedance.

For every direction sector, sub-sector offset and speed bin of the wind table the study
evaluates the percent of the lower flammability limit (LFL) at

* the helideck points,
* every radial flight-path bearing across the obstacle-free sector (maximum over bearing
  and distance), and
* the into-wind approach or departure path.

Exceedance frequencies are weighted by the joint frequency table. They are CONDITIONAL
ON THE RELEASE: ``exceed_pct_hours = 12`` means that during 12 percent of wind hours,
given that an unignited release of that rate is ongoing, the threshold is exceeded
somewhere on the receptor. They are not annual frequencies. Use
:func:`annualise_exposure` together with an explicit flame-out (unignited release)
frequency and duration to obtain an expected exposure per year.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .model import (
    RISE_MODES,
    ModelParameters,
    Release,
    ReleaseCase,
    jet_consistency_check,
)
from .receptors import PlatformGeometry, Receptors
from .wind import StabilityScheme, WindTable, pasquill_by_speed

STUDY_SEMANTICS = (
    "Exceedance values are the percent of wind hours, weighted by the joint "
    "direction x speed frequency table, during which the threshold is exceeded GIVEN "
    "that an unignited release of the stated rate is ongoing. They are conditional "
    "probabilities, not annual frequencies, and carry no information on how often a "
    "flame-out or unignited release occurs."
)
"""Text carried into every results file to state the meaning of exceedance values."""


def threshold_key(threshold: float) -> str:
    """Return the dictionary key used for an exceedance threshold.

    Args:
        threshold: Threshold in percent of the LFL.

    Returns:
        ``"20"`` for 20.0 and ``"7.5"`` for 7.5.
    """
    return str(int(threshold)) if float(threshold) == int(threshold) else str(threshold)


@dataclass
class StudySettings:
    """Settings of the wind sweep.

    Attributes:
        modes: Plume modes to run (``briggs`` and/or ``none``).
        thresholds_pct_lfl: Exceedance thresholds, percent of the LFL.
        sub_offsets_deg: Wind-direction offsets inside each sector, degrees. ``None``
            uses ``[-0.4, -0.2, 0, 0.2, 0.4]`` times the sector width, which is
            ``[-9, -4.5, 0, 4.5, 9]`` degrees for 16 sectors.
        stability_scheme: Pasquill scheme name, bounds or callable (see
            :func:`flare_helideck_dispersion.wind.pasquill_by_speed`).
        params: Plume-model parameters.
    """

    modes: tuple[str, ...] = ("briggs", "none")
    thresholds_pct_lfl: tuple[float, ...] = (5.0, 10.0, 20.0, 50.0)
    sub_offsets_deg: Sequence[float] | None = None
    stability_scheme: StabilityScheme = "conservative_stable"
    params: ModelParameters = field(default_factory=ModelParameters)

    def __post_init__(self) -> None:
        """Validate the modes.

        Raises:
            ValueError: If a mode is unknown.
        """
        for mode in self.modes:
            if mode not in RISE_MODES:
                raise ValueError(f"mode must be one of {RISE_MODES}")

    def offsets_for(self, wind: WindTable) -> np.ndarray:
        """Return the sub-sector offsets for a wind table.

        Args:
            wind: The wind table.

        Returns:
            Array of offsets, degrees.
        """
        if self.sub_offsets_deg is not None:
            return np.asarray(self.sub_offsets_deg, dtype=float)
        return wind.sector_width_deg * np.array([-0.4, -0.2, 0.0, 0.2, 0.4])

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable mapping."""
        scheme = self.stability_scheme
        return {
            "modes": list(self.modes),
            "thresholds_pct_lfl": list(self.thresholds_pct_lfl),
            "sub_offsets_deg": (
                None
                if self.sub_offsets_deg is None
                else [float(v) for v in self.sub_offsets_deg]
            ),
            "stability_scheme": scheme if isinstance(scheme, str) else "custom",
            "params": {
                "tilt_deg": self.params.tilt_deg,
                "sigma0_divisor": self.params.sigma0_divisor,
                "wind_exponent": self.params.wind_exponent,
                "reference_height_m": self.params.reference_height_m,
                "ambient_temperature_k": self.params.ambient_temperature_k,
                "stable_dtheta_dz": dict(self.params.stable_dtheta_dz),
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> StudySettings:
        """Build settings from a mapping (for example parsed JSON).

        Args:
            data: Mapping with the keys of :meth:`to_dict`; all are optional.

        Returns:
            The settings.
        """
        kwargs: dict[str, Any] = {}
        if "modes" in data:
            kwargs["modes"] = tuple(data["modes"])
        if "thresholds_pct_lfl" in data:
            kwargs["thresholds_pct_lfl"] = tuple(
                float(v) for v in data["thresholds_pct_lfl"]
            )
        if data.get("sub_offsets_deg") is not None:
            kwargs["sub_offsets_deg"] = list(data["sub_offsets_deg"])
        if "stability_scheme" in data:
            kwargs["stability_scheme"] = data["stability_scheme"]
        if "params" in data:
            kwargs["params"] = ModelParameters(**dict(data["params"]))
        return cls(**kwargs)


@dataclass
class CaseArrays:
    """Percent-of-LFL arrays of one case and mode.

    All arrays are indexed ``[sector, sub_offset, speed_bin]``.

    Attributes:
        deck: Maximum over the helideck points.
        any_path: Maximum over all flight-path bearings and distances.
        into_wind: Maximum over the into-wind path.
        any_path_loc: ``(bearing_deg, distance_m)`` of the any-path maximum.
    """

    deck: np.ndarray
    any_path: np.ndarray
    into_wind: np.ndarray
    any_path_loc: np.ndarray


def run_case(
    release: Release,
    wind: WindTable,
    receptors: Receptors,
    settings: StudySettings,
    mode: str,
) -> CaseArrays:
    """Evaluate one release over the whole wind table for one plume mode.

    Args:
        release: The release.
        wind: Joint wind table.
        receptors: Helideck and flight-path points.
        settings: Study settings.
        mode: ``briggs`` or ``none``.

    Returns:
        The percent-of-LFL arrays.
    """
    tip = receptors.geometry.tip_position
    offsets = settings.offsets_for(wind)
    ns, nb = len(wind.sectors), len(wind.speed_bins)
    shape = (ns, len(offsets), nb)
    deck = np.zeros(shape)
    anypath = np.zeros(shape)
    intowind = np.zeros(shape)
    loc = np.zeros(shape + (2,))
    stabilities = [
        pasquill_by_speed(float(u), settings.stability_scheme)
        for u in wind.speed_rep_ms
    ]
    n_pts = receptors.n_path_points
    for i in range(ns):
        for j, off in enumerate(offsets):
            wd = (wind.sector_deg[i] + off) % 360.0
            into_pts = receptors.path_points(receptors.into_wind_bearing(wd))
            for k in range(nb):
                u = float(wind.speed_rep_ms[k])
                st = stabilities[k]
                deck[i, j, k] = release.pct_lfl(
                    receptors.deck_points, wd, u, st, tip, mode
                ).max()
                c = release.pct_lfl(receptors.all_paths, wd, u, st, tip, mode)
                idx = int(np.argmax(c))
                anypath[i, j, k] = c[idx]
                loc[i, j, k] = (
                    receptors.path_bearings[idx // n_pts],
                    receptors.path_distances[idx % n_pts],
                )
                intowind[i, j, k] = release.pct_lfl(
                    into_pts, wd, u, st, tip, mode
                ).max()
    return CaseArrays(deck, anypath, intowind, loc)


def exceedance_pct(arr: np.ndarray, wind: WindTable, threshold: float) -> float:
    """Percent of all wind hours with ``arr >= threshold`` (conditional on a release).

    Each sector and speed-bin cell is weighted by its share of hours; the sub-sector
    offsets share the cell weight equally.

    Args:
        arr: Array ``[sector, sub_offset, speed_bin]`` of percent of LFL.
        wind: Joint wind table.
        threshold: Threshold in percent of the LFL.

    Returns:
        Percent of wind hours given an ongoing release.
    """
    return float(np.sum(wind.table_pct * np.mean(arr >= threshold, axis=1)))


def exceedance_by_speed_bin(
    arr: np.ndarray, wind: WindTable, threshold: float
) -> dict[str, float]:
    """Contribution of each speed bin to the exceedance percentage.

    The contributions sum to :func:`exceedance_pct`.

    Args:
        arr: Array ``[sector, sub_offset, speed_bin]`` of percent of LFL.
        wind: Joint wind table.
        threshold: Threshold in percent of the LFL.

    Returns:
        Mapping of speed-bin label to percent of all hours.
    """
    per_bin = np.sum(wind.table_pct * np.mean(arr >= threshold, axis=1), axis=0)
    return {label: float(v) for label, v in zip(wind.speed_bins, per_bin)}


def annualise_exposure(
    conditional_pct_hours: float,
    release_frequency_per_year: float | None,
    hours_per_release: float | None,
) -> dict[str, float]:
    """Convert a conditional exceedance to expected exposed hours per year.

    Requires an explicit frequency of unignited releases (flame-out) and a duration. No
    default is offered on purpose: without a release frequency the conditional
    percentage cannot be turned into an annual figure.

    Args:
        conditional_pct_hours: Exceedance, percent of wind hours given a release.
        release_frequency_per_year: Frequency of unignited releases, 1/year.
        hours_per_release: Duration of one release, hours.

    Returns:
        Dictionary with ``exposed_hours_per_year`` and ``release_hours_per_year``.

    Raises:
        ValueError: If the frequency or duration is missing or negative.
    """
    if release_frequency_per_year is None or hours_per_release is None:
        raise ValueError(
            "an annual figure needs release_frequency_per_year (flame-out frequency) "
            "and hours_per_release; the conditional percentage alone is not annual"
        )
    if release_frequency_per_year < 0.0 or hours_per_release < 0.0:
        raise ValueError("frequency and duration must be non-negative")
    release_hours = release_frequency_per_year * hours_per_release
    return {
        "release_hours_per_year": release_hours,
        "exposed_hours_per_year": release_hours * conditional_pct_hours / 100.0,
    }


def _mode_summary(
    arrays: CaseArrays,
    wind: WindTable,
    receptors: Receptors,
    settings: StudySettings,
) -> dict[str, Any]:
    """Summarise one case and mode into peaks, exceedance and worst condition."""
    offsets = settings.offsets_for(wind)
    out: dict[str, Any] = {
        "peak_pct_lfl_helideck": float(arrays.deck.max()),
        "peak_pct_lfl_any_path": float(arrays.any_path.max()),
        "peak_pct_lfl_into_wind_path": float(arrays.into_wind.max()),
        "exceed_pct_hours": {},
        "exceed_any_path_by_speed_bin_pct_hours": {},
    }
    for thr in settings.thresholds_pct_lfl:
        key = threshold_key(thr)
        out["exceed_pct_hours"][key] = {
            "helideck": exceedance_pct(arrays.deck, wind, thr),
            "any_path": exceedance_pct(arrays.any_path, wind, thr),
            "into_wind_path": exceedance_pct(arrays.into_wind, wind, thr),
        }
        out["exceed_any_path_by_speed_bin_pct_hours"][key] = exceedance_by_speed_bin(
            arrays.any_path, wind, thr
        )
    pk = np.unravel_index(np.argmax(arrays.any_path), arrays.any_path.shape)
    out["peak_any_path_condition"] = {
        "sector": wind.sectors[pk[0]],
        "wind_from_deg": float((wind.sector_deg[pk[0]] + offsets[pk[1]]) % 360.0),
        "speed_bin": wind.speed_bins[pk[2]],
        "speed_m_s": float(wind.speed_rep_ms[pk[2]]),
        "path_bearing_deg": float(arrays.any_path_loc[pk][0]),
        "path_distance_m": float(arrays.any_path_loc[pk][1]),
    }
    return out


@dataclass
class StudyResult:
    """Result of a study over several release cases.

    Attributes:
        settings: The study settings used.
        wind: The wind table.
        geometry: The platform geometry.
        receptors: The receptor set.
        releases: Release objects by case name.
        summaries: Summary dictionary by case name.
        arrays: Mapping ``"<case>_<mode>"`` to :class:`CaseArrays`.
        warnings: Warnings collected during the run.
        semantics: Statement of the meaning of the exceedance values.
    """

    settings: StudySettings
    wind: WindTable
    geometry: PlatformGeometry
    receptors: Receptors
    releases: dict[str, Release]
    summaries: dict[str, dict[str, Any]]
    arrays: dict[str, CaseArrays]
    warnings: list[str] = field(default_factory=list)
    semantics: str = STUDY_SEMANTICS

    def case_arrays(self, case: str, mode: str = "briggs") -> CaseArrays:
        """Return the arrays of a case and mode.

        Args:
            case: Case name.
            mode: Plume mode.

        Returns:
            The arrays.
        """
        return self.arrays[f"{case}_{mode}"]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable mapping of the study summary."""
        return {
            "semantics": self.semantics,
            "settings": self.settings.to_dict(),
            "geometry": self.geometry.to_dict(),
            "receptors": self.receptors.describe(),
            "wind_metadata": dict(self.wind.metadata),
            "warnings": list(self.warnings),
            "cases": [self.summaries[name] for name in self.releases],
        }

    def save(self, out_dir: str | Path) -> tuple[Path, Path]:
        """Write ``study_results.json`` and ``study_arrays.npz``.

        Args:
            out_dir: Output directory (created if needed).

        Returns:
            Paths of the JSON and NPZ files.
        """
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        json_path = out / "study_results.json"
        npz_path = out / "study_arrays.npz"
        json_path.write_text(
            json.dumps(self.to_dict(), indent=1, default=float), encoding="utf-8"
        )
        flat: dict[str, np.ndarray] = {}
        for key, arr in self.arrays.items():
            flat[key + "_deck"] = arr.deck
            flat[key + "_any"] = arr.any_path
            flat[key + "_into"] = arr.into_wind
            flat[key + "_loc"] = arr.any_path_loc
        np.savez_compressed(npz_path, **flat)
        return json_path, npz_path


def run_study(
    cases: Sequence[ReleaseCase],
    wind: WindTable,
    geometry: PlatformGeometry,
    settings: StudySettings | None = None,
) -> StudyResult:
    """Run the wind sweep for all release cases.

    Args:
        cases: Release cases.
        wind: Joint wind table (validated here).
        geometry: Platform geometry.
        settings: Study settings (defaults are used if ``None``).

    Returns:
        The study result with summaries and arrays.
    """
    settings = settings or StudySettings()
    warnings = list(wind.validate())
    receptors = Receptors(geometry)
    warnings.extend(receptors.warnings())
    warnings.append(
        "plume model is a screening Gaussian model without platform wake or "
        "downwash; a Gaussian plume is not valid much below 1 m/s"
    )
    releases: dict[str, Release] = {}
    summaries: dict[str, dict[str, Any]] = {}
    arrays: dict[str, CaseArrays] = {}
    for case in cases:
        release = Release(case, settings.params)
        releases[case.name] = release
        entry: dict[str, Any] = {
            "name": case.name,
            "case": case.to_dict(),
            "tip": dict(release.tip),
            "jet_axial_distance_20pct_lfl_m": release.jet_distance_to(0.2),
            "jet_axial_distance_10pct_lfl_m": release.jet_distance_to(0.1),
            "jet_consistency_20pct_lfl": [],
            "modes": {},
        }
        for k, label in enumerate(wind.speed_bins):
            if wind.speed_rep_ms[k] >= 9.0:
                break
            stab = pasquill_by_speed(
                float(wind.speed_rep_ms[k]), settings.stability_scheme
            )
            check = jet_consistency_check(
                release,
                float(wind.speed_rep_ms[k]),
                stab,
                geometry.tip_height_asl_m,
                0.2,
            )
            check["speed_bin"] = label
            entry["jet_consistency_20pct_lfl"].append(check)
        for mode in settings.modes:
            arr = run_case(release, wind, receptors, settings, mode)
            arrays[f"{case.name}_{mode}"] = arr
            entry["modes"][mode] = _mode_summary(arr, wind, receptors, settings)
        summaries[case.name] = entry
    return StudyResult(
        settings, wind, geometry, receptors, releases, summaries, arrays, warnings
    )


def load_study(
    out_dir: str | Path,
    cases: Sequence[ReleaseCase],
    wind: WindTable,
    geometry: PlatformGeometry,
    settings: StudySettings | None = None,
) -> StudyResult:
    """Reload a saved study without re-running the wind sweep.

    The summaries are read from ``study_results.json`` and the arrays from
    ``study_arrays.npz``; release objects are rebuilt from the cases.

    Args:
        out_dir: Directory written by :meth:`StudyResult.save`.
        cases: The release cases of the saved run.
        wind: The wind table of the saved run.
        geometry: The geometry of the saved run.
        settings: The settings of the saved run.

    Returns:
        The study result.

    Raises:
        FileNotFoundError: If the saved files are missing.
    """
    out = Path(out_dir)
    data = json.loads((out / "study_results.json").read_text(encoding="utf-8"))
    npz = np.load(out / "study_arrays.npz")
    settings = settings or StudySettings.from_dict(data.get("settings", {}))
    receptors = Receptors(geometry)
    releases = {case.name: Release(case, settings.params) for case in cases}
    summaries = {entry["name"]: entry for entry in data["cases"]}
    arrays: dict[str, CaseArrays] = {}
    for case in cases:
        for mode in settings.modes:
            key = f"{case.name}_{mode}"
            arrays[key] = CaseArrays(
                npz[key + "_deck"],
                npz[key + "_any"],
                npz[key + "_into"],
                npz[key + "_loc"],
            )
    return StudyResult(
        settings,
        wind,
        geometry,
        receptors,
        releases,
        summaries,
        arrays,
        list(data.get("warnings", [])),
        data.get("semantics", STUDY_SEMANTICS),
    )


@dataclass
class BenchmarkScenario:
    """A comparison scenario against an independent (for example CFD) study.

    The helideck peak of the screening model, maximised over all wind directions at a
    fixed speed, is computed here and never typed into text. The reference outcome is
    supplied by the user together with its source.

    Attributes:
        label: Short label, for example ``330 kg/s, -50 C, 4 m/s``.
        case: Release case of the scenario.
        speed_m_s: Wind speed at the reference height, m/s.
        reference_outcome: What the independent study reported (user supplied).
        reference_source: Citation of the independent study (user supplied).
        reference_pct_lfl_max: Upper bound of the helideck concentration reported by the
            independent study, percent of the LFL (0 when it found no flammable gas);
            ``None`` when it reported no number.
    """

    label: str
    case: ReleaseCase
    speed_m_s: float
    reference_outcome: str = ""
    reference_source: str = ""
    reference_pct_lfl_max: float | None = None


def helideck_peak_over_directions(
    scenario: BenchmarkScenario,
    receptors: Receptors,
    settings: StudySettings,
    direction_step_deg: float = 2.0,
) -> dict[str, float]:
    """Peak percent of the LFL at the helideck over all wind directions at one speed.

    Args:
        scenario: Benchmark scenario.
        receptors: Receptor set.
        settings: Study settings (parameters and stability scheme).
        direction_step_deg: Direction step, degrees.

    Returns:
        Dictionary with ``peak_pct_lfl`` and ``wind_from_deg`` of the maximum.
    """
    release = Release(scenario.case, settings.params)
    stab = pasquill_by_speed(scenario.speed_m_s, settings.stability_scheme)
    tip = receptors.geometry.tip_position
    best, best_dir = 0.0, 0.0
    for wd in np.arange(0.0, 360.0, direction_step_deg):
        v = float(
            release.pct_lfl(
                receptors.deck_points, wd, scenario.speed_m_s, stab, tip
            ).max()
        )
        if v > best:
            best, best_dir = v, float(wd)
    return {"peak_pct_lfl": best, "wind_from_deg": best_dir, "stability": stab}
