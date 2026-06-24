import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from subsea_layout_geometry import SubseaLayoutModel

# NOTE: x, y are in METERS (the skill converts to km internally).
nodes = [
    {"name": "HOST", "x": 0.0, "y": 0.0, "water_depth_m": 320, "kind": "host"},
    {"name": "WELL-A", "x": 8500.0, "y": 3200.0, "water_depth_m": 340, "kind": "well"},
    {"name": "WELL-B", "x": 12100.0, "y": -4000.0, "water_depth_m": 355, "kind": "well"},
    {"name": "MANIFOLD-1", "x": 6000.0, "y": 1500.0, "water_depth_m": 335, "kind": "manifold"},
]
res = SubseaLayoutModel(max_step_out_km=50.0).evaluate(nodes=nodes, host_name="HOST")

fig, (ax_map, ax_bar) = plt.subplots(1, 2, figsize=(12, 5))
host = next(n for n in nodes if n["name"] == "HOST")
colors = {"host": "k", "well": "tab:red", "manifold": "tab:blue"}
for n in nodes:
    x_km, y_km = n["x"] / 1000.0, n["y"] / 1000.0
    ax_map.scatter(x_km, y_km, s=120, c=colors.get(n["kind"], "gray"), zorder=3)
    ax_map.annotate(n["name"], (x_km, y_km), textcoords="offset points", xytext=(6, 6))
    if n["name"] != host["name"]:
        hx, hy = host["x"] / 1000.0, host["y"] / 1000.0
        ax_map.plot([hx, x_km], [hy, y_km], "--", c="gray", lw=1, zorder=1)
        mx, my = (hx + x_km) / 2, (hy + y_km) / 2
        ax_map.annotate(f"{res.step_out_km[n['name']]:.1f} km", (mx, my), color="gray", fontsize=8)
ax_map.set_xlabel("Easting [km]")
ax_map.set_ylabel("Northing [km]")
ax_map.set_title("Subsea field plan view")
ax_map.grid(True, ls=":")
ax_map.set_aspect("equal")

names = list(res.step_out_km)
vals = [res.step_out_km[k] for k in names]
ax_bar.bar(names, vals, color="tab:red")
ax_bar.axhline(res.max_step_out_km, ls="--", c="k", label="max in field")
ax_bar.axhline(50.0, ls=":", c="orange", label="guideline 50 km")
ax_bar.set_ylabel("Step-out [km]")
ax_bar.set_title("Step-out to host")
ax_bar.legend()
fig.tight_layout()
fig.savefig("subsea_layout_map.png", dpi=150)

print("node_count", res.node_count)
print("step_out_km", res.step_out_km)
print("max_step_out_km", res.max_step_out_km)
print("warning", repr(res.step_out_warning))
print("saved subsea_layout_map.png")
