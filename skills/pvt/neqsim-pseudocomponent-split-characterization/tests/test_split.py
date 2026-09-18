import math

import pytest

from pseudocomponent_split import (
    calculate_split_factor,
    delump_composition,
    gamma_mole_split,
)


def test_gamma_split_sums_to_z_plus():
    result = gamma_mole_split(
        z_plus=0.05,
        m_plus=220.0,
        boundaries=[90.0, 140.0, 200.0, 300.0, math.inf],
        alpha=1.0,
        eta=90.0,
    )
    assert len(result.mole_fractions) == 4
    assert sum(result.mole_fractions) == pytest.approx(0.05, rel=1e-9)
    # Molar masses increase across pseudocomponents.
    masses = result.molar_masses
    assert all(masses[i] < masses[i + 1] for i in range(len(masses) - 1))
    # Overall molar mass average is close to m_plus.
    avg = sum(z * m for z, m in zip(result.mole_fractions, masses)) / sum(result.mole_fractions)
    assert avg == pytest.approx(220.0, rel=0.15)


def test_alpha_narrows_distribution():
    boundaries = [90.0, 140.0, 200.0, 300.0, math.inf]
    low_alpha = gamma_mole_split(0.05, 220.0, boundaries, alpha=0.6, eta=90.0)
    high_alpha = gamma_mole_split(0.05, 220.0, boundaries, alpha=3.0, eta=90.0)
    # Higher alpha puts relatively less mole fraction in the heaviest tail.
    assert high_alpha.mole_fractions[-1] < low_alpha.mole_fractions[-1]


def test_split_factor_and_delump_roundtrip():
    full = [0.70, 0.10, 0.06, 0.04, 0.03, 0.07]
    scheme = [[0], [1, 2], [3, 4, 5]]
    sf = calculate_split_factor(full, scheme)
    # Factors within each lump sum to 1.
    assert sf.split_factors[1] + sf.split_factors[2] == pytest.approx(1.0)
    assert sf.split_factors[3] + sf.split_factors[4] + sf.split_factors[5] == pytest.approx(1.0)
    lumped = list(sf.lump_totals)
    reconstructed = delump_composition(lumped, sf.split_factors, scheme)
    for original, back in zip(full, reconstructed):
        assert back == pytest.approx(original, rel=1e-9)


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        gamma_mole_split(0.0, 220.0, [90.0, math.inf])
    with pytest.raises(ValueError):
        gamma_mole_split(0.05, 80.0, [90.0, math.inf], eta=90.0)
    with pytest.raises(ValueError):
        calculate_split_factor([0.1, 0.2], [[0], [0]])
    with pytest.raises(ValueError):
        delump_composition([0.5], [0.5, 0.5], [[0], [1]])
