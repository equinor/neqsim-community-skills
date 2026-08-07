"""Link NeqSim process simulations and engineering documents to finite elements.

Seven layers, usable together or separately:

``design_basis``
    Merge P&ID, STID, datasheet, insulation-specification, inspection and
    plant-data inputs into one traceable design basis, and report what is missing
    before a mesh is generated.
``materials``
    Solid-side properties - conductivity, heat capacity, modulus, expansion - with
    a stated basis, because NeqSim supplies only the fluid side.
``thermal``
    Turn a flashed NeqSim fluid into a film coefficient, a Biot and Fourier
    number, a thermal penetration depth, and the element size and time step that
    follow from them.
``conduction``
    A dependency-free one-dimensional multilayer finite-element solver, steady and
    transient, verified against the closed-form composite resistance. Includes the
    cooldown model with a lumped bore fluid.
``mesh``
    A structured Gmsh mesh for a layered geometry, with every layer interface on
    an element boundary and a physical group per material and per face.
``solver``
    Choose a finite-element backend and state why, then write, run and read back a
    scikit-fem or FEniCSx case driven by one shared ``inputs.json``.
``stress``
    Convert the temperature field into thermal and pressure stress with the right
    stress category attached.
``model``
    Gate the study on discretisation, mesh independence, energy balance and
    boundary placement, and reduce it to the U-value, U-multiplier and hot-spot
    factor a one-dimensional NeqSim model consumes.
"""

from .conduction import (
    ConductionLayer,
    RadialConductionModel,
    SteadyConductionResult,
    TransientConductionResult,
    analytic_composite_resistance,
)
from .design_basis import (
    MODEL_REQUIREMENTS,
    SOURCE_PRECEDENCE,
    STRESS_REQUIREMENTS,
    THERMAL_REQUIREMENTS,
    FemDesignBasis,
    FieldConflict,
    FieldRecord,
    build_design_basis,
    required_fields,
)
from .materials import SolidMaterial, custom_material, list_materials, material
from .mesh import (
    FemMeshSpec,
    MeshLayer,
    MeshOutcome,
    MeshSegment,
    detect_gmsh,
)
from .model import (
    FemCouplingModel,
    FemQualityResult,
    FemResolutionPlan,
    FemThermalHandoff,
)
from .solver import (
    BACKENDS,
    BackendRecommendation,
    BoundaryCondition,
    ConductionProblem,
    FemCase,
    FemResults,
    MaterialAssignment,
    RunOutcome,
    RunStep,
    TransientSettings,
    detect_backends,
    read_case_results,
    recommend_backend,
)
from .stress import (
    PressureStressResult,
    ThermalStressResult,
    evaluate_wall_stress,
    pressure_stress,
    thermal_stress,
    von_mises,
)
from .thermal import (
    FemFluidState,
    FemThermalConditions,
    FilmCoefficient,
    derive_thermal_conditions,
    effective_diffusivity,
    film_coefficient,
    fluid_state_from_neqsim,
    hydraulic_diameter_annulus,
    surface_area_per_length,
)

__all__ = [
    "BACKENDS",
    "BackendRecommendation",
    "BoundaryCondition",
    "ConductionLayer",
    "ConductionProblem",
    "FemCase",
    "FemCouplingModel",
    "FemDesignBasis",
    "FemFluidState",
    "FemMeshSpec",
    "FemQualityResult",
    "FemResolutionPlan",
    "FemResults",
    "FemThermalConditions",
    "FemThermalHandoff",
    "FieldConflict",
    "FieldRecord",
    "FilmCoefficient",
    "MODEL_REQUIREMENTS",
    "MaterialAssignment",
    "MeshLayer",
    "MeshOutcome",
    "MeshSegment",
    "PressureStressResult",
    "RadialConductionModel",
    "RunOutcome",
    "RunStep",
    "SOURCE_PRECEDENCE",
    "STRESS_REQUIREMENTS",
    "SolidMaterial",
    "SteadyConductionResult",
    "THERMAL_REQUIREMENTS",
    "ThermalStressResult",
    "TransientConductionResult",
    "TransientSettings",
    "analytic_composite_resistance",
    "build_design_basis",
    "custom_material",
    "derive_thermal_conditions",
    "detect_backends",
    "detect_gmsh",
    "effective_diffusivity",
    "evaluate_wall_stress",
    "film_coefficient",
    "fluid_state_from_neqsim",
    "hydraulic_diameter_annulus",
    "list_materials",
    "material",
    "pressure_stress",
    "read_case_results",
    "recommend_backend",
    "required_fields",
    "surface_area_per_length",
    "thermal_stress",
    "von_mises",
]
