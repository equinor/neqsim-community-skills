"""Run the user's subsea field layout through SubseaLayoutModel.

User supplied coordinates in km; the skill treats x/y in METERS
(it divides by 1000 internally), so km values are scaled by 1000.
"""

from subsea_layout_geometry.model import SubseaLayoutModel

# (name, x_km, y_km, depth_m, kind)
raw = [
    ("HOST", 0.0, 0.0, 320, "host"),
    ("WELL-A", 8.5, 3.2, 340, "well"),
    ("WELL-B", 12.1, -4.0, 355, "well"),
    ("MANIFOLD-1", 6.0, 1.5, 335, "manifold"),
]

nodes = [
    {"name": n, "x": x_km * 1000.0, "y": y_km * 1000.0, "water_depth_m": d, "kind": k}
    for (n, x_km, y_km, d, k) in raw
]

res = SubseaLayoutModel(max_step_out_km=50.0).evaluate(
    nodes=nodes, host_name="HOST", coordinate_system="cartesian"
)

print("=== INVENTORY ===")
print(f"node_count = {res.node_count}, host = {res.host_name}")
kinds = {}
for n in nodes:
    kinds.setdefault(n["kind"], []).append(n["name"])
for k, names in kinds.items():
    print(f"  {k}: {', '.join(names)}")

print("\n=== STEP-OUT TO HOST (km) ===")
for name, km in res.step_out_km.items():
    sl = res.straight_line_km[name]
    print(f"  {name:12s} horizontal {km:7.3f}   straight-line {sl:7.3f}")
print(f"  max step-out = {res.max_step_out_km:.3f} km  ->  {res.step_out_warning}")

print("\n=== NODE-TO-NODE DISTANCE MATRIX (horizontal km) ===")
names = [n["name"] for n in nodes]
print("            " + "".join(f"{nm:>12s}" for nm in names))
dmap = {}
for d in res.pairwise_distances:
    dmap[(d.from_name, d.to_name)] = d.horizontal_km
    dmap[(d.to_name, d.from_name)] = d.horizontal_km
for a in names:
    row = f"{a:12s}"
    for b in names:
        row += f"{(0.0 if a == b else dmap.get((a, b), 0.0)):12.3f}"
    print(row)
