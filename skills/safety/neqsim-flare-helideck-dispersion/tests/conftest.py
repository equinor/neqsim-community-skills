"""Shared fixtures: a small synthetic platform, wind table and releases (public, synthetic)."""

import numpy as np
import pytest
from flare_helideck_dispersion import (
    FlightPathSettings,
    PlatformGeometry,
    ReleaseCase,
    StudySettings,
    WindTable,
    run_study,
)
from flare_helideck_dispersion.wind import (
    SECTOR_NAMES_16,
    default_representative_speeds,
)

BIN_LABELS = ["0-2", "2-4", "4-8", ">8"]


def make_wind_table() -> WindTable:
    """Deterministic 16-sector x 4-bin table that sums to 100 percent."""
    centres = np.arange(16) * 22.5
    sector_w = 1.0 + 0.5 * np.cos(np.radians(centres - 200.0))
    bin_w = np.array([4.0, 12.0, 40.0, 44.0])
    table = np.outer(sector_w, bin_w)
    table = table / table.sum() * 100.0
    return WindTable(
        list(SECTOR_NAMES_16),
        centres,
        list(BIN_LABELS),
        default_representative_speeds(BIN_LABELS),
        table,
        {"source": "synthetic test table"},
    )


def release_cases():
    """A warm, a cold dense and a small case."""
    return [
        ReleaseCase("warm", 150.0, 0.0215, 1.25, 273.15, 0.04, 0.96, 0.6),
        ReleaseCase("cold", 150.0, 0.0215, 1.25, 190.0, 0.04, 0.96, 0.6),
        ReleaseCase("small", 20.0, 0.0215, 1.25, 323.15, 0.04, 0.96, 0.6),
    ]


@pytest.fixture(scope="session")
def wind() -> WindTable:
    return make_wind_table()


@pytest.fixture(scope="session")
def coarse_geometry() -> PlatformGeometry:
    return PlatformGeometry(
        flight_paths=FlightPathSettings(distance_step_m=100.0, bearing_step_deg=15.0)
    )


@pytest.fixture(scope="session")
def cases():
    return release_cases()


@pytest.fixture(scope="session")
def coarse_study(wind, coarse_geometry, cases):
    """Study with coarse paths for fast figure and results tests."""
    return run_study(cases, wind, coarse_geometry, StudySettings())
