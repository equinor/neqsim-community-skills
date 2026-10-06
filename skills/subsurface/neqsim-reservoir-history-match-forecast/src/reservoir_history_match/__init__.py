"""Reservoir history match and forecast on a compositional depletion path (multi-tank, multi-well)."""

from .core import DepletionPath, FluidModel, StreamState
from .field import Field, SimResult, Tank, Well
from .forecast import Scenario, ensemble, forecast, well_series
from .handoff import WellStream, history_forecast_table, run_process_series, stream_table, well_streams_at
from .prep import deliverability_history, field_cgr_observations, monthly_rates, shut_in_pressure_observations
from .match import MatchResult, Matcher, Param, TankSpec, fit_deliverability

__all__ = [
    "DepletionPath", "FluidModel", "StreamState", "Field", "SimResult", "Tank", "Well", "Scenario", "ensemble", "forecast",
    "well_series", "WellStream", "history_forecast_table", "run_process_series", "stream_table", "well_streams_at", "MatchResult",
    "Matcher", "Param", "TankSpec", "fit_deliverability", "deliverability_history", "field_cgr_observations", "monthly_rates",
    "shut_in_pressure_observations",
]

