"""Bridge between E300 files and rigorous NeqSim fluids.

This module wraps ``neqsim.thermo.util.readwrite.EclipseFluidReadWrite`` so a
skill or agent can:

- read an E300 file into a NeqSim ``SystemInterface`` fluid,
- read an E300 file and add water in one call,
- add water to an existing NeqSim fluid with the public PVTsim water
  parameters (volume shift 0.084004, parachor 10.0, kij 0.5),
- write a NeqSim fluid back to an E300 file,
- render a NeqSim fluid as E300 text.

All functions degrade gracefully when NeqSim is not installed: they raise a
clear :class:`RuntimeError` instead of an opaque import error.
"""

from __future__ import annotations

from importlib.util import find_spec
from typing import Optional

_DEFAULT_WATER_KIJ = 0.5
_DEFAULT_RESERVOIR_TEMP_C = 100.0


def neqsim_available() -> bool:
    """Return True when the ``neqsim`` Python package is importable."""
    return find_spec("neqsim") is not None


def _eclipse_reader():
    """Return the NeqSim ``EclipseFluidReadWrite`` Java class.

    Returns:
        The ``EclipseFluidReadWrite`` class object.

    Raises:
        RuntimeError: When NeqSim is not installed.
    """
    if not neqsim_available():
        raise RuntimeError(
            "NeqSim is not installed. Install it with 'pip install neqsim' to "
            "use the E300 <-> NeqSim bridge functions."
        )
    from neqsim import jneqsim

    return jneqsim.thermo.util.readwrite.EclipseFluidReadWrite


def read_e300_to_neqsim(
    path: str,
    add_water: bool = False,
    water_kij: float = _DEFAULT_WATER_KIJ,
    pseudo_name: Optional[str] = None,
):
    """Read an E300 file into a NeqSim fluid.

    Args:
        path: Path to the E300 file.
        add_water: When True, append water using the PVTsim water parameters.
        water_kij: Water binary interaction parameter when ``add_water`` is True.
        pseudo_name: Optional pseudo-component name prefix passed to NeqSim.

    Returns:
        A NeqSim ``SystemInterface`` fluid.
    """
    reader = _eclipse_reader()
    if pseudo_name is not None:
        return reader.read(path, pseudo_name, bool(add_water), float(water_kij))
    if add_water:
        return reader.read(path, True, float(water_kij))
    return reader.read(path)


def neqsim_add_water(fluid, water_kij: float = _DEFAULT_WATER_KIJ):
    """Add water to an existing NeqSim fluid using PVTsim water parameters.

    Delegates to ``EclipseFluidReadWrite.addWaterToFluid``, which sets the water
    volume correction (0.084004), parachor (10.0), and a binary interaction
    parameter of ``water_kij`` against all other components, then enables the
    multiphase check.

    Args:
        fluid: A NeqSim ``SystemInterface`` fluid.
        water_kij: Water binary interaction parameter (PVTsim default 0.5).

    Returns:
        The same fluid instance, now containing water.
    """
    reader = _eclipse_reader()
    reader.addWaterToFluid(fluid, float(water_kij))
    return fluid


def write_neqsim_to_e300(
    fluid, path: str, reservoir_temp_c: float = _DEFAULT_RESERVOIR_TEMP_C
) -> str:
    """Write a NeqSim fluid to an E300 file.

    Args:
        fluid: A NeqSim ``SystemInterface`` fluid.
        path: Destination E300 file path.
        reservoir_temp_c: Reservoir temperature written to the RTEMP keyword.

    Returns:
        The destination path.
    """
    reader = _eclipse_reader()
    reader.write(fluid, path, float(reservoir_temp_c))
    return path


def neqsim_to_e300_string(
    fluid, reservoir_temp_c: float = _DEFAULT_RESERVOIR_TEMP_C
) -> str:
    """Render a NeqSim fluid as E300 keyword text.

    Args:
        fluid: A NeqSim ``SystemInterface`` fluid.
        reservoir_temp_c: Reservoir temperature written to the RTEMP keyword.

    Returns:
        E300 file content as a string.
    """
    reader = _eclipse_reader()
    return str(reader.toE300String(fluid, float(reservoir_temp_c)))
