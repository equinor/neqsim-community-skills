"""Link NeqSim process simulations and engineering documents to CFD.

Five layers, usable together or separately:

``design_basis``
    Merge P&ID, STID, datasheet, plant-data and estimated inputs into one
    traceable design basis, and report what is missing before meshing.
``boundary``
    Turn a flashed NeqSim fluid into single-phase CFD boundary conditions,
    turbulence inlet state, flow regime and the solver class that follows.
``multiphase``
    Take two phases and the interfacial tension from one flash, derive the
    superficial and mixture quantities, and screen which multiphase CFD model is
    defensible.
``openfoam``
    Write, run and read back a complete OpenFOAM case - steady single-phase, or
    transient volume of fluid.
``model``
    Gate a CFD study on quality, and convert local-versus-bulk results into the
    enhancement factors a one-dimensional model needs.
"""

from .boundary import (
    C_MU,
    CfdBoundaryConditions,
    FluidState,
    derive_boundary_conditions,
    fluid_state_from_neqsim,
    friction_velocity,
)
from .design_basis import (
    GEOMETRY_REQUIREMENTS,
    PROCESS_REQUIREMENTS,
    SOURCE_PRECEDENCE,
    CfdDesignBasis,
    FieldConflict,
    FieldRecord,
    build_design_basis,
    required_fields,
)
from .model import (
    CfdCouplingModel,
    CfdEnhancementResult,
    CfdQualityResult,
    CfdWallResolutionResult,
)
from .multiphase import (
    GRAVITY_M_PER_S2,
    MultiphaseBoundaryConditions,
    MultiphaseState,
    derive_multiphase_conditions,
    multiphase_state_from_neqsim,
)
from .openfoam import (
    MeshSpec,
    OpenFoamCase,
    OpenFoamResults,
    RunOutcome,
    RunStep,
    VofOpenFoamCase,
    detect_openfoam,
    read_case_results,
)

__all__ = [
    "C_MU",
    "CfdBoundaryConditions",
    "CfdCouplingModel",
    "CfdDesignBasis",
    "CfdEnhancementResult",
    "CfdQualityResult",
    "CfdWallResolutionResult",
    "FieldConflict",
    "FieldRecord",
    "FluidState",
    "GEOMETRY_REQUIREMENTS",
    "GRAVITY_M_PER_S2",
    "MeshSpec",
    "MultiphaseBoundaryConditions",
    "MultiphaseState",
    "OpenFoamCase",
    "OpenFoamResults",
    "PROCESS_REQUIREMENTS",
    "RunOutcome",
    "RunStep",
    "SOURCE_PRECEDENCE",
    "VofOpenFoamCase",
    "build_design_basis",
    "derive_boundary_conditions",
    "derive_multiphase_conditions",
    "detect_openfoam",
    "fluid_state_from_neqsim",
    "friction_velocity",
    "multiphase_state_from_neqsim",
    "read_case_results",
    "required_fields",
]
