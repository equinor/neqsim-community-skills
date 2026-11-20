"""Shared fixtures: a small synthetic platform, wind table and releases (public, synthetic)."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from flare_helideck_dispersion import (
    FlightPathSettings,
    PlatformGeometry,
    StudySettings,
    WindTable,
    run_study,
)
from flare_helideck_dispersion.wind import (
    SECTOR_NAMES_16,
    default_representative_speeds,
)
from flare_release_cases import release_cases

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
