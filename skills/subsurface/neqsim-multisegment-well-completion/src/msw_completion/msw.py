"""Read just enough of an Eclipse/OPM deck to give standard wells a plain multi-segment description.

completor needs WELSEGS and COMPSEGS in its input. Screening decks often define wells with WELSPECS and COMPDAT
only. ``add_plain_msw`` adds one tubing segment per connection, with measured depth along the connection cell
centres, so that completor can then add the device and annulus layers. It supports block-centred cartesian grids
(DXV/DYV/DZV or DX/DY/DZ with TOPS); corner-point grids need cell centres from the grid file (``cell_centres``).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

CellCentre = Tuple[float, float, float]
_KEYWORD = re.compile(r"^[A-Z][A-Z0-9_]{0,7}\s*$")


def strip_comment(line: str) -> str:
    """Remove a ``--`` comment that is not inside quotes."""
    quote = False
    for i, ch in enumerate(line):
        if ch == "'":
            quote = not quote
        elif not quote and line.startswith("--", i):
            return line[:i]
    return line


def tokens(text: str) -> List[str]:
    """Split record text into tokens, keeping quoted strings and expanding nothing."""
    return re.findall(r"'[^']*'|\S+", text)


def expand(values: Iterable[str]) -> List[Optional[str]]:
    """Expand ``n*value`` repeats and ``n*`` defaults (None)."""
    out: List[Optional[str]] = []
    for tok in values:
        match = re.fullmatch(r"(\d+)\*(.*)", tok)
        if match:
            out.extend([match.group(2) or None] * int(match.group(1)))
        else:
            out.append(tok)
    return out


def keyword_blocks(
    text: str, keyword: str
) -> List[Tuple[int, int, List[List[Optional[str]]]]]:
    """Return ``(start_line, end_line, records)`` for every occurrence of a record-list keyword."""
    lines = text.splitlines()
    blocks = []
    i = 0
    while i < len(lines):
        if lines[i].strip().upper() == keyword:
            start = i
            records: List[List[Optional[str]]] = []
            current: List[str] = []
            i += 1
            while i < len(lines):
                body = strip_comment(lines[i]).strip()
                if not body:
                    i += 1
                    continue
                if body == "/" and not current:
                    break
                if "/" in body:
                    current += tokens(body.split("/")[0])
                    records.append(expand(current))
                    current = []
                else:
                    current += tokens(body)
                i += 1
            blocks.append((start, i, records))
        i += 1
    return blocks


def array_keyword(text: str, keyword: str) -> Optional[List[float]]:
    """Values of a single-record array keyword (DXV, TOPS, ...) or None when absent."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip().upper() == keyword:
            values: List[str] = []
            for body in lines[i + 1 :]:
                body = strip_comment(body)
                if "/" in body:
                    values += tokens(body.split("/")[0])
                    break
                values += tokens(body)
            return [float(v) for v in expand(values) if v is not None]
    return None


def split_schedule(deck: str) -> Tuple[str, str]:
    """Split a deck at the SCHEDULE keyword into (everything before, the schedule section)."""
    match = re.search(r"^SCHEDULE\s*$", deck, flags=re.MULTILINE)
    if not match:
        return "", deck
    return deck[: match.start()], deck[match.start() :]


@dataclass
class RegularGrid:
    """Block-centred cartesian grid from DIMENS, DXV/DYV/DZV (or DX/DY/DZ) and TOPS."""

    nx: int
    ny: int
    nz: int
    dx: List[float]
    dy: List[float]
    dz: List[float]
    tops: List[float] = field(default_factory=list)

    @classmethod
    def from_deck(cls, deck: str) -> "RegularGrid":
        dims = array_keyword(deck, "DIMENS")
        if not dims:
            raise ValueError("DIMENS not found")
        nx, ny, nz = (int(v) for v in dims[:3])
        dx = array_keyword(deck, "DXV")
        dy = array_keyword(deck, "DYV")
        dz = array_keyword(deck, "DZV")
        if dx is None or dy is None or dz is None:
            cell_dx, cell_dy, cell_dz = (
                array_keyword(deck, k) for k in ("DX", "DY", "DZ")
            )
            if not (cell_dx and cell_dy and cell_dz):
                raise ValueError(
                    "only DXV/DYV/DZV or DX/DY/DZ cartesian grids are supported; pass cell_centres "
                    "for corner-point grids"
                )
            dx = cell_dx[:nx]
            dy = [cell_dy[j * nx] for j in range(ny)]
            dz = [cell_dz[k * nx * ny] for k in range(nz)]
        tops = array_keyword(deck, "TOPS") or []
        if len(tops) not in (nx * ny, nx * ny * nz):
            raise ValueError(
                f"TOPS has {len(tops)} values, expected {nx * ny} or {nx * ny * nz}"
            )
        return cls(nx, ny, nz, dx, dy, dz, tops)

    def centre(self, i: int, j: int, k: int) -> CellCentre:
        """Cell-centre x, y and depth for 1-based indices."""
        if not (1 <= i <= self.nx and 1 <= j <= self.ny and 1 <= k <= self.nz):
            raise ValueError(f"cell ({i},{j},{k}) is outside the grid")
        x = sum(self.dx[: i - 1]) + self.dx[i - 1] / 2.0
        y = sum(self.dy[: j - 1]) + self.dy[j - 1] / 2.0
        if len(self.tops) == self.nx * self.ny * self.nz:
            top = self.tops[(k - 1) * self.nx * self.ny + (j - 1) * self.nx + (i - 1)]
        else:
            top = self.tops[(j - 1) * self.nx + (i - 1)] + sum(self.dz[: k - 1])
        return x, y, top + self.dz[k - 1] / 2.0

    def length(self, i: int, j: int, k: int, direction: str) -> float:
        return {"X": self.dx[i - 1], "Y": self.dy[j - 1]}.get(
            direction.upper(), self.dz[k - 1]
        )


def _name(token: Optional[str]) -> str:
    return (token or "").strip("'")


def connections(schedule: str) -> Dict[str, List[Tuple[int, int, int, str]]]:
    """Connections ``(i, j, k, direction)`` per well from the first COMPDAT block, in listed order."""
    blocks = keyword_blocks(schedule, "COMPDAT")
    if not blocks:
        return {}
    result: Dict[str, List[Tuple[int, int, int, str]]] = {}
    for rec in blocks[0][2]:
        rec = rec + [None] * (14 - len(rec))
        well = _name(rec[0])
        i, j, k1, k2 = (int(v) for v in rec[1:5])
        direction = _name(rec[12]) or "Z"
        for k in range(k1, k2 + 1):
            result.setdefault(well, []).append((i, j, k, direction))
    return result


def _msw_text(
    well: str,
    conns: Sequence[Tuple[int, int, int, str]],
    centre: Callable[[int, int, int], CellCentre],
    length: Callable[[int, int, int, str], float],
    diameter: float,
    roughness: float,
) -> Tuple[str, dict]:
    points = [centre(i, j, k) for i, j, k, _ in conns]
    md_centre = [0.0]
    for a, b in zip(points, points[1:]):
        md_centre.append(md_centre[-1] + math.dist(a, b))
    first_half = length(*conns[0]) / 2.0
    top_md = points[0][2] - first_half if conns[0][3].upper() == "Z" else points[0][2]
    md_centre = [top_md + first_half + m for m in md_centre]
    bounds = [md_centre[0] - first_half]
    for a, b in zip(md_centre, md_centre[1:]):
        bounds.append((a + b) / 2.0)
    bounds.append(md_centre[-1] + length(*conns[-1]) / 2.0)
    welsegs = ["WELSEGS", f"  '{well}' {points[0][2]:.3f} {bounds[0]:.3f} 1* 'ABS' /"]
    for n, (md, point) in enumerate(zip(bounds[1:], points), start=2):
        welsegs.append(
            f"  {n} {n} 1 {n - 1} {md:.3f} {point[2]:.3f} {diameter:g} {roughness:g} /"
        )
    welsegs.append("/")
    compsegs = ["COMPSEGS", f"  '{well}' /"]
    for (i, j, k, _), start, end in zip(conns, bounds, bounds[1:]):
        compsegs.append(f"  {i} {j} {k} 1 {start:.3f} {end:.3f} /")
    compsegs.append("/")
    info = {
        "well": well,
        "connections": len(conns),
        "top_md": round(bounds[0], 3),
        "end_md": round(bounds[-1], 3),
    }
    return "\n".join(welsegs + [""] + compsegs) + "\n", info


def add_plain_msw(
    deck: str,
    wells: Optional[Sequence[str]] = None,
    diameter_m: float = 0.15,
    roughness_m: float = 1.0e-4,
    cell_centres: Optional[Callable[[int, int, int], CellCentre]] = None,
) -> Tuple[str, List[dict]]:
    """Add WELSEGS/COMPSEGS (one segment per connection) and WSEGDIMS so completor can process the wells.

    Returns the new deck and one record per converted well (connections, top and end measured depth).
    Wells that already have WELSEGS are left as they are.
    """
    head, schedule = split_schedule(deck)
    conns = connections(schedule)
    if not conns:
        raise ValueError("no COMPDAT connections found in the schedule section")
    existing = {
        _name(r[0])
        for _, _, recs in keyword_blocks(schedule, "WELSEGS")
        for r in recs[:1]
    }
    selected = [w for w in (wells or conns.keys()) if w in conns and w not in existing]
    missing = [w for w in (wells or []) if w not in conns]
    if missing:
        raise ValueError(f"wells not in COMPDAT: {', '.join(missing)}")
    if cell_centres is None:
        grid = RegularGrid.from_deck(deck)
        centre, length = grid.centre, grid.length
    else:
        centre = cell_centres

        def length(i: int, j: int, k: int, direction: str) -> float:
            return 1.0

    text, infos = [], []
    for well in selected:
        block, info = _msw_text(
            well, conns[well], centre, length, diameter_m, roughness_m
        )
        text.append(block)
        infos.append(info)
    lines = schedule.splitlines()
    _, end, _ = keyword_blocks(schedule, "COMPDAT")[0]
    schedule = "\n".join(lines[: end + 1] + [""] + text + lines[end + 1 :]) + "\n"
    max_conn = max(len(conns[w]) for w in selected) if selected else 1
    head = set_wsegdims(
        head, len(selected) + len(existing), 4 * max_conn + 10, 3 * max_conn + 5
    )
    return head + schedule, infos


def set_wsegdims(runspec: str, wells: int, segments: int, branches: int) -> str:
    """Insert or enlarge WSEGDIMS in the RUNSPEC part of a deck."""
    record = f"WSEGDIMS\n  {wells} {segments} {branches} /\n"
    blocks = keyword_blocks(runspec, "WSEGDIMS")
    lines = runspec.splitlines()
    if blocks:
        start, end, recs = blocks[0]
        old = (
            [int(v) if v else 0 for v in (recs[0] + [None] * 3)[:3]]
            if recs
            else [0, 0, 0]
        )
        record = f"WSEGDIMS\n  {max(old[0], wells)} {max(old[1], segments)} {max(old[2], branches)} /\n"
        return "\n".join(lines[:start] + record.splitlines() + lines[end + 1 :]) + "\n"
    for anchor in ("WELLDIMS", "TABDIMS", "DIMENS"):
        for i, line in enumerate(lines):
            if line.strip().upper() == anchor:
                j = i + 1
                while j < len(lines) and "/" not in strip_comment(lines[j]):
                    j += 1
                return (
                    "\n".join(lines[: j + 1] + record.splitlines() + lines[j + 1 :])
                    + "\n"
                )
    return record + runspec
