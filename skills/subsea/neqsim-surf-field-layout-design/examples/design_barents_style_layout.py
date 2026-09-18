"""Design a screening SURF layout for a Barents Sea style oil field.

Places 8 producers, 6 water injectors and 2 gas injectors on 4-slot drill
centres around a weathervaning FPSO in 400 m of water, routes and sizes every
flowline, riser and umbilical, and writes a GeoJSON file plus a map.

Run:  python design_barents_style_layout.py
"""

from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from surf_field_layout_design import (
    attribution_block,
    block_bounds,
    design_surf_layout,
    execute,
    plan_layout_data_package,
    plot_layout_map,
)

OUTPUT = Path(__file__).resolve().parent

# Where the field sits. A block designation gives an orientation box; the real
# position must come from the open Sodir wellbore layer.
BLOCK = block_bounds("7324/8")

# What the open-data package would ask for. Nothing is fetched without an adapter.
DATA_PLAN = execute(
    plan_layout_data_package(
        BLOCK["west_longitude_deg"],
        BLOCK["south_latitude_deg"],
        BLOCK["east_longitude_deg"],
        BLOCK["north_latitude_deg"],
    )
)

layout = design_surf_layout(
    field_name="Barents-style oil field",
    centre_latitude_deg=BLOCK["centre_latitude_deg"],
    centre_longitude_deg=BLOCK["centre_longitude_deg"],
    water_depth_m=400.0,
    producers=8,
    water_injectors=6,
    gas_injectors=2,
    slots_per_template=4,
    reservoir_length_km=6.0,
    reservoir_width_km=3.1,
    field_axis_bearing_deg=30.0,
    host_offset_km=2.5,
    host_bearing_deg=270.0,
    production_architecture="dual_loop",
    design_liquid_rate_m3_per_s=28500.0 / 86400.0,
    design_water_injection_rate_m3_per_s=20000.0 / 86400.0,
    design_gas_injection_rate_am3_per_s=0.63e6 * 0.012 / 86400.0,
    data_sources=["emodnet_bathymetry", "sodir_factmaps"],
)

print("drill centres      :", layout.summary["drill_centres"])
print("Xmas trees         :", layout.summary["xmas_trees"])
print("flowline length    : %.2f km" % layout.summary["flowline_length_km"])
print("umbilical length   : %.2f km" % layout.summary["umbilical_length_km"])
print("riser length       : %.2f km" % layout.summary["riser_length_km"])
print("max step-out       : %.2f km" % layout.summary["max_step_out_km"])
for line in layout.lines_of_service("production")[:1]:
    if line.size:
        print("production flowline: %g inch nominal, %.2f m/s, erosional ratio %.2f"
              % (line.size.nominal_inch, line.size.velocity_m_per_s, line.size.erosional_ratio))
for warning in layout.warnings:
    print("  !", warning)

(OUTPUT / "layout.geojson").write_text(json.dumps(layout.to_geojson(), indent=2), encoding="utf-8")
(OUTPUT / "layout.json").write_text(json.dumps(layout.to_dict(), indent=2), encoding="utf-8")
plot_layout_map(
    layout,
    str(OUTPUT / "layout_map.png"),
    attribution=attribution_block(["emodnet_bathymetry", "sodir_factmaps"]),
)

print()
print("open-data requests planned (not executed):")
for request in DATA_PLAN["requests"]:
    print("  %-18s %s" % (request["source"], request["purpose"]))
