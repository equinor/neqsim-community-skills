---
name: neqsim-adsorbent-capillary-condensation-screening
calculation_basis: "screening"
version: "0.1.0"
description: "Educational screening of the maximum allowable condensable-contaminant concentration in a gas feeding a fixed adsorbent bed (mercury guard bed, molecular sieve, catalyst guard) before capillary condensation floods the sorbent pores. USE WHEN: a task needs a public, screening-level contaminant ppmv limit from the Kelvin equation and a sorbent pore radius, or needs to explain why a bed degrades with no free liquid at the inlet."
last_verified: "2026-09-08"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Adsorbent Capillary Condensation Screening

Use this skill to turn a sorbent pore size into a **contaminant concentration
limit** for the gas entering a fixed bed. It answers the question "how much
methanol / water / heavy hydrocarbon can this feed carry before the bed stops
working", which is a different and much tighter question than "when does a bulk
liquid drop out".

## When to Use

- A mercury guard bed, molecular sieve, or catalyst guard bed is degrading and
  there is **no free liquid** at the inlet.
- A feed specification has to be written for a condensable polar contaminant
  (methanol, water, glycol, heavy ends) upstream of an adsorbent.
- An agent needs to explain why a "no free liquids" clause is not a sufficient
  specification.

## The physics in one line

A concave meniscus in a pore condenses vapour **below** bulk saturation:

$$\ln a_c = -\frac{G\,\gamma V_m\cos\theta}{r R T}$$

with $G = 2$ for cylindrical pores and $G = 1$ for slit pores. The bed limit is
then $y_{max} = a_c \cdot y_{sat}$, where $y_{sat}$ is the bulk saturation mole
fraction of the contaminant in the gas.

For methanol at 20 °C, $2\gamma V_m/RT = 0.75$ nm, so a 1.5 nm pore floods at
60 % of bulk saturation and a 6 nm pore at 88 %.

## Inputs

- `temperature`: gas temperature in kelvin.
- `surface_tension`: contaminant liquid surface tension in N/m.
- `molar_volume`: contaminant liquid molar volume in m³/mol.
- `pore_radius_nm`: representative sorbent pore radius in nm.
- `saturation_mole_fraction`: bulk saturation mole fraction $y_{sat}$ of the
  contaminant in the gas at bed T and P. **Obtain this from a real equation of
  state, not from $P^{sat}/P$** — see the coupling note below.
- `contaminant_mole_fraction`: optional current concentration, for a margin check.
- `contact_angle_deg`: default 0 (perfect wetting, conservative).
- `geometry_factor`: 2.0 cylindrical (default), 1.0 slit.

## Outputs

- `kelvin_length_nm`: $G\gamma V_m\cos\theta / RT$ in nm.
- `onset_relative_saturation`: $a_c$.
- `max_mole_fraction` / `max_ppmv`: the contaminant limit.
- `relative_saturation`, `margin_ratio`: only when a current concentration is given.
- `kelvin_valid`: false below ~2 nm radius, where Kelvin is **non-conservative**.
- `warning`: `ok`, `watch`, or `condensation-expected`.
- `assumptions`: the public assumptions applied.

## Engineering Method

`CapillaryCondensationScreeningModel.evaluate()` applies the open Kelvin
equation only, in four steps:

1. Kelvin length `L = G * gamma * Vm * cos(theta) / (R T)`, reported in nm.
2. Onset relative saturation `a_c = exp(-L / r)` for pore radius `r`.
3. Contaminant limit `y_max = a_c * y_sat`, also reported as ppmv. `y_sat` is
   supplied by the caller and is **never** derived inside the model.
4. If a current concentration is given, `relative_saturation = y / y_sat` and
   `margin_ratio = y / y_max` set the warning: `ok`, `watch` above
   `watch_margin` (default 0.5), `condensation-expected` at or above 1.0.

`kelvin_valid` is false below `KELVIN_VALIDITY_RADIUS_NM` (2 nm), where the
continuum meniscus breaks down and the Kelvin limit is an upper bound only; use
`micropore_filling_fraction()` (Dubinin-Radushkevich volume filling) there.

This is educational, screening-only logic for a **single** condensable. It does
not flash the mixture, does not model pore size distribution, and is not a
substitute for the validated NeqSim route described below.

## Critical coupling — get `y_sat` from an EOS, on a fugacity basis

The screening result is only as good as `y_sat`. Two traps:

1. **Do not use $y_{sat} = P^{sat}/P$.** At elevated pressure a real gas dissolves
   considerably more polar contaminant than the ideal ratio suggests. For methanol
   in rich natural gas the enhancement factor is about 1.5 at 40 bara, 1.9 at
   70 bara and 2.9 at 100 bara. Using the ideal ratio makes the limit roughly
   two to three times tighter than it needs to be.
2. **Use an associating EOS for associating contaminants.** Methanol, water and
   glycols need CPA (`SystemSrkCPAstatoil`, `setMixingRule(10)`). Corresponding-
   states vapour-pressure correlations such as Lee-Kesler are unusable for these
   components — for methanol at 5–35 °C Lee-Kesler over-predicts $P^{sat}$ by
   roughly an order of magnitude.

Get `y_sat` by flashing the gas against an excess of the pure contaminant liquid
and reading the gas-phase mole fraction:

```python
sys = SystemSrkCPAstatoil(273.15 + 20.0, 70.0)
for name, frac in rich_gas.items():
    sys.addComponent(name, frac)
sys.addComponent("methanol", 5.0)          # excess liquid
sys.setMixingRule(10)
sys.setMultiPhaseCheck(True)
ThermodynamicOperations(sys).TPflash()
sys.initProperties()
y_sat = sys.getPhase("gas").getComponent("methanol").getx()
```

## Python Usage Pattern

```python
from adsorbent_capillary_condensation_screening import CapillaryCondensationScreeningModel

model = CapillaryCondensationScreeningModel()
result = model.evaluate(
    temperature=293.15,
    surface_tension=0.0225,        # methanol
    molar_volume=40.7e-6,
    pore_radius_nm=6.0,            # mesoporous alumina-supported sorbent
    saturation_mole_fraction=3.55e-3,   # from CPA, not Psat/P
    contaminant_mole_fraction=500e-6,
)

print(result.max_ppmv, result.warning)
```

## Micropores — where this screening stops

Below about 2 nm radius the meniscus is only a few molecules across and the
continuum Kelvin equation over-predicts the onset. Real micropores fill
progressively from $a \sim 0.01$–0.1 by volume filling (Dubinin–Radushkevich):

$$W = W_0\exp\left[-\left(\frac{RT\ln(1/a)}{\beta E_0}\right)^2\right]$$

`micropore_filling_fraction()` provides this estimate. For a microporous sorbent
(activated carbon, molecular sieve) treat the Kelvin number as an **upper bound**
and expect the true tolerance to be lower.

## Never specify two condensables independently

Methanol and water are fully miscible and **co-condense**. A pore fills when their
**combined** activity reaches the Kelvin onset, so a gas that is individually
below saturation in both can still flood the sorbent. Screening them separately
is the most common way to get this wrong.

Use the activity sum:

$$\sum_i \frac{y_i}{y_{sat,i}} \geq a_c(r) \quad\Rightarrow\quad \text{pore fills}$$

so the allowance for the second contaminant is what the first leaves behind:

```python
a_water = y_water / y_sat_water
a_methanol_allowed = onset - a_water          # onset from the Kelvin equation
methanol_limit = max(0.0, a_methanol_allowed) * y_sat_methanol
```

A worked case at 115 bara and 1 °C over a 6 nm sorbent, where the gas holds only
110 ppmv water in total:

| Water | Methanol limit |
|---|---|
| 0 ppmv | 1 200 ppmv |
| 25 ppmv | 890 ppmv |
| 50 ppmv | 570 ppmv |
| 100 ppmv | **0 — water alone fills the pore** |

Cross-check the result with
`ThermodynamicOperations.capillaryDewPointTemperatureFlash(poreRadiusM)` on the
real multicomponent mixture: condensation is expected when the capillary dew
point rises above the bed temperature. In the case above the two methods agree,
and the capillary dew point sits 1.2–1.4 °C **above** the bulk dew point — which
is precisely the margin a "no free liquids" specification fails to capture.

## Rigorous route in NeqSim

For a multicomponent gas where several contaminants can co-condense (methanol
**and** water is the usual case), do not add limits component by component. Use:

- `neqsim.physicalproperties.interfaceproperties.solidadsorption.CapillaryCondensationModel`
  with `setSaturationMoleFraction(component, ySat)` and
  `setRelativeSaturationBasis(SATURATION_MOLE_FRACTION)` — the exact,
  flash-grounded basis — then `getMaxAllowableMoleFraction(component, poreRadiusNm, phase)`.
  The `FUGACITY` basis is also available but references a hypothetical *pure*
  liquid, so it carries a bias of about 14 % at 70 bara and can report a limit
  above bulk saturation unless the saturation mole fraction is supplied to cap it;
- `CapillaryCondensationModel.microporeFillingFraction(a, T, betaE0, beta)` for
  the micropore regime, and the constant `KELVIN_VALIDITY_RADIUS_NM`;
- `neqsim.process.equipment.adsorber.MercuryRemovalBed.assessContaminant(name, ySat)`
  to screen a contaminant against a guard bed directly. It picks Kelvin or
  micropore filling from the sorbent pore radius, returns the relative saturation,
  the Kelvin onset, the ppmv limit and the blocked pore fraction, and
  `applyContaminantDegradation(...)` folds that blocked fraction into the bed's
  capacity instead of a hand-picked degradation factor;
- `ThermodynamicOperations.capillaryDewPointTemperatureFlash(poreRadiusM)` to get
  the pore dew-point temperature of the real mixture directly.

## Validation Checklist

- [ ] `y_sat` came from an EOS flash against excess contaminant liquid, not from
      `P_sat / P`, and CPA was used for an associating contaminant.
- [ ] Temperature, surface tension, molar volume and pore radius are positive and
      `0 < y_sat <= 1`.
- [ ] The pore radius is at or above 2 nm, or `kelvin_valid` being false is
      reported and the micropore route is used.
- [ ] Every condensable that can co-condense is included through the activity
      sum, not screened component by component.
- [ ] The result is described as an educational screening indicator, with real
      assessment redirected to the NeqSim classes above.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Limit two to three times too tight | `y_sat` taken as `P_sat / P` | Flash against excess liquid on a real EOS |
| `P_sat` off by an order of magnitude | Lee-Kesler used for methanol/water/glycol | Use CPA (`SystemSrkCPAstatoil`, `setMixingRule(10)`) |
| Bed floods although both contaminants pass | Condensables screened independently | Use the activity sum `sum(y_i / y_sat,i) >= a_c` |
| Limit looks generous on a molecular sieve | Micropores below 2 nm, `kelvin_valid` false | Treat as an upper bound and use `micropore_filling_fraction()` |
| Onset near 1.0 for every pore | `pore_radius_nm` entered in µm or Å | Enter the representative pore radius in nm |

## Limitations

- Screening only. Contact angle, pore geometry and the pore size distribution are
  assumptions unless a vendor BJH/DFT distribution is supplied.
- Perfect wetting ($\cos\theta = 1$) is assumed by default; a partially wetted or
  hydrophobised surface tolerates more.
- Single-contaminant. Mixed condensates (methanol + water) condense earlier than
  either component alone.
- Says nothing about chemical degradation routes (support hydration, sulphur
  mobilisation, pellet attrition from slugs).

## References

- Thomson, W. (Lord Kelvin), On the Equilibrium of Vapour at a Curved Surface of
  Liquid, Philosophical Magazine, 42 (1871) 448-452.
- Gregg, S. J., and Sing, K. S. W., Adsorption, Surface Area and Porosity, 2nd
  Edition, Academic Press, 1982 — Kelvin equation validity and the micropore limit.
- Dubinin, M. M., and Radushkevich, L. V., Equation of the Characteristic Curve
  of Activated Charcoal, Proc. Acad. Sci. USSR, 55 (1947) 331-333.
- Kontogeorgis, G. M., et al., An Equation of State for Associating Fluids (CPA),
  Ind. Eng. Chem. Res., 35 (1996) 4310-4318.
- NeqSim repository: https://github.com/equinor/neqsim

## Related skills

- `neqsim-water-dewpoint-dehydration-screening` — sets the water content that
  feeds the co-condensation case.
- `neqsim-teg-dehydration-modeling` — upstream dehydration performance.
- `neqsim-flow-assurance` — methanol injection and inhibitor carry-over sources.
