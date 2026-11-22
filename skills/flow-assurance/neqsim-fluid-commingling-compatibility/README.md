# Fluid Commingling Compatibility

Screens two fluids that will be mixed — a tie-in into a host, two zones in one
well, gas lift into heavy oil, a shared flowline — for problems that only the
mixture has. Each blend ratio is run through NeqSim, and the report shows the
worst ratio for each check:

| Check | What can go wrong in the mixture | Finding codes |
| --- | --- | --- |
| Asphaltene stability | A lighter fluid dilutes an asphaltenic oil and lowers its solvent power | `asphaltene-onset-crossed`, `asphaltene-marginal`, `asphaltene-dilution`, `de-boer-worse-than-host` |
| Free gas | Two single-phase streams release gas where they meet | `free-gas-at-commingling` |
| Hydrate | The blend hydrate temperature exceeds both end members, or the operating margin | `hydrate-blend-maximum`, `hydrate-margin` |
| Sour gas | Mixed separator gas exceeds an H2S or CO2 limit | `h2s-limit`, `co2-limit` |
| PVT | End-member PVT cannot be interpolated for the blend | `saturation-nonlinear` |
| Wax | The blend wax appearance temperature is above the operating minimum, or above both fluids | `wax-margin`, `wax-blend-maximum` |
| Naphthenates | An acidic oil meets calcium-rich water whose pH rises as CO2 flashes off | `calcium-naphthenate`, `naphthenate-not-assessed` |

Method, equations, limitations and references are in [SKILL.md](SKILL.md).

## Install

From a NeqSim community workspace (installs the skill and keeps it importable):

```bash
neqsim skill install neqsim-fluid-commingling-compatibility --vscode
```

Or directly from a checkout of this repository:

```bash
python -m pip install -e "skills/flow-assurance/neqsim-fluid-commingling-compatibility[neqsim]"
```

`neqsim` (3.29.0 or later) needs a Java runtime. Without it, the package still
imports, but `NeqSimBlendEvaluator()` raises `NeqSimUnavailableError`.

## Quick Start

```bash
python skills/flow-assurance/neqsim-fluid-commingling-compatibility/examples/heavy_oil_condensate_tie_in.py
```

A public synthetic case: a gas condensate tied into an asphaltenic host oil.
It runs in about 15 s and prints the findings and the blend table. Add `--json`
for the machine-readable report.

## How to Use

### 1. Describe the two fluids

```python
from fluid_commingling_compatibility import FluidSpec, PseudoComponent

host = FluidSpec(
    label="host",                       # 1-12 letters/digits, used in names
    asphaltenic=True,                   # this fluid carries the asphaltenes
    components={"methane": 18.0, "ethane": 6.0, "propane": 5.0, "CO2": 1.0,
                "H2S": 0.02, "n-butane": 3.0, "n-hexane": 2.5},
    pseudo_components=[                 # name, amount, kg/mol, g/cm3
        PseudoComponent("C10", 20.0, 0.140, 0.80),
        PseudoComponent("C30", 20.0, 0.450, 0.93),
    ],
)
tiein = FluidSpec(
    label="tiein",
    components={"methane": 72.0, "ethane": 8.0, "propane": 5.0, "CO2": 2.5,
                "H2S": 0.05},
    pseudo_components=[PseudoComponent("C7", 4.0, 0.098, 0.74)],
)
```

- Component names are NeqSim names (`methane`, `CO2`, `H2S`, `water`,
  `n-butane` ...). Amounts can be mol %, mole fractions or molar rates; each
  fluid is normalised.
- Pseudo-component molar mass is in **kg/mol** (0.140, not 140) and density in
  **g/cm3**. Values out of range are rejected with a message.
- Use the characterisation from your PVT report or tuned EoS model. The skill
  does not tune the equation of state.
- Add `"water"` if the stream carries water; the evaluator then switches to
  SRK-CPA. Asphaltene and density checks always use the water-free blend.

### 2. Put the operating point on the blend axis

The blend axis `x_B` is the **mole** fraction of fluid B. Convert your rates:

```python
from fluid_commingling_compatibility import (
    NeqSimBlendEvaluator, mole_fraction_from_mass_rates, mole_fraction_from_rates,
)

evaluator = NeqSimBlendEvaluator()
x_operating = mole_fraction_from_mass_rates(
    150_000.0, evaluator.molar_mass_kg_mol(host),    # kg/h, kg/mol
    25_000.0,  evaluator.molar_mass_kg_mol(tiein),
)                                                    # -> about 0.49
# or, with molar rates already known:
x_operating = mole_fraction_from_rates(kmol_h_host, kmol_h_tiein)
```

A light fluid takes a large mole fraction for a small mass rate: in the example,
25 t/h of condensate into 150 t/h of oil is about half the moles of the blend.

### 3. Set the conditions and limits

```python
from fluid_commingling_compatibility import EvaluationConditions, ScreeningLimits

conditions = EvaluationConditions(
    commingling_pressure_bara=200.0,   # where the streams meet
    commingling_temperature_c=80.0,
    path_end_pressure_bara=20.0,       # bottom of the depressurisation path
    path_points=12,                    # pressures scanned for the RI minimum
    separator_pressure_bara=40.0,      # optional, for H2S/CO2 in the gas
    separator_temperature_c=60.0,
    hydrate_pressure_bara=120.0,       # optional, for the hydrate check
)
limits = ScreeningLimits(
    onset_ri=1.445,                    # measured onset RI of the asphaltenic fluid
    min_operating_temperature_c=25.0,
    h2s_limit_ppm=400.0,
    co2_limit_mol_pct=3.0,
)
```

The asphaltene verdict depends on the onset refractive index (P_RI) of the
asphaltenic fluid:

| What you have | What to pass | What the report gives |
| --- | --- | --- |
| Measured onset (titration) | `ScreeningLimits(onset_ri=...)` | Absolute stability class per blend |
| SARA analysis only | `sara=(sat, aro, res, asph)` to `screen_commingling` | Class from a correlation onset; stated in the report |
| Neither | nothing | Relative drop in RI versus the host alone (`asphaltene-dilution`) |

### 3b. Wax and naphthenates (optional)

```python
from dataclasses import replace
from fluid_commingling_compatibility import WaterChemistry

host = replace(host, tan_mg_koh_g=1.5)      # stabilised-oil TAN, mg KOH/g
tiein = replace(tiein, tan_mg_koh_g=0.05)
conditions = replace(
    conditions,
    wax_pressure_bara=50.0,                 # WAT of each blend at this pressure
    separator_water=WaterChemistry(calcium_mg_l=800.0, bicarbonate_mg_l=1500.0,
                                   chloride_mg_l=30000.0),
)
```

- The wax check uses NeqSim's TBP wax model on your C7+ cuts. Compare WAT
  with the coldest point of the line (`min_operating_temperature_c`).
- The naphthenate screen flags blends where blend TAN, separator water pH and
  calcium all exceed `ScreeningLimits.naphthenate_*` (defaults 0.5 mg KOH/g,
  pH 6.0, 100 mg/L). Lower separator pressure means more CO2 flashing, a
  higher pH and a higher risk.

### 4. Run the sweep

```python
from fluid_commingling_compatibility import screen_commingling

report = screen_commingling(
    host, tiein, conditions, evaluator,
    fractions=(0.0, 0.1, 0.2, 0.3, round(x_operating, 2), 0.7, 1.0),
    limits=limits,
)
print(report.to_markdown())
data = report.to_dict()          # JSON-safe, for notebooks and task reports
```

Include the planned operating ratio in `fractions`. End members are always
added. Each blend takes 1-2 s.

### 5. Read the report

- `report.highest_severity`: `high`, `warning`, `info` or `none`.
- `report.findings`: each `Finding` has `severity`, `code` and a message
  that names the blend range and the next step.
- `report.worst_cases`: the worst blend per check, e.g.
  `report.worst_cases["asphaltene"]["fraction_b"]`.
- The table's `min RI (at bara)` is the lowest live-oil refractive index along
  the pressure path and where it occurs — normally just above the bubble
  point. `n/a` marks blends that contain no asphaltenic fluid.

What to do with each `high` finding:

| Finding | Next step |
| --- | --- |
| `asphaltene-onset-crossed` | Onset titration or HPM test on the blend at the flagged ratio; consider a blending-ratio limit or inhibitor screening |
| `hydrate-margin` | Hydrate inhibitor dosing for the blend (MEG/methanol), using the worst-blend hydrate temperature |
| `h2s-limit` / `co2-limit` | Sour-service materials review, export-gas treatment or ratio limit |
| `wax-margin` | Wax deposition and pigging study for the blend; insulation or heating |
| `calcium-naphthenate` | Bottle tests on the blend and water; acid or naphthenate-inhibitor dosing; separator pressure strategy |

## Typical Studies

- **Tie-in screening:** host fluid + tie-in fluid at the commingling manifold;
  run at the arrival pressure and again at the separator pressure.
- **Two zones in one well:** zone A + zone B at bottom-hole conditions; mark the
  zone with asphaltene history as `asphaltenic`.
- **Gas lift:** heavy oil + lift gas; set the path from the injection point
  down to wellhead pressure to see where along the tubing the onset is crossed.
- **Ranges of operating conditions:** wrap `screen_commingling` or
  `evaluator.evaluate` in the `neqsim-active-learning-surrogate` skill to learn
  where the stability boundary lies over blend ratio, pressure and temperature
  with a few dozen NeqSim runs.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `NeqSimUnavailableError` | `python -m pip install neqsim` and check that `java -version` works |
| `FluidSpecError: ... give kg/mol` | Divide pseudo-component molar mass by 1000 |
| Host alone is "HIGHLY_UNSTABLE" | The onset RI is probably a SARA estimate compared with a light live oil; use a measured onset or rely on the relative result |
| `evaluation-note` findings | A flash failed for that blend; check the composition, or narrow the pressure path |
| Minimum RI not near the bubble point | Increase `path_points` |
| Slow sweeps | Fewer `fractions`, fewer `path_points`, or skip the hydrate check (it is the slowest step) |
| WAT shows `-` with "no wax appearance above -60 C" | The blend has no wax formers in its C7+ cuts (typical for light condensate) |

**Why there is no tuned asphaltene onset model:** NeqSim's equation-of-state
asphaltene onset can be calibrated to the host oil. But on 3.29.0 every
calibration predicted that condensate stabilises the blend, which contradicts
laboratory evidence. The details are in SKILL.md, Limitations.

## Extending

`screen_commingling` takes any object with
`evaluate(blend, conditions) -> BlendProperties`. Wrap a tuned fluid model, a
different equation of state or laboratory data in your own evaluator; the
findings and report stay the same. `tests/test_screening.py` shows a minimal
analytic evaluator.

## Tests

```bash
python -m pytest skills/flow-assurance/neqsim-fluid-commingling-compatibility/tests
```

The screening logic is tested without Java through an analytic stand-in
evaluator. `tests/test_neqsim_integration.py` runs the real NeqSim backend and
is skipped when `neqsim` is not installed.

## Public Scope

Published correlations (Buckley et al. 1998 refractive-index method, de Boer et
al. 1995) and NeqSim thermodynamics only. Example compositions are synthetic.
Results are screening-level and need qualified review and laboratory
confirmation before design or operating decisions.
