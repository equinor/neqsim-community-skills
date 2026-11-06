# Seabed Protection Screening

Educational trenching, burial and rock-dump screening for subsea pipelines. Samples
public or project map layers along a route (seabed substrate, fishing intensity, ice
scour, no-rock zones, existing pipelines), selects a trenching method or rock dump
per segment, sizes trench depth, rock volume and tonnage, crossing and free-span
supports, and hands the resulting burial state to NeqSim cooldown and thermal models.

This skill supports screening only. It does not perform trawl interference,
upheaval-buckling, free-span, stability or pipe-soil assessment, and every default
(trencher capability and rates, cover per fishing class, rock geometry) is a
placeholder that must be replaced with the project basis. A qualified human review is
always required.

## Install

```bash
pip install -e .[test]
```

## Run the tests

```bash
python -m pytest
```

## Example

```bash
python examples/basic_seabed_protection_screening.py
```

See `SKILL.md` for inputs, outputs, engineering method, validation checklist and
limitations.
