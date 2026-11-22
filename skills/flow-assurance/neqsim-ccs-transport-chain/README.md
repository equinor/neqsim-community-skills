# CCS Transport Chain

Follows one CO2 stream from the pipeline inlet to the reservoir with NeqSim,
and reports the weakest link:

| Link | Question | Finding codes |
| --- | --- | --- |
| Pipeline | Does the stream stay single-phase as it cools, with margin? | `two-phase-flow`, `single-phase-margin`, `above-maop` |
| Water | Is the water content below solubility at the coldest point? | `free-water`, `water-margin` |
| Impurities | Do O2, H2S, SO2, NOx, N2, H2 meet screening limits? | `impurity-specification` |
| Depressurisation | How cold does a blowdown get? Does dry ice form? | `dry-ice`, `below-design-temperature` |
| Injection well | Is bottom-hole pressure above reservoir and below fracture pressure? | `no-injectivity`, `above-fracture-pressure`, `well-analyzer` |

Method, limitations and references are in [SKILL.md](SKILL.md).

## Install

```bash
neqsim skill install neqsim-ccs-transport-chain --vscode
```

or from a checkout:

```bash
python -m pip install -e "skills/flow-assurance/neqsim-ccs-transport-chain[neqsim]"
```

## Quick Start

```bash
python skills/flow-assurance/neqsim-ccs-transport-chain/examples/ccs_pipeline_to_injector.py
```

A synthetic 80 km, 16-inch line from 150 bara and 35 C to 4 C seabed, and a
1300 m injector. In about 20 s it shows:

- a single-phase margin of at least 70 bar;
- water at 42 times below solubility;
- blowdown to dry ice;
- 247 bara bottom-hole pressure, above the 210 bara fracture pressure. The
  dense CO2 column adds about 100 bar, so the arrival pressure has to be
  choked back.

## How to Use

### 1. The stream

```python
from ccs_transport_chain import Co2Stream

stream = Co2Stream(
    {"CO2": 0.955, "nitrogen": 0.02, "argon": 0.005, "hydrogen": 0.005,
     "oxygen": 0.00002, "methane": 0.01488, "water": 0.00005},  # mole fractions
    so2_ppmv=10.0, nox_ppmv=5.0,
)
```

Light impurities (N2, H2, Ar, CH4) raise the two-phase boundary; H2 most
strongly. Water is the dissolved water after dehydration.

### 2. Pipeline and well

```python
from ccs_transport_chain import ChainLimits, Co2Pipeline, InjectionWell

pipe = Co2Pipeline(length_m=80000.0, inner_diameter_m=0.38,
                   mass_flow_kg_h=200000.0,           # about 1.75 Mt/year
                   inlet_pressure_bara=150.0, inlet_temperature_c=35.0,
                   ambient_temperature_c=4.0, overall_u_w_m2k=5.0, segments=10)
well = InjectionWell(depth_m=1300.0, tubing_inner_diameter_m=0.157,
                     reservoir_pressure_bara=120.0,
                     top_formation_temperature_c=4.0,
                     bottom_formation_temperature_c=45.0,
                     fracture_pressure_bara=210.0)
limits = ChainLimits(min_single_phase_margin_bar=10.0, water_margin_factor=2.0,
                     min_design_temperature_c=-46.0, maop_bara=180.0)
```

To use your own pressure-temperature profile (for example from a transient
simulator), pass `stations=[Station(distance_m, pressure_bara,
temperature_c), ...]`.

### 3. Run and read

```python
from ccs_transport_chain import assess_transport_chain

report = assess_transport_chain(stream, pipe, well, limits)
print(report.to_markdown())
report.summary                 # arrival P/T, minimum margins, coldest blowdown
report.stations[-1]            # arrival station details
report.well["analyzer"]        # full NeqSim CO2InjectionWellAnalyzer result
```

| Finding | Next step |
| --- | --- |
| `two-phase-flow` / `single-phase-margin` | Raise operating pressure, or tighten light-impurity limits |
| `free-water` / `water-margin` | Tighten the water specification (dehydration) |
| `impurity-specification` | Agree O2, H2S, SO2 and NOx limits with materials and storage |
| `dry-ice` / `below-design-temperature` | Vent and blowdown design, low-temperature materials |
| `above-fracture-pressure` | Wellhead choke (check JT cooling) or lower line pressure |
| `no-injectivity` | Higher arrival pressure or booster pumping |

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Margin shows `-` at the inlet | Above the cricondentherm the stream cannot split at any pressure |
| Run takes over a minute | Reduce `segments`; each station needs a flash scan |
| Depressurisation near -90 C | Peng-Robinson has no solid phase: read it as dry ice forming near -56.6 C |

## Tests

```bash
python -m pytest skills/flow-assurance/neqsim-ccs-transport-chain/tests
```

The findings logic is tested without Java. The NeqSim integration tests check
three things: that the flash-scan boundary matches NeqSim's bubble-point flash,
that water solubility in dense CO2 is plausible, and that a short chain runs
end to end.

## Public Scope

Published methods (Peng-Robinson, SRK-CPA, isenthalpic and isentropic
flashes) as implemented in NeqSim, with synthetic data. Screening-level only.
