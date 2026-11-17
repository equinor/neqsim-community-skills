"""Reservoir history match and forecast on a compositional depletion path (multi-tank, multi-well)."""

from .core import DepletionPath, FluidModel, StreamState
from .field import Field, SimResult, Tank, Well
from .forecast import Scenario, ensemble, forecast, well_series
from .handoff import (
    WellStream,
    history_forecast_table,
    run_process_series,
    stream_table,
    well_streams_at,
)
from .match import Matcher, MatchResult, Param, TankSpec, fit_deliverability
from .prep import (
    deliverability_history,
    field_cgr_observations,
    monthly_rates,
    shut_in_pressure_observations,
)

__all__ = [
    "DepletionPath",
    "Field",
    "FluidModel",
    "MatchResult",
    "Matcher",
    "Param",
    "Scenario",
    "SimResult",
    "StreamState",
    "Tank",
    "TankSpec",
    "Well",
    "WellStream",
    "deliverability_history",
    "ensemble",
    "field_cgr_observations",
    "fit_deliverability",
    "forecast",
    "history_forecast_table",
    "monthly_rates",
    "run_process_series",
    "shut_in_pressure_observations",
    "stream_table",
    "well_series",
    "well_streams_at",
]
