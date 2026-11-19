"""Import UTC timestamp producers on every supported runtime, including 3.11."""

import importlib

import pytest


@pytest.mark.parametrize(
    "module",
    [
        "well_log_reading.evidence",
        "segy_seismic_reading.evidence",
        "weather_data.open_meteo",
        "weather_data.service",
        "ncs_infrastructure_network.build",
        "ncs_infrastructure_network.open_api",
        "ncs_ownership_equity.sodir",
        "sodir_open_data.client",
        "sodir_open_data.refresh",
        "thermoml_experimental_data.client",
        "open_incident_data.client",
        "open_marine_constraints.client",
        "open_marine_constraints.screen",
        "opm_open_decks.client",
    ],
)
def test_timestamp_modules_import_on_supported_python(module):
    importlib.import_module(module)
