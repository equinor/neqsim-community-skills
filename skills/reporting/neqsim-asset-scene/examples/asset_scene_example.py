"""Combined illustration: topside train (existing + proposed), subsea tie-back and a well.

Run: python examples/asset_scene_example.py OUT_DIR
Synthetic, public data only.
"""

import sys
from pathlib import Path

from asset_scene import (
    AssetScene,
    ColorBy,
    attach_values,
    from_equipment_records,
    from_subsea_nodes,
    from_well_trajectory,
    render_all,
    results_fragment,
)


def build() -> dict:
    records = [
        {"tag": "20-VA-001", "kind": "vessel", "diameter_m": 3.2, "length_m": 11.0, "orientation": "horizontal",
         "size_quality": "derived", "size_source": "NeqSim MechanicalDesignData"},
        {"tag": "23-VG-001", "kind": "vessel", "diameter_m": 1.8, "length_m": 4.5, "orientation": "vertical"},
        {"tag": "23-KA-001", "kind": "compressor", "size_m": [7.0, 4.0, 4.5]},
        {"tag": "23-HB-001", "kind": "heat_exchanger", "diameter_m": 1.2, "length_m": 6.0, "orientation": "horizontal"},
        {"tag": "23-KA-002", "kind": "compressor", "size_m": [7.0, 4.0, 4.5], "state": "proposed"},
    ]
    connections = [
        {"from": "20-VA-001", "to": "23-VG-001"},
        {"from": "23-VG-001", "to": "23-KA-001"},
        {"from": "23-KA-001", "to": "23-HB-001"},
        {"from": "23-VG-001", "to": "23-KA-002", "state": "proposed"},
    ]
    topside = from_equipment_records(records, connections, scene=AssetScene("Gas compression train"))
    attach_values(topside, {"23-KA-001": {"utilisation": 0.97}, "20-VA-001": {"utilisation": 0.72},
                            "23-HB-001": {"utilisation": 0.55}, "23-VG-001": {"utilisation": 1.08}})

    nodes = [
        {"name": "HOST", "x": 0, "y": 0, "water_depth_m": 120, "kind": "host"},
        {"name": "TEMPLATE-B", "x": 5200, "y": 3100, "water_depth_m": 135, "kind": "template", "state": "proposed"},
        {"name": "MANIFOLD-A", "x": 2600, "y": -1500, "water_depth_m": 128, "kind": "manifold", "quality": "verified"},
    ]
    lines = [
        {"from": "MANIFOLD-A", "to": "HOST", "kind": "flowline", "quality": "verified",
         "route": [[2600, -1500], [1500, -900], [0, 0]]},
        {"from": "TEMPLATE-B", "to": "MANIFOLD-A", "kind": "flowline", "state": "proposed"},
        {"from": "TEMPLATE-B", "to": "HOST", "kind": "umbilical", "state": "proposed"},
    ]
    field = from_subsea_nodes(nodes, lines, scene=AssetScene("Tie-back"))
    stations = [{"md_m": md, "inc_deg": min(60.0, max(0.0, (md - 400) / 20)), "azi_deg": 35.0}
                for md in range(0, 3201, 100)]
    from_well_trajectory("B-1 H", stations, (5200, 3100), datum_z=-135.0, scene=field, state="proposed",
                         quality="assumed", reference="concept well path")
    return {"topside": topside, "field": field}


def main(out_dir: str) -> None:
    scenes = build()
    out = Path(out_dir)
    r1 = render_all(scenes["topside"], out, "topside", views=("iso", "plan"))
    r2 = render_all(scenes["topside"], out, "topside_utilisation",
                    color_by=ColorBy("results", "utilisation", mode="utilisation", unit="-"), views=("iso",))
    r3 = render_all(scenes["field"], out, "field", views=("iso", "plan"))
    for r in (r1, r2, r3):
        print(r["html"], [p["path"] for p in r["png"]])
    print(results_fragment(scenes["field"], r3)["data_gaps"])


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "asset_scene_out")
