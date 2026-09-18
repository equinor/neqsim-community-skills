# Adsorbent Capillary Condensation Screening

Educational, dependency-free screening of the maximum condensable-contaminant
concentration a fixed adsorbent bed can tolerate before liquid fills its pores.

Answers "how much methanol can this feed carry before the mercury guard bed stops
working", which is a much tighter limit than "when does a bulk liquid drop out".

## Install and test

```bash
pip install -e .[test]
pytest
```

## Quick start

```python
from adsorbent_capillary_condensation_screening import CapillaryCondensationScreeningModel

model = CapillaryCondensationScreeningModel()
result = model.evaluate(
    temperature=293.15,
    surface_tension=0.0225,           # methanol at 20 C, N/m
    molar_volume=40.7e-6,             # m3/mol
    pore_radius_nm=6.0,
    saturation_mole_fraction=3.553e-3,  # from CPA at 20 C / 70 bara
    contaminant_mole_fraction=500e-6,
)
print(result.onset_relative_saturation, result.max_ppmv, result.warning)
```

## Two things that are easy to get wrong

1. `saturation_mole_fraction` must come from a real equation of state, not from
   `Psat/P`. At 70 bara the real gas holds about twice as much methanol as the
   ideal ratio suggests.
2. Below about 2 nm pore radius the Kelvin equation is **non-conservative**. Use
   `micropore_filling_fraction()` for microporous sorbents; volume filling starts
   at only a few percent of saturation.

See `SKILL.md` for the full method, the NeqSim coupling and the limitations.
