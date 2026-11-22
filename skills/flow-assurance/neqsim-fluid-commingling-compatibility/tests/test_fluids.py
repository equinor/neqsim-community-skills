import math

import pytest
from fluid_commingling_compatibility import (
    FluidSpec,
    FluidSpecError,
    PseudoComponent,
    blend,
    mole_fraction_from_rates,
)


def oil():
    return FluidSpec(
        "host",
        {"methane": 20.0, "propane": 10.0, "water": 0.0},
        [PseudoComponent("C10", 70.0, 0.14, 0.80)],
        asphaltenic=True,
    )


def gas():
    return FluidSpec("new", {"methane": 90.0, "propane": 10.0})


def test_blend_is_normalised_and_sums_shared_components():
    mix = blend(oil(), gas(), 0.5)
    total = sum(mix.components.values()) + sum(
        p.mole_fraction for p in mix.pseudo_components
    )
    assert math.isclose(total, 1.0)
    assert math.isclose(mix.components["methane"], 0.5 * 0.2 + 0.5 * 0.9)
    assert [p.name for p in mix.pseudo_components] == ["C10host"]


def test_end_members_drop_the_other_fluid():
    assert blend(oil(), gas(), 1.0).pseudo_components == ()
    assert math.isclose(blend(oil(), gas(), 0.0).components["methane"], 0.2)


def test_pseudo_components_from_each_fluid_stay_separate():
    other = FluidSpec(
        "other", {"methane": 50.0}, [PseudoComponent("C10", 50.0, 0.13, 0.78)]
    )
    names = {p.name for p in blend(oil(), other, 0.5).pseudo_components}
    assert names == {"C10host", "C10other"}


def test_without_water_renormalises():
    wet = FluidSpec("wet", {"methane": 80.0, "water": 20.0})
    mix = blend(wet, gas(), 0.0)
    assert mix.has_water()
    dry = mix.without_water()
    assert not dry.has_water()
    assert math.isclose(sum(dry.components.values()), 1.0)


@pytest.mark.parametrize("fraction", [-0.1, 1.1])
def test_fraction_out_of_range(fraction):
    with pytest.raises(FluidSpecError):
        blend(oil(), gas(), fraction)


def test_invalid_specs():
    with pytest.raises(FluidSpecError):
        FluidSpec("bad label", {"methane": 1.0})
    with pytest.raises(FluidSpecError):
        FluidSpec("x", {"methane": -1.0})
    with pytest.raises(FluidSpecError):
        FluidSpec("x", {"methane": 0.0})
    with pytest.raises(FluidSpecError, match="kg/mol"):
        PseudoComponent("C10", 1.0, 140.0, 0.8)
    with pytest.raises(FluidSpecError):
        blend(oil(), oil(), 0.5)


def test_mole_fraction_from_rates():
    assert math.isclose(mole_fraction_from_rates(300.0, 100.0), 0.25)
    with pytest.raises(FluidSpecError):
        mole_fraction_from_rates(0.0, 0.0)
    with pytest.raises(FluidSpecError):
        mole_fraction_from_rates(-1.0, 1.0)


def test_mole_fraction_from_mass_rates():
    from fluid_commingling_compatibility import mole_fraction_from_mass_rates

    # 150 t/h of 0.170 kg/mol oil and 25 t/h of 0.029 kg/mol condensate
    x_b = mole_fraction_from_mass_rates(150.0, 0.170, 25.0, 0.029)
    assert math.isclose(x_b, (25 / 0.029) / (150 / 0.170 + 25 / 0.029))
    with pytest.raises(FluidSpecError):
        mole_fraction_from_mass_rates(1.0, 0.0, 1.0, 0.1)


def test_as_blend_is_the_fluid_alone():
    from fluid_commingling_compatibility import as_blend

    single = as_blend(oil())
    assert single.fraction_b == 0.0
    assert math.isclose(single.components["methane"], 0.2)
    assert [p.name for p in single.pseudo_components] == ["C10host"]
