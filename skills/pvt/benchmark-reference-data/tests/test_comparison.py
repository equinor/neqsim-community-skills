from __future__ import annotations

import pytest

from benchmark_reference_data.comparison import (
    STATUS_FAIL,
    STATUS_INFO,
    STATUS_PASS,
    STATUS_WARN,
    BenchmarkCase,
    compare,
    compare_many,
    default_tolerance_pct,
)
from benchmark_reference_data.reference_data import ReferencePoint, find_anchor


def _co2_tc() -> ReferencePoint:
    return find_anchor("co2", "critical_temperature")


def test_exact_match_passes_with_zero_deviation():
    result = compare("Tc", 304.1282, _co2_tc())
    assert result.status == STATUS_PASS
    assert result.deviation == pytest.approx(0.0)
    assert result.deviation_pct == pytest.approx(0.0)


def test_deviation_inside_tolerance_passes():
    result = compare("Tc", 306.0, _co2_tc(), tolerance_pct=1.0)
    assert result.status == STATUS_PASS


def test_deviation_between_one_and_two_tolerances_warns():
    result = compare("Tc", 304.1282 * 1.015, _co2_tc(), tolerance_pct=1.0)
    assert result.status == STATUS_WARN


def test_deviation_beyond_the_warn_band_fails():
    result = compare("Tc", 340.0, _co2_tc(), tolerance_pct=1.0)
    assert result.status == STATUS_FAIL
    assert result.deviation_pct > 0.0


def test_sign_of_deviation_follows_the_model_value():
    low = compare("Tc", 300.0, _co2_tc())
    assert low.deviation < 0.0
    assert low.deviation_pct < 0.0


def test_reference_of_equal_authority_is_reported_as_informational():
    result = compare("Tc", 304.13, _co2_tc(), model_tier="reference_eos")
    assert result.status == STATUS_INFO
    assert result.independent is False
    assert "does not outrank" in result.note


def test_informational_flag_suppresses_grading():
    result = compare("Tc", 304.1282, _co2_tc(), informational=True)
    assert result.status == STATUS_INFO


def test_zero_reference_value_cannot_be_graded_relatively():
    point = ReferencePoint(
        fluid="test",
        property_name="density",
        value=0.0,
        unit="kg/m3",
        source_key="experimental",
    )
    result = compare("zero", 1.0, point)
    assert result.deviation_pct is None
    assert result.status == STATUS_INFO


def test_within_source_uncertainty_is_recorded():
    tight = compare("Tc", 304.1282 * 1.0005, _co2_tc())
    loose = compare("Tc", 304.1282 * 1.005, _co2_tc())
    assert tight.within_source_uncertainty is True
    assert loose.within_source_uncertainty is False


def test_default_tolerance_is_property_specific_with_a_fallback():
    assert default_tolerance_pct("density") == 2.0
    assert default_tolerance_pct("viscosity") == 10.0
    assert default_tolerance_pct("something_unlisted") == 5.0


def test_compare_many_preserves_order():
    cases = [
        BenchmarkCase("first", 304.1282, _co2_tc()),
        BenchmarkCase("second", 300.0, _co2_tc()),
    ]
    results = compare_many(cases)
    assert [r.name for r in results] == ["first", "second"]


def test_result_dict_carries_provenance_and_status():
    payload = compare("Tc", 304.1282, _co2_tc()).to_dict()
    assert payload["status"] == STATUS_PASS
    assert payload["reference"] == "span_wagner_co2"
    assert "Span" in payload["citation"]
    assert payload["neqsim_value"] == pytest.approx(304.1282)


def test_description_includes_state_when_present():
    point = find_anchor(
        "water", "density", temperature_K=298.15, pressure_Pa=101325.0
    )
    result = compare("water density", 997.0, point)
    assert "temperature_K=298.15" in result.description()
