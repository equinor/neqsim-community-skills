"""Tests for the geometry discretisation module."""

from __future__ import annotations

import math

import pytest

from olga_multiphase_simulator.geometry import (
    DiscretizationError,
    discretize_route,
)


def test_uniform_route_hits_the_target_section_length():
    """A flat evenly spaced route should give the requested section length."""
    x = [0.0, 1000.0, 2000.0, 3000.0]
    y = [0.0, 0.0, 0.0, 0.0]
    mesh = discretize_route(x, y, target_section_length=250.0)

    assert len(mesh.pipes) == 3
    assert mesh.total_sections == 12
    for length in mesh.section_lengths:
        assert length == pytest.approx(250.0)
    assert mesh.max_adjacent_ratio == pytest.approx(1.0)


def test_section_lengths_sum_to_the_pipe_length_including_elevation():
    """Pipe length follows the route, not just the horizontal distance."""
    x = [0.0, 300.0]
    y = [0.0, 400.0]
    mesh = discretize_route(x, y, target_section_length=100.0)

    pipe = mesh.pipes[0]
    assert pipe.length == pytest.approx(500.0)
    assert sum(pipe.section_lengths) == pytest.approx(500.0)
    assert pipe.inclination_deg == pytest.approx(math.degrees(math.atan2(400.0, 300.0)))


def test_neighbour_ratio_is_enforced_across_a_pipe_boundary():
    """A short pipe next to a long one must not create a large section jump."""
    x = [0.0, 100.0, 5100.0]
    y = [0.0, 0.0, 0.0]
    mesh = discretize_route(x, y, target_section_length=100.0,
                            max_section_length=5000.0, max_adjacent_ratio=2.0)

    assert mesh.max_adjacent_ratio <= 2.0 + 1e-9


def test_max_section_length_is_respected():
    """No section may exceed the stated maximum."""
    x = [0.0, 10000.0]
    y = [0.0, 0.0]
    mesh = discretize_route(x, y, target_section_length=5000.0,
                            max_section_length=500.0)

    assert max(mesh.section_lengths) <= 500.0 + 1e-9


def test_boundary_refinement_grades_toward_both_ends():
    """Inlet and outlet sections should be the short ones."""
    x = [0.0, 2000.0, 4000.0, 6000.0]
    y = [0.0, 0.0, 0.0, 0.0]
    mesh = discretize_route(x, y, target_section_length=250.0,
                            boundary_section_length=50.0,
                            max_adjacent_ratio=1.5)

    lengths = mesh.section_lengths
    assert lengths[0] < lengths[len(lengths) // 2]
    assert lengths[-1] < lengths[len(lengths) // 2]
    assert sum(mesh.pipes[0].section_lengths) == pytest.approx(2000.0)
    assert sum(mesh.pipes[-1].section_lengths) == pytest.approx(2000.0)


def test_boundary_section_keeps_its_requested_length():
    """The boundary section must not be rescaled away by the grading."""
    mesh = discretize_route([0.0, 4000.0], [0.0, 0.0],
                            target_section_length=500.0,
                            boundary_section_length=100.0,
                            max_adjacent_ratio=1.5)

    assert mesh.pipes[0].section_lengths[0] == pytest.approx(100.0)
    assert sum(mesh.pipes[0].section_lengths) == pytest.approx(4000.0)


def test_graded_mesh_still_respects_the_neighbour_ratio():
    """Boundary grading must not create a section jump larger than the limit."""
    x = [0.0, 3692.0, 7385.0, 11077.0, 14769.0]
    y = [-307.4, -294.8, -272.1, -255.7, -270.0]
    mesh = discretize_route(x, y, target_section_length=500.0,
                            boundary_section_length=100.0,
                            max_adjacent_ratio=1.5,
                            refine_low_points=True)

    assert mesh.max_adjacent_ratio <= 1.5 + 1e-6
    for pipe in mesh.pipes:
        assert sum(pipe.section_lengths) == pytest.approx(pipe.length)


def test_low_point_refinement_adds_sections_around_a_dip():
    """The pipes either side of a local minimum get a finer mesh."""
    x = [0.0, 1000.0, 2000.0, 3000.0]
    y = [0.0, -50.0, 0.0, 0.0]

    coarse = discretize_route(x, y, target_section_length=250.0)
    refined = discretize_route(x, y, target_section_length=250.0,
                               refine_low_points=True,
                               low_point_section_length=50.0)

    assert refined.total_sections > coarse.total_sections
    assert refined.pipes[0].nsegments > coarse.pipes[0].nsegments
    assert refined.pipes[1].nsegments > coarse.pipes[1].nsegments


def test_genkey_rendering_contains_the_expected_keywords():
    """The rendered statement must be valid OLGA PIPE syntax."""
    mesh = discretize_route([0.0, 500.0], [0.0, 10.0], target_section_length=250.0)
    text = mesh.to_genkey(diameter_m=0.355, roughness_m=4.5e-5, wall_label="PIPEWALL")

    assert "PIPE LABEL=PIPE_01" in text
    assert "NSEGMENT=2" in text
    assert "LSEGMENT=(" in text
    assert "DIAMETER=0.3550 m" in text
    assert "WALL=\"PIPEWALL\"" in text
    assert "YEND=10.000 m" in text


def test_summary_reports_mesh_quality():
    """The summary carries the numbers an engineer checks."""
    mesh = discretize_route([0.0, 1000.0], [0.0, 0.0], target_section_length=100.0)
    summary = mesh.summary()

    assert summary["pipes"] == 1
    assert summary["total_sections"] == 10
    assert summary["total_length_m"] == pytest.approx(1000.0)
    assert summary["min_section_length_m"] == pytest.approx(100.0)
    assert summary["max_adjacent_ratio"] == pytest.approx(1.0)


def test_rejects_a_non_monotonic_route():
    """A route that goes backwards is a data error, not a mesh to build."""
    with pytest.raises(DiscretizationError):
        discretize_route([0.0, 500.0, 400.0], [0.0, 0.0, 0.0],
                         target_section_length=100.0)


def test_rejects_mismatched_or_degenerate_input():
    """Guard the obvious input mistakes."""
    with pytest.raises(DiscretizationError):
        discretize_route([0.0, 100.0], [0.0], target_section_length=50.0)
    with pytest.raises(DiscretizationError):
        discretize_route([0.0], [0.0], target_section_length=50.0)
    with pytest.raises(DiscretizationError):
        discretize_route([0.0, 100.0], [0.0, 0.0], target_section_length=0.0)
