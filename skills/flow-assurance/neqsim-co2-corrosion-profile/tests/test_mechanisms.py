import math

import pytest
from co2_corrosion_profile import (
    condensation_rates,
    glycol_factor,
    sour_regime,
    tlc_risk,
)


@pytest.mark.parametrize(
    "w, expected",
    [
        (0.0, 1.0),
        (0.3, 0.7),
        (0.5, 0.5 * 0.25 + 0.05),
        (0.6, 0.5 * 0.16 + 0.05),
        (0.85, 0.05),
    ],
)
def test_glycol_factor(w, expected):
    assert glycol_factor(w) == pytest.approx(expected)


def test_condensation_rate_from_vapour_drop():
    # 36 t/h, 0.254 m pipe; vapour falls from 0.002 to 0.001 kg/kg over 1 km
    rates = condensation_rates([0.0, 1000.0], [0.002, 0.001], 36000.0, 0.254)
    expected = 0.001 * 10.0 * 1000.0 / (math.pi * 0.254 * 1000.0)
    assert rates[0] == 0.0
    assert rates[1] == pytest.approx(expected)
    assert condensation_rates([0.0, 1.0], [0.001, 0.002], 100.0, 0.1)[1] == 0.0
    with pytest.raises(ValueError):
        condensation_rates([0.0], [0.0], 0.0, 0.1)


@pytest.mark.parametrize(
    "rate, regime, expected",
    [
        (0.3, "SEGREGATED", "high"),
        (0.2, None, "moderate"),
        (0.1, "SEGREGATED", "low"),
        (0.5, "DISTRIBUTED", "low"),
        (0.0, None, None),
        (math.nan, None, None),
    ],
)
def test_tlc_risk(rate, regime, expected):
    assert tlc_risk(rate, regime) == expected


@pytest.mark.parametrize(
    "pco2, ph2s, expected",
    [
        (3.0, 0.002, "sweet"),
        (3.0, 0.005, "sweet"),
        (3.0, 0.05, "mixed"),
        (1.0, 0.1, "sour"),
    ],
)
def test_sour_regime(pco2, ph2s, expected):
    assert sour_regime(pco2, ph2s) == expected
