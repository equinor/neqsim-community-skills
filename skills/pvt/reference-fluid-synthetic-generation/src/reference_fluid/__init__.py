"""Reference-fluid synthetic generation helpers.

Plant-agnostic, dependency-free building blocks for generating representative or
synthetic fluid cases from a common reference fluid, matching a split /
characterization factor to a measured target, and combining several well or
fluid compositions into a field composition by molar-rate allocation.

These support the "common reference EOS -> adjust split factor -> match measured
data -> generate representative fluids" workflow, and map to the rigorous NeqSim
``neqsim.thermo.characterization`` classes for design-grade work.
"""

from reference_fluid.generate import (
    BlendResult,
    MatchResult,
    blend_compositions,
    generate_fluid_cases,
    match_split_factor,
)

__all__ = [
    "BlendResult",
    "MatchResult",
    "blend_compositions",
    "generate_fluid_cases",
    "match_split_factor",
]
