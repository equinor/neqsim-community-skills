"""Tests for the presentation illustration: geometry, facts panel, and rendering."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from math import cos, radians, sin

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from surf_field_layout_design import (  # noqa: E402
    Annotation,
    Horizon,
    KeyFact,
    Seabed,
    build_well_paths,
    design_surf_layout,
    horizon_from_model_grid,
    render_field_illustration,
)


def _layout():
    return design_surf_layout(
        field_name="Testfield",
        centre_latitude_deg=61.22,
        centre_longitude_deg=2.35,
        water_depth_m=260.0,
        producers=4,
        water_injectors=2,
        slots_per_template=4,
        reservoir_length_km=5.0,
        reservoir_width_km=2.5,
        field_axis_bearing_deg=78.0,
        host_offset_km=4.0,
        design_liquid_rate_m3_per_s=0.09,
        design_water_injection_rate_m3_per_s=0.05,
    )


class HorizonFromModelGridTest(unittest.TestCase):
    def test_shape_and_values_are_preserved(self):
        nx, ny = 6, 4
        values = [float(i + 10 * j) for j in range(ny) for i in range(nx)]
        horizon = horizon_from_model_grid(
            values, nx=nx, ny=ny, dx_m=100.0, dy_m=100.0,
            origin_east_m=0.0, origin_north_m=0.0, axis_bearing_deg=0.0)
        self.assertEqual(len(horizon.depth_m_tvdmsl), ny)
        self.assertEqual(len(horizon.depth_m_tvdmsl[0]), nx)
        self.assertAlmostEqual(float(horizon.depth_m_tvdmsl[0][0]), 0.0)
        self.assertAlmostEqual(float(horizon.depth_m_tvdmsl[3][5]), 35.0)

    def test_rejects_a_grid_that_does_not_match_nx_ny(self):
        with self.assertRaises(ValueError):
            horizon_from_model_grid([1.0, 2.0], nx=3, ny=3, dx_m=1.0, dy_m=1.0,
                                    origin_east_m=0.0, origin_north_m=0.0,
                                    axis_bearing_deg=0.0)

    def test_the_model_x_axis_follows_the_requested_true_bearing(self):
        nx, ny = 8, 3
        values = [0.0] * (nx * ny)
        bearing = 78.0
        horizon = horizon_from_model_grid(
            values, nx=nx, ny=ny, dx_m=100.0, dy_m=100.0,
            origin_east_m=0.0, origin_north_m=0.0, axis_bearing_deg=bearing)
        mid = ny // 2
        east = horizon.east_m[mid]
        north = horizon.north_m[mid]
        run_e = float(east[-1]) - float(east[0])
        run_n = float(north[-1]) - float(north[0])
        self.assertAlmostEqual(run_e / run_n, sin(radians(bearing)) / cos(radians(bearing)),
                               places=6)
        self.assertGreater(run_e, 0.0)

    def test_the_across_axis_is_centred_on_the_origin(self):
        nx, ny = 4, 5
        horizon = horizon_from_model_grid(
            [0.0] * (nx * ny), nx=nx, ny=ny, dx_m=100.0, dy_m=100.0,
            origin_east_m=0.0, origin_north_m=0.0, axis_bearing_deg=0.0)
        column = [float(row[0]) for row in horizon.east_m]
        self.assertAlmostEqual(sum(column) / len(column), 0.0, places=6)


class KeyFactTest(unittest.TestCase):
    def test_rendered_joins_value_and_unit(self):
        self.assertEqual(KeyFact("x", "12.3", "bara").rendered(), "12.3 bara")

    def test_rendered_omits_an_empty_unit(self):
        self.assertEqual(KeyFact("x", "8 in").rendered(), "8 in")


class RenderFieldIllustrationTest(unittest.TestCase):
    def setUp(self):
        try:
            import matplotlib  # noqa: F401
            import numpy  # noqa: F401
        except ImportError:
            self.skipTest("matplotlib and numpy are required")
        self.layout = _layout()
        self.paths = build_well_paths(self.layout, reservoir_depth_m_tvdmsl=3000.0,
                                      field_axis_bearing_deg=78.0)

    def _render(self, **kwargs):
        with tempfile.TemporaryDirectory() as folder:
            target = os.path.join(folder, "field.png")
            result = render_field_illustration(self.layout, self.paths, target, **kwargs)
            self.assertEqual(result, target)
            self.assertTrue(os.path.exists(target))
            return os.path.getsize(target)

    def test_renders_without_a_horizon_or_facts(self):
        self.assertGreater(self._render(), 5000)

    def test_renders_with_a_horizon_a_seabed_facts_and_annotations(self):
        import numpy as np

        nx, ny = 20, 10
        values = [3000.0 + 40.0 * ((i / nx) ** 2) - 25.0 * (j / ny)
                  for j in range(ny) for i in range(nx)]
        horizon = horizon_from_model_grid(
            values, nx=nx, ny=ny, dx_m=250.0, dy_m=250.0,
            origin_east_m=-2500.0, origin_north_m=0.0, axis_bearing_deg=78.0,
            contact_depth_m_tvdmsl=3030.0, attribution="test model")
        grid_e, grid_n = np.meshgrid(np.linspace(-4000, 4000, 12),
                                     np.linspace(-3000, 3000, 9))
        seabed = Seabed(east_m=grid_e, north_m=grid_n,
                        depth_m=260.0 + 6.0 * np.sin(grid_e / 1500.0),
                        attribution="test bathymetry")
        facts = [
            KeyFact("Gas in place", "6.12", "GSm3", "model", "RESERVOIR"),
            KeyFact("Recovery factor", "60.8", "%", "simulation", "RESERVOIR"),
            KeyFact("Flowline", "8 in", "", "API RP 14E", "SURF"),
        ]
        size = self._render(horizon=horizon, seabed=seabed, key_facts=facts,
                            annotations=[Annotation("host", 0.0, 0.0, -100.0)],
                            title="Testfield", subtitle="unit test")
        self.assertGreater(size, 20000)

    def test_a_horizon_without_a_contact_still_renders(self):
        horizon = Horizon(name="top", east_m=[[0.0, 100.0], [0.0, 100.0]],
                          north_m=[[0.0, 0.0], [100.0, 100.0]],
                          depth_m_tvdmsl=[[3000.0, 3010.0], [3005.0, 3015.0]])
        self.assertGreater(self._render(horizon=horizon), 5000)


if __name__ == "__main__":
    unittest.main()
