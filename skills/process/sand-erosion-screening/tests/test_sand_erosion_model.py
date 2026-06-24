import pytest

from sand_erosion_screening import SandErosionModel


def test_sand_erosion_model_flags_high_with_heavy_sand() -> None:
    result = SandErosionModel().evaluate(
        fluid_velocity=12.0,
        mixture_density=120.0,
        pipe_diameter=0.1524,
        wall_thickness=12.7,
        sand_rate=50.0,
        corrosion_allowance=3.0,
        material_factor=1.0,
        design_life_years=25.0,
    )

    assert result.erosion_warning == "high"
    assert result.erosion_rate_mm_per_yr == pytest.approx(3.1, abs=0.05)
    assert result.remaining_life_years == pytest.approx(3.13, abs=0.05)
    assert result.remaining_wall_mm < 0.0
    assert result.assumptions


def test_sand_erosion_model_returns_ok_with_light_sand() -> None:
    result = SandErosionModel().evaluate(
        fluid_velocity=5.0,
        mixture_density=200.0,
        pipe_diameter=0.3,
        wall_thickness=15.0,
        sand_rate=2.0,
        corrosion_allowance=3.0,
        design_life_years=25.0,
    )

    assert result.erosion_warning == "ok"
    assert result.remaining_life_years > result.usable_wall_mm
    assert result.remaining_wall_mm > 0.0


def test_sand_erosion_model_flags_watch_on_remaining_life() -> None:
    result = SandErosionModel().evaluate(
        fluid_velocity=3.0,
        mixture_density=120.0,
        pipe_diameter=0.1,
        wall_thickness=15.0,
        sand_rate=74.0,
        corrosion_allowance=3.0,
        design_life_years=25.0,
    )

    assert result.erosion_warning == "watch"
    assert 12.5 <= result.remaining_life_years <= 25.0


def test_sand_erosion_model_handles_no_sand() -> None:
    result = SandErosionModel().evaluate(
        fluid_velocity=5.0,
        mixture_density=200.0,
        pipe_diameter=0.3,
        wall_thickness=15.0,
        sand_rate=0.0,
    )

    assert result.erosion_rate_mm_per_yr == 0.0
    assert result.remaining_life_years is None
    assert result.erosion_warning == "ok"


def test_sand_erosion_model_rejects_negative_density() -> None:
    with pytest.raises(ValueError, match="mixture_density"):
        SandErosionModel().evaluate(
            fluid_velocity=12.0,
            mixture_density=-120.0,
            pipe_diameter=0.1524,
            wall_thickness=12.7,
            sand_rate=50.0,
        )


def test_sand_erosion_model_rejects_corrosion_allowance_above_wall() -> None:
    with pytest.raises(ValueError, match="corrosion_allowance"):
        SandErosionModel().evaluate(
            fluid_velocity=12.0,
            mixture_density=120.0,
            pipe_diameter=0.1524,
            wall_thickness=3.0,
            sand_rate=50.0,
            corrosion_allowance=3.0,
        )
