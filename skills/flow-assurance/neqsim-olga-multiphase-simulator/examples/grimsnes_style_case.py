"""Render a Grimsnes-style tie-back genkey from a SURF route profile JSON (no OLGA licence needed to render or rule-check the text).

usage: python grimsnes_style_case.py route_profile.json fluid.tab FLUIDLABEL out.genkey [--run]

The route file is the SURF format: ``{"kp_km": [...], "depth_m": [...]}`` (depth positive down).  The PVT table must carry the label
FLUIDLABEL (``BRANCH FLUID=``).  Mass rate and source phase fractions below are placeholders: take them from a NeqSim TP flash at the
source conditions (gas mass fraction of the hydrocarbon part, aqueous mass fraction of the total) and confirm them in the
``MASS SOURCE INFORMATION`` block of the ``.out`` file.
"""

import sys
from pathlib import Path

from olga_multiphase_simulator import (
    STEEL,
    FlowlineCaseSpec,
    Material,
    OlgaRunner,
    WallLayer,
    build_mesh,
    equivalent_insulation_thickness,
    load_route_profile,
    render_genkey,
)

route_file, tab, label, out = sys.argv[1:5]
route = load_route_profile(route_file)
mesh = build_mesh(
    route,
    riser_length_m=150.0,
    riser_rise_m=121.0,
    target_section_m=250.0,
    riser_section_m=10.0,
)
foam = Material("PU_FOAM", 0.12, 600.0, 1800.0)
t_foam = equivalent_insulation_thickness(
    2.0, 0.2857, 0.0191, foam, h_outer=100.0
)  # screening U = 2.0 W/m2K (inner basis) as layers
layers = [WallLayer(STEEL, 0.0191), WallLayer(foam, t_foam)]
spec = FlowlineCaseSpec(
    name="grimsnes_style",
    pvt_file=tab,
    fluid_label=label,
    mesh=mesh,
    diameter_m=0.2857,
    layers_seabed=layers,
    layers_riser=layers,
    source_massflow_kg_s=(40.0,),
    gas_fraction_hc=0.5,
    water_fraction=0.3,
    p_outlet_bara=13.0,
    end_time_s=3600.0,
    esdv_times_s=(0.0, 1800.0, 1810.0),
    esdv_opening=(1.0, 1.0, 0.0),
)
Path(out).write_text(render_genkey(spec), encoding="utf-8")
print("mesh", mesh.summary())
runner = OlgaRunner()
check = runner.rule_check(out)
print("rule check:", check.code_name, "(this does not open the PVT table)")
if "--run" in sys.argv and check.succeeded:
    print(
        runner.run(
            out, out_dir=str(Path(out).with_suffix("")) + "_out", timeout=3600
        ).summary()
    )
