---
name: neqsim-heat-exchanger-fouling-assessment
calculation_basis: "screening"
version: "0.1.0"
description: "Educational heat-exchanger performance monitoring and fouling assessment for plate and shell-and-tube coolers, condensers, and seawater or glycol cooling-medium loops: reduce an operating snapshot to an overall U-value, normalise it to design flow without scaling the deposit, separate fouling resistance from film resistance, rule out maldistribution, and convert the degradation into a capacity limitation and a cleaning interval. USE WHEN: a task asks whether a heat exchanger, cooler, condenser, or cooling-medium loop has fouled or degraded, by how much against its design U-value, what the degradation is costing in duty or capacity, or how often it must be cleaned."
last_verified: "2026-09-17"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Heat Exchanger Fouling and Performance Assessment

Use this skill to answer the recurring operational question "has this exchanger degraded, by how much, and what is it costing me?". It reduces one operating snapshot to an overall coefficient, normalises that coefficient to design flow correctly, splits the shortfall into fouling and film resistance, rules out area effects before blaming the deposit, and converts the answer into the operating limit a production engineer can act on.

## When to Use

- A cooler, condenser, or cooling-medium exchanger is suspected of fouling or of limiting capacity.
- A measured U-value must be compared against a vendor data-sheet design U at different flows.
- A cleaning interval, or the value of cleaning at all, has to be justified.
- A "the valve is wide open and it still will not cool" complaint needs an algebraic explanation.

## Inputs

- `area`: heat-transfer area in m2 (the credited area, see the maldistribution rule-out).
- `design_overall_coefficient`: data-sheet overall coefficient in W/(m2 K).
- `hot_mass_flow`, `hot_specific_heat`, `hot_inlet_temperature`, `hot_outlet_temperature`.
- `cold_mass_flow`, `cold_specific_heat`, `cold_inlet_temperature`, `cold_outlet_temperature`.
- `design_hot_mass_flow`, `design_cold_mass_flow`: data-sheet flows, for normalisation.
- `design_fouling_allowance`: fouling resistance already credited in the design U, m2 K/W.
- `wall_resistance`: wall and contact resistance in m2 K/W, default 0.
- `hot_film_coefficient`, `cold_film_coefficient`: design films in W/(m2 K); when absent they are split out of the design U using `hot_film_resistance_fraction`.
- `lmtd_correction_factor`: F factor for multi-pass or cross-flow, default 1.0.
- `duty_source`: `auto`, `hot`, `cold`, or `mean`.
- `installed_units`: number of parallel units sharing the area, for the maldistribution scan.

## Outputs

- `duty_kw`, `duty_hot_kw`, `duty_cold_kw`, `duty_imbalance_fraction`, `duty_source`.
- `lmtd_k`, `lmtd_reliable`, `effectiveness`, `ntu`, `capacity_ratio`.
- `u_measured_w_m2k` and `u_measured_basis` (`lmtd` or `effectiveness-ntu`).
- `u_normalised_to_design_flow_w_m2k` and `u_naive_one_sided_w_m2k`, with `naive_optimism_percentage_points`.
- `performance_ratio`: normalised U as a fraction of design U.
- `fouling_resistance_m2k_w`, `design_fouling_allowance_m2k_w`, `excess_fouling_resistance_m2k_w`.
- `condition`: `clean`, `within-allowance`, `fouled`, or `heavily-fouled`.
- `maldistribution_scan`: apparent U crediting N, N-1, N-2 ... units.
- `warnings`, `assumptions`.

Separate entry points return `CapacityLimitResult` and `CleaningIntervalResult`.

## Engineering Method

### 1. Duty reduction

Take the duty from the better-instrumented side and close the other side from the energy balance. State which side was measured and which was derived. The model reports both and the imbalance fraction; an imbalance above tolerance is a warning, not a silent average.

### 2. Flow normalisation, the two-sided form

A film coefficient scales roughly as $G^{0.8}$. A fouling deposit does not: it is a fixed conduction resistance, and pushing more flow through it does not make it thinner. Only the two convective films may be re-evaluated:

$$\frac{1}{U}=\underbrace{\frac{1}{h_1 (G_1/G_{1,d})^{0.8}}+\frac{1}{h_2 (G_2/G_{2,d})^{0.8}}+R_{wall}}_{\text{flow dependent}}+\underbrace{R_f}_{\text{flow independent}}$$

The common error is the one-sided form

$$U_{scaled}=\left(\frac{G_1}{G_{1,d}}\right)^{0.8} U$$

which multiplies the **whole** coefficient, fouling included. It is always optimistic, and the error can exceed the measurement uncertainty of the whole study. The model computes both and reports the gap in percentage points of design so the optimistic form cannot be used unnoticed.

### 3. Fouling resistance against design allowance

$$R_f = \frac{1}{U_{meas}} - R_{films} - R_{wall}$$

A vendor design U usually **already contains** a fouling allowance, so the measured shortfall is fouling *in excess of design margin*, not total fouling. Plate exchangers in seawater are typically designed with 0.2 to 0.5 x 10^-4 m2 K/W, far tighter than shell-and-tube, because of the high channel shear.

### 4. Effectiveness-NTU in the low-approach regime

When a terminal difference is small, the LMTD is sensitive to small temperature errors. Below a 3 K terminal difference the model switches the coefficient basis to effectiveness-NTU and says so:

$$\varepsilon = \frac{Q}{C_{min}(T_{h,in}-T_{c,in})},\qquad NTU = \frac{1}{1-C_r}\ln\frac{\varepsilon-1}{\varepsilon C_r-1},\qquad U=\frac{NTU\,C_{min}}{A}$$

### 5. The maldistribution rule-out

Apparent U is inversely proportional to the credited area. Before attributing everything to fouling, recompute U crediting N-1, N-2 ... effective units. If the shortfall disappears at N-1, the finding is an area or distribution problem (a blocked pass, a bypassing unit, a closed branch), not a film problem, and cleaning will not fix it.

### 6. Capacity limit

For a fixed-rate loop holding a supply set point:

$$Q_{max}=\frac{\varepsilon C_{min}(T_{set}-T_{cold,in})}{1-\varepsilon C_{min}/C_h}$$

which goes to zero as the cold inlet approaches the set point. This is the algebraic statement of "it is the temperature difference that runs out, not the valve".

### 7. Cleaning interval

Two fouling resistances and the time between them give a rate, hence the time to a limit. Frequency cannot fix a clean that is not *effective*: with a residual fraction left behind, the achievable cycle shortens, and once the residual exceeds the limit no interval recovers the duty and the cleaning method itself must change.

## Python Usage Pattern

```python
from heat_exchanger_fouling_assessment import HeatExchangerFoulingModel

model = HeatExchangerFoulingModel()
result = model.evaluate(
    area=420.0,
    design_overall_coefficient=1250.0,
    hot_mass_flow=180.0,
    hot_specific_heat=3.6,
    hot_inlet_temperature=338.15,
    hot_outlet_temperature=318.15,
    cold_mass_flow=260.0,
    cold_specific_heat=4.0,
    cold_inlet_temperature=288.15,
    cold_outlet_temperature=300.65,
    design_hot_mass_flow=220.0,
    design_cold_mass_flow=300.0,
    design_fouling_allowance=2.0e-4,
    installed_units=3,
)

print(result.condition, result.performance_ratio)
print(result.naive_optimism_percentage_points)

limit = model.capacity_limit(
    effectiveness=result.effectiveness,
    hot_capacity_rate=180.0 * 3.6,
    cold_capacity_rate=260.0 * 4.0,
    set_point_temperature=318.15,
    cold_inlet_temperature=298.15,
    required_duty=result.duty_kw,
)

cycle = model.cleaning_interval(
    fouling_resistance_start=2.0e-5,
    fouling_resistance_end=result.fouling_resistance_m2k_w,
    elapsed_days=180.0,
    fouling_resistance_limit=6.0e-4,
    cleaning_residual_fraction=0.4,
)
```

## Related NeqSim Functionality

For validated, design-grade calculations, redirect to NeqSim:

- `neqsim.process.equipment.heatexchanger.HeatExchanger` — rigorous two-stream exchanger with UA, duty, and outlet conditions on a real fluid.
- `neqsim.process.equipment.heatexchanger.Cooler` and `Heater` — single-stream duty with rigorous enthalpy.
- `neqsim.process.mechanicaldesign.heatexchanger.ThermalDesignCalculator` and `BellDelawareMethod` — thermal-hydraulic sizing and shell-side film coefficients.
- `neqsim.process.mechanicaldesign.heatexchanger.HeatExchangerDesignFeasibilityReport` — TEMA/ASME feasibility verdict and cost.
- `neqsim.process.equipment.heatexchanger.heatintegration.PinchAnalysis` — where the exchanger sits in the plant heat recovery.

Related community skills:

- `neqsim-control-authority-screening` — the other half of the "wide open and it still will not cool" complaint: a degraded exchanger consumes the cooling valve's margin until the loop has no authority left. Run both before blaming an external disturbance.
- `neqsim-root-cause-analysis` — the framework that consumes a fouling verdict as hypothesis evidence.

A NeqSim flash gives the specific heats and the property basis; take the cooling-medium heat capacity from the fluid model rather than a constant when the medium is water-rich or glycol-rich.

## Validation Checklist

- [ ] Both side duties are reported and the imbalance is stated, with the measured side named.
- [ ] The design U basis is quoted from a data sheet, with its fouling allowance and its design flows.
- [ ] Flow normalisation uses the two-sided form; the one-sided value, if quoted anywhere, is flagged as optimistic.
- [ ] The coefficient basis (LMTD or effectiveness-NTU) is stated, with the terminal differences.
- [ ] The maldistribution scan is run before fouling is asserted.
- [ ] The capacity statement names the constraint (temperature difference, flow, or area).
- [ ] Cleaning recommendations state the assumed cleaning effectiveness.
- [ ] Qualified human review is completed before operational or investment decisions.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Performance looks better than it is | One-sided flow normalisation scaling the whole U | Use the two-sided form; hold the fouling resistance out of the scaling |
| Fouling looks worse than it is | Design U compared without its own fouling allowance | Report fouling in excess of allowance, not total |
| U swings wildly between snapshots | LMTD near a close approach | Switch to effectiveness-NTU and check instrument accuracy |
| Everything blamed on fouling | Full installed area credited when a unit is bypassing | Run the N-1, N-2 credited-area scan first |
| Cleaning more often does not help | Cleaning leaves most of the deposit | Fix cleaning effectiveness before interval |
| Duty short but valve saturated | Temperature approach exhausted | Use the capacity-limit form; the constraint is not the valve |

## Limitations

- Screening reduction of a steady snapshot; no transient, no tube-by-tube, no vendor rating method.
- Counter-current terminal differences; multi-pass and cross-flow need an externally supplied F factor.
- Constant specific heats; no phase change, so condensers and reboilers need a latent-duty treatment.
- The film split from a design U is an assumption unless the data sheet gives both films.
- No proprietary vendor rating software, data sheets, or company specifications are included.

## References

- NeqSim repository: https://github.com/equinor/neqsim
- NeqSim Skills Guide: https://github.com/equinor/neqsim/blob/master/docs/integration/skills_guide.md
- TEMA Standards of the Tubular Exchanger Manufacturers Association — fouling resistance tables
- Kern, D. Q. — Process Heat Transfer (LMTD and fouling basis)
- Kays and London — Compact Heat Exchangers (effectiveness-NTU relations)
