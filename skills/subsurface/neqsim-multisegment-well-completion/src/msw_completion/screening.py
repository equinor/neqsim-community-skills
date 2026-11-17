"""Zonal inflow with and without inflow-control devices, using the simulator's device equations.

Each zone is isolated by packers and produces through its own devices into a common tubing pressure. A zone has
a productivity index for total reservoir rate and fixed in-situ water and gas fractions. With devices, the zone
rate ``q`` solves ``drawdown = q / PI + dP_device(q / N)``. The phase split of a zone is held fixed: the result is
the immediate re-allocation of inflow between zones. It does not capture delayed water or gas breakthrough, nor a
change of a zone's phase split, so a multi-segment simulation must confirm the long-term benefit.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .devices import Device, PhaseProperties, pressure_drop_bar


@dataclass(frozen=True)
class Zone:
    """One packer-isolated completion zone."""

    name: str
    productivity_index: float  # rm3/day/bar, total reservoir rate
    water_fraction: float
    gas_fraction: float
    devices: float = 0.0  # number of devices in the zone; 0 = open hole / perforation
    reservoir_pressure_offset_bar: float = 0.0  # zone pressure minus the reference reservoir pressure

    @property
    def fractions(self):
        oil = 1.0 - self.water_fraction - self.gas_fraction
        if oil < -1e-9 or self.water_fraction < 0 or self.gas_fraction < 0:
            raise ValueError(f"zone {self.name}: fractions must be non-negative and sum to at most 1")
        return max(oil, 0.0), self.water_fraction, self.gas_fraction


def zone_rate(zone: Zone, drawdown_bar: float, device: Device | None, props: PhaseProperties) -> dict[str, float]:
    """Reservoir rate of one zone and the split of its drawdown between reservoir and device."""
    dd = drawdown_bar + zone.reservoir_pressure_offset_bar
    if dd <= 0.0:
        return {"rate": 0.0, "device_dp": 0.0, "reservoir_dp": 0.0}
    if device is None or zone.devices <= 0:
        return {"rate": zone.productivity_index * dd, "device_dp": 0.0, "reservoir_dp": dd}
    lo, hi = 0.0, zone.productivity_index * dd
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        total = mid / zone.productivity_index + pressure_drop_bar(device, mid / zone.devices, zone.fractions, props)
        if total < dd:
            lo = mid
        else:
            hi = mid
        if hi - lo <= 1e-9 * max(hi, 1.0):
            break
    rate = 0.5 * (lo + hi)
    device_dp = pressure_drop_bar(device, rate / zone.devices, zone.fractions, props)
    return {"rate": rate, "device_dp": device_dp, "reservoir_dp": rate / zone.productivity_index}


def well_inflow(zones: Sequence[Zone], drawdown_bar: float, device: Device | None,
                props: PhaseProperties) -> dict[str, object]:
    """Oil, water and gas reservoir rates per zone and in total for one drawdown."""
    rows: list[dict[str, object]] = []
    totals = {"oil": 0.0, "water": 0.0, "gas": 0.0}
    for zone in zones:
        result = zone_rate(zone, drawdown_bar, device, props)
        fo, fw, fg = zone.fractions
        row = {"zone": zone.name, "rate_rm3_day": result["rate"], "oil_rm3_day": result["rate"] * fo,
               "water_rm3_day": result["rate"] * fw, "gas_rm3_day": result["rate"] * fg,
               "device_dp_bar": result["device_dp"]}
        rows.append(row)
        for phase in totals:
            totals[phase] += row[f"{phase}_rm3_day"]
    return {"drawdown_bar": drawdown_bar, "zones": rows, "totals_rm3_day": totals}


def compare_at_same_oil(zones: Sequence[Zone], device: Device, props: PhaseProperties, bare_drawdown_bar: float,
                        max_drawdown_bar: float) -> dict[str, object]:
    """Water and gas reduction with devices at the oil rate of the bare completion.

    The drawdown with devices is raised until the oil rate matches the bare completion, up to
    ``max_drawdown_bar``. ``oil_rate_reached`` is False when the limit stops it; the comparison is then at the
    limit and the oil loss is reported.
    """
    bare = well_inflow(zones, bare_drawdown_bar, None, props)
    target = bare["totals_rm3_day"]["oil"]
    if target <= 0.0:
        raise ValueError("the bare completion produces no oil at this drawdown")
    lo, hi = bare_drawdown_bar, max_drawdown_bar
    if well_inflow(zones, hi, device, props)["totals_rm3_day"]["oil"] < target:
        dd, reached = hi, False
    else:
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if well_inflow(zones, mid, device, props)["totals_rm3_day"]["oil"] < target:
                lo = mid
            else:
                hi = mid
            if hi - lo < 1e-6:
                break
        dd, reached = hi, True
    with_devices = well_inflow(zones, dd, device, props)
    b, d = bare["totals_rm3_day"], with_devices["totals_rm3_day"]

    def change(phase: str) -> float | None:
        return (d[phase] - b[phase]) / b[phase] if b[phase] > 0 else None

    return {
        "bare": bare, "with_devices": with_devices, "oil_rate_reached": reached,
        "extra_drawdown_bar": dd - bare_drawdown_bar,
        "oil_change_fraction": change("oil"), "water_change_fraction": change("water"),
        "gas_change_fraction": change("gas"),
        "note": ("Fixed phase split per zone: this is the immediate re-allocation of inflow, without delayed "
                 "breakthrough. Confirm the long-term benefit with a multi-segment simulation of the completor "
                 "deck."),
    }
