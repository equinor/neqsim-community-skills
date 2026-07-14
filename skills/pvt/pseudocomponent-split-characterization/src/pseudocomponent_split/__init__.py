"""Public pseudocomponent split-factor characterization helpers.

This package provides plant-agnostic, dependency-free building blocks for the
heavy-end (plus fraction) split-factor characterization workflow: a Whitson
three-parameter gamma molar distribution, a lumping split factor, and a
delumping reconstruction. These mirror the concepts used by NeqSim's
``neqsim.thermo.characterization`` classes so a qualified engineer can move to
the rigorous Java implementation for design-grade work.
"""

from pseudocomponent_split.split import (
    GammaSplitResult,
    LumpingScheme,
    SplitFactorResult,
    calculate_split_factor,
    delump_composition,
    gamma_mole_split,
)

__all__ = [
    "GammaSplitResult",
    "LumpingScheme",
    "SplitFactorResult",
    "calculate_split_factor",
    "delump_composition",
    "gamma_mole_split",
]
