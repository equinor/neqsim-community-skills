import pytest

from production_network_routing import ProductionNetworkModel


def _wells(**overrides):
    base = [
        {
            "name": "WELL-A",
            "manifold": "MANIFOLD-1",
            "reservoir_pressure_bara": 300.0,
            "flowing_bottomhole_pressure_bara": 250.0,
            "productivity_index_sm3_per_day_bar": 1.0e5,
            "tubing_head_pressure_bara": 140.0,
        },
        {
            "name": "WELL-B",
            "manifold": "MANIFOLD-1",
            "reservoir_pressure_bara": 295.0,
            "flowing_bottomhole_pressure_bara": 240.0,
            "productivity_index_sm3_per_day_bar": 0.9e5,
            "tubing_head_pressure_bara": 135.0,
        },
    ]
    if overrides:
        for well in base:
            well.update(overrides)
    return base


def _manifolds(**overrides):
    manifold = {
        "name": "MANIFOLD-1",
        "flowline_length_km": 8.0,
        "pressure_gradient_bar_per_km": 1.5,
        "riser_dp_bar": 20.0,
    }
    manifold.update(overrides)
    return [manifold]


def test_well_rate_from_productivity_index() -> None:
    result = ProductionNetworkModel().evaluate(
        wells=_wells(),
        manifolds=_manifolds(),
        required_arrival_pressure_bara=90.0,
    )
    well_a = next(w for w in result.wells if w.name == "WELL-A")
    # PI 1e5 * drawdown (300 - 250) = 5e6 Sm3/day.
    assert well_a.rate_sm3_per_day == pytest.approx(5.0e6)
    assert well_a.flow_warning == "ok"


def test_arrival_pressure_rollup() -> None:
    result = ProductionNetworkModel().evaluate(
        wells=_wells(),
        manifolds=_manifolds(),
        required_arrival_pressure_bara=90.0,
    )
    manifold = result.manifolds[0]
    # manifold pressure = min THP = 135; flowline dp = 1.5*8 = 12; riser = 20.
    assert manifold.manifold_pressure_bara == pytest.approx(135.0)
    assert manifold.flowline_dp_bar == pytest.approx(12.0)
    assert manifold.arrival_pressure_bara == pytest.approx(103.0)
    assert manifold.arrival_warning == "ok"
    assert result.min_arrival_pressure_bara == pytest.approx(103.0)


def test_total_rate_aggregates_wells() -> None:
    result = ProductionNetworkModel().evaluate(
        wells=_wells(),
        manifolds=_manifolds(),
        required_arrival_pressure_bara=90.0,
    )
    # 5e6 (A) + 0.9e5*55 = 4.95e6 (B).
    assert result.total_rate_sm3_per_day == pytest.approx(5.0e6 + 4.95e6)


def test_negative_arrival_margin_is_high() -> None:
    result = ProductionNetworkModel().evaluate(
        wells=_wells(),
        manifolds=_manifolds(riser_dp_bar=60.0),
        required_arrival_pressure_bara=90.0,
    )
    # arrival = 135 - 12 - 60 = 63 < 90 -> high.
    assert result.manifolds[0].arrival_warning == "high"
    assert result.overall_warning == "high"


def test_no_drawdown_well_flags_high() -> None:
    wells = _wells()
    wells[0]["flowing_bottomhole_pressure_bara"] = 300.0  # equals reservoir P
    result = ProductionNetworkModel().evaluate(
        wells=wells,
        manifolds=_manifolds(),
        required_arrival_pressure_bara=90.0,
    )
    well_a = next(w for w in result.wells if w.name == "WELL-A")
    assert well_a.rate_sm3_per_day == 0.0
    assert well_a.flow_warning == "high"
    assert result.overall_warning == "high"


def test_unknown_manifold_raises() -> None:
    wells = _wells()
    wells[0]["manifold"] = "MISSING"
    with pytest.raises(ValueError):
        ProductionNetworkModel().evaluate(
            wells=wells,
            manifolds=_manifolds(),
            required_arrival_pressure_bara=90.0,
        )


def test_empty_manifold_flags_high() -> None:
    wells = [w for w in _wells() if w["name"] == "WELL-A"]
    manifolds = _manifolds() + [
        {
            "name": "MANIFOLD-2",
            "flowline_length_km": 5.0,
            "pressure_gradient_bar_per_km": 1.0,
        }
    ]
    result = ProductionNetworkModel().evaluate(
        wells=wells,
        manifolds=manifolds,
        required_arrival_pressure_bara=90.0,
    )
    empty = next(m for m in result.manifolds if m.name == "MANIFOLD-2")
    assert empty.well_count == 0
    assert empty.arrival_warning == "high"


def test_duplicate_well_name_raises() -> None:
    wells = _wells()
    wells[1]["name"] = "WELL-A"
    with pytest.raises(ValueError):
        ProductionNetworkModel().evaluate(
            wells=wells,
            manifolds=_manifolds(),
            required_arrival_pressure_bara=90.0,
        )
