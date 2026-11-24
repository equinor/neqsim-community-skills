"""Offline tests of the reservoir-state proxy extraction (synthetic summary vectors, no simulator, no resdata)."""

from __future__ import annotations

import numpy as np
import pytest

from simulator_state_proxy import (
    StateTable,
    SummaryData,
    compare,
    inventory,
    performance_curve,
    replay_profile,
    unit_pressure_table,
    well_state_table,
)


def synthetic(shut_in: bool = False) -> SummaryData:
    """Two wells in one tank: pressure falls with total cumulative oil, constant productivity index."""
    t = np.arange(0.0, 31.0) * 30.0
    q1 = 1000.0 * np.exp(-t / 600.0)
    q2 = 600.0 * np.exp(-t / 900.0)
    q1[0] = q2[0] = 0.0                       # the first report step is the initial state
    if shut_in:
        q1[10:13] = 0.0
    c1 = np.concatenate([[0.0], np.cumsum(q1[1:] * 30.0)])
    c2 = np.concatenate([[0.0], np.cumsum(q2[1:] * 30.0)])
    pres = 250.0 - (c1 + c2) / 2.0e4
    return SummaryData(t, {
        "WOPR:P1": q1, "WOPT:P1": c1, "WBHP:P1": pres - q1 / 25.0, "WWCT:P1": np.clip(c1 / 2.0e6, 0.0, 0.9),
        "WGOR:P1": 150.0 + c1 / 1.0e4, "WBP9:P1": pres - q1 / 100.0,
        "WOPR:P2": q2, "WOPT:P2": c2, "WBHP:P2": pres - q2 / 10.0, "WWCT:P2": np.zeros_like(t),
        "WGOR:P2": np.full_like(t, 150.0),
        "RPR:1": pres, "FPR": pres, "WWIT:I1": 400.0 * t,
    })


def test_inventory_reports_what_can_be_built_and_what_is_missing():
    report = inventory(synthetic())
    assert report["wells"]["P1"]["can_build_proxy"]
    assert report["wells"]["P1"]["well_pressure_sources"] == ["WBP9:P1"]
    assert report["region_pressures"] == ["RPR:1"]
    assert report["missing"] == []
    data = SummaryData([0.0, 30.0], {"WOPR:P1": [0.0, 10.0], "WOPT:P1": [0.0, 300.0]})
    report = inventory(data)
    assert not report["wells"]["P1"]["can_build_proxy"]
    assert "WBHP:P1" in report["missing"]
    assert any("RPR or FPR" in item for item in report["missing"])


def test_well_table_recovers_the_productivity_index_of_the_reference_pressure():
    table = well_state_table(synthetic(), "P1", "RPR:1", extra_quantities={"WATER_INJECTED": "WWIT:I1"})
    assert table.abscissa == "OIL_PRODUCED"
    assert table.columns["cumulative"][0] == 0.0
    assert np.all(np.diff(table.columns["cumulative"]) > 0.0)
    np.testing.assert_allclose(table.columns["pi"], 25.0, rtol=1e-9)
    assert table.columns["pressure"][0] == pytest.approx(250.0)
    assert table.columns["WATER_INJECTED"][0] == 0.0
    assert table.columns["WATER_INJECTED"][-1] == pytest.approx(400.0 * 900.0)
    # the same well against its block pressure gives another, equally consistent, index
    block = well_state_table(synthetic(), "P1", "WBP9:P1")
    np.testing.assert_allclose(block.columns["pi"], 100.0 / 3.0, rtol=1e-9)


def test_shut_in_rows_are_dropped_and_cumulative_stays_strictly_increasing():
    table = well_state_table(synthetic(shut_in=True), "P1", "RPR:1")
    assert table.provenance["rows_dropped_not_flowing"] == 4
    assert np.all(np.diff(table.columns["cumulative"]) > 0.0)
    assert table.rows == 31 - 4 + 1


def test_reference_pressure_below_flowing_pressure_is_rejected():
    data = synthetic()
    with pytest.raises(ValueError, match="choose another pressure source"):
        well_state_table(data, "P1", data.get("WBHP:P1") - 1.0)
    with pytest.raises(KeyError, match="SUMMARY section"):
        well_state_table(data, "P9", "RPR:1")


def test_unit_pressure_follows_the_cumulative_of_all_wells():
    data = synthetic()
    unit = unit_pressure_table(data, "TANK", ["P1", "P2"], "RPR:1")
    total = data.get("WOPT:P1")[-1] + data.get("WOPT:P2")[-1]
    assert unit.columns["cumulative"][-1] == pytest.approx(total)
    assert unit.at(5.0e5)["pressure"] == pytest.approx(250.0 - 5.0e5 / 2.0e4, abs=0.05)


def test_csv_layout_matches_the_java_reader(tmp_path):
    table = well_state_table(synthetic(), "P1", "RPR:1", extra_quantities={"WATER_INJECTED": "WWIT:I1"})
    path = table.to_csv(tmp_path / "P1.csv")
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if not line.startswith("#")]
    assert lines[0] == "cumulative,pressure,waterCut,gor,pi,ELAPSED_TIME,WATER_INJECTED"
    assert len(lines) == table.rows + 1
    first = [float(x) for x in lines[1].split(",")]
    assert first[0] == 0.0 and first[1] == pytest.approx(250.0)


def test_table_needs_strictly_increasing_cumulative():
    with pytest.raises(ValueError, match="strictly increasing"):
        StateTable("bad", "OIL_PRODUCED", {"cumulative": np.array([0.0, 1.0, 1.0]), "pressure": np.ones(3)})


def test_replay_reproduces_the_run_it_came_from_and_ignores_the_network():
    data = synthetic()
    curve = performance_curve(data, "P1")
    rate, cumulative = replay_profile(curve, data.time_days, substeps=50)
    result = compare(data.time_days[1:], data.get("WOPR:P1")[1:], data.time_days, rate)
    assert result["mean_abs_pct"] < 2.0
    assert cumulative[-1] == pytest.approx(data.get("WOPT:P1")[-1], rel=0.03)
    capped, _ = replay_profile(curve, data.time_days, rate_cap=400.0)
    assert capped.max() <= 400.0 + 1e-9
    assert capped[-1] > rate[-1]              # holding the well back defers production to later


def test_compare_reports_relative_and_absolute_errors():
    t = np.array([0.0, 1.0, 2.0, 3.0])
    result = compare(t, [100.0, 100.0, 100.0, 0.1], t, [110.0, 90.0, 100.0, 5.0])
    assert result["points"] == 3
    assert result["mean_abs_pct"] == pytest.approx(20.0 / 3.0)
    assert result["max_abs_pct"] == pytest.approx(10.0)
    assert result["bias_pct"] == pytest.approx(0.0, abs=1e-9)
