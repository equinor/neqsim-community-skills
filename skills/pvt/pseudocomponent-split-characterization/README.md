# Pseudocomponent Split-Factor Characterization (community skill)

Public, dependency-free building blocks for plus-fraction (C7+) characterization
driven by a single controllable split factor:

- **Whitson gamma molar split** of a plus fraction (`gamma_mole_split`).
- **Lumping split factor** from a detailed reference fluid (`calculate_split_factor`).
- **Delumping** reconstruction of a detailed composition (`delump_composition`).

See [SKILL.md](SKILL.md) for the engineering method, NeqSim mapping, and usage.

## Install and test

```bash
pip install -e .[test]
pytest
```

## Scope

Screening-level and reproducible. For design-grade characterization use the
NeqSim `neqsim.thermo.characterization` Java classes (`PlusFractionModel`,
`PlusCharacterize`, `TBPCharacterize`, `LumpingModel`, `Recombine`).
Results require qualified PVT review before engineering use.
