# neqsim-asset-scene

One 3D scene contract (`neqsim_asset_scene.v1`) for illustrating process equipment, SURF and wells,
existing and proposed, with NeqSim results or live values as colours. Renders:

- **GLB** (metres, glTF Y-up, one named node per tag with provenance in `extras`);
- an **offline interactive HTML viewer** (no external scripts): rotate, pan, zoom, iso/plan/side,
  filters, hover table with source quality, NeqSim results and live values;
- **PNG** figures with legend, classification mark and a provenance caption.

Adapters: NeqSim `ProcessSystem` (mechanical design sizes and graph connectivity), plant-layout
items, subsea layout nodes and lines, well trajectories (minimum curvature), values per tag.

See [SKILL.md](./SKILL.md). Example: `python examples/asset_scene_example.py OUT_DIR`.
Tests: `pytest skills/reporting/neqsim-asset-scene`.
