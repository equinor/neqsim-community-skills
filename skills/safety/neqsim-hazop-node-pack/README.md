# HAZOP Node Pack and P&ID Placement Rules

## Purpose

Vendor-neutral, offline tools for HAZOP preparation from a `neqsim.pfd_layout.v1` P&ID layout: a node-pack generator (marked-up drawings, node tables, seeded deviations, evidence gates) and twelve data-driven safeguard placement rules with a layout checker (`check_layout`).

## Validation Status

Validated on small synthetic layouts only (`tests/`): selection by tag/glob/prefix, junction and pipe selection, list-row matching, mark-up output (source PNG byte-identical afterwards), node gates, and each placement rule firing and staying quiet. The rules are conventions, not verified standard text; no compliance is claimed.

## Data Status

Examples and tests use synthetic drawings and placeholder tags. Do not commit real P&IDs, company data or credentials.

## Inputs and Outputs

Inputs: layout or connectivity JSON, an optional drawing PNG, valve/instrument and line list CSV files, node definitions. Outputs: `nodes.csv`, `node_items.csv`, `node_modes.csv`, `node_seeds.csv`, `pack.json`, `README.md`, mark-up PNGs, and a list of `Finding` objects from the rules. See `SKILL.md`.

## Install

```powershell
python -m pip install -e "skills/safety/neqsim-hazop-node-pack[test]"
```

## Example

```powershell
python skills/safety/neqsim-hazop-node-pack/examples/hazop_node_pack_example.py
```

## Test

```powershell
python -m pytest skills/safety/neqsim-hazop-node-pack/tests
```

## Limitations and Human Review

A finding is a prompt for the HAZOP team, and an empty finding list does not prove the design adequate. Node boundaries are bounding boxes to be confirmed on the drawing. A qualified HAZOP chair and multidisciplinary team must review every node, finding and gap before any result is used.
