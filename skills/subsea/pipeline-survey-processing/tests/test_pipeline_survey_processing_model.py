import pytest

from pipeline_survey_processing import PipelineSurveyProcessor


def build_records(offset_m: float = 0.0, count: int = 200):
    """Negative-up survey rows; seabed 0.2 m above the pipe top, i.e. 0.2 m cover."""
    records = []
    for index in range(count):
        kp = index * 5.0
        depth = -300.0 + 0.01 * kp + offset_m
        records.append({"kp_m": kp, "depth_to_top_m": depth, "seabed_depth_m": depth + 0.2})
    return records


def test_detects_negative_up_convention_and_normalises_depths():
    result = PipelineSurveyProcessor().process(records=build_records())

    assert result.depth_convention == "negative-up"
    assert all(point.depth_to_top_m > 0.0 for point in result.points)
    assert result.elevation_profile_m[0] < 0.0


def test_mixed_sign_depths_are_refused():
    records = [
        {"kp_m": 0.0, "depth_to_top_m": -300.0},
        {"kp_m": 5.0, "depth_to_top_m": 300.0},
    ]

    with pytest.raises(ValueError, match="mixed signs"):
        PipelineSurveyProcessor().process(records=records)


def test_sentinel_and_non_finite_values_are_removed():
    records = build_records(count=40)
    records[5]["depth_to_top_m"] = -999.25
    records[6]["depth_to_top_m"] = float("nan")

    result = PipelineSurveyProcessor(minimum_kp_spacing_m=1.0).process(records=records)

    assert result.rejected_point_count == 2
    assert result.retained_point_count == len(records) - 2
    assert any("non-valid or sentinel" in entry for entry in result.processing_log)


def test_resolution_filter_thins_closely_spaced_points_and_keeps_endpoints():
    records = build_records(count=100)

    result = PipelineSurveyProcessor(minimum_kp_spacing_m=50.0).process(records=records)

    assert result.retained_point_count < 100
    assert result.kp_profile_m[0] == pytest.approx(0.0)
    assert result.kp_profile_m[-1] == pytest.approx(495.0)


def test_duplicate_and_non_increasing_kp_are_removed():
    records = build_records(count=20)
    records.append({"kp_m": 10.0, "depth_to_top_m": -299.0, "seabed_depth_m": -298.8})

    result = PipelineSurveyProcessor(minimum_kp_spacing_m=1.0).process(records=records)

    stations = list(result.kp_profile_m)
    assert stations == sorted(stations)
    assert len(set(stations)) == len(stations)


def test_erroneous_point_is_flagged_not_deleted():
    records = build_records(count=80)
    records[40]["depth_to_top_m"] += 40.0

    result = PipelineSurveyProcessor(minimum_kp_spacing_m=1.0).process(records=records)

    flagged_stations = [point.kp_m for point in result.flagged_points]
    assert 200.0 in flagged_stations
    assert 200.0 in result.kp_profile_m


def test_flagged_point_does_not_drive_span_or_cover_geometry():
    records = build_records(count=80)
    records[40]["depth_to_top_m"] -= 40.0  # pipe top 40 m below the seabed reading

    result = PipelineSurveyProcessor(minimum_kp_spacing_m=1.0).process(records=records)

    assert [point.kp_m for point in result.flagged_points] == [200.0]
    assert result.minimum_cover_m == pytest.approx(0.2, abs=1e-3)
    assert result.span_candidates == ()


def test_edge_points_are_not_assessed_for_outliers():
    records = build_records(count=40)
    records[0]["depth_to_top_m"] -= 40.0

    result = PipelineSurveyProcessor(minimum_kp_spacing_m=1.0, smoothing_window=11).process(records=records)

    assert result.flagged_points == ()
    assert any("edge points not assessed" in entry for entry in result.processing_log)


def test_section_trim_keeps_only_the_requested_window():
    result = PipelineSurveyProcessor(minimum_kp_spacing_m=1.0).process(
        records=build_records(count=100), start_kp_m=100.0, end_kp_m=200.0
    )

    assert result.kp_profile_m[0] >= 100.0
    assert result.kp_profile_m[-1] <= 200.0
    assert result.route_length_m == pytest.approx(100.0)


def test_free_span_candidates_group_consecutive_gaps():
    records = build_records(count=100)
    for index in range(40, 51):
        records[index]["seabed_depth_m"] = records[index]["depth_to_top_m"] - 0.4

    result = PipelineSurveyProcessor(minimum_kp_spacing_m=1.0).process(records=records)

    assert len(result.span_candidates) == 1
    span = result.span_candidates[0]
    assert span.start_kp_m == pytest.approx(200.0)
    assert span.end_kp_m == pytest.approx(250.0)
    assert span.max_gap_m == pytest.approx(0.4, abs=1e-3)
    assert result.longest_span_m == pytest.approx(50.0)


def test_burial_intervals_and_minimum_cover_are_reported():
    records = build_records(count=30)

    result = PipelineSurveyProcessor(minimum_kp_spacing_m=1.0).process(records=records)

    assert result.minimum_cover_m == pytest.approx(0.2, abs=1e-3)
    assert len(result.buried_intervals) == 1
    assert result.exposed_length_m == pytest.approx(0.0)


def test_missing_seabed_depth_skips_span_screening_and_records_a_gap():
    records = [{"kp_m": index * 5.0, "depth_to_top_m": -300.0 + 0.01 * index} for index in range(20)]

    result = PipelineSurveyProcessor(minimum_kp_spacing_m=1.0).process(records=records)

    assert result.span_candidates == ()
    assert result.minimum_cover_m is None
    assert any("Seabed depth" in gap for gap in result.data_gaps)


def test_user_supplied_outer_diameter_is_recorded_as_a_gap():
    result = PipelineSurveyProcessor().process(records=build_records(count=20), outer_diameter_m=0.3239)

    assert result.outer_diameter_m == pytest.approx(0.3239)
    assert result.outer_diameter_source == "user_override"
    assert any("Outer diameter was supplied manually" in gap for gap in result.data_gaps)


def test_missing_outer_diameter_is_reported_rather_than_assumed():
    result = PipelineSurveyProcessor().process(records=build_records(count=20))

    assert result.outer_diameter_m is None
    assert result.outer_diameter_source == "missing"


def test_swapped_latitude_longitude_columns_are_corrected_and_kp_derived():
    records = []
    for index in range(20):
        records.append(
            {
                "latitude_deg": 100.0 + index * 0.001,  # longitude value in the latitude column
                "longitude_deg": 60.0,
                "depth_to_top_m": -300.0,
            }
        )

    result = PipelineSurveyProcessor(minimum_kp_spacing_m=1.0).process(records=records)

    assert any("column order corrected" in entry for entry in result.processing_log)
    assert result.route_length_m > 0.0
    assert any("KP was derived" in gap for gap in result.data_gaps)


def test_kp_is_derived_from_projected_coordinates_when_absent():
    records = [
        {"easting_m": index * 100.0, "northing_m": 0.0, "depth_to_top_m": -300.0} for index in range(10)
    ]

    result = PipelineSurveyProcessor(minimum_kp_spacing_m=1.0).process(records=records)

    assert result.route_length_m == pytest.approx(900.0)


def test_slope_warning_escalates_on_a_steep_section():
    records = [
        {"kp_m": 0.0, "depth_to_top_m": -300.0},
        {"kp_m": 10.0, "depth_to_top_m": -290.0},
        {"kp_m": 20.0, "depth_to_top_m": -289.0},
    ]

    result = PipelineSurveyProcessor(minimum_kp_spacing_m=1.0, max_slope_deg=10.0).process(records=records)

    assert result.max_slope_deg > 10.0
    assert result.slope_warning == "high"


def test_repeat_survey_comparison_detects_lowering():
    processor = PipelineSurveyProcessor(minimum_kp_spacing_m=1.0)
    baseline = processor.process(records=build_records(count=60), survey_id="2006")
    repeat = processor.process(records=build_records(offset_m=-0.5, count=60), survey_id="2010")

    change = processor.compare(baseline=baseline, repeat=repeat, change_threshold_m=0.2)

    assert change.baseline_survey_id == "2006"
    assert change.max_lowering_m == pytest.approx(0.5, abs=1e-2)
    assert change.max_lifting_m == pytest.approx(0.0)
    assert change.changed_intervals[0].direction == "lowering"


def test_comparison_requires_overlapping_kp():
    processor = PipelineSurveyProcessor(minimum_kp_spacing_m=1.0)
    first = processor.process(records=build_records(count=20))
    second = processor.process(
        records=[{"kp_m": 10000.0 + index * 5.0, "depth_to_top_m": -300.0} for index in range(20)]
    )

    with pytest.raises(ValueError, match="do not overlap"):
        processor.compare(baseline=first, repeat=second)


def test_neqsim_elevation_profile_handoff_is_evenly_spaced():
    result = PipelineSurveyProcessor(minimum_kp_spacing_m=1.0).process(records=build_records(count=50))

    handoff = PipelineSurveyProcessor.to_neqsim_elevation_profile(result, section_count=10)

    assert len(handoff["leg_positions_m"]) == 11
    assert len(handoff["elevation_profile_m"]) == 11
    assert handoff["leg_positions_m"][0] == pytest.approx(0.0)
    assert handoff["leg_positions_m"][-1] == pytest.approx(result.route_length_m)
    assert handoff["elevation_profile_m"][-1] > handoff["elevation_profile_m"][0]


def test_processing_log_and_assumptions_are_always_populated():
    result = PipelineSurveyProcessor().process(records=build_records(count=20))

    assert result.processing_log
    assert result.assumptions
    assert result.neqsim_available in (True, False)


def test_too_few_records_is_refused():
    with pytest.raises(ValueError, match="at least two"):
        PipelineSurveyProcessor().process(records=[{"kp_m": 0.0, "depth_to_top_m": -300.0}])


def test_invalid_smoothing_window_is_refused():
    with pytest.raises(ValueError, match="odd integer"):
        PipelineSurveyProcessor(smoothing_window=10)
