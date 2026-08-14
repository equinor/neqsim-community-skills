"""Read OLGA ASCII result files: ``.tpl`` trends and ``.ppl`` profiles.

Both files share the same layout, verified against output from OLGA
2025.1.0.24773::

    'OLGA 2025.1.0.24773'
    TIME PLOT | PROFILE PLOT
    INPUT FILE / PVT FILES / DATE / PROJECT / TITLE / AUTHOR
    NETWORK
    <number of branches>
    GEOMETRY ' (M)  '
    BRANCH
    '<BRANCH NAME>'
    <number of sections>
    <x coordinates of the section boundaries>
    <y coordinates of the section boundaries>
    ...
    CATALOG
    <number of variables>
    <VAR> 'BOUNDARY:'|'SECTION:' 'BRANCH:' '<branch>' ... '(UNIT)' '<description>'
    TIME SERIES  ' (S)  '
    <numbers>

In a ``.tpl`` each data row is ``time`` followed by one scalar per catalog entry.
In a ``.ppl`` each time step is the time value followed by one full profile per
catalog entry: ``nsections + 1`` values for a ``BOUNDARY:`` variable and
``nsections`` values for a ``SECTION:`` variable of that variable's branch.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

__all__ = [
    "OlgaBranch",
    "OlgaVariable",
    "TrendData",
    "ProfileData",
    "read_tpl",
    "read_ppl",
]

_QUOTED_RE = re.compile(r"'([^']*)'")
_UNIT_RE = re.compile(r"^\((?P<unit>.*)\)$")
_NUMBER_RE = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eEdD][-+]?\d+)?")


class OlgaResultError(ValueError):
    """Raised when an OLGA result file cannot be interpreted."""


@dataclass(frozen=True)
class OlgaBranch:
    """A branch (flow path) described in a result-file header."""

    name: str
    nsections: int

    @property
    def nboundaries(self) -> int:
        """Number of section boundaries, i.e. ``nsections + 1``."""
        return self.nsections + 1


@dataclass(frozen=True)
class OlgaVariable:
    """One catalog entry: an output variable at a location."""

    name: str
    branch: str
    unit: str
    description: str
    location: str = "SECTION"
    pipe: Optional[str] = None
    section: Optional[str] = None

    @property
    def is_boundary(self) -> bool:
        """``True`` for variables reported at section boundaries."""
        return self.location.upper().startswith("BOUNDARY")

    def label(self) -> str:
        """Return a compact, human-readable identifier."""
        parts = [self.name, self.branch]
        if self.pipe:
            parts.append(self.pipe)
        if self.section:
            parts.append(f"NR={self.section}")
        return ":".join(p for p in parts if p)


@dataclass(frozen=True)
class _Header:
    kind: str
    branches: Tuple[OlgaBranch, ...]
    variables: Tuple[OlgaVariable, ...]
    data_start: int
    metadata: Mapping[str, str]


@dataclass(frozen=True)
class TrendData:
    """Time-series results read from an OLGA ``.tpl`` file."""

    path: Path
    time: Tuple[float, ...]
    variables: Tuple[OlgaVariable, ...]
    values: Tuple[Tuple[float, ...], ...]
    branches: Tuple[OlgaBranch, ...] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)

    @property
    def time_unit(self) -> str:
        """Unit of the time column, normally ``S``."""
        return self.metadata.get("time_unit", "S")

    def names(self) -> List[str]:
        """Return the catalog variable names in file order."""
        return [v.name for v in self.variables]

    def index_of(self, name: str, branch: Optional[str] = None) -> int:
        """Return the catalog index of a variable, optionally restricted to a branch."""
        for index, variable in enumerate(self.variables):
            if variable.name.upper() != name.upper():
                continue
            if branch is not None and variable.branch.upper() != branch.upper():
                continue
            return index
        raise KeyError(f"Variable {name!r} not found in {self.path.name}")

    def series(self, name: str, branch: Optional[str] = None) -> Tuple[float, ...]:
        """Return the time series of one variable."""
        return self.values[self.index_of(name, branch)]

    def final(self, name: str, branch: Optional[str] = None) -> float:
        """Return the last value of one variable."""
        return self.series(name, branch)[-1]


@dataclass(frozen=True)
class ProfileData:
    """Spatial profiles versus time read from an OLGA ``.ppl`` file."""

    path: Path
    times: Tuple[float, ...]
    variables: Tuple[OlgaVariable, ...]
    branches: Tuple[OlgaBranch, ...]
    profiles: Tuple[Tuple[Tuple[float, ...], ...], ...]
    metadata: Mapping[str, str] = field(default_factory=dict)

    def index_of(self, name: str, branch: Optional[str] = None) -> int:
        """Return the catalog index of a variable, optionally restricted to a branch."""
        for index, variable in enumerate(self.variables):
            if variable.name.upper() != name.upper():
                continue
            if branch is not None and variable.branch.upper() != branch.upper():
                continue
            return index
        raise KeyError(f"Variable {name!r} not found in {self.path.name}")

    def profile(
        self,
        name: str,
        time_index: int = -1,
        branch: Optional[str] = None,
    ) -> Tuple[float, ...]:
        """Return one variable's spatial profile at one output time.

        Args:
            name: Catalog variable name, e.g. ``"PT"``.
            time_index: Index into :attr:`times`; ``-1`` is the last output time.
            branch: Restrict to a branch when the variable appears on several.
        """
        return self.profiles[time_index][self.index_of(name, branch)]


def read_tpl(path: str | os.PathLike[str], encoding: str = "utf-8") -> TrendData:
    """Read an OLGA ``.tpl`` trend file.

    Args:
        path: Path to the ``.tpl`` file.
        encoding: Text encoding; OLGA writes plain ASCII.

    Raises:
        OlgaResultError: If the data block does not match the catalog.
    """
    file_path = Path(path)
    lines = file_path.read_text(encoding=encoding, errors="replace").splitlines()
    header = _parse_header(lines)
    numbers = _numbers_from(lines[header.data_start :])

    stride = len(header.variables) + 1
    if stride == 1 or len(numbers) % stride != 0:
        raise OlgaResultError(
            f"{file_path.name}: {len(numbers)} values are not a multiple of "
            f"{stride} (time + {len(header.variables)} variables)"
        )
    nrows = len(numbers) // stride
    time = tuple(numbers[row * stride] for row in range(nrows))
    values = tuple(
        tuple(numbers[row * stride + 1 + column] for row in range(nrows))
        for column in range(len(header.variables))
    )
    return TrendData(
        path=file_path,
        time=time,
        variables=header.variables,
        values=values,
        branches=header.branches,
        metadata=header.metadata,
    )


def read_ppl(path: str | os.PathLike[str], encoding: str = "utf-8") -> ProfileData:
    """Read an OLGA ``.ppl`` profile file.

    Args:
        path: Path to the ``.ppl`` file.
        encoding: Text encoding; OLGA writes plain ASCII.

    Raises:
        OlgaResultError: If a time block is truncated or the catalog is unusable.
    """
    file_path = Path(path)
    lines = file_path.read_text(encoding=encoding, errors="replace").splitlines()
    header = _parse_header(lines)
    numbers = _numbers_from(lines[header.data_start :])

    sizes = _profile_sizes(header)
    block = 1 + sum(sizes)
    if block <= 1:
        raise OlgaResultError(f"{file_path.name}: catalog is empty")

    times: List[float] = []
    profiles: List[Tuple[Tuple[float, ...], ...]] = []
    cursor = 0
    total = len(numbers)
    while cursor + block <= total:
        times.append(numbers[cursor])
        cursor += 1
        step: List[Tuple[float, ...]] = []
        for size in sizes:
            step.append(tuple(numbers[cursor : cursor + size]))
            cursor += size
        profiles.append(tuple(step))
    if cursor != total:
        raise OlgaResultError(
            f"{file_path.name}: {total - cursor} trailing value(s) do not form a "
            f"complete time block of {block} values"
        )
    return ProfileData(
        path=file_path,
        times=tuple(times),
        variables=header.variables,
        branches=header.branches,
        profiles=tuple(profiles),
        metadata=header.metadata,
    )


# -- header parsing -----------------------------------------------------------


def _parse_header(lines: Sequence[str]) -> _Header:
    catalog_index = _index_of_token(lines, "CATALOG")
    if catalog_index is None:
        raise OlgaResultError("No CATALOG block found; not an OLGA .tpl/.ppl file")

    metadata: Dict[str, str] = {}
    if lines:
        metadata["engine"] = lines[0].strip().strip("'")
    kind = lines[1].strip().upper() if len(lines) > 1 else ""
    metadata["kind"] = kind
    for key, label in (("input_file", "INPUT FILE"), ("date", "DATE"), ("project", "PROJECT")):
        index = _index_of_token(lines[:catalog_index], label)
        if index is not None and index + 1 < catalog_index:
            metadata[key] = lines[index + 1].strip().strip("'")

    branches = _parse_branches(lines[:catalog_index])

    try:
        count = int(lines[catalog_index + 1].strip())
    except (IndexError, ValueError) as exc:
        raise OlgaResultError("CATALOG is not followed by a variable count") from exc
    catalog_lines = lines[catalog_index + 2 : catalog_index + 2 + count]
    if len(catalog_lines) < count:
        raise OlgaResultError(f"CATALOG declares {count} variables but only {len(catalog_lines)} follow")
    variables = tuple(_parse_catalog_line(line) for line in catalog_lines)

    data_start = catalog_index + 2 + count
    for offset in range(data_start, min(data_start + 5, len(lines))):
        if lines[offset].lstrip().upper().startswith("TIME SERIES"):
            match = _QUOTED_RE.search(lines[offset])
            if match:
                raw_unit = match.group(1).strip()
                unit_match = _UNIT_RE.match(raw_unit)
                metadata["time_unit"] = unit_match.group("unit").strip() if unit_match else raw_unit
            data_start = offset + 1
            break
    return _Header(
        kind=kind,
        branches=branches,
        variables=variables,
        data_start=data_start,
        metadata=metadata,
    )


def _index_of_token(lines: Sequence[str], token: str) -> Optional[int]:
    upper = token.upper()
    for index, line in enumerate(lines):
        if line.strip().upper().startswith(upper):
            return index
    return None


def _parse_branches(header_lines: Sequence[str]) -> Tuple[OlgaBranch, ...]:
    branches: List[OlgaBranch] = []
    index = 0
    while index < len(header_lines):
        if header_lines[index].strip().upper() == "BRANCH":
            name = header_lines[index + 1].strip().strip("'") if index + 1 < len(header_lines) else ""
            nsections = 0
            if index + 2 < len(header_lines):
                try:
                    nsections = int(header_lines[index + 2].strip())
                except ValueError:
                    nsections = 0
            branches.append(OlgaBranch(name=name, nsections=nsections))
            index += 3
            continue
        index += 1
    return tuple(branches)


def _parse_catalog_line(line: str) -> OlgaVariable:
    stripped = line.strip()
    name = stripped.split(None, 1)[0] if stripped else ""
    fields = _QUOTED_RE.findall(stripped)

    location = "SECTION"
    branch = ""
    pipe: Optional[str] = None
    section: Optional[str] = None
    unit = ""
    description = ""

    for position, value in enumerate(fields):
        token = value.strip()
        upper = token.upper()
        if upper in ("BOUNDARY:", "SECTION:", "GLOBAL:", "POSITION:"):
            location = upper.rstrip(":")
        elif upper == "BRANCH:" and position + 1 < len(fields):
            branch = fields[position + 1].strip()
        elif upper == "PIPE:" and position + 1 < len(fields):
            pipe = fields[position + 1].strip()
        elif upper == "NR:" and position + 1 < len(fields):
            section = fields[position + 1].strip()
        else:
            unit_match = _UNIT_RE.match(token)
            if unit_match:
                unit = unit_match.group("unit").strip()
    if fields:
        description = fields[-1].strip()
    return OlgaVariable(
        name=name,
        branch=branch,
        unit=unit,
        description=description,
        location=location,
        pipe=pipe,
        section=section,
    )


def _profile_sizes(header: _Header) -> List[int]:
    by_name = {b.name.upper(): b for b in header.branches}
    sizes: List[int] = []
    for variable in header.variables:
        branch = by_name.get(variable.branch.upper())
        if branch is None:
            raise OlgaResultError(
                f"Catalog variable {variable.name!r} refers to unknown branch {variable.branch!r}"
            )
        sizes.append(branch.nboundaries if variable.is_boundary else branch.nsections)
    return sizes


def _numbers_from(lines: Sequence[str]) -> List[float]:
    values: List[float] = []
    for line in lines:
        for token in _NUMBER_RE.findall(line):
            values.append(float(token.replace("d", "e").replace("D", "E")))
    return values
