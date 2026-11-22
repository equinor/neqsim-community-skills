# neqsim-meg-loop

Size a MEG hydrate-inhibition loop with NeqSim: lean MEG injection,
regeneration and salt handling from one well-stream model.

## Install

From the repository root:

```bash
uv sync
python -m pip install "neqsim>=3.29.0"
```

## Quick start

```bash
python skills/flow-assurance/neqsim-meg-loop/examples/gas_tieback_meg_loop.py
```

The example is a 8 MSm3/d gas tie-back with 20 m3/d of 60 g/L formation
water, shut-in at 150 bara and 4 C with a 3 C margin. Result (NeqSim 3.29.0):

| Quantity | Value |
| --- | ---: |
| Uninhibited hydrate temperature | 22.2 C |
| Lean MEG (90 wt %) injection | 2774 kg/h (60.5 m3/d) |
| Rich MEG at arrival | 49.2 wt % (Hammerschmidt 50.4) |
| Reboiler | 143.7 C, 1705 kW |
| Salt in | 1200 kg/day |
| Minimum reclaimer slipstream | 36 % (30 % given: high finding) |

## How to use it

1. **Describe the stream** without MEG. Add `water` for the condensed water
   and `formation_water_m3_d` / `formation_water_tds_mg_l` from the water
   forecast. Run one case per year of the profile: formation water usually
   drives both the duty and the salt.
2. **Pick the design point**: the coldest temperature at the highest pressure
   the line can see (shut-in or settle-out at seabed temperature).
3. **Set the regeneration basis**: lean concentration, regenerator pressure,
   reclaimer slipstream and salt limit from the project.
4. **Read the report**: check the rich MEG against Hammerschmidt, compare
   injection and duty with the existing pump and regeneration capacity, and
   act on `salt-accumulation`.

```python
from meg_loop import HydrateDesign, Regeneration, WellStream, assess_meg_loop

for year, water in [(2027, 5.0), (2030, 20.0), (2034, 60.0)]:
    stream = WellStream(
        {"methane": 85, "ethane": 6, "propane": 3, "n-butane": 1,
         "CO2": 2, "nitrogen": 1, "water": 0.6},
        flow_rate=8.0, formation_water_m3_d=water, formation_water_tds_mg_l=60000.0)
    rep = assess_meg_loop(
        stream,
        HydrateDesign(150.0, 4.0, arrival_pressure_bara=60.0, arrival_temperature_c=15.0),
        Regeneration(reclaimer_slipstream=0.3, lean_alternatives=()))
    r = rep.results
    print(year, round(r["lean_meg_kg_h"]), round(r["reboiler_duty_kw"]),
          round(r["min_slipstream_pct"], 1), rep.highest_severity)
```

Output (year, kg/h lean MEG, kW reboiler, % minimum slipstream, severity):

```text
2027 2038 1250 12.3 info
2030 2773 1713 36.1 high
2034 4731 2947 63.4 high
```

Water breakthrough more than doubles the injection and duty, and a 30 %
reclaimer slipstream stops being enough between 2027 and 2030.

Get JSON with `report.to_dict()` (NaN becomes `null`).

## Tests

```bash
uv run pytest skills/flow-assurance/neqsim-meg-loop
```

Logic tests run without Java; integration tests need `neqsim` and check the
hydrate target, the mass balance, Hammerschmidt agreement at 30 wt %, the
salt balance and the bubble-point reboiler temperature.

## Limits

Screening only. Hydrate equilibrium without salt correction, idealised
reclaimer, enthalpy-balance regenerator. See `SKILL.md`.
