"""Register a trained surrogate in NeqSim's ``SurrogateModelRegistry``.

The registry (``neqsim.process.ml.surrogate.SurrogateModelRegistry``) is
NeqSim's Java-side home for fast proxies. ``predictWithFallback`` calls the
surrogate when the input is inside its trained bounds and the physics model
otherwise, and it tracks prediction, failure and extrapolation counts.

:func:`register_in_neqsim` wraps a :class:`~.learner.Surrogate` as a JPype
proxy for the registry's ``SurrogateModel`` interface. Inputs are in
engineering units, in the order of ``surrogate.parameters``; outputs are the
surrogate means, in the order of ``outputs``.

The proxy lives in this Python process: it works for Java code running in the
same JVM (for example a NeqSim process model driven from Python), but it cannot
be saved with ``SurrogateModelRegistry.saveModel``. Save the surrogate with
``Surrogate.to_json`` and register it again after loading.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from .learner import Surrogate, SurrogateError

REGISTRY_CLASS = "neqsim.process.ml.surrogate.SurrogateModelRegistry"


def _jpype():
    try:
        import jpype
        from neqsim import jneqsim  # noqa: F401  (starts the JVM)
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise SurrogateError(
            "neqsim is not installed: python -m pip install neqsim"
        ) from exc
    return jpype


def register_in_neqsim(
    surrogate: Surrogate,
    model_id: str,
    outputs: Sequence[str] | None = None,
    expected_accuracy: float | None = None,
    training_source: str = "neqsim-active-learning-surrogate",
):
    """Register ``surrogate`` in the NeqSim registry under ``model_id``.

    Args:
        surrogate: A trained surrogate.
        model_id: Registry key.
        outputs: Outputs to expose, in order (default: all).
        expected_accuracy: Stored in the metadata; defaults to the lowest
            leave-one-out Q2 of the exposed outputs.
        training_source: Free text stored in the metadata.

    Returns:
        The registry instance (``SurrogateModelRegistry.getInstance()``).
    """
    jpype = _jpype()
    names = list(outputs) if outputs is not None else list(surrogate.outputs)
    unknown = [n for n in names if n not in surrogate.models]
    if unknown:
        raise SurrogateError(f"unknown outputs {unknown}")
    registry_class = jpype.JClass(REGISTRY_CLASS)
    interface = jpype.JClass(REGISTRY_CLASS + "$SurrogateModel")
    metadata_class = jpype.JClass(REGISTRY_CLASS + "$SurrogateMetadata")
    parameters = surrogate.parameters
    dim = len(parameters)

    @jpype.JImplements(interface)
    class _Proxy:
        @jpype.JOverride
        def predict(self, values):
            row = {p.name: float(v) for p, v in zip(parameters, values)}
            means = surrogate.predict(row)
            return jpype.JArray(jpype.JDouble)([float(means[n][0][0]) for n in names])

        @jpype.JOverride
        def getInputDimension(self):
            return dim

        @jpype.JOverride
        def getOutputDimension(self):
            return len(names)

    metadata = metadata_class()
    metadata.setModelType("gaussian-process (matern52-ard, active learning)")
    metadata.setTrainingDataSource(training_source)
    metadata.setTrainedAt(jpype.JClass("java.time.Instant").now())
    metadata.setInputBounds(
        jpype.JArray(jpype.JDouble)([float(p.low) for p in parameters]),
        jpype.JArray(jpype.JDouble)([float(p.high) for p in parameters]),
    )
    if expected_accuracy is None:
        expected_accuracy = min(surrogate.models[n].loo_q2() for n in names)
    metadata.setExpectedAccuracy(float(expected_accuracy))
    registry = registry_class.getInstance()
    proxy = _Proxy()
    registry.register(model_id, proxy, metadata)
    # Keep the Python object alive as long as the registry may call it.
    _LIVE_PROXIES[model_id] = proxy
    return registry


def predict_with_fallback(
    model_id: str,
    values: Sequence[float],
    physics: Callable[[Sequence[float]], Sequence[float]],
) -> list[float]:
    """Call ``SurrogateModelRegistry.predictWithFallback`` from Python.

    ``physics`` receives the input list and returns the outputs; it runs when
    the input is outside the trained bounds or the surrogate fails.
    """
    jpype = _jpype()
    registry = jpype.JClass(REGISTRY_CLASS).getInstance()
    function = jpype.JClass("java.util.function.Function")

    @jpype.JImplements(function)
    class _Physics:
        @jpype.JOverride
        def apply(self, x):
            return jpype.JArray(jpype.JDouble)([float(v) for v in physics(list(x))])

    result = registry.predictWithFallback(
        model_id, jpype.JArray(jpype.JDouble)([float(v) for v in values]), _Physics()
    )
    return [float(v) for v in result]


_LIVE_PROXIES: dict[str, object] = {}
