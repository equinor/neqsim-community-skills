"""Pure-Python reader, writer, and water handler for Eclipse E300 fluid files.

This module documents and implements the Eclipse 300 (E300) compositional EOS
keyword format used by PVTsim Nova and read by NeqSim's
``neqsim.thermo.util.readwrite.EclipseFluidReadWrite``.

It contains no proprietary fluid data. The water parameterization constants
match the public PVTsim water calibration that NeqSim already applies in
``EclipseFluidReadWrite.addWaterToFluid`` (volume shift 0.084004, parachor 10.0,
binary interaction parameter 0.5 against all other components).

The pure-Python path lets a skill or agent inspect, edit, and write E300 files
without a running Java/NeqSim environment. The companion ``neqsim_bridge`` module
loads such files into rigorous NeqSim fluids when NeqSim is available.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

# Per-component vector keywords that hold one numeric value per component.
_VECTOR_KEYWORDS = (
    "TCRIT",
    "PCRIT",
    "ACF",
    "OMEGAA",
    "OMEGAB",
    "MW",
    "TBOIL",
    "VCRIT",
    "ZCRIT",
    "SSHIFT",
    "PARACHOR",
    "ZI",
    "SSHIFTS",
)

# Water EOS parameters matching the public PVTsim water calibration
# (osebergfluid_water.e300). These are the values a Peng-Robinson E300 file
# uses when water is added as the last component.
WATER_E300_PARAMETERS = {
    "CNAME": "H2O",
    "TCRIT": 647.096,
    "PCRIT": 220.6,
    "ACF": 0.34400001168251,
    "OMEGAA": 0.427480012178421,
    "OMEGAB": 0.07780,
    "MW": 18.0153408050537,
    "TBOIL": 373.15,
    "VCRIT": 0.0559999880707264,
    "ZCRIT": 0.29159,
    "SSHIFT": 0.084004,
    "PARACHOR": 10.0,
    "ZI": 0.0,
    "SSHIFTS": 0.126143,
    # Binary interaction parameter between water and every other component.
    "BIC": 0.5,
}


@dataclass
class E300Fluid:
    """In-memory representation of an Eclipse E300 compositional fluid file.

    Vector attributes hold one value per component, in component order.
    ``bic`` is the full symmetric binary interaction parameter matrix.
    """

    names: List[str] = field(default_factory=list)
    eos: str = "PR"
    eos_correction: Optional[str] = "PRCORR"
    reservoir_temp_c: float = 100.0
    standard_temp_c: float = 15.0
    standard_pressure_bara: float = 1.01325
    tcrit: List[float] = field(default_factory=list)
    pcrit: List[float] = field(default_factory=list)
    acf: List[float] = field(default_factory=list)
    omegaa: List[float] = field(default_factory=list)
    omegab: List[float] = field(default_factory=list)
    mw: List[float] = field(default_factory=list)
    tboil: List[float] = field(default_factory=list)
    vcrit: List[float] = field(default_factory=list)
    zcrit: List[float] = field(default_factory=list)
    sshift: List[float] = field(default_factory=list)
    parachor: List[float] = field(default_factory=list)
    zi: List[float] = field(default_factory=list)
    sshifts: List[float] = field(default_factory=list)
    bic: List[List[float]] = field(default_factory=list)
    pedersen: bool = False

    @property
    def ncomps(self) -> int:
        """Number of components in the fluid."""
        return len(self.names)

    def has_water(self) -> bool:
        """Return True when a water component (H2O) is already present."""
        return any(_is_water_name(name) for name in self.names)

    def _vector(self, keyword: str) -> List[float]:
        return getattr(self, keyword.lower())

    def validate(self) -> List[str]:
        """Return a list of structural problems, empty when the fluid is valid."""
        problems: List[str] = []
        n = self.ncomps
        if n == 0:
            problems.append("fluid has no components")
        for keyword in _VECTOR_KEYWORDS:
            values = self._vector(keyword)
            if values and len(values) != n:
                problems.append(
                    f"{keyword} has {len(values)} values but expected {n}"
                )
        if self.bic:
            if len(self.bic) != n or any(len(row) != n for row in self.bic):
                problems.append("BIC matrix is not square with one row per component")
        return problems


def _is_water_name(name: str) -> bool:
    normalized = name.strip().lower().replace(" ", "").replace("_", "").replace("-", "")
    return normalized in {"h2o", "water"}


def _strip_comment(line: str) -> str:
    return line.split("--", 1)[0]


def parse_e300(text: str) -> E300Fluid:
    """Parse Eclipse E300 file content into an :class:`E300Fluid`.

    Args:
        text: Full text content of an E300 file.

    Returns:
        Parsed :class:`E300Fluid`.
    """
    fluid = E300Fluid()
    lines = text.splitlines()
    i = 0
    n_lines = len(lines)

    while i < n_lines:
        raw = lines[i]
        keyword = raw.strip()
        i += 1

        if keyword.startswith("--") or keyword == "":
            continue
        if keyword == "METRIC":
            continue
        if keyword == "PEDERSEN":
            fluid.pedersen = True
            continue
        if keyword in ("PRCORR", "PRLKCORR"):
            fluid.eos_correction = keyword
            continue

        if keyword == "EOS":
            tokens, i = _read_tokens(lines, i)
            if tokens:
                fluid.eos = tokens[0]
            continue
        if keyword == "NCOMPS":
            _, i = _read_tokens(lines, i)
            continue
        if keyword == "RTEMP":
            tokens, i = _read_tokens(lines, i)
            if tokens:
                fluid.reservoir_temp_c = float(tokens[0])
            continue
        if keyword == "STCOND":
            tokens, i = _read_tokens(lines, i)
            if len(tokens) >= 2:
                fluid.standard_temp_c = float(tokens[0])
                fluid.standard_pressure_bara = float(tokens[1])
            continue
        if keyword == "CNAMES":
            tokens, i = _read_tokens(lines, i)
            fluid.names = [t for t in tokens]
            continue
        if keyword in _VECTOR_KEYWORDS:
            tokens, i = _read_tokens(lines, i)
            setattr(fluid, keyword.lower(), [float(t) for t in tokens])
            continue
        if keyword in ("BIC", "BICS"):
            values, i = _read_tokens(lines, i)
            numbers = [float(t) for t in values]
            matrix = _build_bic_matrix(numbers, fluid.ncomps)
            if keyword == "BIC":
                fluid.bic = matrix
            continue
        # Unknown keyword with a value block: consume it to stay in sync.
        if keyword.isupper() and i < n_lines:
            _, i = _read_tokens(lines, i)

    return fluid


def _read_tokens(lines: List[str], start: int):
    """Read whitespace-separated tokens until a ``/`` terminator or comment.

    Args:
        lines: All file lines.
        start: Index to begin reading from.

    Returns:
        Tuple of (token list, next line index). The ``/`` terminator is removed.
    """
    tokens: List[str] = []
    i = start
    n_lines = len(lines)
    while i < n_lines:
        content = _strip_comment(lines[i])
        i += 1
        if content.strip() == "" and not tokens:
            # Allow a leading blank/comment-only line before the value block.
            if lines[i - 1].strip().startswith("--"):
                continue
            break
        terminated = "/" in content
        content = content.replace("/", " ")
        for token in content.split():
            tokens.append(token)
        if terminated:
            break
    return tokens, i


def _build_bic_matrix(values: List[float], n: int) -> List[List[float]]:
    """Build a symmetric BIC matrix from lower-triangular values.

    The E300 BIC block lists, for component ``r`` (1-based, r = 1..n-1), the
    ``r`` interaction values against components ``0..r-1``.

    Args:
        values: Flat lower-triangular value list.
        n: Number of components.

    Returns:
        Symmetric ``n x n`` matrix with a zero diagonal.
    """
    matrix = [[0.0 for _ in range(n)] for _ in range(n)]
    if n <= 1:
        return matrix
    idx = 0
    for r in range(1, n):
        for c in range(r):
            if idx < len(values):
                matrix[r][c] = values[idx]
                matrix[c][r] = values[idx]
                idx += 1
    return matrix


def add_water(fluid: E300Fluid, water_kij: float = 0.5) -> E300Fluid:
    """Add a water component (H2O) to an :class:`E300Fluid` in place.

    Water is appended as the last component with the public PVTsim water
    parameters (see :data:`WATER_E300_PARAMETERS`), zero mole fraction, and a
    binary interaction parameter of ``water_kij`` against every other component.

    Args:
        fluid: Fluid to modify.
        water_kij: Binary interaction parameter between water and all other
            components (PVTsim default 0.5).

    Returns:
        The same fluid instance, now containing water.
    """
    if fluid.has_water():
        return fluid

    params = WATER_E300_PARAMETERS
    fluid.names.append(params["CNAME"])

    _append_if_present(fluid.tcrit, params["TCRIT"], fluid.ncomps)
    _append_if_present(fluid.pcrit, params["PCRIT"], fluid.ncomps)
    _append_if_present(fluid.acf, params["ACF"], fluid.ncomps)
    _append_if_present(fluid.omegaa, params["OMEGAA"], fluid.ncomps)
    _append_if_present(fluid.omegab, params["OMEGAB"], fluid.ncomps)
    _append_if_present(fluid.mw, params["MW"], fluid.ncomps)
    _append_if_present(fluid.tboil, params["TBOIL"], fluid.ncomps)
    _append_if_present(fluid.vcrit, params["VCRIT"], fluid.ncomps)
    _append_if_present(fluid.zcrit, params["ZCRIT"], fluid.ncomps)
    _append_if_present(fluid.sshift, params["SSHIFT"], fluid.ncomps)
    _append_if_present(fluid.parachor, params["PARACHOR"], fluid.ncomps)
    _append_if_present(fluid.zi, params["ZI"], fluid.ncomps)
    _append_if_present(fluid.sshifts, params["SSHIFTS"], fluid.ncomps)

    n = fluid.ncomps
    if fluid.bic:
        for row in fluid.bic:
            row.append(water_kij)
        fluid.bic.append([water_kij] * (n - 1) + [0.0])
    return fluid


def _append_if_present(vector: List[float], value: float, target_len: int) -> None:
    """Append ``value`` to ``vector`` only when the vector was populated.

    Args:
        vector: Per-component vector that may or may not have been read.
        value: Water value to append.
        target_len: Component count after the water name was appended.
    """
    if vector and len(vector) == target_len - 1:
        vector.append(value)


def serialize_e300(fluid: E300Fluid) -> str:
    """Serialize an :class:`E300Fluid` back to E300 keyword text.

    The output uses one component value per line and one BIC row per line, which
    is a valid E300 layout that NeqSim's ``EclipseFluidReadWrite`` reads back.

    Args:
        fluid: Fluid to serialize.

    Returns:
        E300 file content as a string.
    """
    out: List[str] = []
    out.append("-- Eclipse 300 Compositional EOS File")
    out.append("-- Generated by neqsim-e300-fluid-io")
    out.append("-- Units")
    out.append("METRIC")
    out.append("-- Number of components:")
    out.append("NCOMPS")
    out.append(f"{fluid.ncomps} /")
    out.append("-- Equation of state")
    out.append("EOS")
    out.append(f"{fluid.eos} /")
    if fluid.eos_correction:
        out.append(fluid.eos_correction)
    out.append("-- Reservoir temperature (C)")
    out.append("RTEMP")
    out.append(f"    {fluid.reservoir_temp_c:.2f} /")
    out.append("-- Standard Conditions (C and bara)")
    out.append("STCOND")
    out.append(
        f"   {fluid.standard_temp_c:.5f}    {fluid.standard_pressure_bara:.5f}  /"
    )
    out.append("-- Component names")
    out.append("CNAMES")
    out.extend(fluid.names)
    out.append("/")

    _write_vector(out, "-- Tc (K)", "TCRIT", fluid.tcrit, "{:.3f}")
    _write_vector(out, "-- Pc (Bar)", "PCRIT", fluid.pcrit, "{:.4f}")
    _write_vector(out, "-- Omega", "ACF", fluid.acf, "{:.8f}")
    _write_vector(out, "-- OmegaA", "OMEGAA", fluid.omegaa, "{:.8f}")
    _write_vector(out, "-- OmegaB", "OMEGAB", fluid.omegab, "{:.5f}")
    _write_vector(out, "-- Molecular weights", "MW", fluid.mw, "{:.4f}")
    _write_vector(out, "-- Boiling points (K)", "TBOIL", fluid.tboil, "{:.3f}")
    _write_vector(out, "-- Critical volumes (m3/kg-mole)", "VCRIT", fluid.vcrit, "{:.6f}")
    _write_vector(out, "-- Critical Z-factors", "ZCRIT", fluid.zcrit, "{:.5f}")
    _write_vector(out, "-- Volume translation/co-volume", "SSHIFT", fluid.sshift, "{:.6f}")
    _write_vector(out, "-- Parachors (dyn/cm)", "PARACHOR", fluid.parachor, "{:.4f}")
    _write_vector(out, "-- Overall composition", "ZI", fluid.zi, "{:.10f}")

    if fluid.bic:
        out.append("-- Binary interaction coefficients for PR")
        out.append("BIC")
        for r in range(1, fluid.ncomps):
            row = "  ".join(f"{fluid.bic[r][c]:.6f}" for c in range(r))
            out.append("  " + row)
        out.append("/")

    if fluid.pedersen:
        out.append("-- Viscosity correlation")
        out.append("PEDERSEN")

    if fluid.sshifts:
        _write_vector(
            out,
            "-- Volume translation/co-volume at surface conditions",
            "SSHIFTS",
            fluid.sshifts,
            "{:.6f}",
        )

    return "\n".join(out) + "\n"


def _write_vector(out: List[str], comment: str, keyword: str, values: List[float], fmt: str) -> None:
    if not values:
        return
    out.append(comment)
    out.append(keyword)
    for value in values:
        out.append("   " + fmt.format(value))
    out.append("/")


def read_e300_file(path: str) -> E300Fluid:
    """Read an E300 file from disk into an :class:`E300Fluid`.

    Args:
        path: Path to the E300 file.

    Returns:
        Parsed fluid.
    """
    with open(path, "r", encoding="utf-8-sig") as handle:
        return parse_e300(handle.read())


def write_e300_file(fluid: E300Fluid, path: str) -> None:
    """Write an :class:`E300Fluid` to disk in E300 keyword format.

    Args:
        fluid: Fluid to write.
        path: Destination path.
    """
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(serialize_e300(fluid))


def add_water_to_e300_file(
    input_path: str, output_path: str, water_kij: float = 0.5
) -> E300Fluid:
    """Read an E300 file, add a water component, and write a new E300 file.

    This reproduces the structure of a PVTsim ``*_water.e300`` file: water is
    appended as the last component with the public PVTsim water parameters and a
    binary interaction parameter of ``water_kij`` against all other components.

    Args:
        input_path: Source E300 file without water.
        output_path: Destination E300 file with water added.
        water_kij: Water binary interaction parameter (PVTsim default 0.5).

    Returns:
        The water-containing fluid that was written.
    """
    fluid = read_e300_file(input_path)
    add_water(fluid, water_kij=water_kij)
    write_e300_file(fluid, output_path)
    return fluid
