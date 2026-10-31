"""Minimal worked example: window, seats, casing strings and a time/cost range for a synthetic exploration well."""

from well_design_study import CostBasis, NptEvent, SectionTime, monte_carlo, run_well_study

SPEC = {
    "name": "synthetic exploration well",
    "reference": {"water_depth_m": 370.0, "air_gap_m": 30.0},
    "pressure": {
        "pore": {"low": [[500, 1.03], [4000, 1.10]], "base": [[500, 1.03], [3000, 1.05], [4000, 1.25]], "high": [[500, 1.03], [3000, 1.10], [4000, 1.35]]},
        "frac": {"low": [[500, 1.35], [1500, 1.55], [3000, 1.75], [4000, 1.85]], "base": [[500, 1.45], [4000, 1.95]], "high": [[500, 1.6], [4000, 2.1]]},
    },
    "kick": {"intensity_sg": 0.06, "kt_min_m3": 5.0},
    "max_temp_c": 150.0,
    "completion": {"shut_in_wellhead_bar": 380.0, "max_surface_pressure_bar": 400.0},
    "sections": [
        {"name": "26 in", "hole_in": 26, "casing_od_in": 20.0, "top_tvd_m": 400.0, "shoe_tvd_m": 1000.0, "shoe_md_m": 1000.0, "mud_sg": 1.10},
        {"name": "17.5 in", "hole_in": 17.5, "casing_od_in": 13.375, "top_tvd_m": 1000.0, "shoe_tvd_m": 2000.0, "shoe_md_m": 2000.0, "mud_sg": 1.25},
        {"name": "12.25 in", "hole_in": 12.25, "casing_od_in": 9.625, "top_tvd_m": 2000.0, "shoe_tvd_m": 3500.0, "shoe_md_m": 3500.0, "mud_sg": 1.35},
    ],
}

if __name__ == "__main__":
    res = run_well_study(SPEC)
    print(res["readiness"])
    for s in res["strings"]:
        print(s["string"], s["status"], s["selected"]["pipe"] if s["selected"] else None)
    mc = monte_carlo([SectionTime("26 in", 3, 4, 7), SectionTime("17.5 in", 5, 8, 14), SectionTime("12.25 in", 9, 14, 24)],
                     [NptEvent("losses", 0.3, 1, 3, 8)], CostBasis(3.2, 140.0, 110.0))
    print({k: round(v, 1) for k, v in mc["days_total"].items()}, {k: round(v) for k, v in mc["cost_mnok"].items()})
