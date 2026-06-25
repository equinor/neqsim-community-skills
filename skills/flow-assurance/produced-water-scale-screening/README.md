# produced-water-scale-screening

Public, deterministic produced-water (brine) builder and screening-level scale
evaluation for NeqSim community examples.

This skill turns an ion analysis (or a preset / a single TDS value) into a
normalized produced-water description, performs a charge-balance check, and
emits a **NeqSim-ready ion mapping** that can be fed straight into
`neqsim.thermo.util.ProducedWaterFluidBuilder.createFromIons` to build a real
electrolyte-CPA fluid. It also computes **screening-level** scale saturation
indices (BaSO4, SrSO4, CaSO4, CaCO3), a two-water mixing-incompatibility sweep,
and informational CO2/H2S corrosion flags.

> **Screening only.** The saturation indices use public 25 degC solubility
> products and the Davies activity model. They rank scaling tendency and flag
> water-mixing incompatibility — they do **not** size inhibitor programs. For
> design-grade results, build the fluid with `ProducedWaterFluidBuilder` and run
> `ThermodynamicOperations.checkScalePotential` on the electrolyte-CPA system.

## Install / test

```bash
pip install -e .[test]
pytest -q
```

## Quick start

```python
from produced_water_scale_screening import ProducedWaterBuilder, ScaleScreener

builder = ProducedWaterBuilder()
formation = builder.build(preset="formation_water_high_ba", ph=6.5)
seawater = builder.build(preset="seawater", ph=8.1)

# NeqSim builder input (mole fractions of water + ions):
print(formation.neqsim_components)

# Worst-case scale during seawater injection (Ba/Sr meeting SO4):
for item in ScaleScreener().mixing_incompatibility(formation, seawater):
    print(item.salt, item.worst_saturation_index, item.risk)
```

Run the full demo:

```bash
python examples/scale_screening_demo.py
```

## Contents

| File | Purpose |
| ---- | ------- |
| `src/produced_water_scale_screening/chemistry.py` | Ion data, Davies activity model, ionic strength, charge balance |
| `src/produced_water_scale_screening/builder.py` | `ProducedWaterBuilder`, presets, mixing, NeqSim mapping |
| `src/produced_water_scale_screening/scale.py` | `ScaleScreener` — saturation indices, mixing sweep, corrosion flags |
| `examples/scale_screening_demo.py` | End-to-end demo |
| `tests/` | Pytest suite |

See `SKILL.md` for the full method, inputs/outputs, and limitations.
