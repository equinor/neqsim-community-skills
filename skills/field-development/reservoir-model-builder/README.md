# neqsim-reservoir-model-builder

Set up a screening-level reservoir model from whatever data exists, and refine it
as better data arrives.

The skill implements a data-maturity ladder: a public headline volume and a depth
are enough to build a first model, analogue rock properties refine it, and
appraisal-well plus PVT data replace the analogues. Every number carries a
provenance label, so the model always reports what was known, what was assumed,
and which missing measurement matters most.

See [SKILL.md](SKILL.md) for the full documentation.

## Quick start

```bash
python -m pip install -e ".[test]"
python -m pytest
python examples/build_wisting_style_model.py
```

```python
from reservoir_model_builder import build_reservoir_model, summarize

model = build_reservoir_model(
    field_name="Example NCS oil field",
    fluid_type="oil",
    sea_area="barents_sea",
    water_depth_m=400.0,
    datum_depth_m_tvdmsl=650.0,
    recoverable_oil_Sm3=79.5e6,
)
print(summarize(model))
```

## Scope

Screening and orientation only. This is a tank-level parameter set, not a
reservoir simulator, and it does not produce reserves statements. All defaults
are generic public values. A qualified reservoir engineer must review the model
before it is used for any decision.
