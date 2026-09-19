"""Locate OLGA multiphase flow simulator installations on the local machine.

The discovery layer is deliberately pure and offline: it only inspects the file
system and the process environment, never a network resource, and it never
hard-codes a site licence server.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

__all__ = [
    "OlgaInstallation",
    "OlgaNotFoundError",
    "DEFAULT_SEARCH_ROOTS",
    "LICENSE_ENV_VARS",
    "find_olga_installations",
    "find_olga",
    "license_environment",
    "olgas_point_model_roots",
]


class OlgaNotFoundError(RuntimeError):
    """Raised when no usable OLGA installation can be located."""


DEFAULT_SEARCH_ROOTS: Tuple[str, ...] = (
    r"C:\Program Files\Schlumberger",
    r"C:\Program Files (x86)\Schlumberger",
    r"C:\Apps\Schlumberger",
    r"D:\Program Files\Schlumberger",
)

#: Environment variables that influence OLGA licence checkout.
LICENSE_ENV_VARS: Tuple[str, ...] = (
    "LM_LICENSE_FILE",
    "SLBSLS_LICENSE_FILE",
    "SLB_LICENSE_FILE",
    "LSHOST",
    "LSFORCEHOST",
)

# Directory names that live next to OLGA but are not the simulator itself.
_EXCLUDED_DIR_PATTERNS = (
    re.compile(r"^olga[-\s]s\b", re.IGNORECASE),
    re.compile(r"^olga namespace explorer", re.IGNORECASE),
    re.compile(r"^olgaenum", re.IGNORECASE),
)

_OLGA_DIR_RE = re.compile(r"^olga[\s_-]+(?P<version>\S.*)$", re.IGNORECASE)
_ENGINE_NAME_RE = re.compile(r"^olga-.+\.exe$", re.IGNORECASE)
_VERSION_NUMBERS_RE = re.compile(r"\d+")

#: Auxiliary executables shipped with OLGA, relative to the installation root.
_TOOL_RELPATHS: Dict[str, str] = {
    "gui": "OPGFramework.exe",
    "opi_launcher": "opi.exe",
    "exit_code_lookup": "OlgaExecutables/exit_code_lookup.exe",
    "opc_server": "OlgaExecutables/OlgaOpc-*.exe",
    "viewer": "Tools/OLGAViewer/OlgaViewer.exe",
    "fluid_def_tool": "Tools/FluidDefTool/FluidDefTool.exe",
    "profile_generator": "Tools/ProfileGenerator/ProfileGeneratorTool.exe",
    "rocx": "Tools/Rocx/Rocx.exe",
    "multiflash": "Tools/Multiflash/MFBJ01.exe",
    "fem_therm_viewer": "Tools/FEMThermViewer/FEMThermViewer.exe",
    "parameter_study": "Modules/RmoParameterStudy/RmoBin/RMO64.exe",
}


@dataclass(frozen=True)
class OlgaInstallation:
    """A single OLGA installation discovered on disk.

    Attributes:
        root: Installation root, e.g. ``C:/Program Files/Schlumberger/Olga 2025.1.0``.
        version: Version string taken from the engine executable name.
        engine: The batch solver executable (``Olga-<version>.exe``).
        tools: Auxiliary executables that were found, keyed by short name.
        sample_cases: Directory holding the bundled sample case library, if present.
    """

    root: Path
    version: str
    engine: Path
    tools: Mapping[str, Path] = field(default_factory=dict)
    sample_cases: Optional[Path] = None

    @property
    def version_key(self) -> Tuple[int, ...]:
        """Numeric sort key derived from the version string."""
        return tuple(int(n) for n in _VERSION_NUMBERS_RE.findall(self.version))

    @property
    def gui(self) -> Optional[Path]:
        """Path to the OLGA graphical front end, if installed."""
        return self.tools.get("gui")

    def tool(self, name: str) -> Path:
        """Return an auxiliary executable path or raise ``KeyError``."""
        return self.tools[name]

    def describe(self) -> Dict[str, object]:
        """Return a JSON-friendly summary of the installation."""
        return {
            "root": str(self.root),
            "version": self.version,
            "engine": str(self.engine),
            "tools": {k: str(v) for k, v in sorted(self.tools.items())},
            "sample_cases": str(self.sample_cases) if self.sample_cases else None,
        }


def _is_excluded(name: str) -> bool:
    return any(pattern.match(name) for pattern in _EXCLUDED_DIR_PATTERNS)


def _find_engine(root: Path) -> Optional[Path]:
    for directory in (root / "OlgaExecutables", root):
        if not directory.is_dir():
            continue
        candidates = sorted(
            entry
            for entry in directory.iterdir()
            if entry.is_file() and _ENGINE_NAME_RE.match(entry.name)
        )
        if candidates:
            return candidates[-1]
    return None


def _engine_version(engine: Path, root: Path) -> str:
    stem = engine.stem  # "Olga-2025.1.0"
    if "-" in stem:
        return stem.split("-", 1)[1]
    match = _OLGA_DIR_RE.match(root.name)
    return match.group("version") if match else stem


def _collect_tools(root: Path) -> Dict[str, Path]:
    tools: Dict[str, Path] = {}
    for name, relpath in _TOOL_RELPATHS.items():
        if "*" in relpath:
            matches = sorted(root.glob(relpath))
            if matches:
                tools[name] = matches[-1]
            continue
        candidate = root / relpath
        if candidate.is_file():
            tools[name] = candidate
    return tools


def _build_installation(root: Path) -> Optional[OlgaInstallation]:
    engine = _find_engine(root)
    if engine is None:
        return None
    samples = root / "Data" / "OPG Files"
    return OlgaInstallation(
        root=root,
        version=_engine_version(engine, root),
        engine=engine,
        tools=_collect_tools(root),
        sample_cases=samples if samples.is_dir() else None,
    )


def find_olga_installations(
    search_roots: Optional[Sequence[str | os.PathLike[str]]] = None,
    env: Optional[Mapping[str, str]] = None,
) -> List[OlgaInstallation]:
    """Return every OLGA installation found, newest version first.

    Resolution order:

    1. ``OLGA_ENGINE`` — full path to an ``Olga-<version>.exe`` batch solver.
    2. ``OLGA_HOME`` — an installation root (one or more, ``os.pathsep`` separated).
    3. ``search_roots`` (defaults to the standard Windows install locations).

    Args:
        search_roots: Directories that contain per-version OLGA folders.
        env: Environment mapping to read; defaults to ``os.environ``.

    Returns:
        Discovered installations sorted newest-first. Empty if OLGA is absent.
    """
    environ = os.environ if env is None else env
    found: Dict[Path, OlgaInstallation] = {}

    explicit_engine = environ.get("OLGA_ENGINE") or environ.get("OLGA_EXE")
    if explicit_engine:
        engine = Path(explicit_engine)
        if engine.is_file():
            root = engine.parent.parent if engine.parent.name == "OlgaExecutables" else engine.parent
            found[root] = OlgaInstallation(
                root=root,
                version=_engine_version(engine, root),
                engine=engine,
                tools=_collect_tools(root),
            )

    for home in _split_paths(environ.get("OLGA_HOME")):
        installation = _build_installation(home)
        if installation is not None:
            found.setdefault(installation.root, installation)

    roots = DEFAULT_SEARCH_ROOTS if search_roots is None else search_roots
    for raw_root in roots:
        parent = Path(raw_root)
        if not parent.is_dir():
            continue
        for child in sorted(parent.iterdir()):
            if not child.is_dir() or _is_excluded(child.name):
                continue
            if not _OLGA_DIR_RE.match(child.name):
                continue
            installation = _build_installation(child)
            if installation is not None:
                found.setdefault(installation.root, installation)

    return sorted(found.values(), key=lambda i: (i.version_key, i.version), reverse=True)


def _split_paths(value: Optional[str]) -> Iterable[Path]:
    if not value:
        return ()
    return (Path(part) for part in value.split(os.pathsep) if part.strip())


def find_olga(
    version: Optional[str] = None,
    search_roots: Optional[Sequence[str | os.PathLike[str]]] = None,
    env: Optional[Mapping[str, str]] = None,
) -> OlgaInstallation:
    """Return one OLGA installation, preferring the newest version.

    Args:
        version: Optional version prefix filter, e.g. ``"2025"`` or ``"2025.1.0"``.
        search_roots: Directories that contain per-version OLGA folders.
        env: Environment mapping to read; defaults to ``os.environ``.

    Raises:
        OlgaNotFoundError: If nothing matches.
    """
    installations = find_olga_installations(search_roots=search_roots, env=env)
    if version is not None:
        installations = [i for i in installations if i.version.startswith(version)]
    if not installations:
        raise OlgaNotFoundError(
            "No OLGA installation found. Set OLGA_HOME to the installation root "
            "(e.g. 'C:/Program Files/Schlumberger/Olga 2025.1.0') or OLGA_ENGINE to the "
            "'Olga-<version>.exe' batch solver."
            + (f" Version filter was {version!r}." if version else "")
        )
    return installations[0]


def license_environment(env: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    """Return the licence-related environment variables that are set.

    OLGA checks out a licence at engine start-up; an unset or unreachable licence
    source surfaces as exit code 26 (``LICENSE_FAIL``).
    """
    environ = os.environ if env is None else env
    return {name: environ[name] for name in LICENSE_ENV_VARS if environ.get(name)}


def olgas_point_model_roots(env: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    """Return the ``OLGAS_SLB_*`` point-model roots exported by the installer.

    These point at the OLGA-S steady-state point model used by third-party hosts
    (process simulators, nodal-analysis tools) rather than by the OLGA engine.
    """
    environ = os.environ if env is None else env
    return {k: v for k, v in sorted(environ.items()) if k.upper().startswith("OLGAS_SLB")}
