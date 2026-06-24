"""Minimal production-network routing screening example.

Wells route via a manifold and flowline/riser to the host; the model rolls up a
screening arrival pressure at the host.

Run from inside the skill folder:

    python examples/basic_production_network.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from production_network_routing import ProductionNetworkModel


def main() -> None:
    wells = [
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
    manifolds = [
        {
            "name": "MANIFOLD-1",
            "flowline_length_km": 8.0,
            "pressure_gradient_bar_per_km": 1.5,
            "riser_dp_bar": 20.0,
        },
    ]

    result = ProductionNetworkModel().evaluate(
        wells=wells,
        manifolds=manifolds,
        host_name="HOST",
        required_arrival_pressure_bara=90.0,
    )

    print(f"host: {result.host_name}")
    print(f"required arrival: {result.required_arrival_pressure_bara} bara")
    print(f"total network rate: {result.total_rate_sm3_per_day:.0f} Sm3/day")
    print(f"min arrival pressure: {result.min_arrival_pressure_bara} bara")
    print(f"verdict: {result.overall_warning}")

    print("\nWells:")
    for well in result.wells:
        print(
            f"  {well.name} -> {well.manifold}: rate {well.rate_sm3_per_day:.0f} "
            f"Sm3/day ({well.flow_warning})"
        )
    print("Manifolds:")
    for manifold in result.manifolds:
        print(
            f"  {manifold.name}: {manifold.total_rate_sm3_per_day:.0f} Sm3/day, "
            f"arrival {manifold.arrival_pressure_bara} bara ({manifold.arrival_warning})"
        )

    print("\nNeqSim available:", result.neqsim_available)
    print(
        "Validated path: NeqSim PipeBeggsAndBrills / SimpleReservoir / "
        "MCP runPipeline / runProcess"
    )

    # Pressure-regulated multiwell flow: solve each well rate from a fixed
    # facility inlet/separator pressure and the reservoir pressures.
    regulated = ProductionNetworkModel().regulate_flow_from_inlet_pressure(
        wells=[
            {
                "name": "WELL-A",
                "manifold": "MANIFOLD-1",
                "reservoir_pressure_bara": 300.0,
                "productivity_index_sm3_per_day_bar": 1.0e5,
            },
            {
                "name": "WELL-B",
                "manifold": "MANIFOLD-1",
                "reservoir_pressure_bara": 295.0,
                "productivity_index_sm3_per_day_bar": 0.9e5,
            },
        ],
        target_inlet_pressure_bara=140.0,
    )

    print("\nPressure-regulated flow (inlet 140 bara):")
    print(f"  segment dp: {regulated.segment_dp_bar} bar")
    print(
        f"  total rate: {regulated.total_rate_sm3_per_day:.0f} Sm3/day, "
        f"flowing wells: {regulated.flowing_well_count}, "
        f"verdict: {regulated.overall_warning}"
    )
    for well in regulated.wells:
        print(
            f"  {well.name}: fbhp {well.flowing_bottomhole_pressure_bara} bara, "
            f"rate {well.rate_sm3_per_day:.0f} Sm3/day ({well.flow_warning})"
        )


if __name__ == "__main__":
    main()
