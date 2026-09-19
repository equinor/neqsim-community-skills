# neqsim-firewater-deluge-design

Educational fire-water and deluge coverage screening for NeqSim community examples.

Turns a protected area and an application rate into a fire-water demand, a deluge nozzle
count and a grid pitch, and screens the two alternatives that get proposed whenever a fixed
nozzle net is inconvenient: dedicated protection of the individual items, and fire monitors.

See [SKILL.md](SKILL.md) for the full description, method and limitations.

## Quick start

```bash
python -m pip install -e .[test]
python examples/basic_firewater_deluge_design.py
pytest
```

```python
from firewater_deluge_design import FireWaterCoverageModel

model = FireWaterCoverageModel()
demand = model.demand(protected_area_m2=510.0, area_rate_lpm_per_m2=10.0, duration_min=30.0)
layout = model.deluge_layout(
    protected_area_m2=510.0,
    required_density_lpm_per_m2=10.0,
    nozzle_k_lpm_per_sqrt_bar=42.9,
    nozzle_min_pressure_barg=3.5,
    max_spacing_m=3.0,
    operating_pressure_barg=5.0,
)
print(demand.total_demand_m3_per_h, layout.nozzle_count, layout.governing_criterion)
```

## Scope

Screening only. It performs no network hydraulics and decides no compliance question.
Application rates, durations and the acceptability of selective protection come from the
governing project standard and any accepted deviations.
