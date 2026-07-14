"""Public pseudocomponent split-factor characterization helpers.

This package provides plant-agnostic, dependency-free building blocks for the
heavy-end (plus fraction) split-factor characterization workflow: a Whitson
three-parameter gamma molar distribution, a lumping split factor, and a
delumping reconstruction. These mirror the concepts used by NeqSim's
``neqsim.thermo.characterization`` classes so a qualified engineer can move to
the rigorous Java implementation for design-grade work.
"""

from pseudocomponent_split.pa_split import (
    C7PLUS_INTERCEPT,
    C7PLUS_SLOPE,
    CoreLumpMap,
    SourceToPaMap,
    apply_constant_split_to_vector,
    c7plus_split_correlation,
    constant_pa_split,
    map_source_to_pa_core_totals,
    recombine_core_totals,
    two_endpoint_pa_split,
)
from pseudocomponent_split.split import (
    GammaSplitResult,
    LumpingScheme,
    SplitFactorResult,
    calculate_split_factor,
    delump_composition,
    gamma_mole_split,
)

__all__ = [
    "C7PLUS_INTERCEPT",
    "C7PLUS_SLOPE",
    "CoreLumpMap",
    "GammaSplitResult",
    "LumpingScheme",
    "SourceToPaMap",
    "SplitFactorResult",
    "apply_constant_split_to_vector",
    "c7plus_split_correlation",
    "calculate_split_factor",
    "constant_pa_split",
    "delump_composition",
    "gamma_mole_split",
    "map_source_to_pa_core_totals",
    "recombine_core_totals",
    "two_endpoint_pa_split",
]
