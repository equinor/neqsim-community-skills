"""Screening dispersion of unignited release gas from any source on a facility to any receptor.

The original use is a flare tip, a helideck and its flight paths; the same model serves
air intakes, accommodation, muster areas, escape routes, crane cabs, ignition sources and
any other point, area or route.

Public API (matplotlib is only needed for the ``figures``, ``overlay``, ``style`` and
``facility_figures`` modules, which are imported explicitly):

* :mod:`.model` - choked tip, Birch notional jet, Briggs rise, Gaussian plume.
* :mod:`.wind` - joint direction x speed table and Pasquill rules.
* :mod:`.facility` - sources, receptors of any shape, facility study, tilt scan, tornado.
* :mod:`.facility_results` - ``results.json`` fragment of a facility study.
* :mod:`.receptors` - geometry, helideck points, flight paths, into-wind logic.
* :mod:`.study` - wind sweep and conditional exceedance of the helideck preset.
* :mod:`.sensitivity` - tilt scan, tornado, seeded Monte Carlo of the helideck preset.
* :mod:`.sources` - gas properties, rated PSV flow, optional NeqSim PSV sizing.
* :mod:`.results` - ``results.json`` fragments of the helideck study.
* :mod:`.figures`, :mod:`.overlay`, :mod:`.style` - house-style illustrations.
"""

from .facility import (
    FacilityRelease,
    FacilityStudyResult,
    Receptor,
    Source,
    evaluate_facility,
    facility_section,
    facility_tilt_scan,
    facility_tornado,
    helideck_facility,
    run_facility_study,
    write_facility_section,
)
from .facility_results import build_facility_results
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
    "FacilityRelease",
    "FacilityStudyResult",
    "FlightPathSettings",
    "ModelParameters",
    "PlatformGeometry",
    "Receptor",
    "Receptors",
    "Release",
    "ReleaseCase",
    "Source",
    "StudyResult",
    "StudySettings",
    "WindTable",
    "annualise_exposure",
    "api520_rated_mass_flow_kg_s",
    "build_facility_results",
    "choked_tip",
    "composition_to_release_properties",
    "evaluate",
    "evaluate_facility",
    "exceedance_pct",
    "facility_section",
    "facility_tilt_scan",
    "facility_tornado",
    "helideck_facility",
    "jet_consistency_check",
    "monte_carlo",
    "neqsim_available",
    "pasquill_by_speed",
    "release_case_from_composition",
    "run_facility_study",
    "run_sensitivity",
    "run_study",
    "sigmas",
    "size_psv_api520_gas",
    "tilt_scan",
    "tornado",
    "write_facility_section",
]
