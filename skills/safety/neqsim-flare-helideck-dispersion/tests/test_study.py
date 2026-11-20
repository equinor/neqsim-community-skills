import copy

import numpy as np
import pytest
from flare_helideck_dispersion import (
    BenchmarkScenario,
    PlatformGeometry,
    ReleaseCase,
    StudySettings,
    WindTable,
    annualise_exposure,
    exceedance_pct,
    run_study,
)
from flare_helideck_dispersion.study import (
    exceedance_by_speed_bin,
    helideck_peak_over_directions,
    load_study,
)
from flare_helideck_dispersion.wind import (
    SECTOR_NAMES_16,
    default_representative_speeds,
)

REGRESSION_CASE = ReleaseCase("regress", 150.0, 0.0215, 1.25, 190.0, 0.04, 0.96, 0.6)
LABELS = [
    "0-2",
    "2-4",
    "4-6",
    "6-8",
    "8-10",
    "10-12",
    "12-14",
    "14-16",
    "16-18",
    "18-20",
    ">20",
]


def regression_wind() -> WindTable:
    sec = np.arange(16) * 22.5
    sector_w = 1.0 + 0.5 * np.cos(np.radians(sec - 200.0))
    bin_w = np.array([3, 10, 17, 20, 17, 14, 9, 5.5, 2.5, 1.5, 0.5])
    table = np.outer(sector_w, bin_w)
    table = table / table.sum() * 100.0
    return WindTable(
        list(SECTOR_NAMES_16), sec, LABELS, default_representative_speeds(LABELS), table
    )


def test_regression_reproduces_reference_numbers():
    """Expected numbers come from the reference implementation of the same equations."""
    study = run_study(
        [REGRESSION_CASE], regression_wind(), PlatformGeometry(), StudySettings()
    )
    entry = study.summaries["regress"]
    tip = entry["tip"]
    assert tip["v_exit_ms"] == pytest.approx(323.31799351109726, rel=1e-6)
    assert tip["d_eff_m"] == pytest.approx(0.6170578007857885, rel=1e-6)
    assert tip["rho_ratio_to_air"] == pytest.approx(1.222525444471903, rel=1e-6)
    assert entry["jet_axial_distance_20pct_lfl_m"] == pytest.approx(
        507.6071560462334, rel=1e-6
    )
    briggs, none = entry["modes"]["briggs"], entry["modes"]["none"]
    assert briggs["peak_pct_lfl_helideck"] == pytest.approx(
        0.00659589636365415, rel=1e-6
    )
    assert briggs["peak_pct_lfl_any_path"] == pytest.approx(
        324.71069629273546, rel=1e-6
    )
    assert briggs["peak_pct_lfl_into_wind_path"] == pytest.approx(
        0.003748830040931935, rel=1e-6
    )
    assert briggs["exceed_pct_hours"]["20"]["any_path"] == pytest.approx(
        4.08572472537763, rel=1e-6
    )
    assert briggs["exceed_pct_hours"]["10"]["any_path"] == pytest.approx(
        5.581911988126482, rel=1e-6
    )
    assert none["peak_pct_lfl_helideck"] == pytest.approx(0.127689069260328, rel=1e-6)
    assert none["peak_pct_lfl_any_path"] == pytest.approx(232.24423050918924, rel=1e-6)
    assert none["peak_pct_lfl_into_wind_path"] == pytest.approx(
        0.08759274113165993, rel=1e-6
    )
    assert none["exceed_pct_hours"]["20"]["any_path"] == pytest.approx(
        4.464078841977606, rel=1e-6
    )
    assert none["exceed_pct_hours"]["10"]["any_path"] == pytest.approx(
        7.296804497872955, rel=1e-6
    )
    pts = np.array([[-300.0, -150.0, 90.0], [-600.0, -400.0, 120.0]])
    rel = study.releases["regress"]
    tip_pos = study.geometry.tip_position
    assert rel.pct_lfl(
        pts, 60.0, 3.0, "E", tip_pos, "briggs"
    ).tolist() == pytest.approx([11.710723331860638, 8.396767441050027], rel=1e-6)
    assert rel.pct_lfl(pts, 60.0, 3.0, "E", tip_pos, "none").tolist() == pytest.approx(
        [0.05076609483796611, 10.889122742840424], rel=1e-6
    )


def test_conditional_weighting_sums(coarse_study, wind):
    for name in coarse_study.releases:
        arr = coarse_study.case_arrays(name)
        total = exceedance_pct(arr.any_path, wind, 10.0)
        by_bin = exceedance_by_speed_bin(arr.any_path, wind, 10.0)
        assert sum(by_bin.values()) == pytest.approx(total)
        assert 0.0 <= total <= wind.total_pct
    ones = np.full((16, 5, 4), 1000.0)
    assert exceedance_pct(ones, wind, 20.0) == pytest.approx(wind.total_pct)
    assert exceedance_pct(ones * 0.0, wind, 20.0) == 0.0
    half = ones.copy()
    half[:, :2, :] = 0.0
    assert exceedance_pct(half, wind, 20.0) == pytest.approx(0.6 * wind.total_pct)


def test_exceedance_is_conditional_not_annual():
    with pytest.raises(ValueError):
        annualise_exposure(5.0, None, None)
    with pytest.raises(ValueError):
        annualise_exposure(5.0, 0.01, None)
    out = annualise_exposure(5.0, 0.02, 10.0)
    assert out["exposed_hours_per_year"] == pytest.approx(0.02 * 10.0 * 0.05)


def test_study_semantics_and_warnings(coarse_study):
    assert "conditional" in coarse_study.semantics.lower()
    assert "not annual" in coarse_study.semantics.lower()
    assert any("under-sampled" in w for w in coarse_study.warnings)
    assert any("wake" in w for w in coarse_study.warnings)
    data = coarse_study.to_dict()
    assert data["semantics"] == coarse_study.semantics


def test_stability_scheme_changes_results(wind, coarse_geometry):
    cases = [ReleaseCase("w", 150.0, 0.0215, 1.25, 273.15, 0.04, 0.96, 0.6)]
    stable = run_study(cases, wind, coarse_geometry, StudySettings(modes=("briggs",)))
    neutral = run_study(
        cases,
        wind,
        coarse_geometry,
        StudySettings(modes=("briggs",), stability_scheme="neutral"),
    )
    a = stable.summaries["w"]["modes"]["briggs"]["peak_pct_lfl_any_path"]
    b = neutral.summaries["w"]["modes"]["briggs"]["peak_pct_lfl_any_path"]
    assert a != pytest.approx(b)


def test_save_and_load_round_trip(coarse_study, wind, coarse_geometry, cases, tmp_path):
    coarse_study.save(tmp_path)
    again = load_study(tmp_path, cases, wind, coarse_geometry)
    for name in coarse_study.releases:
        for mode in ("briggs", "none"):
            assert np.array_equal(
                again.case_arrays(name, mode).any_path,
                coarse_study.case_arrays(name, mode).any_path,
            )
    assert again.summaries["cold"]["modes"]["briggs"][
        "peak_pct_lfl_any_path"
    ] == pytest.approx(
        coarse_study.summaries["cold"]["modes"]["briggs"]["peak_pct_lfl_any_path"]
    )


def test_helideck_peak_over_directions(coarse_study):
    cold = ReleaseCase("cold", 150.0, 0.0215, 1.25, 190.0, 0.04, 0.96, 0.6)
    scenario = BenchmarkScenario("s", cold, 2.0, reference_pct_lfl_max=0.0)
    res = helideck_peak_over_directions(
        scenario, coarse_study.receptors, coarse_study.settings
    )
    assert res["peak_pct_lfl"] >= 0.0
    # the worst direction is the one that carries the plume from the tip toward the deck
    if res["peak_pct_lfl"] > 0.0:
        deviation = abs(
            (
                res["wind_from_deg"]
                - coarse_study.geometry.azimuth_toward_deck_wind_from_deg
                + 180
            )
            % 360
            - 180
        )
        assert deviation <= 30.0


def test_invalid_mode_and_table_are_rejected(wind, coarse_geometry, cases):
    with pytest.raises(ValueError):
        StudySettings(modes=("fancy",))
    bad = copy.deepcopy(wind)
    bad.table_pct[0, 0] = -1.0
    with pytest.raises(ValueError):
        run_study(cases[:1], bad, coarse_geometry)
