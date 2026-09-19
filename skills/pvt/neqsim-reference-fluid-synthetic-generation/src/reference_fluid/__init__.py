"""Reference-fluid synthetic generation helpers.

Plant-agnostic, dependency-free building blocks for generating representative or
synthetic fluid cases from a common reference fluid, matching a split /
characterization factor to a measured target, and combining several well or
fluid compositions into a field composition by molar-rate allocation.

These support the "common reference EOS -> adjust split factor -> match measured
data -> generate representative fluids" workflow, and map to the rigorous NeqSim
``neqsim.thermo.characterization`` classes for design-grade work.
"""

from reference_fluid.analogue_fluid import (
    FLUID_TYPE_BANDS,
    GOR_DEFINITIONS,
    OVERPRESSURE_WARNING,
    PRESSURE_GRADIENTS,
    PROVENANCE_RANKS,
    THERMAL_DEFAULTS,
    Assumption,
    FluidAnalogue,
    api_to_density,
    build_analogue_fluid_basis,
    classify_fluid_type,
    density_to_api,
    estimate_reservoir_conditions,
    interpolate_by_depth,
    reconcile_gor_definitions,
    reconcile_with_measured,
)
from reference_fluid.generate import (
    BlendResult,
    MatchResult,
    blend_compositions,
    generate_fluid_cases,
    match_split_factor,
)

__all__ = [
    "Assumption",
    "BlendResult",
    "FLUID_TYPE_BANDS",
    "FluidAnalogue",
    "GOR_DEFINITIONS",
    "MatchResult",
    "OVERPRESSURE_WARNING",
    "PRESSURE_GRADIENTS",
    "PROVENANCE_RANKS",
    "THERMAL_DEFAULTS",
    "api_to_density",
    "blend_compositions",
    "build_analogue_fluid_basis",
    "classify_fluid_type",
    "density_to_api",
    "estimate_reservoir_conditions",
    "generate_fluid_cases",
    "interpolate_by_depth",
    "match_split_factor",
    "reconcile_gor_definitions",
    "reconcile_with_measured",
]
