import json

import numpy as np
import pytest
from flare_helideck_dispersion import (
    FlightPathSettings,
    PlatformGeometry,
    ReleaseCase,
    StudySettings,
    run_study,
)
from flare_helideck_dispersion.facility import (
    FacilityRelease,
    Receptor,
    Source,
    evaluate_facility,
    facility_section,
    facility_tilt_scan,
    facility_tornado,
    helideck_facility,
    into_wind_bearing,
    run_facility_study,
    write_facility_section,
)
from flare_release_cases import release_cases

SETTINGS = StudySettings(modes=("briggs",))


def test_helideck_preset_reproduces_the_helideck_study(wind):
    geometry = PlatformGeometry(
        flight_paths=FlightPathSettings(distance_step_m=100.0, bearing_step_deg=15.0)
    )
    case = release_cases()[1]
    old = run_study([case], wind, geometry, SETTINGS)
    source, receptors = helideck_facility(geometry)
    new = run_facility_study([FacilityRelease(case, source)], wind, receptors, SETTINGS)
    a = old.summaries[case.name]["modes"]["briggs"]
    b = new.summaries[case.name]["modes"]["briggs"]["receptors"]
    assert b["helideck"]["peak_pct_lfl"] == pytest.approx(a["peak_pct_lfl_helideck"])
    assert b["any_flight_path"]["peak_pct_lfl"] == pytest.approx(
        a["peak_pct_lfl_any_path"]
    )
    assert b["into_wind_path"]["peak_pct_lfl"] == pytest.approx(
        a["peak_pct_lfl_into_wind_path"]
    )
    for thr in ("10", "20"):
        assert b["any_flight_path"]["exceed_pct_hours"][thr] == pytest.approx(
            a["exceed_pct_hours"][thr]["any_path"]
        )
    cond = b["any_flight_path"]["peak_condition"]
    ref = a["peak_any_path_condition"]
    assert cond["path_bearing_deg"] == pytest.approx(ref["path_bearing_deg"])
    assert cond["path_distance_m"] == pytest.approx(ref["path_distance_m"])


def test_a_passive_release_dilutes_with_distance(wind):
    source = Source("vent", 0.0, 0.0, 40.0, "atmospheric_vent", tilt_deg=90.0)
    case = release_cases()[0]
    near = Receptor.point("near", "air_intake", 0.0, -100.0, 40.0)
    far = Receptor.point("far", "air_intake", 0.0, -1000.0, 40.0)
    passive = StudySettings(modes=("none",))
    result = run_facility_study(
        [FacilityRelease(case, source)], wind, [near, far], passive
    )
    rec = result.summaries[case.name]["modes"]["none"]["receptors"]
    assert rec["near"]["peak_pct_lfl"] > rec["far"]["peak_pct_lfl"] > 0.0
    for thr in (1.0, 5.0):
        assert result.exceedance(case.name, "far", thr, "none") <= result.exceedance(
            case.name, "near", thr, "none"
        )


def test_exceedance_decreases_with_the_threshold(wind):
    source = Source("flare", 0.0, 0.0, 60.0, "flare_tip", tilt_deg=30.0)
    cold = release_cases()[1]
    muster = Receptor.rectangle(
        "muster", "muster_area", 40.0, -80.0, 70.0, -50.0, 12.0, 10.0
    )
    result = run_facility_study(
        [FacilityRelease(cold, source)], wind, [muster], SETTINGS
    )
    values = [result.exceedance(cold.name, "muster", t) for t in (1.0, 5.0, 20.0, 50.0)]
    assert values == sorted(values, reverse=True)
    assert values[0] > 0.0


def test_two_sources_and_per_receptor_thresholds(wind):
    flare = Source("flare", 0.0, 0.0, 80.0, "flare_tip", tilt_deg=45.0)
    vent = Source("cold_vent", 150.0, 40.0, 55.0, "cold_vent", tilt_deg=90.0)
    cases = release_cases()
    releases = [FacilityRelease(cases[0], flare), FacilityRelease(cases[2], vent)]
    receptors = [
        Receptor.point(
            "hvac",
            "air_intake",
            90.0,
            20.0,
            45.0,
            thresholds_pct_lfl=(5.0, 10.0),
            criterion_source="design basis",
        ),
        Receptor.polyline(
            "escape", "escape_route", [(0, -40, 30), (60, -40, 30), (60, 30, 30)], 10.0
        ),
    ]
    result = run_facility_study(releases, wind, receptors, SETTINGS)
    hvac = result.summaries[cases[0].name]["modes"]["briggs"]["receptors"]["hvac"]
    assert set(hvac["exceed_pct_hours"]) == {"5", "10"}
    escape = result.summaries[cases[2].name]["modes"]["briggs"]["receptors"]["escape"]
    assert "20" in escape["exceed_pct_hours"]
    assert escape["peak_condition"]["path_distance_m"] >= 0.0
    ranking = result.ranking(20.0)
    assert len(ranking) == 4
    assert ranking == sorted(
        ranking, key=lambda r: (-r["exceed_pct_hours"], -r["peak_pct_lfl"])
    )
    assert any("no stated criterion" in w for w in result.warnings)
    assert [s.name for s in result.sources] == ["flare", "cold_vent"]


def test_receptor_shapes_from_dict_and_round_trip():
    specs = [
        {
            "name": "p",
            "kind": "air_intake",
            "shape": "point",
            "east_m": 1,
            "north_m": 2,
            "height_asl_m": 3,
        },
        {
            "name": "d",
            "shape": "disc",
            "east_m": 0,
            "north_m": 0,
            "height_asl_m": 10,
            "radius_m": 5,
        },
        {
            "name": "r",
            "shape": "rectangle",
            "east_min_m": 0,
            "north_min_m": 0,
            "east_max_m": 10,
            "north_max_m": 10,
            "heights_asl_m": [5, 10],
            "spacing_m": 5,
        },
        {
            "name": "l",
            "shape": "polyline",
            "vertices": [[0, 0, 5], [20, 0, 5]],
            "spacing_m": 5,
        },
        {
            "name": "f",
            "shape": "fan",
            "east_m": 0,
            "north_m": 0,
            "height_asl_m": 5,
            "start_deg": 350,
            "end_deg": 10,
            "length_m": 100,
            "distance_step_m": 50,
            "bearing_step_deg": 10,
        },
        {
            "name": "w",
            "shape": "into_wind_path",
            "east_m": 0,
            "north_m": 0,
            "height_asl_m": 5,
            "clear_start_deg": 90,
            "clear_end_deg": 180,
            "length_m": 100,
            "distance_step_m": 50,
        },
        {"name": "x", "shape": "points", "points": [[0, 0, 1], [1, 1, 1]]},
    ]
    built = [Receptor.from_dict(s) for s in specs]
    assert [len(r.points) for r in built[:6]] == [1, 5, 18, 5, 9, 1]
    assert built[5].follows_wind
    assert built[0].to_dict() == specs[0]
    with pytest.raises(ValueError):
        Receptor.from_dict({"name": "bad", "shape": "sphere"})
    with pytest.raises(ValueError):
        Receptor("empty", "other", np.zeros((0, 3)))


def test_into_wind_path_uses_the_nearest_edge_outside_the_sector():
    assert into_wind_bearing(120.0, 90.0, 180.0) == pytest.approx(120.0)
    assert into_wind_bearing(10.0, 90.0, 180.0) == pytest.approx(90.0)
    assert into_wind_bearing(260.0, 90.0, 180.0) == pytest.approx(180.0)
    path = Receptor.into_wind_path(
        "w", "flight_path", 0, 0, 5, 90.0, 180.0, 100.0, 50.0
    )
    pts = path.points_for_wind(120.0)
    assert pts[-1][0] == pytest.approx(100.0 * np.sin(np.radians(120.0)))


def test_duplicate_names_and_empty_inputs_are_rejected(wind):
    source = Source("s", 0, 0, 40)
    case = release_cases()[0]
    point = Receptor.point("a", "other", 10, 10, 10)
    with pytest.raises(ValueError):
        run_facility_study(
            [FacilityRelease(case, source)], wind, [point, point], SETTINGS
        )
    with pytest.raises(ValueError):
        run_facility_study([], wind, [point], SETTINGS)
    with pytest.raises(ValueError):
        Source("bad", height_asl_m=0.0)


def test_tilt_scan_and_tornado_report_every_receptor(wind):
    source = Source("flare", 0.0, 0.0, 70.0, "flare_tip", tilt_deg=45.0)
    fr = FacilityRelease(release_cases()[1], source)
    receptors = [
        Receptor.point("a", "air_intake", 0.0, -100.0, 60.0),
        Receptor.point("b", "muster_area", 80.0, -80.0, 20.0),
    ]
    rows = facility_tilt_scan(fr, wind, receptors, SETTINGS, (20.0, 70.0))
    assert [r["tilt_deg"] for r in rows] == [20.0, 45.0, 70.0]
    assert set(rows[0]["receptors"]) == {"a", "b"}
    assert "hours_ge20" in rows[0]["receptors"]["a"]
    tornado = facility_tornado(fr, wind, receptors, SETTINGS, "a")
    assert [t["parameter"] for t in tornado]
    assert tornado == sorted(tornado, key=lambda t: -t["swing_hours"])
    with pytest.raises(ValueError):
        evaluate_facility(fr, wind, receptors, SETTINGS, {"nonsense": 1.0})


def test_save_writes_json_and_arrays(tmp_path, wind):
    source = Source("flare", 0.0, 0.0, 60.0)
    case = ReleaseCase("c", 50.0, 0.0215, 1.25, 273.15, 0.04, 0.96, 0.6)
    result = run_facility_study(
        [FacilityRelease(case, source)],
        wind,
        [Receptor.point("a", "other", 0, -50, 50)],
        SETTINGS,
    )
    json_path, npz_path = result.save(tmp_path)
    assert json_path.exists() and npz_path.exists()
    assert "c_briggs__a__peak" in np.load(npz_path).files


def test_section_exports_a_plane_and_marks_receptors_in_it(tmp_path, wind):
    source = Source("flare", 0.0, 0.0, 40.0, "flare_tip", tilt_deg=20.0)
    case = release_cases()[1]
    muster = Receptor.point("muster", "muster_area", 50.0, -50.0, 25.0)
    aside = Receptor.point("aside", "air_intake", -200.0, 100.0, 25.0)
    result = run_facility_study(
        [FacilityRelease(case, source)], wind, [muster, aside], SETTINGS
    )
    section = facility_section(
        result, case.name, 315.0, 1.5, (-20.0, 150.0), (2.0, 80.0), 5.0, 2.0
    )
    values = np.asarray(section["values"])
    assert values.shape == (len(section["z"]), len(section["s"]))
    assert section["azimuth_deg"] == pytest.approx(135.0)
    assert section["peak_pct_lfl"] == pytest.approx(values.max())
    assert [m["label"] for m in section["marks"]] == ["muster"]
    mark = section["marks"][0]
    assert mark["s_m"] == pytest.approx(np.hypot(50.0, 50.0))
    assert mark["lateral_offset_m"] < 1.0
    written = write_facility_section(tmp_path / "s" / "section.json", section)
    assert set(json.loads(written.read_text(encoding="utf-8"))) >= {
        "s",
        "z",
        "values",
        "marks",
    }
    with pytest.raises(ValueError):
        facility_section(result, case.name, 315.0, 1.5, (10.0, 10.0))
