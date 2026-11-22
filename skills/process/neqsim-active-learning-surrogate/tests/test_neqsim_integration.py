"""Learns a real NeqSim flowsheet boundary; skipped without neqsim."""

import runpy
from pathlib import Path

import pytest

pytest.importorskip("neqsim")

from active_learning_surrogate import ActiveLearner, Parameter, validate


@pytest.fixture(scope="module", autouse=True)
def _keep_jvm_alive_at_exit():
    """Skip JVM teardown at interpreter exit.

    JPype can segfault in its exit-time JVM shutdown after NeqSim has run in
    the same pytest session as other test directories. The tests have finished
    by then; this only avoids a spurious non-zero exit code.
    """
    import jpype.config

    jpype.config.destroy_jvm = False
    yield


EXAMPLE = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "host_compressor_capacity_boundary.py"
)


def test_limit_state_on_neqsim_host_model():
    host_model = runpy.run_path(str(EXAMPLE))["host_model"]

    def model(values):
        return host_model({**values, "inlet_temperature_c": 50.0})

    result = ActiveLearner(
        model,
        [
            Parameter("tiein_rate_kgh", 0.0, 60000.0),
            Parameter("separator_pressure_bara", 30.0, 70.0),
        ],
        ["compressor_power_kw"],
        mode="limit_state",
        limit_output="compressor_power_kw",
        threshold=6500.0,
        max_evaluations=30,
        pool_size=800,
    ).run()
    assert result.converged, result.stop_reason
    report = validate(result.surrogate, model, n=6, seed=3)
    assert report.classification_agreement == 1.0
    assert report.max_abs_error["compressor_power_kw"] < 300.0
