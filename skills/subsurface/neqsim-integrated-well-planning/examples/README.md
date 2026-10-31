# Integrated well planning - examples

Four synthetic worked cases (every value is a demonstration assumption, `study.synthetic: true`):

| File | Well | Environment | Question |
|---|---|---|---|
| `oil_producer_platform.yaml` | oil producer | platform | tubing size and back pressure for 1500 Sm3/d |
| `gas_condensate_producer_subsea.yaml` | gas-condensate producer | subsea, 8 km flowline | tubing, erosion, hydrate and shut-in cooldown |
| `water_injector_onshore.yaml` | water injector | onshore | required wellhead pressure, fracture margin, pump duty |
| `gas_injector_platform.yaml` | gas injector | platform | required wellhead pressure and compression duty |

Run all (needs a NeqSim runtime with the wellplanning classes; the script stops with the reason otherwise):

```
<python> examples/run_cases.py <output-folder>
```

or step by step with the CLI: `<python> -m integrated_well_planning init-study <folder> --basis examples/water_injector_onshore.yaml`, then `validate-basis`, `run-model`, `alternatives`, `envelope`, `drawings`, `report`.

Limits in the examples have `limit_basis` SYNTHETIC or ASSUMED, so the operating-envelope rows stay `NEEDS_REVIEW` with an indicative status: replace them with approved limits and their sources to get PASS/WARN/FAIL.
