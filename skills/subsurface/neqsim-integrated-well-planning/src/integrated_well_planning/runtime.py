"""NeqSim runtime discovery for integrated well planning.

The calculation chain drives NeqSim Java classes through JPype. This module starts the JVM
once, reports which classes are actually present (the ``wellplanning`` package is newer than
many NeqSim releases) and lets every caller degrade to a clearly labelled "not available"
result instead of failing.

Classpath resolution order (first hit wins):

1. ``IWP_NEQSIM_CLASSPATH`` - explicit classpath entries separated by ``os.pathsep``.
2. A NeqSim source checkout (``NEQSIM_PROJECT_ROOT`` or a sibling ``neqsim`` folder):
   ``target/classes`` plus ``target/neqsim-dev-classpath.txt`` when present, otherwise the
   shaded jar of the installed ``neqsim`` pip package (or ``NEQSIM_JAR``) for the third-party
   dependencies.
3. The shaded jar of the installed ``neqsim`` pip package or ``NEQSIM_JAR`` alone.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

WELLPLANNING_PKG = "neqsim.process.fielddevelopment.wellplanning."
WELLPLANNING_CLASSES = (
    "WellboreThermalModel",
    "DriftFluxWellboreHydraulics",
    "GasCondensateInflowModel",
    "AnnularPressureBuildup",
    "TubingMovementCalculator",
    "WellChemicalTreatment",
    "InjectionWellHydraulics",
    "NodalAnalysis",
)
CORE_CLASSES = {
    "SystemSrkEos": "neqsim.thermo.system.SystemSrkEos",
    "SystemPrEos": "neqsim.thermo.system.SystemPrEos",
    "SystemSrkCPAstatoil": "neqsim.thermo.system.SystemSrkCPAstatoil",
    "ThermodynamicOperations": "neqsim.thermodynamicoperations.ThermodynamicOperations",
    "WellIntegrityScreening": "neqsim.process.mechanicaldesign.subsea.WellIntegrityScreening",
    "VfpTableBuilder": "neqsim.process.fielddevelopment.reservoir.VfpTableBuilder",
    "WellSystem": "neqsim.process.equipment.reservoir.WellSystem",
    "PipeBeggsAndBrills": "neqsim.process.equipment.pipeline.PipeBeggsAndBrills",
    "ArtificialLiftScreener": "neqsim.process.fielddevelopment.screening.ArtificialLiftScreener",
    "WellDesignCalculator": "neqsim.process.mechanicaldesign.subsea.WellDesignCalculator",
    "WellCostEstimator": "neqsim.process.mechanicaldesign.subsea.WellCostEstimator",
    "SourServiceAssessment": "neqsim.process.corrosion.SourServiceAssessment",
}

_STATE: Dict[str, object] = {"status": None}


@dataclass
class RuntimeStatus:
    """Snapshot of what the NeqSim runtime can do right now."""

    jvm_started: bool = False
    reason: str = ""
    classpath: List[str] = field(default_factory=list)
    wellplanning: Dict[str, bool] = field(default_factory=dict)
    core: Dict[str, bool] = field(default_factory=dict)

    @property
    def wellplanning_available(self) -> bool:
        """Return True when every wellplanning class loaded."""
        return bool(self.wellplanning) and all(self.wellplanning.values())

    def has(self, name: str) -> bool:
        """Return True when a wellplanning or core class (short name) is loadable."""
        return bool(self.wellplanning.get(name) or self.core.get(name))

    def to_dict(self) -> Dict[str, object]:
        """Return a JSON-friendly dictionary."""
        return {
            "jvm_started": self.jvm_started,
            "reason": self.reason,
            "classpath": self.classpath,
            "wellplanning": self.wellplanning,
            "core": self.core,
            "wellplanning_available": self.wellplanning_available,
        }


def _candidate_roots() -> List[Path]:
    roots: List[Path] = []
    env = os.environ.get("NEQSIM_PROJECT_ROOT")
    if env:
        roots.append(Path(env))
    here = Path(__file__).resolve()
    for parent in list(here.parents)[:8]:
        roots.append(parent / "neqsim")
        roots.append(parent.parent / "neqsim")
    roots.append(Path.home() / "Documents" / "GitHub" / "neqsim")
    seen, out = set(), []
    for r in roots:
        key = str(r)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _pip_jars() -> List[Path]:
    env_jar = os.environ.get("NEQSIM_JAR")
    if env_jar:
        p = Path(env_jar)
        if p.is_file():
            return [p]
        if p.is_dir():
            return sorted(p.glob("*.jar"))
    try:
        import importlib.util

        spec = importlib.util.find_spec("neqsim")
    except (ImportError, ValueError):
        spec = None
    if spec and spec.submodule_search_locations:
        for loc in spec.submodule_search_locations:
            jars = sorted(Path(loc).glob("lib/*.jar"))
            if jars:
                return [jars[-1]]
    return []


def resolve_classpath() -> List[str]:
    """Return the classpath that :func:`ensure_runtime` would start the JVM with."""
    explicit = os.environ.get("IWP_NEQSIM_CLASSPATH")
    if explicit:
        return [p for p in explicit.split(os.pathsep) if p]
    for root in _candidate_roots():
        classes = root / "target" / "classes"
        if (root / "pom.xml").exists() and classes.is_dir():
            cp = [str(classes)]
            cp_file = root / "target" / "neqsim-dev-classpath.txt"
            if cp_file.exists():
                cp.extend(p for p in cp_file.read_text(encoding="utf-8").strip().split(os.pathsep) if p)
            else:
                cp.extend(str(j) for j in _pip_jars())
            return cp
    return [str(j) for j in _pip_jars()]


def _probe(jclass) -> RuntimeStatus:
    status = RuntimeStatus(jvm_started=True)
    for name in WELLPLANNING_CLASSES:
        try:
            jclass(WELLPLANNING_PKG + name)
            status.wellplanning[name] = True
        except Exception:  # noqa: BLE001 - any JPype lookup failure means "absent"
            status.wellplanning[name] = False
    for short, full in CORE_CLASSES.items():
        try:
            jclass(full)
            status.core[short] = True
        except Exception:  # noqa: BLE001
            status.core[short] = False
    return status


def ensure_runtime(start: bool = True) -> RuntimeStatus:
    """Start (once) and probe the NeqSim JVM; never raises.

    Args:
        start: when False only report an already started JVM.

    Returns:
        The cached :class:`RuntimeStatus`.
    """
    cached = _STATE.get("status")
    if isinstance(cached, RuntimeStatus) and (cached.jvm_started or not start):
        return cached
    try:
        import jpype
    except ImportError:
        st = RuntimeStatus(reason="jpype is not installed; NeqSim-backed calculations are unavailable")
        _STATE["status"] = st
        return st
    if not jpype.isJVMStarted():
        if not start:
            return RuntimeStatus(reason="JVM not started")
        classpath = resolve_classpath()
        if not classpath:
            st = RuntimeStatus(reason="no NeqSim classpath found (set IWP_NEQSIM_CLASSPATH, NEQSIM_PROJECT_ROOT or install neqsim)")
            _STATE["status"] = st
            return st
        os.environ.setdefault("NEQSIM_JVM_AUTOSTART", "0")
        try:
            jpype.startJVM("-Xmx1g", "--enable-native-access=ALL-UNNAMED", classpath=classpath, convertStrings=True)
        except Exception as exc:  # noqa: BLE001
            try:
                sys.path.insert(0, str(next(r for r in _candidate_roots() if (r / "devtools").is_dir()) / "devtools"))
                from java_locator import ensure_java_home  # type: ignore

                ensure_java_home()
                jpype.startJVM("-Xmx1g", classpath=classpath, convertStrings=True)
            except Exception as exc2:  # noqa: BLE001
                st = RuntimeStatus(reason="JVM start failed: {} / {}".format(exc, exc2), classpath=classpath)
                _STATE["status"] = st
                return st
        used = classpath
    else:
        used = []
    st = _probe(jpype.JClass)
    st.classpath = used
    if not st.wellplanning_available:
        missing = [k for k, v in st.wellplanning.items() if not v]
        st.reason = "wellplanning classes missing: {} (NeqSim build older than the well-planning physics)".format(
            ", ".join(missing))
    _STATE["status"] = st
    return st


def jclass(short_or_full: str):
    """Return a JPype class by wellplanning short name, core short name or full name.

    Raises:
        RuntimeError: when the runtime is not available or the class is absent.
    """
    st = ensure_runtime()
    if not st.jvm_started:
        raise RuntimeError("NeqSim runtime unavailable: " + st.reason)
    import jpype

    if short_or_full in WELLPLANNING_CLASSES:
        full = WELLPLANNING_PKG + short_or_full
    else:
        full = CORE_CLASSES.get(short_or_full, short_or_full)
    try:
        return jpype.JClass(full)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("NeqSim class not available: {}".format(full)) from exc


def reset_runtime_cache() -> None:
    """Forget the cached status (the JVM itself cannot be restarted)."""
    _STATE["status"] = None


def runtime_skip_reason() -> Optional[str]:
    """Return None when the wellplanning chain can run, else a human-readable skip reason."""
    st = ensure_runtime()
    if st.wellplanning_available:
        return None
    return st.reason or "wellplanning classes unavailable"
