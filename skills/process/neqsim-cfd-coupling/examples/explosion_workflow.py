"""Gas dispersion + explosion workflow for a congested module (illustrative, runs without Docker up to case writing).

1. fail-closed readiness gate  2. module domain aligned to cells  3. leak source with enthalpy-consistent fuel source
4. explosion case (cloud, ignition, monitors)  5. closed-vessel verification against the adiabatic isochoric value  6. grid-convergence index.
Needs ESI OpenFOAM v2512 (PDRFoam) in a container for the run step; set RUN=1 to execute (hours for a real module).
"""

import os
from pathlib import Path

from cfd_coupling import explosion as ex
from cfd_coupling import verification as ver

# 1. fail closed: assumed inputs give 'ready_screening', missing inputs give 'not_ready'
gate = ex.assess_explosion_readiness(
    {
        "geometry": {"source": "STID arrangement drawing", "status": "assumed"},
        "congestion": {"source": "line list + MTO", "status": "assumed"},
        "source": {"source": "NeqSim flash, 25 mm leak"},
        "ignition_location": {"source": "three points (central, edge, other)"},
        "vents_confinement": {
            "source": "assumed open N/S/E, 3 variants",
            "status": "assumed",
        },
        "gas_detection": {
            "source": "ESD philosophy: 60 % LFL, HIPPS 1 s",
            "status": "assumed",
        },
    }
)
print(gate.verdict, gate.findings)

# 2. module 22.5 x 22.5 x 6.5 m, west wall (explosion barrier) as rigid plane, 1 m cells, deck/roof one cell thick
dom = ex.Domain.for_module(
    (22.5, 22.5, 6.5),
    1.0,
    margin_cells=3,
    far=(0.0, 60.0, -20.0, 45.0, -10.0, 20.0),
    growth=1.25,
    west_wall=True,
)
obstacles = (
    "FoamFile{version 2.0;format ascii;class dictionary;object obstaclesDict;}\nscale 1.0;\nverbose 0;\nsteel\n{\n enabled true;\n obstacles\n (\n"
    "  box { point (8 8 0); size (3 3 2); }\n  cyl { point (4 4 1.5); direction y; length 6; diameter 0.3; }\n );\n}\n"
)

# 3./4. explosion case: 50 % fill stoichiometric propane cloud, west ignition, probes at a panel and in the module
spec = ex.PdrCaseSpec(
    name="module_explosion",
    domain=dom,
    obstacles_dict=obstacles,
    fuel="propane",
    cloud=ex.Cloud((0, 0, 0), (11.25, 22.5, 6.5), k0=0.5, length_scale=0.3),
    ignition=ex.Ignition((1.2, 11.0, 2.5), diameter=1.0, strength=2.0, duration=0.05),
    monitor_points={"centre": (11, 11, 3)},
    wall_panel_points={"T450": [(0.5, 6, 3), (0.5, 16, 3)]},
    end_time=2.5,
    write_interval=0.25,
    max_co=0.3,
    max_dt=3e-3,
    n_outer=3,
)
case = ex.write_case(spec, Path("work") / spec.name)
print("case written:", case, "cells:", dom.n_cells())

# dispersion variant: same geometry, leak source (momentum-conserving pseudo-source) and wind
leak = ex.LeakSource(
    (4.5, 16.3, 1.9),
    (0, 1, 0),
    fuel_rate_kg_s=24.5,
    thrust_N=7800.0,
    box_half_width=1.5,
    ramp_s=3.0,
)
print(
    "ha source value [W] (sign convention of PDRFoam EaEqn):",
    ex.leak_enthalpy_source("methane", 24.5),
)

# 5. verification BEFORE quoting any module result: closed vessel vs adiabatic isochoric complete combustion (needs scipy)
print(
    "AICC reference (CH4, 298 K):",
    ver.aicc_isochoric({"CH4": 1.0}, 298.15, 101325.0)["P_ratio"],
)

# 6. grid-convergence index from three levels with constant refinement ratio r (coarse -> fine: f3, f2, f1)
print(ex.gci(2.04, 3.41, 10.9, 2**0.5))

if os.environ.get("RUN") == "1":
    r = ex.docker_run(case, ex.explosion_commands(1), cpus=2)
    print(r.returncode)
