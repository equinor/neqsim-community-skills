---
name: neqsim-hazop-node-pack
calculation_basis: "screening"
version: "1.0.0"
description: "Vendor-neutral HAZOP preparation from P&ID layouts. USE WHEN: a facilitator needs a node pack (marked-up P&ID per node, item/mode tables, seeded guide-word deviations incl. well, SURF, riser, HIPPS, pig receiver) with evidence gates, or a P&ID needs a screening check of safeguard placement (thermal relief, pig trap, ESDV, HIPPS voting, EDP orifice, vents, duplicate tags). Prompts for the team, not findings or compliance."
last_verified: "2026-11-22"
requires:
  python_packages: ["pillow"]
  java_packages: []
  env: []
  network: []
---

# HAZOP Node Pack and P&ID Placement Rules

Two offline, Java-free tools for HAZOP preparation from a `neqsim.pfd_layout.v1` P&ID layout:

1. **Node pack generator** (`hazop_node_pack.node_pack`): the pre-session document set per node - the drawing with the node boundary marked, design intent, conditions per operating mode, the items and list rows taken from the drawing and the valve/instrument/line lists, seeded guide-word/parameter deviations and evidence gates.
2. **Placement rules** (`hazop_node_pack.placement_rules`): twelve data-driven conventions (`RULES`) and `check_layout(layout)` that turn the drawing graph into prompts for the HAZOP team.

No network, no subprocess, no run-time install. Pillow is the only dependency (mark-up PNGs).

## When to Use

- Preparing node documents before a facilitated HAZOP: nodes marked on the P&IDs, node item lists, operating modes, seeded worksheet rows.
- Screening a P&ID layout for missing or unusual safeguard placement before the HAZOP, so the team starts with a list of questions.
- Hand-off to LOPA/SIL work: the generator and the rules never allocate integrity levels.

Do not use it as a HAZOP, a safety analysis table or a compliance check. A finding is a prompt, and an empty finding list does **not** prove the design adequate.

## Inputs

| Input | Form | Notes |
| --- | --- | --- |
| P&ID layout | `sheet_from_layout(layout.json, image_size, image_path=png)` | `nodes` with `id`, `kind`, `tag`, `bbox` `[x, y, w, h]`, `texts`; `edges` with `from`, `to`, `fluid`, `points`. |
| P&ID connectivity | `sheet_from_connectivity(conn.json, image_size, canvas_mm=(420, 297), y_up=True)` | nodes with `anchor` in mm, `pipes`, `edges`. |
| Valve/instrument list, line list | `read_csv_rows(csv)` | columns `sheet`, `tag`; `sheet`, `line_number`. |
| Node definitions | list of dicts | `node_id`, `name`, `design_intent`, `boundary`, `equipment_types`, `modes`, `drawings` (`sheet`, `tags`, `tag_globs`, `keys`, `line_nos`), `notes`, `links`. |
| Layout for the rules | dict or path | optional node attributes: `measure`, `voting`, `module`/`area`, `exempt`, `fail_position`, `interlock`, `travel_stop`, `tap`; layout-level `hazop_exemptions`. |

Tags match with the proposal asterisk and the project prefixes in `TAG_PREFIXES` (default `GR-`, an example; set `()` to disable) ignored. A junction joins a node selection when two of its neighbours are selected, repeatedly.

## Outputs

- Node pack (`build_node_pack(..., out_dir=...)`): `nodes.csv`, `node_items.csv`, `node_modes.csv`, `node_seeds.csv`, `pack.json` (schema `hazop_node_pack.v1`), `README.md`, `markups/<node>_<sheet>.png` (selected lines and items highlighted, dashed node boundary). The source drawing is never modified and the mark-up refuses to overwrite it. `boundary_box_px` is in source-image pixels.
- Rules: `Finding(rule_id, severity, message, objects, fix)`; severity `ERROR`, `WARN` or `INFO`; `format_findings()` appends the evidence notice.

### Seeds by equipment type

Process types (separator, compressor, pump, heater, heat exchanger, cooler, valve, pipeline, seal gas, separation gas, seal vent, lube oil, flare, vent) plus `tree`, `annulus`, `umbilical`, `pigreceiver`, `hipps`, `riser`, `manifold` and `chemicalstorage`. Wording such as `pig receiver`, `XMT` or `chemical storage` is folded onto these keys; an unknown type falls back to a two-row default and is listed in `missing_evidence`.

## Engineering Method

Node pack: select items by tag/glob/key, add in-line junctions, select pipes with two selected members or a listed line number, match list rows by sheet and normalised tag, infer equipment types from item kinds, seed deviations, and draw the mark-up. Gates per node: design intent, boundary text, drawing items, a positive design pressure in at least one mode, an operating mode. Every failed gate, unmatched tag/key/glob, valve or instrument without a list row, missing drawing image, unknown equipment type and duplicate node id becomes a `missing_evidence` entry. A gap is never a pass. A mode `status` left empty becomes `UNVERIFIED`. `ready_for_hazop_facilitation` means no gap was found by the generator, not that values are verified.

Placement rules (conventions, not verified text; no compliance claim):

| Id | Prompt | Basis (convention) |
| --- | --- | --- |
| PR-01 | Liquid or mixed segment between two closable valves has no relief device | API STD 521 trapped-liquid thermal relief |
| PR-02 | Pig receiver lacks vent, drain, relief connection, inlet or outlet isolation | API RP 14C / ISO 10418 safety analysis table |
| PR-03 | No ESD valve between an import/riser boundary and the first process equipment | API RP 14C / ISO 10418 |
| PR-04 | HIPPS-like function lacks two series valves, three pressure transmitters on separate taps (2oo3) or a logic solver; INFO when a class break has none | IEC 61511 independence/voting |
| PR-05 | Pump discharge has no relief device or transmitter pair | API RP 14C / ISO 10418 |
| PR-06 | Chemical injection lacks two checks, or a check plus an isolation valve | API RP 14C / ISO 10418 |
| PR-07 | EDP/BDV line lacks a restriction orifice or a flare/closed destination | API RP 14C / ISO 10418 |
| PR-08 | Hydrocarbon module has fewer than two gas detectors or no flame detector | NORSOK S-001 |
| PR-09 | Voted initiator (PAHH, LAHH ...) rests on a single transmitter | IEC 61511 |
| PR-10 | Vent or drain ends in atmosphere or an open end | NORSOK S-001 |
| PR-11 | Choke/control valve near a class break has no interlock, travel stop or fail-closed note | IEC 61511 |
| PR-12 | Duplicate tag on a sheet | drafting convention |

Rules read node `kind`, `tag`, texts and edge `fluid`; walks are limited to a few hops and stop at equipment and boundaries. Exempt an item with the node/edge attribute `exempt` (`true` or a rule id) or a layout-level `hazop_exemptions` entry `{"rule": "PR-01", "objects": ["J1"], "reason": "..."}`.

## Python Usage Pattern

```python
from hazop_node_pack import build_node_pack, check_layout, format_findings, sheet_from_layout

findings = check_layout("SYN-PID-001.layout.json")   # dict or path
print(format_findings(findings))                       # prompts for the HAZOP team

sheet = sheet_from_layout("SYN-PID-001.layout.json", (1600, 1200), image_path="SYN-PID-001.png")
pack = build_node_pack([node_definition], {"SYN-PID-001": sheet}, valve_rows=rows, out_dir="pack")
```

`examples/hazop_node_pack_example.py` builds a synthetic sheet and one node pack; `tests/test_placement_rules.py::test_worked_example_riser_landing_finding_ids` builds a small riser-landing layout and asserts the exact finding ids for a missing PSV (`PR-02`), a missing ESDV (`PR-03`), a HIPPS with two instead of three transmitters (`PR-04`) and an EDP line without orifice (`PR-07`).

## Validation Checklist

- Every finding was reviewed against the full drawing set (the safeguard may be on another sheet).
- Node boundaries were confirmed on the marked-up drawing; the box is only a bounding box.
- `missing_evidence` was closed or carried into the HAZOP record as open items.
- Operating conditions in the node definition come from a named source and `status` is set.
- Exemptions carry a reason.

## Common Mistakes

- Reading an empty finding list as an adequate design.
- Passing a PNG whose size differs from the layout canvas aspect without `image_size`.
- Leaving the default `GR-` prefix on when tags legitimately start with it (set `TAG_PREFIXES = ()`).
- Treating `ready_for_hazop_facilitation` as verified data.

## Limitations

- Graph heuristics (tag tokens, hop limits, fluid words) miss unusual drawings and can flag safeguards drawn elsewhere.
- Series valves, separate taps and voting are checked by count and attachment, not by geometry or independence analysis.
- Does not choose nodes, judge causes/consequences/safeguards, verify values, allocate SIL or replace the facilitated session.
- Rules are conventions paraphrased from public practice; no compliance with any standard is claimed.

## References

- IEC 61882 - HAZOP studies (guide words, node/deviation method).
- API RP 14C / ISO 10418 - safety analysis table convention.
- API STD 521 - thermal relief of trapped liquid.
- IEC 61511 - functional safety, independence and voting.
- NORSOK S-001 - technical safety (detection, layout expectations).
- `neqsim-safety-function-coverage-screening` - component-level protective-function coverage.
