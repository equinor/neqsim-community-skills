import os

import pytest

from surf_field_layout_design import design_surf_layout, plot_layout_map

matplotlib = pytest.importorskip("matplotlib")


@pytest.fixture()
def layout():
    return design_surf_layout(
        field_name="Test field",
        centre_latitude_deg=73.375,
        centre_longitude_deg=25.0,
        water_depth_m=400.0,
        producers=8,
        water_injectors=6,
        gas_injectors=2,
        design_liquid_rate_m3_per_s=0.33,
    )


def test_map_is_written(tmp_path, layout):
    path = str(tmp_path / "layout.png")
    plot_layout_map(layout, path, attribution=["EMODnet Bathymetry Consortium"])
    assert os.path.exists(path)
    assert os.path.getsize(path) > 5000


def test_map_accepts_a_custom_title(tmp_path, layout):
    path = str(tmp_path / "titled.png")
    plot_layout_map(layout, path, title="Custom title")
    assert os.path.exists(path)
