"""Synthetic example: a template with three wells, one closed bore re-used as a slot-recovery sidetrack.

All coordinates are synthetic (local E, N in m; V = TVD below MSL). Run:
    <python> examples/synthetic_template_example.py
"""

import json

import numpy as np

from well_trajectory_anticollision import (
    ErrorModel,
    SFRule,
    Wellpath,
    add_model_covariance,
    check_slot,
    compare_growth,
    governing,
    group_by_surface,
    plan_from_surface,
    plan_sidetrack,
    pull_back_search,
    scan,
    summarize,
)

MODEL = ErrorModel(b_total_nt=50000.0, dip_deg=72.0)
RULE = SFRule()


def offset(name, slot_en, kop, target, dls=2.5, parent=None):
    wp = plan_from_surface(
        (slot_en[0], slot_en[1], 350.0), kop, target, dls, name=name, step=30.0
    )
    wp.parent = parent
    return add_model_covariance(wp, MODEL, from_md=float(wp.md[0]))


def main():
    w1 = offset("T-1 H", (0.0, 0.0), 600.0, (900.0, 2200.0, 2100.0))
    w2 = offset("T-2 H", (2.5, 0.0), 650.0, (1700.0, 1400.0, 2080.0))
    w3 = offset("T-3 H", (5.0, 0.0), 700.0, (-400.0, 2600.0, 2150.0))
    md_x = np.arange(0.0, 2401.0, 30.0)
    expl = add_model_covariance(
        Wellpath.from_survey(
            "X-1",
            md_x,
            np.zeros_like(md_x),
            np.zeros_like(md_x),
            start_xyz=(1500.0, 2700.0, 300.0),
        ),
        MODEL,
    )
    slots = group_by_surface(
        [
            {
                "name": "T-1 H",
                "easting": 0.0,
                "northing": 0.0,
                "status": "producing",
                "slot": "01",
            },
            {
                "name": "T-2 H",
                "easting": 2.5,
                "northing": 0.0,
                "status": "closed",
                "slot": "02",
            },
            {
                "name": "T-3 H",
                "easting": 5.0,
                "northing": 0.0,
                "status": "producing",
                "slot": "03",
            },
        ]
    )
    print("slot 02:", check_slot(slots, slot="02")["status"])

    target = np.array(
        [1490.0, 2680.0, 2100.0]
    )  # 22 m from the vertical X-1: expect a STOP

    def plan(tgt, tie=900.0, dls=3.0):
        wp = plan_sidetrack(w2, tie, tgt, dls, name="T-2 AH plan", step=10.0)
        return add_model_covariance(wp, MODEL)

    tie_md = float(w2.md[np.argmin(abs(w2.md - 900.0))])
    base = plan(target, tie=tie_md)
    res = scan(base, [w1, w2, w3, expl], RULE, model=MODEL)
    print("plan:", json.dumps(summarize(base, (2.5, 0.0))))
    print("governing:", governing(res))
    for row in res["offsets"]:
        extra = (
            f" parent exit {row['last_md_below_caution']} m MD"
            if row["parent_bore"]
            else ""
        )
        print(
            f"  {row['wellbore']:6s} SF {row['sf']:6.2f}  cc {row['cc_m']:7.1f} m  {row['status']}{extra}"
        )
    pb = pull_back_search(
        lambda t: plan(t, tie=tie_md),
        target,
        (2.5, 0.0),
        [w1, w2, w3, expl],
        RULE,
        model=MODEL,
    )
    print("pull-back chosen:", pb["chosen"])
    print("model vs reference growth:", compare_growth(w1, MODEL)[:2])


if __name__ == "__main__":
    main()
