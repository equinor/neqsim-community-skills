"""Screening dispersion of unignited flare-tip gas to a helideck and its flight paths.

Public API (matplotlib is only needed for the ``figures``, ``overlay`` and ``style``
modules, which are imported explicitly):

* :mod:`.model` - choked tip, Birch notional jet, Briggs rise, Gaussian plume.
* :mod:`.wind` - joint direction x speed table and Pasquill rules.
* :mod:`.receptors` - geometry, helideck points, flight paths, into-wind logic.
* :mod:`.study` - wind sweep and conditional exceedance.
* :mod:`.sensitivity` - tilt scan, tornado, seeded Monte Carlo.
* :mod:`.sources` - gas properties, rated PSV flow, optional NeqSim PSV sizing.
* :mod:`.results` - ``results.json`` fragments.
* :mod:`.figures`, :mod:`.overlay`, :mod:`.style` - house-style illustrations.
"""

from .model import (
    ModelParameters,
    Release,
    ReleaseCase,
    choked_tip,
    jet_consistency_check,
    sigmas,
)
from .receptors import FlightPathSettings, PlatformGeometry, Receptors
from .sensitivity import evaluate, monte_carlo, run_sensitivity, tilt_scan, tornado
from .sources import (
    api520_rated_mass_flow_kg_s,
    composition_to_release_properties,
    neqsim_available,
    release_case_from_composition,
    size_psv_api520_gas,
)
from .study import (
    BenchmarkScenario,
    StudyResult,
    StudySettings,
    annualise_exposure,
    exceedance_pct,
    run_study,
)
from .wind import WindTable, pasquill_by_speed

__version__ = "1.0.0"

__all__ = [
    "BenchmarkScenario",
    "FlightPathSettings",
    "ModelParameters",
    "PlatformGeometry",
    "Receptors",
    "Release",
    "ReleaseCase",
    "StudyResult",
    "StudySettings",
    "WindTable",
    "annualise_exposure",
    "api520_rated_mass_flow_kg_s",
    "choked_tip",
    "composition_to_release_properties",
    "evaluate",
    "exceedance_pct",
    "jet_consistency_check",
    "monte_carlo",
    "neqsim_available",
    "pasquill_by_speed",
    "release_case_from_composition",
    "run_sensitivity",
    "run_study",
    "sigmas",
    "size_psv_api520_gas",
    "tilt_scan",
    "tornado",
]
