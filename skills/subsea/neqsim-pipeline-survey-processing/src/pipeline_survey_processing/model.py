from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import atan2, cos, degrees, isfinite, radians

DEFAULT_SENTINELS = (-999.0, -999.25, -9999.0, 9999.0)
EARTH_RADIUS_M = 6371008.8


@dataclass(frozen=True)
class SurveyPoint:
    kp_m: float
    depth_to_top_m: float
    seabed_depth_m: float | None
    easting_m: float | None
    northing_m: float | None


@dataclass(frozen=True)
class FlaggedPoint:
    kp_m: float
    depth_to_top_m: float
    residual_m: float
    reason: str


@dataclass(frozen=True)
class SpanCandidate:
    start_kp_m: float
    end_kp_m: float
    length_m: float
    max_gap_m: float
    mean_gap_m: float


@dataclass(frozen=True)
class BurialInterval:
    start_kp_m: float
    end_kp_m: float
    length_m: float
    min_cover_m: float
    mean_cover_m: float


@dataclass(frozen=True)
class ChangedInterval:
    start_kp_m: float
    end_kp_m: float
    length_m: float
    max_change_m: float
    direction: str


@dataclass(frozen=True)
class SurveyProfileResult:
    pipeline_id: str
    survey_id: str
    depth_convention: str
    raw_point_count: int
    retained_point_count: int
    rejected_point_count: int
    points: tuple[SurveyPoint, ...]
    smoothed_depth_m: tuple[float, ...]
    flagged_points: tuple[FlaggedPoint, ...]
    kp_profile_m: tuple[float, ...]
    elevation_profile_m: tuple[float, ...]
    route_length_m: float
    max_slope_deg: float
    slope_warning: str
    span_candidates: tuple[SpanCandidate, ...]
    exposed_length_m: float
    longest_span_m: float
    buried_intervals: tuple[BurialInterval, ...]
    minimum_cover_m: float | None
    outer_diameter_m: float | None
    outer_diameter_source: str
    processing_log: tuple[str, ...]
    data_gaps: tuple[str, ...]
    neqsim_available: bool
    assumptions: tuple[str, ...]


@dataclass(frozen=True)
class SurveyComparisonResult:
    baseline_survey_id: str
    repeat_survey_id: str
    common_kp_m: tuple[float, ...]
    baseline_depth_m: tuple[float, ...]
    repeat_depth_m: tuple[float, ...]
    depth_change_m: tuple[float, ...]
    max_lowering_m: float
    max_lifting_m: float
    mean_absolute_change_m: float
    changed_intervals: tuple[ChangedInterval, ...]
    overlap_length_m: float
    processing_log: tuple[str, ...]
    assumptions: tuple[str, ...]


class PipelineSurveyProcessor:
    """Educational as-built pipeline survey processing and profile screening.

    Turns raw survey rows (KP, depth to top of pipe, optional seabed depth and
    coordinates) into a cleaned, resolution-filtered, sign-normalised profile
    with flagged erroneous points, free-span and burial candidates, and an
    elevation profile a NeqSim pipe model can consume.
    """

    def __init__(
        self,
        *,
        minimum_kp_spacing_m: float = 1.0,
        outlier_threshold: float = 4.0,
        minimum_residual_m: float = 0.1,
        smoothing_window: int = 11,
        span_gap_threshold_m: float = 0.05,
        max_slope_deg: float = 10.0,
        sentinel_values=DEFAULT_SENTINELS,
    ) -> None:
        self._require_positive("minimum_kp_spacing_m", minimum_kp_spacing_m)
        self._require_positive("outlier_threshold", outlier_threshold)
        self._require_positive("minimum_residual_m", minimum_residual_m)
        self._require_positive("span_gap_threshold_m", span_gap_threshold_m)
        self._require_positive("max_slope_deg", max_slope_deg)
        if smoothing_window < 3 or smoothing_window % 2 == 0:
            raise ValueError("smoothing_window must be an odd integer of at least 3")

        self.minimum_kp_spacing_m = minimum_kp_spacing_m
        self.outlier_threshold = outlier_threshold
        self.minimum_residual_m = minimum_residual_m
        self.smoothing_window = smoothing_window
        self.span_gap_threshold_m = span_gap_threshold_m
        self.max_slope_deg = max_slope_deg
        self.sentinel_values = tuple(float(value) for value in sentinel_values)

    # ------------------------------------------------------------------
    # main entry point
    # ------------------------------------------------------------------
    def process(
        self,
        *,
        records,
        pipeline_id: str = "unknown-pipeline",
        survey_id: str = "unknown-survey",
        start_kp_m: float | None = None,
        end_kp_m: float | None = None,
        outer_diameter_m: float | None = None,
    ) -> SurveyProfileResult:
        log: list[str] = []
        gaps: list[str] = []

        raw = list(records or [])
        if len(raw) < 2:
            raise ValueError("at least two survey records are required")
        log.append(f"read {len(raw)} raw survey records for {pipeline_id} / {survey_id}")

        rows = [self._normalize_row(row, log) for row in raw]
        rows = [row for row in rows if row is not None]
        log.append(f"{len(raw) - len(rows)} records removed as non-valid or sentinel values")

        convention = self._detect_depth_convention(rows, log)
        rows = self._apply_depth_convention(rows, convention)

        rows = self._derive_kp_if_missing(rows, log, gaps)
        rows.sort(key=lambda row: row["kp_m"])
        rows = self._enforce_monotonic_kp(rows, log)
        before_decimation = len(rows)
        rows = self._decimate(rows, log)
        log.append(
            f"resolution filter kept {len(rows)} of {before_decimation} points "
            f"at minimum spacing {self.minimum_kp_spacing_m} m"
        )

        rows = self._trim_section(rows, start_kp_m, end_kp_m, log)
        if len(rows) < 2:
            raise ValueError("fewer than two survey points remain after filtering")

        depths = [row["depth_to_top_m"] for row in rows]
        smoothed = self._rolling_median(depths)
        flagged, flagged_indices = self._flag_outliers(rows, depths, smoothed, log)

        points = tuple(
            SurveyPoint(
                kp_m=round(row["kp_m"], 3),
                depth_to_top_m=round(row["depth_to_top_m"], 3),
                seabed_depth_m=None if row["seabed_depth_m"] is None else round(row["seabed_depth_m"], 3),
                easting_m=row["easting_m"],
                northing_m=row["northing_m"],
            )
            for row in rows
        )

        kp_profile = tuple(point.kp_m for point in points)
        elevation_profile = tuple(round(-point.depth_to_top_m, 3) for point in points)
        route_length = round(kp_profile[-1] - kp_profile[0], 3)
        max_slope = self._max_slope(kp_profile, elevation_profile)

        diameter, diameter_source = self._resolve_diameter(rows, outer_diameter_m, log, gaps)
        spans, buried, exposed_length, minimum_cover = self._gap_analysis(rows, flagged_indices, log, gaps)

        return SurveyProfileResult(
            pipeline_id=pipeline_id,
            survey_id=survey_id,
            depth_convention=convention,
            raw_point_count=len(raw),
            retained_point_count=len(points),
            rejected_point_count=len(raw) - len(points),
            points=points,
            smoothed_depth_m=tuple(round(value, 3) for value in smoothed),
            flagged_points=flagged,
            kp_profile_m=kp_profile,
            elevation_profile_m=elevation_profile,
            route_length_m=route_length,
            max_slope_deg=max_slope,
            slope_warning=self._slope_warning(max_slope),
            span_candidates=spans,
            exposed_length_m=round(exposed_length, 3),
            longest_span_m=round(max((span.length_m for span in spans), default=0.0), 3),
            buried_intervals=buried,
            minimum_cover_m=minimum_cover,
            outer_diameter_m=diameter,
            outer_diameter_source=diameter_source,
            processing_log=tuple(log),
            data_gaps=tuple(gaps),
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational survey-processing screening only; not an as-built integrity assessment.",
                "Depths are normalised to positive-down metres below sea level.",
                "Erroneous points are flagged by robust residual against a rolling median, not by a vendor spline.",
                "Points within half a smoothing window of each end are not assessed for outliers.",
                "Flagged points are excluded from span and cover geometry but retained in the profile.",
                "Span and burial candidates require a seabed depth per point; without it they are not reported.",
                "Span candidates are geometric only; no DNV-RP-F105 modal, VIV, or fatigue assessment is performed.",
                "Move to DNV-RP-F105, DNV-RP-F109, and DNV-RP-F114 kernels and qualified review for design decisions.",
            ),
        )

    # ------------------------------------------------------------------
    # repeat-survey comparison
    # ------------------------------------------------------------------
    def compare(
        self,
        *,
        baseline: SurveyProfileResult,
        repeat: SurveyProfileResult,
        change_threshold_m: float = 0.2,
        sample_count: int = 200,
    ) -> SurveyComparisonResult:
        self._require_positive("change_threshold_m", change_threshold_m)
        if sample_count < 2:
            raise ValueError("sample_count must be at least 2")

        log: list[str] = []
        start = max(baseline.kp_profile_m[0], repeat.kp_profile_m[0])
        end = min(baseline.kp_profile_m[-1], repeat.kp_profile_m[-1])
        if end <= start:
            raise ValueError("baseline and repeat surveys do not overlap in KP")
        log.append(f"common KP window {round(start, 3)} m to {round(end, 3)} m")

        step = (end - start) / (sample_count - 1)
        grid = [start + step * index for index in range(sample_count)]
        base_depths = [self._interpolate(baseline, value) for value in grid]
        repeat_depths = [self._interpolate(repeat, value) for value in grid]
        changes = [repeat_depth - base_depth for base_depth, repeat_depth in zip(base_depths, repeat_depths)]
        log.append(f"compared {sample_count} interpolated stations")

        intervals: list[ChangedInterval] = []
        current: list[tuple[float, float]] = []
        for station, change in zip(grid, changes):
            if abs(change) >= change_threshold_m:
                current.append((station, change))
                continue
            if current:
                intervals.append(self._changed_interval(current))
                current = []
        if current:
            intervals.append(self._changed_interval(current))
        log.append(f"{len(intervals)} intervals exceed the {change_threshold_m} m change threshold")

        return SurveyComparisonResult(
            baseline_survey_id=baseline.survey_id,
            repeat_survey_id=repeat.survey_id,
            common_kp_m=tuple(round(value, 3) for value in grid),
            baseline_depth_m=tuple(round(value, 3) for value in base_depths),
            repeat_depth_m=tuple(round(value, 3) for value in repeat_depths),
            depth_change_m=tuple(round(value, 3) for value in changes),
            max_lowering_m=round(max((value for value in changes if value > 0.0), default=0.0), 3),
            max_lifting_m=round(-min((value for value in changes if value < 0.0), default=0.0), 3),
            mean_absolute_change_m=round(sum(abs(value) for value in changes) / len(changes), 3),
            changed_intervals=tuple(intervals),
            overlap_length_m=round(end - start, 3),
            processing_log=tuple(log),
            assumptions=(
                "Educational repeat-survey comparison only.",
                "Depth change is repeat minus baseline; positive means the pipe top sits deeper.",
                "Both surveys are linearly interpolated onto a common KP grid.",
                "A change can be real movement, a survey datum or tide correction difference, or survey uncertainty.",
                "Confirm datum, tide, and positioning basis before treating a change as pipeline movement.",
            ),
        )

    # ------------------------------------------------------------------
    # NeqSim handoff
    # ------------------------------------------------------------------
    @staticmethod
    def to_neqsim_elevation_profile(result: SurveyProfileResult, section_count: int = 20) -> dict[str, list[float]]:
        """Resample the profile onto an evenly spaced grid for a NeqSim pipe model."""
        if section_count < 1:
            raise ValueError("section_count must be at least 1")
        start = result.kp_profile_m[0]
        end = result.kp_profile_m[-1]
        step = (end - start) / section_count
        positions = [start + step * index for index in range(section_count + 1)]
        elevations = [
            -PipelineSurveyProcessor._interpolate(result, position) for position in positions
        ]
        return {
            "leg_positions_m": [round(value - start, 3) for value in positions],
            "elevation_profile_m": [round(value, 3) for value in elevations],
        }

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _normalize_row(self, raw, log: list[str]) -> dict | None:
        row = {
            "kp_m": self._optional_float(raw.get("kp_m")),
            "depth_to_top_m": self._optional_float(raw.get("depth_to_top_m")),
            "seabed_depth_m": self._optional_float(raw.get("seabed_depth_m")),
            "easting_m": self._optional_float(raw.get("easting_m")),
            "northing_m": self._optional_float(raw.get("northing_m")),
            "outer_diameter_m": self._optional_float(raw.get("outer_diameter_m")),
        }
        latitude = self._optional_float(raw.get("latitude_deg"))
        longitude = self._optional_float(raw.get("longitude_deg"))
        if latitude is not None and longitude is not None:
            if abs(latitude) > 90.0 and abs(longitude) <= 90.0:
                latitude, longitude = longitude, latitude
                if "latitude/longitude column order corrected" not in log:
                    log.append("latitude/longitude column order corrected")
            row["latitude_deg"] = latitude
            row["longitude_deg"] = longitude
        if row["depth_to_top_m"] is None:
            return None
        return row

    def _optional_float(self, value) -> float | None:
        if value is None:
            return None
        number = float(value)
        if not isfinite(number):
            return None
        if any(abs(number - sentinel) < 1.0e-6 for sentinel in self.sentinel_values):
            return None
        return number

    def _detect_depth_convention(self, rows, log: list[str]) -> str:
        depths = [row["depth_to_top_m"] for row in rows]
        if all(value <= 0.0 for value in depths):
            log.append("depth convention detected as negative-up; converted to positive-down")
            return "negative-up"
        if all(value >= 0.0 for value in depths):
            log.append("depth convention detected as positive-down")
            return "positive-down"
        raise ValueError("depth_to_top_m has mixed signs; state the depth convention explicitly")

    @staticmethod
    def _apply_depth_convention(rows, convention: str):
        if convention == "positive-down":
            return rows
        for row in rows:
            row["depth_to_top_m"] = -row["depth_to_top_m"]
            if row["seabed_depth_m"] is not None:
                row["seabed_depth_m"] = -row["seabed_depth_m"]
        return rows

    def _derive_kp_if_missing(self, rows, log: list[str], gaps: list[str]):
        if all(row["kp_m"] is not None for row in rows):
            return rows
        if all(row.get("latitude_deg") is not None for row in rows):
            self._project_lat_lon(rows, log)
        if any(row["easting_m"] is None or row["northing_m"] is None for row in rows):
            raise ValueError("kp_m is missing and no complete coordinate set is available to derive it")

        cumulative = 0.0
        rows[0]["kp_m"] = 0.0
        for index in range(1, len(rows)):
            previous = rows[index - 1]
            current = rows[index]
            step = (
                (current["easting_m"] - previous["easting_m"]) ** 2
                + (current["northing_m"] - previous["northing_m"]) ** 2
            ) ** 0.5
            cumulative += step
            current["kp_m"] = cumulative
        log.append("KP derived from cumulative projected coordinate distance")
        gaps.append("KP was derived from coordinates; confirm against the survey KP reference.")
        return rows

    @staticmethod
    def _project_lat_lon(rows, log: list[str]) -> None:
        origin_lat = rows[0]["latitude_deg"]
        origin_lon = rows[0]["longitude_deg"]
        scale = cos(radians(origin_lat))
        for row in rows:
            row["easting_m"] = radians(row["longitude_deg"] - origin_lon) * EARTH_RADIUS_M * scale
            row["northing_m"] = radians(row["latitude_deg"] - origin_lat) * EARTH_RADIUS_M
        log.append("latitude/longitude projected to local easting/northing (equirectangular, screening only)")

    @staticmethod
    def _enforce_monotonic_kp(rows, log: list[str]):
        kept = [rows[0]]
        dropped = 0
        for row in rows[1:]:
            if row["kp_m"] <= kept[-1]["kp_m"]:
                dropped += 1
                continue
            kept.append(row)
        if dropped:
            log.append(f"{dropped} duplicate or non-increasing KP records removed")
        return kept

    def _decimate(self, rows, log: list[str]):
        kept = [rows[0]]
        for row in rows[1:-1]:
            if row["kp_m"] - kept[-1]["kp_m"] >= self.minimum_kp_spacing_m:
                kept.append(row)
        if rows[-1] is not kept[-1]:
            kept.append(rows[-1])
        return kept

    @staticmethod
    def _trim_section(rows, start_kp_m: float | None, end_kp_m: float | None, log: list[str]):
        if start_kp_m is None and end_kp_m is None:
            return rows
        low = -float("inf") if start_kp_m is None else float(start_kp_m)
        high = float("inf") if end_kp_m is None else float(end_kp_m)
        if high <= low:
            raise ValueError("end_kp_m must be greater than start_kp_m")
        trimmed = [row for row in rows if low <= row["kp_m"] <= high]
        log.append(f"section trimmed to KP {low} m - {high} m keeping {len(trimmed)} points")
        return trimmed

    def _rolling_median(self, values) -> list[float]:
        half = self.smoothing_window // 2
        smoothed: list[float] = []
        for index in range(len(values)):
            low = max(0, index - half)
            high = min(len(values), index + half + 1)
            window = sorted(values[low:high])
            middle = len(window) // 2
            if len(window) % 2:
                smoothed.append(window[middle])
            else:
                smoothed.append(0.5 * (window[middle - 1] + window[middle]))
        return smoothed

    def _flag_outliers(self, rows, depths, smoothed, log: list[str]):
        residuals = [depth - reference for depth, reference in zip(depths, smoothed)]
        half = self.smoothing_window // 2
        assessable = range(half, max(half, len(rows) - half))
        interior = [abs(residuals[index]) for index in assessable]
        if not interior:
            log.append("too few points to assess outliers against the smoothing window")
            return (), frozenset()
        median_absolute = sorted(interior)[len(interior) // 2]
        scale = 1.4826 * median_absolute
        limit = max(self.outlier_threshold * scale, self.minimum_residual_m)

        flagged: list[FlaggedPoint] = []
        indices: list[int] = []
        for index in assessable:
            if abs(residuals[index]) <= limit:
                continue
            indices.append(index)
            flagged.append(
                FlaggedPoint(
                    kp_m=round(rows[index]["kp_m"], 3),
                    depth_to_top_m=round(rows[index]["depth_to_top_m"], 3),
                    residual_m=round(residuals[index], 3),
                    reason="residual exceeds robust threshold against rolling median",
                )
            )
        log.append(
            f"{len(flagged)} points flagged as erroneous above a {round(limit, 3)} m residual "
            f"({self.outlier_threshold} x robust sigma, floored at {self.minimum_residual_m} m); "
            f"{2 * half} edge points not assessed"
        )
        return tuple(flagged), frozenset(indices)

    @staticmethod
    def _max_slope(kp_profile, elevation_profile) -> float:
        worst = 0.0
        for index in range(len(kp_profile) - 1):
            run = kp_profile[index + 1] - kp_profile[index]
            if run <= 0.0:
                continue
            rise = abs(elevation_profile[index + 1] - elevation_profile[index])
            worst = max(worst, degrees(atan2(rise, run)))
        return round(worst, 3)

    def _slope_warning(self, max_slope_deg: float) -> str:
        if max_slope_deg >= self.max_slope_deg:
            return "high"
        if max_slope_deg >= 0.8 * self.max_slope_deg:
            return "watch"
        return "ok"

    @staticmethod
    def _resolve_diameter(rows, override, log: list[str], gaps: list[str]):
        if override is not None:
            value = float(override)
            if value <= 0.0:
                raise ValueError("outer_diameter_m must be positive")
            log.append(f"outer diameter set to {value} m by user override")
            gaps.append("Outer diameter was supplied manually; confirm against the line list or pipe class.")
            return value, "user_override"
        surveyed = [row["outer_diameter_m"] for row in rows if row["outer_diameter_m"]]
        if surveyed:
            value = sum(surveyed) / len(surveyed)
            log.append(f"outer diameter taken from survey records as {round(value, 4)} m")
            return round(value, 4), "survey"
        log.append("no outer diameter available in the survey or as an override")
        gaps.append("Outer diameter is missing; embedment, cover, and span screening cannot be normalised by D.")
        return None, "missing"

    def _gap_analysis(self, rows, flagged_indices, log: list[str], gaps: list[str]):
        with_seabed = [
            row
            for index, row in enumerate(rows)
            if row["seabed_depth_m"] is not None and index not in flagged_indices
        ]
        if len(with_seabed) < 2:
            log.append("seabed depth unavailable; span and burial screening skipped")
            gaps.append("Seabed depth per KP is missing; free-span and cover screening cannot be performed.")
            return (), (), 0.0, None

        spans: list[SpanCandidate] = []
        buried: list[BurialInterval] = []
        exposed_length = 0.0
        covers: list[float] = []
        span_run: list[tuple[float, float]] = []
        buried_run: list[tuple[float, float]] = []

        for row in with_seabed:
            cover = row["depth_to_top_m"] - row["seabed_depth_m"]
            covers.append(cover)
            gap = -cover
            if gap >= self.span_gap_threshold_m:
                span_run.append((row["kp_m"], gap))
            elif span_run:
                spans.append(self._span_from_run(span_run))
                span_run = []
            if cover > 0.0:
                buried_run.append((row["kp_m"], cover))
            elif buried_run:
                buried.append(self._burial_from_run(buried_run))
                buried_run = []
        if span_run:
            spans.append(self._span_from_run(span_run))
        if buried_run:
            buried.append(self._burial_from_run(buried_run))

        exposed_length = sum(span.length_m for span in spans)
        log.append(
            f"{len(spans)} free-span candidates ({round(exposed_length, 1)} m exposed) and "
            f"{len(buried)} buried intervals identified"
        )
        return tuple(spans), tuple(buried), exposed_length, round(min(covers), 3)

    @staticmethod
    def _span_from_run(run) -> SpanCandidate:
        stations = [item[0] for item in run]
        values = [item[1] for item in run]
        return SpanCandidate(
            start_kp_m=round(stations[0], 3),
            end_kp_m=round(stations[-1], 3),
            length_m=round(stations[-1] - stations[0], 3),
            max_gap_m=round(max(values), 3),
            mean_gap_m=round(sum(values) / len(values), 3),
        )

    @staticmethod
    def _burial_from_run(run) -> BurialInterval:
        stations = [item[0] for item in run]
        values = [item[1] for item in run]
        return BurialInterval(
            start_kp_m=round(stations[0], 3),
            end_kp_m=round(stations[-1], 3),
            length_m=round(stations[-1] - stations[0], 3),
            min_cover_m=round(min(values), 3),
            mean_cover_m=round(sum(values) / len(values), 3),
        )

    @staticmethod
    def _changed_interval(run) -> ChangedInterval:
        stations = [item[0] for item in run]
        values = [item[1] for item in run]
        extreme = max(values, key=abs)
        return ChangedInterval(
            start_kp_m=round(stations[0], 3),
            end_kp_m=round(stations[-1], 3),
            length_m=round(stations[-1] - stations[0], 3),
            max_change_m=round(extreme, 3),
            direction="lowering" if extreme > 0.0 else "lifting",
        )

    @staticmethod
    def _interpolate(result: SurveyProfileResult, station: float) -> float:
        kp = result.kp_profile_m
        depths = [point.depth_to_top_m for point in result.points]
        if station <= kp[0]:
            return depths[0]
        if station >= kp[-1]:
            return depths[-1]
        for index in range(len(kp) - 1):
            if kp[index] <= station <= kp[index + 1]:
                span = kp[index + 1] - kp[index]
                fraction = (station - kp[index]) / span
                return depths[index] + fraction * (depths[index + 1] - depths[index])
        return depths[-1]

    @staticmethod
    def _require_positive(name: str, value: float) -> None:
        number = float(value)
        if not isfinite(number) or number <= 0.0:
            raise ValueError(f"{name} must be a positive finite number")
