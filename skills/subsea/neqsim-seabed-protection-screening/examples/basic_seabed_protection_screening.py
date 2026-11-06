"""End-to-end example on synthetic public-style data: map layers to a protection plan."""

import json

from seabed_protection_screening import (
    PipeBasis,
    ScreeningAssumptions,
    SeabedProtectionScreener,
    assemble_segments,
    build_route,
    find_line_crossings,
    plan_protection_data_package,
    sample_polygon_layer,
    to_neqsim_burial_segments,
)


def box(west, south, east, north, **props):
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    return {"type": "Feature", "properties": props, "geometry": {"type": "Polygon", "coordinates": [ring]}}


def main():
    route = build_route([(2.00, 60.00), (2.12, 60.01), (2.25, 60.00)], spacing_m=250.0)
    for request in plan_protection_data_package(1.9, 59.9, 2.35, 60.1):
        print("plan:", request.source_key, request.url)

    substrate = {"type": "FeatureCollection", "features": [
        box(1.9, 59.9, 2.10, 60.1, substrate="sand"),
        box(2.10, 59.9, 2.18, 60.1, substrate="rock"),
        box(2.18, 59.9, 2.35, 60.1, substrate="mud_to_sandy_mud"),
    ]}
    fishing = {"type": "FeatureCollection", "features": [
        box(1.9, 59.9, 2.35, 60.1, level="low"),
        box(2.05, 59.9, 2.30, 60.1, level="high"),
    ]}
    pipelines = {"type": "FeatureCollection", "features": [{
        "type": "Feature", "properties": {"name": "EXPORT-1", "od_in": 20},
        "geometry": {"type": "LineString", "coordinates": [[2.15, 59.95], [2.15, 60.05]]},
    }]}

    soil = sample_polygon_layer(route, substrate, "substrate")
    intensity = sample_polygon_layer(route, fishing, "level", default="none", rank_order=["none", "low", "medium", "high"])
    crossings = find_line_crossings(route, pipelines, outer_diameter_attribute="od_in", outer_diameter_unit_m=0.0254)
    segments = assemble_segments(route, {"soil_class": soil, "fishing_intensity": intensity})

    screener = SeabedProtectionScreener(
        PipeBasis(0.42, "16in-flowline"),
        ScreeningAssumptions(rock_rate_tonnes_per_day=6000.0),
    )
    plan = screener.assess(segments, crossings=crossings, existing_cover_intervals=[])

    for seg in plan.segments:
        print("KP %6.0f-%6.0f %-24s %-22s trench %-18s rock %7.0f t"
              % (seg.start_kp_m, seg.end_kp_m, seg.controlling_hazard, seg.strategy, seg.trench_method, seg.rock_tonnes))
    print("rock tonnes:", round(plan.rock_tonnes), "trench days:", round(plan.trench_days, 1),
          "rock days:", round(plan.rock_days or 0.0, 1), "buried fraction:", round(plan.buried_length_fraction, 2))
    for gap in plan.data_gaps:
        print("data gap:", gap)
    print(json.dumps(to_neqsim_burial_segments(plan, 0.42), indent=1)[:600])


if __name__ == "__main__":
    main()
