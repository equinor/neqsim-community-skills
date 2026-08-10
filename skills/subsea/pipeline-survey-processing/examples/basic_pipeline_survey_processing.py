"""Basic pipeline survey processing example using public synthetic data."""

from pipeline_survey_processing import PipelineSurveyProcessor


def synthetic_survey(offset_m: float = 0.0):
    records = []
    for index in range(0, 400):
        kp = index * 5.0
        depth = -298.0 + 0.004 * kp + offset_m
        seabed = depth + 0.2  # negative-up: seabed above the pipe top means 0.2 m cover
        if index == 120:
            depth = -999.25  # null marker
        if index == 200:
            depth += 45.0  # erroneous point
        if 300 <= index <= 310:
            seabed = depth - 0.4  # seabed below the pipe top: free span
        records.append({"kp_m": kp, "depth_to_top_m": depth, "seabed_depth_m": seabed})
    return records


def main() -> None:
    processor = PipelineSurveyProcessor(minimum_kp_spacing_m=5.0, span_gap_threshold_m=0.05)

    repeat = processor.process(
        records=synthetic_survey(),
        pipeline_id="SYN-Y-101",
        survey_id="2010-survey",
        outer_diameter_m=0.3239,
    )
    baseline = processor.process(
        records=synthetic_survey(offset_m=-0.3),
        pipeline_id="SYN-Y-101",
        survey_id="2006-survey",
        outer_diameter_m=0.3239,
    )

    print(f"depth convention        : {repeat.depth_convention}")
    print(f"retained / rejected     : {repeat.retained_point_count} / {repeat.rejected_point_count}")
    print(f"flagged erroneous points: {[point.kp_m for point in repeat.flagged_points]}")
    print(f"route length            : {repeat.route_length_m} m")
    print(f"span candidates         : {repeat.span_candidates}")
    print(f"minimum cover           : {repeat.minimum_cover_m} m")
    print(f"outer diameter source   : {repeat.outer_diameter_source}")
    print("processing log:")
    for entry in repeat.processing_log:
        print(f"  - {entry}")
    print("data gaps:")
    for entry in repeat.data_gaps:
        print(f"  - {entry}")

    change = processor.compare(baseline=baseline, repeat=repeat, change_threshold_m=0.2)
    print(f"max lowering / lifting  : {change.max_lowering_m} m / {change.max_lifting_m} m")
    print(f"changed intervals       : {len(change.changed_intervals)}")

    handoff = PipelineSurveyProcessor.to_neqsim_elevation_profile(repeat, section_count=10)
    print(f"neqsim leg positions    : {handoff['leg_positions_m'][:4]} ...")
    print(f"neqsim elevations       : {handoff['elevation_profile_m'][:4]} ...")


if __name__ == "__main__":
    main()
