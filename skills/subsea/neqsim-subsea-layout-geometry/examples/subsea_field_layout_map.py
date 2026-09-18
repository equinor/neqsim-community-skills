"""Render a schematic plan-view map of a subsea field layout.

Produces ``subsea_field_layout.png`` next to this example. Requires matplotlib
(install with the optional ``plot`` extra).
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from subsea_layout_geometry import plot_subsea_layout


def main() -> None:
    nodes = [
        {"name": "HOST", "x": 0.0, "y": 0.0, "water_depth_m": 320.0, "kind": "host"},
        {"name": "MANIFOLD-1", "x": 6000.0, "y": 1500.0, "water_depth_m": 335.0, "kind": "manifold"},
        {"name": "TEMPLATE-A", "x": 8500.0, "y": 3200.0, "water_depth_m": 340.0, "kind": "template"},
        {"name": "WELL-A1", "x": 8800.0, "y": 3600.0, "water_depth_m": 342.0, "kind": "well"},
        {"name": "WELL-A2", "x": 9000.0, "y": 2900.0, "water_depth_m": 345.0, "kind": "well"},
        {"name": "WELL-B1", "x": 12100.0, "y": -4000.0, "water_depth_m": 355.0, "kind": "well"},
    ]

    # Explicit routed flowline segments (host <- manifold <- template <- wells).
    flowlines = [
        ("HOST", "MANIFOLD-1"),
        ("MANIFOLD-1", "TEMPLATE-A"),
        ("TEMPLATE-A", "WELL-A1"),
        ("TEMPLATE-A", "WELL-A2"),
        ("MANIFOLD-1", "WELL-B1"),
    ]
    # Umbilical follows the trunk from host to the manifold.
    umbilical = [("HOST", "MANIFOLD-1")]

    output = Path(__file__).resolve().parent / "subsea_field_layout.png"
    plot_subsea_layout(
        nodes,
        host_name="HOST",
        coordinate_system="cartesian",
        flowlines=flowlines,
        umbilical=umbilical,
        max_step_out_km=50.0,
        title="Subsea field layout (schematic plan view)",
        save_path=output,
    )
    print(f"saved {output}")


if __name__ == "__main__":
    main()
