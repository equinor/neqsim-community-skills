import pytest

matplotlib = pytest.importorskip("matplotlib")

matplotlib.use("Agg")

from subsea_layout_geometry import plot_subsea_layout


def _layout():
    return [
        {"name": "HOST", "x": 0.0, "y": 0.0, "water_depth_m": 320.0, "kind": "host"},
        {"name": "M1", "x": 6000.0, "y": 1500.0, "water_depth_m": 335.0, "kind": "manifold"},
        {"name": "W1", "x": 8500.0, "y": 3200.0, "water_depth_m": 340.0, "kind": "well"},
    ]


def test_plot_returns_figure_with_axes():
    fig = plot_subsea_layout(_layout(), host_name="HOST")
    assert fig is not None
    assert len(fig.axes) == 1


def test_plot_default_draws_star_tieback_lines():
    fig = plot_subsea_layout(_layout(), host_name="HOST")
    ax = fig.axes[0]
    # Two non-host nodes -> two dashed tie-back lines.
    line_styles = [line.get_linestyle() for line in ax.get_lines()]
    assert line_styles.count("--") == 2


def test_plot_with_flowlines_draws_solid_segments():
    fig = plot_subsea_layout(
        _layout(),
        host_name="HOST",
        flowlines=[("HOST", "M1"), ("M1", "W1")],
    )
    ax = fig.axes[0]
    solid = [line for line in ax.get_lines() if line.get_linestyle() == "-"]
    assert len(solid) == 2


def test_plot_saves_png(tmp_path):
    out = tmp_path / "layout.png"
    plot_subsea_layout(_layout(), host_name="HOST", save_path=out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_plot_missing_host_raises():
    with pytest.raises(ValueError):
        plot_subsea_layout(_layout(), host_name="NOPE")


def test_plot_unknown_flowline_endpoint_raises():
    with pytest.raises(ValueError):
        plot_subsea_layout(
            _layout(), host_name="HOST", flowlines=[("HOST", "GHOST")]
        )


def test_plot_geographic_uses_degree_axes():
    nodes = [
        {"name": "HOST", "x": 2.0, "y": 60.0, "water_depth_m": 120.0, "kind": "host"},
        {"name": "W1", "x": 2.5, "y": 60.1, "water_depth_m": 130.0, "kind": "well"},
    ]
    fig = plot_subsea_layout(nodes, host_name="HOST", coordinate_system="geographic")
    ax = fig.axes[0]
    assert "deg" in ax.get_xlabel().lower()
