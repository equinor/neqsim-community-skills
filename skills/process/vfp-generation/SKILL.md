---
name: neqsim-vfp-generation
version: "0.1.0"
description: "Generate, post-process, import, and compare Eclipse VFPPROD lift-curve tables from a constraint-based compressor model, with a documented diagnostic visualization style. USE WHEN: a task needs to build or read reservoir-simulator VFPPROD tables, classify operating points against compressor constraints, or enforce monotonic lift curves."
last_verified: "2026-06-05"
requires:
  python_packages: []
  java_packages: ["neqsim (optional, for the solving workflow)"]
  env: []
  network: []
---

# VFP Generation

Use this skill to work with Eclipse VFPPROD lift-curve tables for a compression facility:
classify compressor operating points against constraints (PASS/WARN/FAIL), enforce
monotonic lift curves, export traceable VFPPROD tables, and parse/compare existing
`.VFP` files. The executable code here is dependency-free and public; the full
constraint-solving loop (which needs a process model) is documented as a workflow.

## When to Use

- When you need to classify a compressor value (power, speed, temperature, margin,
  casing capacity) against a limit using a consistent PASS/WARN/FAIL scheme.
- When you must enforce a physically monotonic lift curve before export.
- When you need to write an Eclipse VFPPROD table with a traceability header.
- When you need to parse existing `.VFP` files and compare reference vs generated tables.

For operability-envelope studies (turndown, startup), see a controllability skill. For
field-level network optimization, see a production-optimization skill. This skill is
specifically about VFPPROD table generation and handling.

## Inputs

- Constraint evaluation: a `value`, a `limit`, a `threshold_mode`
  (`factor`, `offset`, `margin_pct`), and `pass_at` / `warn_at` / `fail_at` thresholds.
- VFP export: `table_id`, `datum_depth`, a flow-rate axis (Sm³/day), an outlet-pressure
  (THP) axis (bara), and a 2-D inlet-pressure matrix.
- VFP import: a path to a `.VFP` file or a directory of them.

## Outputs

- `classify_value(...)` → `"PASS"`, `"WARN"`, or `"FAIL"`.
- `enforce_monotonic(rows)` → a copy with each lift curve made non-decreasing.
- `format_eclipse_vfp(...)` → VFPPROD table text (round-trippable with the parser).
- `parse_vfp_file(path)` / `load_vfp_dir(dir)` → `VFPTable` objects.
- `VFPTable`: `table_id`, `datum_depth`, `flow_rates`, `outlet_pressures`,
  `inlet_pressures` (matrix), `comments`, `default_label`.

## Engineering Method

### Constraint classification

Three threshold modes, matching the production generator:

- `factor`: compare `value` to `limit × factor`. PASS if `value ≤ limit·pass_at`,
  FAIL if `value ≥ limit·fail_at`, else WARN. Used for speed vs max-speed and
  casing capacity.
- `offset`: compare `value` to `limit − offset`. PASS if `value ≤ limit − pass_at`,
  FAIL if `value > limit − fail_at`, else WARN. Used for motor power and discharge
  temperature.
- `margin_pct`: `value` *is* a margin percent; higher is safer. PASS if
  `value > pass_at`, FAIL if `value ≤ fail_at`, else WARN. Used for surge, stonewall,
  pipe velocity, and scrubber K-value.

Default thresholds per constraint are in `DEFAULT_THRESHOLDS` and cover all eight
constraint types: `motor_power`, `discharge_temperature`, `surge_margin`,
`stonewall_margin`, `pipe_velocity`, `scrubber_k_value`, `chart_envelope`, and
`max_casing_capacity`.

### Monotonic enforcement

A lift curve (inlet pressure vs flow at fixed outlet pressure) must be non-decreasing
with flow. `enforce_monotonic` performs a left-to-right pass lifting any cell below its
predecessor, which mimics the physical behaviour of opening anti-surge / blade controls.

### Eclipse VFPPROD

The exporter writes a METRIC VFPPROD table with a comment header carrying full
traceability (configuration ids, versions, constraints, compressor metadata). Infeasible
cells are written as a sentinel value. The parser reads the flow axis, the outlet
(THP) axis, and the inlet-pressure matrix back into a `VFPTable`.

### Solving workflow (documented, requires a process model)

1. Define a flow × outlet-pressure grid and a warm-up point.
2. For each cell, solve the inlet pressure that balances the compression train.
3. After each solve, classify every constraint; a hard FAIL marks the cell infeasible.
4. Use a feasibility step-down then bisection to find the limiting inlet pressure.
5. Post-process: interpolate isolated failures, enforce monotonicity, left-pad NaNs.
6. Export to VFPPROD with the traceability header.

## Diagnostic Visualization Style

The diagnostics use a consistent visual language so plots are comparable across runs.

### Colour mapping
- A `viridis` colormap is mapped to total flow rate (MSm³/d) via a single
  `Normalize(min_flow, max_flow)`; every point coloured by its flow.

### Marker convention (compressor maps and driver plots)
| Element | Marker | Style |
| --- | --- | --- |
| First evaluation (warm-up / initial) | open circle `o` | `facecolors="none"`, viridis edge, s≈30, lw 0.8, alpha 0.6, zorder 4 |
| Intermediate iterations | small dot in `.-` trace | viridis, ms≈2, lw 0.7, alpha 0.35, zorder 3 |
| Final PASS / WARN | filled circle `o` | viridis fill, s≈50, black edge lw 0.5, zorder 10 |
| Final FAIL | red cross `x` | red, s≈70, lw 2, zorder 11 |
| NaN / chart unsolvable | red inverted triangle `v` | red, s≈50, lw 1.5, zorder 11 |

### Driver (power) plot
- Driver envelope: solid black line, lw 2.5; green fill below at alpha 0.06.
- PASS / WARN thresholds: green / orange dashed lines, lw 1, alpha 0.6.
- Gas power: circle `o` markers (viridis), s≈50.
- Motor (shaft) power: triangle-up `^` markers (viridis), s≈40.
- Gas→motor link: solid line, same viridis colour, lw 0.8, alpha 0.5.

### Compressor map background
- Speed lines: silver solid, lw 0.8, alpha 0.6.
- Surge line: red dashed, lw 1.5. Stonewall: goldenrod dashed, lw 1.5.

### Binding-constraint colours
`motor_power` #d62728, `chart_envelope` #1f77b4, `discharge_temperature` #ff7f0e,
`none` #2ca02c, default #7f7f7f.

### Max-flow envelope colours (per outlet pressure)
80 #1f77b4, 90 #ff7f0e, 100 #2ca02c, 110 #d62728, 120 #9467bd.

### Constraint table superscripts
ˢ surge, ᶜ choke, ⁿ speed, ᵖ power, ᵈ ΔP, ᵗ temperature, ᵛ velocity, ᵏ K-value.

## Python Usage Pattern

```python
from vfp_generation import (
    classify_value, DEFAULT_THRESHOLDS, get_thresholds,
    enforce_monotonic, format_eclipse_vfp, parse_vfp_file,
)

# Classify a motor-power reading against a 500 MW driver limit (offset mode)
mode, p, w, f = get_thresholds("motor_power")
print(classify_value(498.5, 500.0, mode, p, w, f))  # -> PASS / WARN / FAIL

# Enforce a monotonic lift curve
rows = [[10.0, 9.0, 12.0, 11.0]]
print(enforce_monotonic(rows))  # -> [[10.0, 10.0, 12.0, 12.0]]

# Export and re-parse a VFPPROD table
text = format_eclipse_vfp(
    table_id=1, datum_depth=335.0,
    flow_rates_sm3day=[1e6, 5e6, 1e7],
    outlet_pressures_bara=[80.0, 100.0, 120.0],
    inlet_pressure_matrix=[[40, 50, 60], [55, 65, 75], [70, 80, 90]],
    traceability={"conf_id": "demo", "region": "example"},
)
table = parse_vfp_file_from_text(text)  # helper in examples
```

## Validation Checklist

- [ ] `threshold_mode` matches the constraint's physical meaning.
- [ ] Lift curves are monotonic after post-processing.
- [ ] The flow axis is in Sm³/day and pressures in bara for export.
- [ ] Infeasible cells use the agreed sentinel value, not silently zero.
- [ ] Parsed `VFPTable` dimensions match the source axes.
- [ ] Example inputs are public and synthetic.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Everything WARN | wrong `threshold_mode` | pick factor/offset/margin_pct to match the value |
| Lift curve non-physical | skipped monotonic enforcement | run `enforce_monotonic` before export |
| Parser row/col mismatch | edited a `.VFP` by hand | re-export with `format_eclipse_vfp` |
| Sentinel treated as data | failure value plotted as pressure | mask the sentinel before plotting |

## Limitations

- The constraint-solving loop requires a calibrated process model (optional `neqsim`).
- `DEFAULT_THRESHOLDS` are generic public defaults, not project acceptance criteria.
- The exporter targets a METRIC VFPPROD subset, not every Eclipse keyword option.
- Not a substitute for a validated reservoir-coupled lift-curve study or review.

## References

- Schlumberger Eclipse Reference Manual, VFPPROD keyword (public documentation).
- API Standard 617 for centrifugal compressor concepts.
- NeqSim repository: https://github.com/equinor/neqsim
