"""Rev. 2 correlation: Python reference against values from the NeqSim class."""

import math

import pytest
from co2_corrosion_profile import (
    assess_rate,
    assess_rate_at_fugacity,
    fugacity_bar_reference,
    rate_mm_per_year_reference,
)

# (T C, fCO2 bar, pH, shear Pa, rate mm/y) from
# neqsim.process.corrosion.NorsokM506Rev2.rateMmPerYear (NeqSim master).
JAVA_RATES = [
    (5, 1.0, 4.0, 10, 0.48048),
    (15, 0.5, 5.0, 5, 0.8273043004791801),
    (20, 2.0, 4.2, 20, 8.09895060857745),
    (30, 1.0, 4.6, 19, 6.873575436000003),
    (40, 5.0, 5.5, 50, 15.280596832560528),
    (60, 2.8, 4.8, 14, 15.875612257296945),
    (70, 0.3, 6.2, 100, 0.8207530575041619),
    (80, 4.1, 3.9, 30, 32.29472437683087),
    (85, 1.0, 5.0, 2, 3.0392066219455507),
    (90, 8.0, 4.57, 25, 23.726829275684878),
    (100, 1.0, 5.7, 40, 0.8447164533118584),
    (120, 3.0, 4.29, 60, 18.51018824173154),
    (135, 0.2, 4.9, 150, 0.613399222286908),
    (150, 9.9, 6.5, 1, 0.47184631660765886),
    (150, 0.1, 3.5, 150, 1.5783066408771809),
]
# (T C, P bara, yCO2, fugacity bar) from NorsokM506Rev2.fugacityBar.
JAVA_FUGACITIES = [
    (5, 1, 0.5, 0.4977792040114911),
    (60, 100, 0.03, 2.3275023470726057),
    (150, 1000, 0.01, 8.868907811421126),
    (40, 300, 0.02, 2.7256872010784168),
]


@pytest.mark.parametrize("t, f, ph, tau, expected", JAVA_RATES)
def test_reference_rate_matches_neqsim_class(t, f, ph, tau, expected):
    assert rate_mm_per_year_reference(t, f, ph, tau) == pytest.approx(
        expected, rel=1e-12
    )


@pytest.mark.parametrize("t, p, y, expected", JAVA_FUGACITIES)
def test_reference_fugacity_matches_neqsim_class(t, p, y, expected):
    assert fugacity_bar_reference(t, p, y) == pytest.approx(expected, rel=1e-12)


def test_java_class_parity_when_installed():
    jpype = pytest.importorskip("jpype")
    pytest.importorskip("neqsim")
    from neqsim import jneqsim  # noqa: F401

    try:
        java = jpype.JClass("neqsim.process.corrosion.NorsokM506Rev2")
    except TypeError:  # JPype raises TypeError for an unknown class
        pytest.skip("installed NeqSim has no NorsokM506Rev2")
    for t, f, ph, tau, _ in JAVA_RATES:
        assert rate_mm_per_year_reference(t, f, ph, tau) == pytest.approx(
            float(java.rateMmPerYear(float(t), f, ph, float(tau))), rel=1e-12
        )


@pytest.mark.parametrize(
    "args",
    [
        (4.9, 1, 4, 10),
        (151, 1, 4, 10),
        (60, 0.09, 4, 10),
        (60, 11, 4, 10),
        (60, 1, 3.4, 10),
        (60, 1, 6.6, 10),
        (60, 1, 4, 0.5),
        (60, 1, 4, 151),
    ],
)
def test_reference_rejects_out_of_range(args):
    with pytest.raises(ValueError):
        rate_mm_per_year_reference(*args)


def test_assess_rate_flags_instead_of_raising():
    result = assess_rate(170.0, 100.0, 0.03, 3.2, 300.0)
    assert (
        result.temperature_c == 150.0
        and result.ph == 3.5
        and result.wall_shear_pa == 150.0
    )
    assert len(result.flags) == 3
    low = assess_rate(40.0, 5.0, 0.001, 4.5, 10.0)
    assert low.upper_bound_only
    assert low.rate_mm_y == pytest.approx(
        rate_mm_per_year_reference(40.0, 0.1, 4.5, 10.0)
    )
    high = assess_rate_at_fugacity(40.0, 25.0, 4.5, 10.0)
    assert any("above range" in f for f in high.flags)
    inside = assess_rate(60.0, 100.0, 0.03, 4.8, 14.0)
    assert inside.flags == []
    assert math.isclose(inside.co2_fugacity_bar, 2.3275023470726057, rel_tol=1e-9)
