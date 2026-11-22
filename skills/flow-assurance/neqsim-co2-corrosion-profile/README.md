# CO2 Corrosion Profile

Internal CO2 corrosion along a flowline, station by station, with NeqSim. It
finds where free water exists, how fast carbon steel corrodes there (NORSOK
M-506 Rev. 2), whether the corrosion allowance lasts the design life, and what
NeqSim's materials review says about the line.

| You get | From |
| --- | --- |
| Pressure, temperature and flow along the line | NeqSim Beggs and Brill pipe model, or your own profile |
| Free water and gas CO2/H2S per station | NeqSim SRK-CPA flash |
| In-situ pH | NORSOK M-506 pH model in NeqSim (CO2, bicarbonate, salinity) |
| Bare-steel rate | NORSOK M-506 Rev. 2 (NeqSim `NorsokM506Rev2`, or a tested port on NeqSim 3.29) |
| Design rate, wall loss, allowance check | Your inhibitor availability and design life |
| CO2-line free water and impurities | NeqSim `DensePhaseCO2Corrosion` |
| Material recommendation and damage mechanisms | NeqSim `MaterialsReviewEngine` and NORSOK M-001 |

Method, limitations and references are in [SKILL.md](SKILL.md).

## Install

```bash
neqsim skill install neqsim-co2-corrosion-profile --vscode
```

or from a checkout:

```bash
python -m pip install -e "skills/flow-assurance/neqsim-co2-corrosion-profile[neqsim]"
```

## Quick Start

```bash
python skills/flow-assurance/neqsim-co2-corrosion-profile/examples/wet_gas_flowline.py
```

A synthetic 12 km, 10-inch subsea line with wet gas (3 mol % CO2, saline
water) cooling from 85 C towards 4 C seawater. In about 6 s it shows free water
along the whole line, bare rates up to 22 mm/year, and 57 mm of wall loss over
25 years even with 90 % inhibitor availability. That leads to a 22Cr duplex
recommendation.

## How to Use

### 1. Describe the stream, including water

```python
from co2_corrosion_profile import CorrosionFluid, PseudoCut

fluid = CorrosionFluid(
    components={"methane": 82.0, "ethane": 6.0, "propane": 3.0, "CO2": 3.0,
                "H2S": 0.0005, "water": 2.0},
    pseudo_components=[PseudoCut("C7", 0.8, 0.100, 0.75)],   # kg/mol, g/cm3
    chloride_mg_l=20000.0,      # produced water; 0 for condensed water
    bicarbonate_mg_l=0.0,       # formation-water buffering raises pH
)
```

Water must be in the composition. The flash decides where it drops out, so
give the total water carried, not only the free water at the inlet.

### 2. Get a profile

From NeqSim:

```python
from co2_corrosion_profile import PipelineSpec, neqsim_pipeline_profile

pipe = PipelineSpec(
    length_m=12000.0, inner_diameter_m=0.254, mass_flow_kg_h=90000.0,
    inlet_pressure_bara=110.0, inlet_temperature_c=85.0,
    segments=12,                  # stations = segments + inlet
    elevation_change_m=-50.0,
    ambient_temperature_c=4.0, overall_u_w_m2k=15.0,   # omit both: adiabatic
)
profile = neqsim_pipeline_profile(fluid, pipe)
```

Or from your own simulation (OLGA, LedaFlow, field data):

```python
from co2_corrosion_profile import ProfilePoint

profile = [
    ProfilePoint(0.0,    110.0, 85.0, mixture_velocity_m_s=6.1,
                 mixture_density_kg_m3=95.0, mixture_viscosity_pa_s=1.6e-5),
    ProfilePoint(6000.0, 104.0, 36.0, wall_shear_pa=12.0),   # or shear directly
    ...
]
```

### 3. State the design basis

```python
from co2_corrosion_profile import DesignBasis

basis = DesignBasis(
    design_life_years=25.0,
    corrosion_allowance_mm=6.0,
    inhibitor_availability=0.9,   # 0 = no credit for inhibition
    inhibited_rate_mm_y=0.1,      # rate while inhibited
    inner_diameter_m=0.254,       # for shear and the materials review
    existing_material="Carbon Steel",
)
```

Inhibitor availability and the inhibited rate are design assumptions, often
set by company practice. Report where they come from. The design rate is
`A x min(0.1, CR) + (1 - A) x CR`.

### 4. Run and read the report

```python
from co2_corrosion_profile import assess_corrosion_profile

report = assess_corrosion_profile(fluid, profile, basis)
print(report.to_markdown())
report.summary          # max design rate and where, wall loss, allowance needed
report.findings         # severity, code, message
report.m001_recommendation   # material and allowance from the Rev. 2 rate
report.materials_review      # full NeqSim MaterialsReviewEngine report
report.to_dict()             # JSON-safe for notebooks and task reports
```

What to do with each finding:

| Finding | Meaning | Next step |
| --- | --- | --- |
| `allowance-exceeded` (high) | Wall loss over the design life exceeds the allowance | Higher inhibitor availability (with justification), larger allowance, or CRA; see `m001_recommendation` |
| `allowance-margin` (warning) | More than 80 % of the allowance is used | Check sensitivity to availability and water chemistry |
| `water-dropout` (info) | Free water starts partway along the line | Upstream section can stay dry; check start-up and upsets |
| `dry-line` (info) | No free water anywhere | Confirm water dew-point margin and upset cases |
| `outside-correlation` (warning) | T, pH, fugacity or shear outside M-506 ranges | Read the station flags; the nearest bound was used |
| `low-fugacity` (info) | fCO2 < 0.1 bar | Rates are upper bounds |
| `sour-service` (warning) | H2S partial pressure at or above 0.3 kPa with water; ISO 15156-2 region given | Sour-service qualification of the steel (hardness, HIC) |
| `h2s-regime` (warning/high) | pCO2/pH2S 20-500 (mixed) or below 20 (sour) | Below 20 the M-506 rate does not apply; use a sour-corrosion assessment |
| `top-of-line-corrosion` (high/warning) | Water condenses faster than 0.25 (0.15) g/m2/s in stratified or unknown flow | Insulation, condensation control, TLC-specific study; inhibitor injection does not protect the top |
| `tlc-not-assessed` (info) | No mass flow given | Set `DesignBasis.mass_flow_kg_h` |
| `glycol-correction` (info) | MEG/DEG/TEG in the water reduces the rate | Check the glycol is present at those stations in operation |
| `materials-review-fail` (warning) | NeqSim materials review flags a mechanism | Read the mechanism; its CO2 rate is NeqSim's legacy model |
| `dense-phase-*` | CO2 line results | Water specification, dehydration and impurity limits |

### 5. Glycol, top-of-line and H2S

```python
fluid = CorrosionFluid(
    {"methane": 85.0, "CO2": 3.0, "H2S": 0.01, "water": 4.0, "MEG": 1.5},
)
basis = DesignBasis(corrosion_allowance_mm=3.0, inner_diameter_m=0.254,
                    mass_flow_kg_h=90000.0)     # enables the top-of-line screen
report = assess_corrosion_profile(fluid, profile, basis)
for s in report.stations:
    print(s.distance_m, s.glycol_factor, s.condensation_g_m2_s, s.tlc_risk,
          s.sour_regime, s.iso15156)
```

- **Glycol** comes from the composition: the flash puts it in the water
  phase. Its weight fraction there sets the rate factor (40 wt % MEG gives
  0.6). Turn it off with `apply_glycol_correction=False`.
- **Top-of-line corrosion** needs the mass flow. The condensation rate is
  computed from the water vapour lost between stations. Above 0.25 g/m2/s in
  stratified flow is high risk. Beggs and Brill profiles carry the flow regime
  ("SEGREGATED" = stratified); for your own profile set
  `ProfilePoint.flow_regime`, or it is treated as stratified.
- **H2S** at or above 0.3 kPa gives the ISO 15156-2 region from NeqSim. The
  pCO2/pH2S ratio tells you whether the M-506 rate still applies.

### 6. Use a measured pH or a CO2 line

```python
from co2_corrosion_profile import NeqSimChemistry

report = assess_corrosion_profile(fluid, profile, basis,
                                  chemistry=NeqSimChemistry(ph=5.6))  # measured
```

Streams with more than 50 mol % CO2 (dry basis) switch automatically to the
dense-phase assessment. Add impurities with
`dense_phase_impurities_ppmv={"O2": 20, "SO2": 10, "NOx": 5}`.

## Typical Studies

- **Tie-in to an existing carbon-steel line:** run the host stream, then the
  mixed stream (see `neqsim-fluid-commingling-compatibility`), and compare the
  allowance needed against the allowance left.
- **Carbon steel or CRA:** run with `inhibitor_availability=0` and with the
  availability you can justify. If neither fits the allowance, the M-001
  recommendation shows the CRA option.
- **Uncertain conditions:** wrap `assess_corrosion_profile` in
  `neqsim-active-learning-surrogate` to learn the inhibitor availability or
  water cut at which the allowance is exceeded.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `NeqSimUnavailableError` | `python -m pip install neqsim`; check `java -version` |
| `add water to the composition` | Include the water carried by the stream |
| `rate_engine` says "Python port" | Normal on NeqSim 3.29; newer NeqSim uses the Java class automatically |
| Station has no flow data | Give velocity/density/viscosity or `wall_shear_pa`, or set `default_wall_shear_pa` |
| Slow runs | Fewer `segments`; the first station includes JVM warm-up |

## Tests

```bash
python -m pytest skills/flow-assurance/neqsim-co2-corrosion-profile/tests
```

- `test_m506.py` checks the Rev. 2 reference port against 19 values from NeqSim
  `NorsokM506Rev2`. It also compares the two directly when the installed
  NeqSim has the class.
- `test_study.py` checks the profile logic with an analytic chemistry stand-in
  (no Java).
- `test_neqsim_integration.py` runs the NeqSim pipeline, chemistry, dense phase
  and materials review. It is skipped without `neqsim`.

## Public Scope

Published NORSOK M-506 Rev. 2 and M-001 methods as implemented in NeqSim, with
synthetic examples. Screening-level: not a corrosion design basis or materials
selection report. Results need qualified corrosion and materials review.
