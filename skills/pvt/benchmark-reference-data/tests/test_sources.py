from __future__ import annotations

import pytest

from benchmark_reference_data.sources import (
    ApplicabilityRange,
    ReferenceSource,
    UnknownSourceError,
    get_source,
    list_sources,
    sources_for,
)


def test_registry_contains_core_reference_formulations():
    keys = {source.key for source in list_sources()}
    assert {"iapws95", "span_wagner_co2", "setzmann_wagner_methane", "gerg2008"} <= keys


def test_sources_are_ordered_most_authoritative_first():
    ranks = [source.tier_rank for source in list_sources()]
    assert ranks == sorted(ranks)


def test_unknown_source_lists_known_keys():
    with pytest.raises(UnknownSourceError) as excinfo:
        get_source("not_a_source")
    assert "iapws95" in str(excinfo.value)


def test_applicability_range_rejects_out_of_range_state():
    co2 = get_source("span_wagner_co2")
    assert co2.covers("co2", 300.0, 1.0e6)
    assert not co2.covers("co2", 150.0, 1.0e6)
    assert not co2.covers("water", 300.0, 1.0e6)


def test_applicability_range_without_bounds_accepts_anything():
    unbounded = ApplicabilityRange()
    assert unbounded.covers("anything", 1.0, 1.0)


def test_reference_eos_is_independent_of_a_cubic_correlation():
    co2 = get_source("span_wagner_co2")
    assert co2.is_independent_of("correlation")
    assert not co2.is_independent_of("reference_eos")


def test_sources_for_filters_by_state_and_model_tier():
    found = sources_for("co2", 300.0, 1.0e6, model_tier="correlation")
    keys = {source.key for source in found}
    assert "span_wagner_co2" in keys
    assert "iapws95" not in keys


def test_property_uncertainty_falls_back_to_default():
    source = ReferenceSource(
        key="tmp",
        name="temp",
        tier="reference_eos",
        citation="none",
        uncertainty_pct={"default": 1.0, "density": 0.1},
    )
    assert source.property_uncertainty_pct("density") == 0.1
    assert source.property_uncertainty_pct("enthalpy") == 1.0


def test_property_uncertainty_returns_none_when_unspecified():
    source = ReferenceSource(key="tmp2", name="t", tier="reference_eos", citation="n")
    assert source.property_uncertainty_pct("density") is None
