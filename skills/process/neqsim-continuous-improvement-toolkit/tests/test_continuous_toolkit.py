from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

np = pytest.importorskip("numpy")

from continuous_improvement_toolkit import (TagreaderAdapter, enkf_update, identifiability,
                                            propose_next)


class FakeClient:
    def __init__(self, frame=None, error=None):
        self.frame, self.error = frame, error

    def read(self, tags, since, until, step, read_type=None):
        if self.error:
            raise RuntimeError(self.error)
        return self.frame


def test_tagreader_adapter_writes_part_and_watermark(tmp_path):
    pd = pytest.importorskip("pandas")
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    index = pd.date_range(start, periods=3, freq="h")
    frame = pd.DataFrame({"PT-1": [30.0, 30.1, 29.9]}, index=index)
    adapter = TagreaderAdapter("SRC", {"suction": "PT-1", "discharge": "PT-2"},
                               client=FakeClient(frame))
    result = adapter.pull(start, start + timedelta(hours=3), str(tmp_path))
    assert result.status == "partial" and result.gaps == ["discharge"]
    assert result.rows == 3 and result.watermark.startswith("2026-01-01T02:00")
    text = open(result.outputs[0], encoding="utf-8").read().splitlines()
    assert text[0] == "timestamp,suction" and len(text) == 4


def test_tagreader_adapter_degrades_instead_of_raising(tmp_path):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    failed = TagreaderAdapter("SRC", {"a": "A"}, client=FakeClient(error="401 auth")).pull(
        start, start + timedelta(hours=1), str(tmp_path))
    assert failed.status == "failed"
    empty = TagreaderAdapter("SRC", {"a": "A"}, client=FakeClient(frame=[])).pull(
        start, start + timedelta(hours=1), str(tmp_path))
    assert empty.status == "stale"
    with pytest.raises(ValueError):
        TagreaderAdapter("SRC", {})


def test_bayesian_optimisation_finds_maximum():
    def f(x):
        return -((x[0] - 0.7) ** 2) - ((x[1] - 0.2) ** 2)

    rng = np.random.default_rng(3)
    x = [list(p) for p in rng.random((5, 2))]
    y = [f(p) for p in x]
    for i in range(20):
        step = propose_next(x, y, bounds=[(0, 1), (0, 1)], seed=i)
        x.append(step["x"])
        y.append(f(step["x"]))
    best = x[int(np.argmax(y))]
    assert abs(best[0] - 0.7) < 0.1 and abs(best[1] - 0.2) < 0.1
    assert step["expected_improvement"] >= 0.0


def test_enkf_recovers_parameter():
    rng = np.random.default_rng(0)
    truth = 0.78
    ensemble = rng.normal(0.82, 0.02, size=(100, 1))
    for _ in range(5):
        predictions = 100.0 * ensemble          # model: power = 100 * eta
        ensemble = enkf_update(ensemble, predictions, [100.0 * truth], obs_std=0.2, seed=1)
    assert abs(ensemble.mean() - truth) < 0.005


def test_identifiability_flags_correlated_parameters():
    jacobian = [[1.0, 2.0], [2.0, 4.0], [3.0, 6.0]]    # second column is 2x the first
    report = identifiability(jacobian, names=["a", "b"])
    assert not report["identifiable"] and report["rank"] == 1
    assert set(report["unidentifiable_directions"][0]) == {"a", "b"}
    assert identifiability([[1.0, 0.0], [0.0, 1.0]])["identifiable"]
