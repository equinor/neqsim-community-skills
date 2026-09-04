"""Tests for the best-guess structural layer."""

from __future__ import annotations

import math

import pytest

from reservoir_model_builder import (
    STRATIGRAPHY,
    STRUCTURAL_STYLE,
    assume_structure,
    assumption_register,
    longest_run_above_contact,
    resolve_play,
    solve_amplitude_for_split,
    solve_contact_for_volume,
)


class TestStyleTables:
    def test_every_style_has_a_stratigraphy(self):
        assert set(STRUCTURAL_STYLE) == set(STRATIGRAPHY)

    def test_stratigraphy_fractions_sum_to_one(self):
        for play, formations in STRATIGRAPHY.items():
            total = sum(fraction for _, fraction, *_ in formations)
            assert total == pytest.approx(1.0, abs=1e-9), play

    def test_stratigraphy_carries_a_permeability_contrast(self):
        # A single-permeability sequence would defeat the purpose of layering.
        for play, formations in STRATIGRAPHY.items():
            perms = [perm for *_, perm, _ in formations]
            assert max(perms) / min(perms) > 3.0, play

    def test_faulted_styles_declare_a_seal_multiplier(self):
        for play, style in STRUCTURAL_STYLE.items():
            if style["fault_throw_m"] > 0.0:
                assert style["fault_seal_multiplier"] < 1.0, play


class TestResolvePlay:
    def test_explicit_play_wins(self):
        assert resolve_play("halten_terrace", "north_sea") == "halten_terrace"

    def test_sea_area_maps_to_a_play(self):
        assert resolve_play(None, "North Sea") == "tampen_brent"
        assert resolve_play(None, "barents_sea") == "barents_platform"

    def test_no_information_falls_back_to_a_generic_anticline(self):
        assert resolve_play() == "generic_anticline"

    def test_unknown_play_is_rejected_rather_than_silently_defaulted(self):
        with pytest.raises(KeyError):
            resolve_play("atlantic_margin_turbidite")


class TestAssumeStructure:
    def test_returns_labelled_assumptions(self):
        model = assume_structure(sea_area="north_sea")
        assert model.play == "tampen_brent"
        assert model.is_faulted
        assert model.assumptions
        # Every assumption must say what would replace it.
        for item in model.assumptions:
            assert item.would_be_replaced_by

    def test_parameters_are_never_measured(self):
        model = assume_structure(sea_area="north_sea")
        for parameter in model.parameters.values():
            assert parameter.provenance in ("analogue", "default")
            assert not parameter.is_data_backed

    def test_unfaulted_style_omits_fault_parameters(self):
        model = assume_structure("north_sea_salt_dome")
        assert not model.is_faulted
        assert "fault_throw_m" not in model.parameters

    def test_flags_a_throw_too_small_to_seal(self):
        model = assume_structure("tampen_brent", gross_thickness_m=200.0)
        flags = [a for a in model.assumptions if a.element == "Fault seal check"]
        assert flags and "THROW BELOW" in flags[0].value

    def test_no_flag_when_the_throw_seals(self):
        model = assume_structure("tampen_brent", gross_thickness_m=40.0)
        assert not [a for a in model.assumptions if a.element == "Fault seal check"]

    def test_serialises_with_an_explicit_assumed_label(self):
        payload = assume_structure(sea_area="norwegian_sea").to_dict()
        assert payload["interpretation"].startswith("ASSUMED")
        assert payload["formations"]
        assert payload["assumptions"]

    def test_assumption_register_covers_parameters_too(self):
        model = assume_structure(sea_area="north_sea")
        rows = assumption_register(model)
        elements = {row["element"] for row in rows}
        assert "Structural style" in elements
        assert "regional_dip_deg" in elements


class TestSolveContactForVolume:
    @staticmethod
    def _cone(depth):
        """Volume above a contact in a simple cone: zero at 3000 m, growing down."""
        return max(0.0, (depth - 3000.0)) ** 2

    def test_finds_the_contact_that_honours_the_volume(self):
        contact = solve_contact_for_volume(self._cone, 2500.0, 3000.0, 3200.0)
        assert contact == pytest.approx(3050.0, abs=0.1)

    def test_rejects_a_target_the_structure_cannot_hold(self):
        with pytest.raises(ValueError, match="cannot hold the target volume"):
            solve_contact_for_volume(self._cone, 1.0e9, 3000.0, 3100.0)

    def test_rejects_an_inverted_bracket(self):
        with pytest.raises(ValueError, match="above"):
            solve_contact_for_volume(self._cone, 100.0, 3200.0, 3000.0)


class TestSolveAmplitudeForSplit:
    @staticmethod
    def _split(amplitude):
        """Secondary fraction grows smoothly with the culmination height."""
        return amplitude / (amplitude + 120.0)

    def test_finds_the_amplitude_that_gives_the_split(self):
        amplitude = solve_amplitude_for_split(self._split, 0.23, 10.0, 200.0)
        assert self._split(amplitude) == pytest.approx(0.23, abs=1e-3)

    def test_saturates_at_the_bracket_when_the_split_is_unreachable(self):
        # The bracket tops out well below the requested fraction.
        assert solve_amplitude_for_split(self._split, 0.95, 10.0, 60.0) == 60.0
        # And bottoms out above it.
        assert solve_amplitude_for_split(self._split, 0.01, 50.0, 200.0) == 50.0

    def test_rejects_an_inverted_bracket(self):
        with pytest.raises(ValueError):
            solve_amplitude_for_split(self._split, 0.2, 200.0, 10.0)


class TestLongestRunAboveContact:
    def test_picks_the_longest_run(self):
        depths = [3070.0, 3040.0, 3030.0, 3080.0, 3020.0, 3010.0, 3015.0, 3090.0]
        start, length = longest_run_above_contact(depths, 3050.0)
        assert (start, length) == (4, 3)

    def test_returns_zero_when_the_whole_track_is_wet(self):
        assert longest_run_above_contact([3100.0, 3110.0], 3050.0) == (0, 0)

    def test_handles_a_fully_dry_track(self):
        depths = [3000.0, 3010.0, 3020.0]
        assert longest_run_above_contact(depths, 3050.0) == (0, 3)

    def test_run_ending_at_the_last_cell_is_found(self):
        depths = [3090.0, 3010.0, 3020.0]
        assert longest_run_above_contact(depths, 3050.0) == (1, 2)

    def test_empty_track(self):
        assert longest_run_above_contact([], 3050.0) == (0, 0)


class TestNoNaNLeaksIntoTheModel:
    def test_all_style_numbers_are_finite(self):
        for play, style in STRUCTURAL_STYLE.items():
            for key, value in style.items():
                if isinstance(value, (int, float)):
                    assert math.isfinite(float(value)), (play, key)
