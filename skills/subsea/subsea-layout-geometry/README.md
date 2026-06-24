# Subsea Layout Geometry

Educational subsea field-layout geometry screening skill for public examples and agent guidance.

This skill provides a simple Python `SubseaLayoutModel` that converts supplied well, manifold, and host coordinates into horizontal step-out distances, straight-line tie-back lengths, and a node-to-node distance matrix. It also provides `plot_subsea_layout`, a deterministic schematic plan-view renderer (host, wells, manifolds, templates, tie-backs/flowlines, umbilical) that returns a matplotlib figure for reports. It is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/subsea/subsea-layout-geometry
# optional: schematic plan-view illustration
python -m pip install -e "skills/subsea/subsea-layout-geometry[plot]"
```

## Run Example

```bash
python skills/subsea/subsea-layout-geometry/examples/basic_subsea_layout_geometry.py
# schematic map (requires the [plot] extra)
python skills/subsea/subsea-layout-geometry/examples/subsea_field_layout_map.py
```

## Run Tests

```bash
python -m pytest skills/subsea/subsea-layout-geometry/tests
```

## Public Scope

The model does not contain proprietary field layouts, confidential well coordinates, route corridors, or company-specific routing rules. Coordinates must be public or synthetic. Straight-line lengths are screening lower bounds only. For real work, use validated NeqSim routing and hydraulic workflows and qualified subsea engineering review.
