"""Geometry discretisation for OLGA cases.

The OLGA batch engine does not discretise: it consumes a `PIPE` list that already
carries `NSEGMENT` and `LSEGMENT`. OLGA's own "discretize geometry" is a function
of the Geometry editor / Profile Generator, which are GUI tools with no command
line. This module reproduces that step so a case can be built end to end from a
route profile without opening the GUI.

The rules implemented here are the ones that matter for a flow-assurance result:

* a target section length, clamped to a minimum and maximum;
* a limit on the length ratio between adjacent sections, including across a pipe
  boundary, because a sudden jump in section length is a numerical error source;
* optional geometric refinement toward the inlet and outlet boundaries, where
  gradients are steepest;
* optional refinement around local elevation minima, where liquid accumulates and
  terrain slugging starts.
"""

from __future__ import annotations

import math

__all__ = [
    "DiscretizationError",
    "PipeSegment",
    "Discretization",
    "discretize_route",
]


class DiscretizationError(ValueError):
    """Raised when a route cannot be discretised as requested."""


class PipeSegment(object):
    """One OLGA `PIPE` statement.

    :param label: pipe label
    :param x_start: start distance along the route in m
    :param y_start: start elevation in m
    :param x_end: end distance along the route in m
    :param y_end: end elevation in m
    :param section_lengths: list of section lengths in m, summing to the pipe length
    """

    def __init__(self, label, x_start, y_start, x_end, y_end, section_lengths):
        self.label = label
        self.x_start = x_start
        self.y_start = y_start
        self.x_end = x_end
        self.y_end = y_end
        self.section_lengths = list(section_lengths)

    @property
    def horizontal_length(self):
        """Horizontal extent of the pipe.

        :return: length in m
        """
        return self.x_end - self.x_start

    @property
    def elevation_change(self):
        """Elevation change over the pipe.

        :return: rise in m, negative when falling
        """
        return self.y_end - self.y_start

    @property
    def length(self):
        """Pipe length along the route, including the elevation change.

        :return: length in m
        """
        return math.sqrt(self.horizontal_length ** 2 + self.elevation_change ** 2)

    @property
    def nsegments(self):
        """Number of sections in the pipe.

        :return: section count
        """
        return len(self.section_lengths)

    @property
    def inclination_deg(self):
        """Inclination of the pipe.

        :return: angle in degrees, positive upward
        """
        if self.horizontal_length == 0.0:
            return 90.0 if self.elevation_change > 0 else -90.0
        return math.degrees(math.atan2(self.elevation_change, self.horizontal_length))

    def to_genkey(self, diameter_m, roughness_m, wall_label, indent=" "):
        """Render the pipe as an OLGA `PIPE` statement.

        :param diameter_m: inner diameter in m
        :param roughness_m: absolute roughness in m
        :param wall_label: label of the `WALL` definition
        :param indent: leading whitespace for the statement
        :return: genkey text for this pipe
        """
        lengths = ", ".join("{0:.4f}".format(v) for v in self.section_lengths)
        lines = [
            "{0}PIPE LABEL={1}, ROUGHNESS={2:.6e} m, DIAMETER={3:.4f} m, \\".format(
                indent, self.label, roughness_m, diameter_m),
            "{0}     WALL=\"{1}\", NSEGMENT={2:d}, LSEGMENT=({3}) m, \\".format(
                indent, wall_label, self.nsegments, lengths),
            "{0}     XEND={1:.3f} m, YEND={2:.3f} m, ZEND=0 m".format(
                indent, self.x_end, self.y_end),
        ]
        return "\n".join(lines)


class Discretization(object):
    """Result of discretising a route.

    :param pipes: list of :class:`PipeSegment`
    """

    def __init__(self, pipes):
        self.pipes = list(pipes)

    @property
    def total_sections(self):
        """Total number of sections in the branch.

        :return: section count
        """
        return sum(pipe.nsegments for pipe in self.pipes)

    @property
    def section_lengths(self):
        """Flat list of every section length along the branch.

        :return: list of lengths in m
        """
        lengths = []
        for pipe in self.pipes:
            lengths.extend(pipe.section_lengths)
        return lengths

    @property
    def max_adjacent_ratio(self):
        """Largest length ratio between two neighbouring sections.

        :return: ratio, 1.0 for a uniform mesh
        """
        lengths = self.section_lengths
        worst = 1.0
        for i in range(1, len(lengths)):
            a, b = lengths[i - 1], lengths[i]
            if a <= 0.0 or b <= 0.0:
                continue
            worst = max(worst, a / b, b / a)
        return worst

    def summary(self):
        """Quality-control numbers for the generated mesh.

        :return: dict with the section count and length statistics
        """
        lengths = self.section_lengths
        return {
            "pipes": len(self.pipes),
            "total_sections": self.total_sections,
            "total_length_m": sum(pipe.length for pipe in self.pipes),
            "min_section_length_m": min(lengths) if lengths else 0.0,
            "max_section_length_m": max(lengths) if lengths else 0.0,
            "mean_section_length_m": (sum(lengths) / len(lengths)) if lengths else 0.0,
            "max_adjacent_ratio": self.max_adjacent_ratio,
        }

    def to_genkey(self, diameter_m, roughness_m, wall_label, indent=" "):
        """Render every pipe as OLGA `PIPE` statements.

        :param diameter_m: inner diameter in m
        :param roughness_m: absolute roughness in m
        :param wall_label: label of the `WALL` definition
        :param indent: leading whitespace for each statement
        :return: genkey text for the whole branch
        """
        return "\n".join(
            pipe.to_genkey(diameter_m, roughness_m, wall_label, indent)
            for pipe in self.pipes)


def _graded_lengths(total, first, ratio, target):
    """Grade section lengths from a boundary outward up to the target length.

    The series starts at ``first`` and grows by ``ratio`` until it reaches
    ``target``, after which it stays uniform. The final section absorbs the
    remainder, so the boundary section keeps the length that was asked for
    instead of being rescaled away.

    :param total: pipe length in m
    :param first: length of the section at the boundary in m
    :param ratio: growth ratio between neighbouring sections
    :param target: length the series grows towards in m
    :return: list of lengths in m summing to total
    """
    if total <= first or first <= 0.0:
        return [total]
    lengths = []
    remaining = total
    nxt = first
    while remaining > 0.0:
        step = min(nxt, target, remaining)
        if remaining - step < 0.5 * step:
            lengths.append(remaining)
            break
        lengths.append(step)
        remaining -= step
        nxt = step * ratio
    return lengths


def _enforce_neighbour_ratio(pipes_lengths, ratio, min_length):
    """Split sections until no neighbouring pair exceeds the length ratio.

    Works on the flattened branch, so jumps across a pipe boundary are caught
    as well as jumps inside a pipe.

    :param pipes_lengths: list of per-pipe section length lists, modified in place
    :param ratio: largest allowed ratio between neighbouring sections
    :param min_length: sections at or below this length are never split
    :return: None
    """
    for _ in range(10000):
        flat = []
        for pipe_index, lengths in enumerate(pipes_lengths):
            for section_index in range(len(lengths)):
                flat.append((pipe_index, section_index, lengths[section_index]))
        worst = None
        worst_ratio = ratio * (1.0 + 1e-9)
        for i in range(1, len(flat)):
            a, b = flat[i - 1][2], flat[i][2]
            if a <= 0.0 or b <= 0.0:
                continue
            current = max(a / b, b / a)
            if current > worst_ratio:
                worst_ratio = current
                worst = flat[i - 1] if a > b else flat[i]
        if worst is None:
            return
        pipe_index, section_index, length = worst
        if length / 2.0 < min_length:
            return
        lengths = pipes_lengths[pipe_index]
        lengths[section_index:section_index + 1] = [length / 2.0, length / 2.0]


def _section_count(length, target, minimum, maximum):
    """Choose a section count for a pipe.

    :param length: pipe length in m
    :param target: preferred section length in m
    :param minimum: shortest acceptable section in m
    :param maximum: longest acceptable section in m
    :return: number of sections, at least 1
    """
    count = int(round(length / target)) if target > 0 else 1
    count = max(1, count)
    while length / count > maximum:
        count += 1
    while count > 1 and length / count < minimum:
        count -= 1
    return count


def _local_minima(y):
    """Indices of interior local elevation minima.

    :param y: elevation list in m
    :return: list of indices
    """
    minima = []
    for i in range(1, len(y) - 1):
        if y[i] <= y[i - 1] and y[i] <= y[i + 1] and (y[i] < y[i - 1] or y[i] < y[i + 1]):
            minima.append(i)
    return minima


def discretize_route(x, y, target_section_length, min_section_length=1.0,
                     max_section_length=None, max_adjacent_ratio=2.0,
                     boundary_section_length=None, refine_low_points=False,
                     low_point_section_length=None, label_prefix="PIPE"):
    """Turn a route profile into OLGA pipes with sections.

    Each interval between consecutive route points becomes one `PIPE`. Section
    counts follow the target length, are clamped to the minimum and maximum, and
    are then increased where needed so that no two neighbouring sections differ by
    more than ``max_adjacent_ratio``.

    :param x: distances along the route in m, strictly increasing
    :param y: elevations in m, same length as x
    :param target_section_length: preferred section length in m
    :param min_section_length: shortest acceptable section in m
    :param max_section_length: longest acceptable section in m, defaults to twice
        the target
    :param max_adjacent_ratio: largest allowed length ratio between neighbouring
        sections, including across a pipe boundary
    :param boundary_section_length: if given, grade the first and last pipe
        geometrically down to this section length at the branch inlet and outlet
    :param refine_low_points: refine the pipes on either side of a local
        elevation minimum, where liquid accumulates
    :param low_point_section_length: section length to use at a low point,
        defaults to half the target
    :param label_prefix: prefix for the generated pipe labels
    :return: a :class:`Discretization`
    :raises DiscretizationError: if the route is degenerate or the limits conflict
    """
    if len(x) != len(y):
        raise DiscretizationError("x and y must have the same length")
    if len(x) < 2:
        raise DiscretizationError("a route needs at least two points")
    if target_section_length <= 0.0:
        raise DiscretizationError("target_section_length must be positive")
    for i in range(1, len(x)):
        if x[i] <= x[i - 1]:
            raise DiscretizationError(
                "route distances must increase: x[%d]=%r is not beyond x[%d]=%r"
                % (i, x[i], i - 1, x[i - 1]))
    if max_section_length is None:
        max_section_length = 2.0 * target_section_length
    if max_section_length < min_section_length:
        raise DiscretizationError("max_section_length is below min_section_length")
    if max_adjacent_ratio < 1.0:
        raise DiscretizationError("max_adjacent_ratio must be at least 1")
    if low_point_section_length is None:
        low_point_section_length = 0.5 * target_section_length

    npipes = len(x) - 1
    targets = [target_section_length] * npipes
    if refine_low_points:
        for index in _local_minima(y):
            for pipe in (index - 1, index):
                if 0 <= pipe < npipes:
                    targets[pipe] = min(targets[pipe], low_point_section_length)

    lengths = []
    for i in range(npipes):
        dx = x[i + 1] - x[i]
        dy = y[i + 1] - y[i]
        lengths.append(math.sqrt(dx * dx + dy * dy))

    counts = [_section_count(lengths[i], targets[i], min_section_length,
                             max_section_length) for i in range(npipes)]

    pipes_lengths = []
    for i in range(npipes):
        uniform = lengths[i] / counts[i]
        section_lengths = [uniform] * counts[i]
        if boundary_section_length is not None and boundary_section_length > 0.0:
            if i == 0:
                section_lengths = _graded_lengths(
                    lengths[i], boundary_section_length, max_adjacent_ratio,
                    targets[i])
            elif i == npipes - 1:
                section_lengths = list(reversed(_graded_lengths(
                    lengths[i], boundary_section_length, max_adjacent_ratio,
                    targets[i])))
        pipes_lengths.append(section_lengths)

    _enforce_neighbour_ratio(pipes_lengths, max_adjacent_ratio, min_section_length)

    pipes = []
    for i in range(npipes):
        pipes.append(PipeSegment(
            label="%s_%02d" % (label_prefix, i + 1),
            x_start=x[i], y_start=y[i], x_end=x[i + 1], y_end=y[i + 1],
            section_lengths=pipes_lengths[i]))

    return Discretization(pipes)
