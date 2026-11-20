import copy
import json

import numpy as np
import pytest
from flare_helideck_dispersion import WindTable, pasquill_by_speed
from flare_helideck_dispersion.wind import (
    default_representative_speeds,
    speed_bin_labels,
)


def test_pasquill_schemes():
    assert [pasquill_by_speed(u) for u in (1.0, 3.0, 5.0)] == ["F", "E", "D"]
    assert pasquill_by_speed(1.0, "neutral") == "D"
    assert pasquill_by_speed(1.0, "day_moderate") == "B"
    assert pasquill_by_speed(1.0, [(2.0, "C"), (float("inf"), "D")]) == "C"
    assert pasquill_by_speed(9.0, lambda u: "E") == "E"
    with pytest.raises(ValueError):
        pasquill_by_speed(1.0, "unknown")


def test_labels_and_representative_speeds():
    labels = speed_bin_labels((0, 2, 4, 6))
    assert labels == ["0-2", "2-4", "4-6", ">6"]
    rep = default_representative_speeds(labels)
    assert rep.tolist() == [1.5, 3.0, 5.0, 8.0]
    assert default_representative_speeds(["0-2"], low_bin_speed_ms=1.0)[0] == 1.0
    with pytest.raises(ValueError):
        default_representative_speeds(["slow"])


def test_table_validation(wind):
    table = wind
    assert table.validate() == []
    assert table.total_pct == pytest.approx(100.0)
    bad = copy.deepcopy(wind)
    bad.table_pct[0, 0] = -1.0
    with pytest.raises(ValueError):
        bad.validate()
    off = copy.deepcopy(wind)
    off.table_pct *= 1.2
    with pytest.raises(ValueError):
        off.validate()
    assert off.normalised().total_pct == pytest.approx(100.0)
    with pytest.raises(ValueError):
        WindTable(["N"], [0.0], ["0-2", "2-4"], [1.0, 3.0], np.ones((2, 2)))


def test_json_round_trip_and_nested_layout(tmp_path, wind):
    table = wind
    path = tmp_path / "wind.json"
    table.save_json(path)
    again = WindTable.load_json(path)
    assert np.allclose(again.table_pct, table.table_pct)
    nested = {"joint_direction_x_speed_frequency_pct": table.to_dict()}
    path.write_text(json.dumps(nested), encoding="utf-8")
    assert np.allclose(WindTable.load_json(path).table_pct, table.table_pct)
    with pytest.raises(ValueError):
        WindTable.from_dict({"sectors": ["N"]})


def test_from_hourly_sums_to_100_and_assigns_sectors():
    speeds = [1.0, 3.0, 5.0, 25.0, float("nan")]
    dirs = [0.0, 359.0, 90.0, 180.0, 10.0]
    table = WindTable.from_hourly(speeds, dirs)
    assert table.total_pct == pytest.approx(100.0)
    assert table.metadata["n_dropped_invalid"] == 1
    # 0 and 359 degrees both fall in the north sector
    assert table.sector_frequency_pct()[0] == pytest.approx(50.0)
    assert table.table_pct[table.sectors.index("S"), -1] == pytest.approx(25.0)
    with pytest.raises(ValueError):
        WindTable.from_hourly([float("nan")], [1.0])


def test_from_hourly_csv_detects_columns(tmp_path):
    path = tmp_path / "hourly.csv"
    path.write_text(
        "time,wind_speed_10m,wind_direction_10m\n"
        "2020-01-01T00:00,3.0,200\n2020-01-01T01:00,9.0,210\n2020-01-01T02:00,x,y\n",
        encoding="utf-8",
    )
    table = WindTable.from_hourly_csv(path)
    assert table.metadata["n_hours"] == 2
    assert table.total_pct == pytest.approx(100.0)
    knots = WindTable.from_hourly_csv(path, speed_scale=0.514444)
    assert knots.table_pct.sum() == pytest.approx(100.0)
    (tmp_path / "bad.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError):
        WindTable.from_hourly_csv(tmp_path / "bad.csv")
