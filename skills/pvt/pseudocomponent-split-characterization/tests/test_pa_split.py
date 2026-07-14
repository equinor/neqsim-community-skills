import math

import pytest

from pseudocomponent_split import (
    C7PLUS_INTERCEPT,
    C7PLUS_SLOPE,
    apply_constant_split_to_vector,
    c7plus_split_correlation,
    constant_pa_split,
    map_source_to_pa_core_totals,
    recombine_core_totals,
    two_endpoint_pa_split,
)


def test_c7plus_correlation_matches_paper_form():
    mw = 180.0
    expected = C7PLUS_INTERCEPT - C7PLUS_SLOPE * mw  # 1.3298 - 0.003531*180 = 0.69424
    assert c7plus_split_correlation(mw) == pytest.approx(expected, rel=1e-9)
    # Heavier C7+ -> smaller paraffinic split.
    assert c7plus_split_correlation(240.0) < c7plus_split_correlation(150.0)


def test_c7plus_correlation_clips_to_eps():
    # Very light C7+ pushes S above 1 -> clipped to 1 - eps.
    assert c7plus_split_correlation(50.0, eps=0.02) == pytest.approx(0.98)
    # Very heavy C7+ pushes S below 0 -> clipped to eps.
    assert c7plus_split_correlation(400.0, eps=0.02) == pytest.approx(0.02)


def test_c7plus_correlation_rejects_bad_inputs():
    with pytest.raises(ValueError):
        c7plus_split_correlation(-1.0)
    with pytest.raises(ValueError):
        c7plus_split_correlation(180.0, eps=0.6)


def test_constant_split_conserves_moles():
    totals = [0.02, 0.015, 0.01, 0.005]
    par, aro = constant_pa_split(totals, 0.7)
    for z, p, a in zip(totals, par, aro):
        assert p == pytest.approx(0.7 * z)
        assert a == pytest.approx(0.3 * z)
        assert p + a == pytest.approx(z)


def test_constant_split_rejects_bad_inputs():
    with pytest.raises(ValueError):
        constant_pa_split([0.01], 1.5)
    with pytest.raises(ValueError):
        constant_pa_split([], 0.5)
    with pytest.raises(ValueError):
        constant_pa_split([-0.01], 0.5)


def test_two_endpoint_reduces_to_constant():
    totals = [0.02, 0.015, 0.01]
    mws = [100.0, 200.0, 400.0]
    par_c, aro_c = constant_pa_split(totals, 0.6)
    par_t, aro_t = two_endpoint_pa_split(totals, mws, 0.6, 0.6)
    assert par_t == pytest.approx(par_c)
    assert aro_t == pytest.approx(aro_c)


def test_two_endpoint_interpolates_in_mw():
    totals = [0.02, 0.02, 0.02]
    mws = [100.0, 200.0, 300.0]
    par, aro = two_endpoint_pa_split(totals, mws, 0.8, 0.2)
    # Middle lump S = 0.5 (linear midpoint), lightest 0.8, heaviest 0.2.
    assert par[0] / totals[0] == pytest.approx(0.8)
    assert par[1] / totals[1] == pytest.approx(0.5)
    assert par[2] / totals[2] == pytest.approx(0.2)


def test_recombine_core_totals_pairs_pa_copies():
    names = ["N2", "CO2", "C1", "C7P", "C7A", "C8P", "C8A"]
    zi = [0.01, 0.02, 0.90, 0.03, 0.01, 0.02, 0.01]
    lump_map = recombine_core_totals(names, zi)
    assert lump_map.core_labels == ["C7", "C8"]
    assert lump_map.core_totals[0] == pytest.approx(0.04)  # C7P + C7A
    assert lump_map.core_totals[1] == pytest.approx(0.03)  # C8P + C8A
    assert lump_map.light_index == [0, 1, 2]


def test_apply_constant_split_reassigns_and_conserves():
    names = ["N2", "C1", "C7P", "C7A", "C8P", "C8A"]
    zi = [0.02, 0.90, 0.03, 0.01, 0.03, 0.01]
    out = apply_constant_split_to_vector(names, zi, 0.5)
    # Light unchanged.
    assert out[0] == pytest.approx(0.02)
    assert out[1] == pytest.approx(0.90)
    # Each heavy lump total preserved, now split 50/50.
    assert out[2] == pytest.approx(0.02) and out[3] == pytest.approx(0.02)  # C7 total 0.04
    assert out[4] == pytest.approx(0.02) and out[5] == pytest.approx(0.02)  # C8 total 0.04
    assert sum(out) == pytest.approx(sum(zi))


def test_apply_constant_split_rejects_unpaired():
    names = ["C1", "C7P"]  # paraffinic copy without aromatic pair
    with pytest.raises(ValueError):
        apply_constant_split_to_vector(names, [0.9, 0.1], 0.5)


def test_map_source_to_pa_core_totals_lights_and_nearest_mw():
    # Source: two lights (by name) + three heavy pseudos mapped to nearest core.
    source_names = ["C1", "CO2", "C7", "C10", "C30"]
    source_fractions = [0.80, 0.02, 0.10, 0.05, 0.03]
    source_mw = [16.0, 44.0, 96.0, 140.0, 400.0]
    light_names = ["N2", "CO2", "C1", "C2", "C3"]
    core_labels = ["C7", "C10-14", "C31-50"]
    core_mw = [96.0, 150.0, 500.0]
    m = map_source_to_pa_core_totals(
        source_names, source_fractions, source_mw, light_names, core_labels, core_mw
    )
    assert m.light_fractions["C1"] == pytest.approx(0.80)
    assert m.light_fractions["CO2"] == pytest.approx(0.02)
    # C7 (96) -> C7 core; C10 (140) -> C10-14 core; C30 (400) -> nearest of {96,150,500} = 500 = C31-50.
    assert m.core_totals["C7"] == pytest.approx(0.10)
    assert m.core_totals["C10-14"] == pytest.approx(0.05)
    assert m.core_totals["C31-50"] == pytest.approx(0.03)
    # Total conserved: lights + cores == 1.
    total = sum(m.light_fractions.values()) + sum(m.core_totals.values())
    assert total == pytest.approx(1.0)


def test_map_source_to_pa_core_totals_normalizes():
    m = map_source_to_pa_core_totals(
        ["C1", "C7"], [8.0, 2.0], [16.0, 96.0],
        light_names=["C1"], core_labels=["C7"], core_molecular_weights=[96.0],
    )
    assert m.light_fractions["C1"] == pytest.approx(0.8)
    assert m.core_totals["C7"] == pytest.approx(0.2)
    assert m.sum_in == pytest.approx(10.0)

