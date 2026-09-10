"""Tests for turning a retrieved static model into OPM Flow deck input.

Every case here is a way a deck RUNS and is wrong, which is why the module
exists: a deck that fails to parse announces itself, and these do not.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reservoir_model_builder import (  # noqa: E402
    REQUIRED_KEYWORDS,
    GridDimensions,
    StaticModelArrays,
    build_static_model_deck_input,
    derive_permz,
    rebase_regions,
    reconcile_volume,
    static_model_checklist,
    validate_array,
    write_keyword_include,
)

GRID = GridDimensions(nx=4, ny=3, nz=2, source="unit test")
N = GRID.cell_count  # 24


def good_model():
    model = StaticModelArrays(grid=GRID)
    model.add("PORO", [0.22] * N, unit="fraction", source="geomodel")
    model.add("PERMX", [180.0] * N, unit="mD", source="geomodel")
    model.add("NTG", [0.85] * N, unit="fraction", source="geomodel")
    model.add("SATNUM", [1] * N, unit="index", source="geomodel")
    model.add("EQLNUM", [1] * N, unit="index", source="geomodel")
    return model


# -- grid bookkeeping ------------------------------------------------------
def test_cell_count_is_the_product_of_the_dimensions():
    assert GRID.cell_count == 24


def test_a_short_array_is_blocking():
    report = validate_array("PORO", [0.2] * (N - 1), GRID)
    assert report["usable"] is False
    assert any("cells" in issue["detail"] for issue in report["issues"])


def test_a_long_array_is_blocking():
    assert validate_array("PORO", [0.2] * (N + 5), GRID)["usable"] is False


def test_a_correct_length_array_passes():
    assert validate_array("PORO", [0.2] * N, GRID)["usable"] is True


# -- unit and bounds traps -------------------------------------------------
def test_porosity_in_percent_is_caught():
    report = validate_array("PORO", [22.0] * N, GRID)
    assert report["usable"] is False
    assert any("percent" in issue["detail"] for issue in report["issues"])


def test_negative_permeability_is_caught():
    assert validate_array("PERMX", [-1.0] * N, GRID)["usable"] is False


def test_a_zero_based_region_array_is_caught():
    report = validate_array("SATNUM", [0] * N, GRID)
    assert report["usable"] is False
    assert any("one-based" in issue["detail"] for issue in report["issues"])


def test_a_non_integer_region_index_is_caught():
    assert validate_array("SATNUM", [1.5] * N, GRID)["usable"] is False


def test_non_finite_values_are_blocking():
    values = [0.2] * N
    values[3] = float("nan")
    assert validate_array("PORO", values, GRID)["usable"] is False


def test_a_sentinel_value_warns_without_blocking():
    values = [100.0] * N
    values[0] = 1e30
    report = validate_array("PERMX", values, GRID)
    assert report["usable"] is True
    assert any(issue["severity"] == "warning" for issue in report["issues"])


def test_a_negative_sentinel_blocks_because_it_also_breaks_the_bound():
    values = [100.0] * N
    values[0] = -999.0
    report = validate_array("PERMX", values, GRID)
    assert report["usable"] is False


# -- explicit corrections, never silent ------------------------------------
def test_rebasing_reports_the_shift_it_applied():
    result = rebase_regions([0, 1, 2])
    assert result["values"] == [1, 2, 3] and result["shift"] == 1


def test_an_already_one_based_array_is_left_alone():
    result = rebase_regions([1, 2, 3])
    assert result["values"] == [1, 2, 3] and result["shift"] == 0


def test_permz_requires_a_stated_ratio():
    derived = derive_permz([100.0, 200.0], kv_kh=0.1)
    assert derived["values"] == [10.0, 20.0]
    assert "kv/kh" in derived["provenance"]


@pytest.mark.parametrize("bad", [0.0, -0.1, 1.5])
def test_an_implausible_kv_kh_is_refused(bad):
    with pytest.raises(ValueError):
        derive_permz([100.0], kv_kh=bad)


# -- the deck build --------------------------------------------------------
def test_a_deck_without_permz_is_refused_rather_than_assumed_isotropic():
    report = build_static_model_deck_input(good_model())
    assert report["deck_writable"] is False
    assert any("PERMZ" in reason for reason in report["blocked_because"])


def test_a_stated_kv_kh_unblocks_the_deck_and_is_recorded():
    report = build_static_model_deck_input(good_model(), kv_kh=0.1)
    assert report["deck_writable"] is True
    actions = {a["action"] for a in report["adjustments"]}
    assert "derive_permz" in actions
    assert report["provenance"]["PERMZ"].startswith("derived")


def test_a_missing_required_keyword_blocks_the_deck():
    model = StaticModelArrays(grid=GRID)
    model.add("PORO", [0.2] * N, unit="fraction")
    report = build_static_model_deck_input(model, kv_kh=0.1)
    assert "PERMX" in report["missing_required_keywords"]
    assert report["deck_writable"] is False


def test_required_keywords_are_the_minimum_runnable_set():
    assert set(REQUIRED_KEYWORDS) == {"PORO", "PERMX"}


def test_no_include_files_are_emitted_for_a_blocked_deck():
    assert build_static_model_deck_input(good_model())["include_files"] == {}


def test_include_files_are_named_per_keyword():
    report = build_static_model_deck_input(good_model(), kv_kh=0.1)
    assert "poro.inc" in report["include_files"]
    assert "permz.inc" in report["include_files"]
    assert "specgrid.inc" in report["include_files"]


def test_specgrid_carries_the_declared_dimensions():
    report = build_static_model_deck_input(good_model(), kv_kh=0.1)
    assert "4 3 2 1 F /" in report["include_files"]["specgrid.inc"]


def test_geometry_is_declared_as_not_reconstructible():
    report = build_static_model_deck_input(good_model(), kv_kh=0.1)
    assert "ZCORN" in report["geometry_note"]


def test_a_zero_based_region_blocks_unless_rebasing_is_requested():
    model = good_model()
    model.add("FIPNUM", [0] * N, unit="index")
    assert build_static_model_deck_input(model, kv_kh=0.1)["deck_writable"] is False

    model = good_model()
    model.add("FIPNUM", [0] * N, unit="index")
    report = build_static_model_deck_input(model, kv_kh=0.1,
                                           rebase_zero_based_regions=True)
    assert report["deck_writable"] is True
    assert any(a["action"] == "rebase_regions" for a in report["adjustments"])


def test_permy_is_copied_from_permx_and_the_assumption_is_recorded():
    report = build_static_model_deck_input(good_model(), kv_kh=0.1)
    assert "PERMY" in report["keywords_present"]
    assert "isotropic" in report["provenance"]["PERMY"]


# -- rendering -------------------------------------------------------------
def test_an_integer_keyword_renders_without_decimals():
    text = write_keyword_include("SATNUM", [1, 2, 3])
    assert "1 2 3" in text and "1.0" not in text


def test_a_keyword_include_is_terminated_with_a_slash():
    assert write_keyword_include("PORO", [0.2, 0.3]).rstrip().endswith("/")


def test_provenance_is_carried_into_the_include_comment():
    text = write_keyword_include("PORO", [0.2], comment="from geomodel")
    assert "-- from geomodel" in text


# -- volume reconciliation -------------------------------------------------
def test_a_matching_volume_passes():
    result = reconcile_volume(computed_stoiip_m3=19.0e6, reported_p50_m3=19.3e6)
    assert result["match"] is True


def test_a_hundredfold_error_is_flagged_and_diagnosed():
    result = reconcile_volume(computed_stoiip_m3=1930.0e6, reported_p50_m3=19.3e6)
    assert result["match"] is False
    assert "percent" in result["diagnosis"]


def test_the_p90_p10_range_is_reported_when_published():
    result = reconcile_volume(computed_stoiip_m3=19.0e6, reported_p50_m3=19.3e6,
                              reported_p90_m3=15.8e6, reported_p10_m3=22.9e6)
    assert result["within_p90_p10"] is True


def test_a_zero_reported_volume_is_refused():
    with pytest.raises(ValueError):
        reconcile_volume(computed_stoiip_m3=1.0, reported_p50_m3=0.0)


def test_the_checklist_covers_the_named_failure_modes():
    checks = {item["check"] for item in static_model_checklist()}
    assert {"array length", "units", "region base", "vertical permeability",
            "geometry", "volume reconciliation"} <= checks
