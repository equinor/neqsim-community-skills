"""Minimal fire-water and deluge coverage screening example."""

from __future__ import annotations

from firewater_deluge_design import FireWaterCoverageModel

model = FireWaterCoverageModel()

AREA_M2 = 510.0
RATE = FireWaterCoverageModel.NORSOK_PROCESS_AREA_LPM_M2

cooler = FireWaterCoverageModel.horizontal_vessel_surface_m2(0.72, 6.606)

blanket = model.demand(protected_area_m2=AREA_M2, area_rate_lpm_per_m2=RATE, duration_min=30.0)
selective = model.demand(
    protected_area_m2=0.0,
    area_rate_lpm_per_m2=0.0,
    objects=(("gas cooler", cooler, RATE),),
    duration_min=30.0,
)

print(f"blanket area coverage : {blanket.total_demand_lpm:8.0f} l/min "
      f"({blanket.total_demand_m3_per_h:6.1f} m3/h)")
print(f"one dedicated cooler  : {selective.total_demand_lpm:8.0f} l/min "
      f"({selective.total_demand_m3_per_h:6.1f} m3/h)")

layout = model.deluge_layout(
    protected_area_m2=AREA_M2,
    required_density_lpm_per_m2=RATE,
    nozzle_k_lpm_per_sqrt_bar=42.9,
    nozzle_min_pressure_barg=3.5,
    max_spacing_m=3.0,
    operating_pressure_barg=5.0,
)
print(
    f"nozzles: {layout.nozzle_count} on a {layout.grid_spacing_m:.2f} m grid "
    f"({layout.governing_criterion} governs; flow criterion alone would give "
    f"{layout.nozzle_count_from_flow})"
)

monitor = model.monitor_screening(
    target_area_m2=AREA_M2,
    required_density_lpm_per_m2=RATE,
    monitor_count=4,
    monitor_flow_lpm=4000.0,
    wind_speed_m_s=15.0,
    fall_height_m=12.0,
    characteristic_dimension_m=25.5,
)
print(
    f"monitors: {monitor.nominal_density_lpm_per_m2:.1f} (l/min)/m2 still air, "
    f"{monitor.effective_density_lpm_per_m2:.1f} after {monitor.drift_displacement_m:.1f} m of "
    f"wind drift -> {monitor.verdict}"
)
