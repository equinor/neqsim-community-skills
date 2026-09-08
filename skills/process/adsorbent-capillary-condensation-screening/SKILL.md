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

## Rigorous route in NeqSim

For a multicomponent gas where several contaminants can co-condense (methanol
**and** water is the usual case), do not add limits component by component. Use:

- `neqsim.physicalproperties.interfaceproperties.solidadsorption.CapillaryCondensationModel`
  with `setRelativeSaturationBasis(FUGACITY)` and
  `getMaxAllowableMoleFraction(component, poreRadiusNm, phase)`, iterated to a
  fixed point because an associating contaminant's fugacity coefficient depends
  on its own concentration; or
- `ThermodynamicOperations.capillaryDewPointTemperatureFlash(poreRadiusM)` to get
  the pore dew-point temperature of the real mixture directly.

## Limitations

- Screening only. Contact angle, pore geometry and the pore size distribution are
  assumptions unless a vendor BJH/DFT distribution is supplied.
- Perfect wetting ($\cos\theta = 1$) is assumed by default; a partially wetted or
  hydrophobised surface tolerates more.
- Single-contaminant. Mixed condensates (methanol + water) condense earlier than
  either component alone.
- Says nothing about chemical degradation routes (support hydration, sulphur
  mobilisation, pellet attrition from slugs).

## Related skills

- `neqsim-water-dewpoint-dehydration-screening` — sets the water content that
  feeds the co-condensation case.
- `neqsim-teg-dehydration-modeling` — upstream dehydration performance.
- `neqsim-flow-assurance` — methanol injection and inhibitor carry-over sources.
