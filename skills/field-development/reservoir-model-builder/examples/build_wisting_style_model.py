"""Build a Wisting-style Barents Sea reservoir model on the data-maturity ladder.

The three stages show how the same builder is used with progressively more data:

    stage 1  a public headline volume and a depth only
    stage 2  add analogue rock and fluid properties for the play
    stage 3  add appraisal-well and PVT data

IMPORTANT — the numbers below are illustrative, public order-of-magnitude values
used to exercise the workflow. Before any engineering use they must be replaced
with figures verified against the Norwegian Offshore Directorate FactPages and
the operator's own reporting. Nothing here is an official resource statement.
"""

from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reservoir_model_builder import build_reservoir_model, summarize

# Public headline figures, all requiring verification before use.
BARRELS_PER_SM3 = 6.2898
RECOVERABLE_OIL_SM3 = 500.0e6 / BARRELS_PER_SM3  # ~500 million barrels reported
WATER_DEPTH_M = 400.0
DEPTH_BELOW_SEABED_M = 250.0  # unusually shallow reservoir
DATUM_DEPTH_M = WATER_DEPTH_M + DEPTH_BELOW_SEABED_M


def stage_1_public_headline():
    """Everything that can be built from an open-data headline entry."""
    return build_reservoir_model(
        field_name="Wisting (illustrative)",
        fluid_type="oil",
        sea_area="barents_sea",
        water_depth_m=WATER_DEPTH_M,
        datum_depth_m_tvdmsl=DATUM_DEPTH_M,
        recoverable_oil_Sm3=RECOVERABLE_OIL_SM3,
        provenance="public-reported",
        reference="public resource reporting; verify against Sodir FactPages",
        simulation_years=25.0,
    )


def stage_2_play_analogue(model):
    """Add rock and drive properties borrowed from the play, not from the field."""
    return model.refine(
        {
            "porosity": 0.28,
            "water_saturation": 0.25,
            "net_to_gross": 0.85,
            "aquifer_strength": "moderate",
            "injection_plan": "water_injection",
        },
        provenance="analogue",
        reference="Realgrunnen-type shallow-marine sandstone analogue; not field data",
    )


def stage_3_appraisal_data(model):
    """Add the data an appraisal well and a PVT report would deliver."""
    return model.refine(
        {
            "area_km2": 21.0,
            "net_pay_m": 45.0,
            "porosity": 0.30,
            "water_saturation": 0.20,
            "permeability_mD": 2000.0,
            "reservoir_temperature_C": 18.0,
            "initial_pressure_bara": 76.0,
            "oil_formation_volume_factor": 1.12,
            "oil_viscosity_cP": 1.5,
            "fluid_composition": {
                "nitrogen": 0.004,
                "CO2": 0.006,
                "methane": 0.240,
                "ethane": 0.035,
                "propane": 0.032,
                "n-butane": 0.028,
                "n-pentane": 0.022,
                "n-hexane": 0.028,
                "n-heptane": 0.605,
            },
            "target_plateau_rate_Sm3_per_day": 19000.0,
        },
        provenance="measured",
        reference="illustrative appraisal-well logs, DST and PVT report",
    )


def main() -> None:
    stage_1 = stage_1_public_headline()
    stage_2 = stage_2_play_analogue(stage_1)
    stage_3 = stage_3_appraisal_data(stage_2)

    for label, model in (
        ("STAGE 1 - public headline only", stage_1),
        ("STAGE 2 - play analogue added", stage_2),
        ("STAGE 3 - appraisal and PVT data added", stage_3),
    ):
        print("=" * 78)
        print(label)
        print("=" * 78)
        print(summarize(model))
        print()

    print("=" * 78)
    print("REFINEMENT AUDIT TRAIL (stage 2 -> stage 3)")
    print("=" * 78)
    for change in stage_3.changes:
        before = change["provenance_before"] or "absent"
        after = change["provenance_after"] or "absent"
        if before == after:
            continue
        print(f"  {change['parameter']:<38} {before:>16} -> {after}")

    print()
    print("=" * 78)
    print("CONSISTENCY CHECK - what an over-mapped area looks like")
    print("=" * 78)
    oversized = stage_3.refine({"area_km2": 55.0}, provenance="interpreted",
                               reference="deliberately over-mapped area")
    for warning in oversized.warnings:
        if "implies a recovery factor" in warning:
            print(f"  ! {warning}")

    print()
    print("=" * 78)
    print("NEQSIM RESERVOIR SPECIFICATION (stage 3)")
    print("=" * 78)
    print(json.dumps(stage_3.neqsim_spec, indent=2))


if __name__ == "__main__":
    main()
