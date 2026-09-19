"""Build, run, and report a default-case TEG dehydration plant.

Requires NeqSim (``pip install neqsim``). Inputs are public and synthetic.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from teg_dehydration_modeling import (
    DEFAULT_FEED,
    build_teg_plant,
    classify_emissions,
    teg_mass_fraction,
)


def main() -> None:
    process, streams = build_teg_plant(
        feed_fractions=DEFAULT_FEED,
        feed_flow_MSm3_day=4.65,
        feed_temp_C=25.0,
        feed_pressure_bara=70.0,
        absorber_pressure_bara=85.0,
        absorber_temp_C=35.0,
        teg_flow_kg_hr=5500.0,
        teg_feed_temp_C=48.5,
        lean_teg_purity=0.97,
        flash_drum_pressure_bara=4.8,
        reboiler_temp_C=197.5,
        stripping_gas_Sm3_hr=180.0,
        n_absorber_stages=4,
        stage_efficiency=0.7,
    )

    thr = process.runAsThread()
    thr.join(300000)

    water_dew_C = float(streams["waterDewAnalyser"].getMeasuredValue("C"))
    lean_teg_wt = teg_mass_fraction(streams["leanTEGtoAbs"])
    still_vent = classify_emissions(streams["stillVent"])

    print("TEG dehydration plant result")
    print(f"water_dew_point_C={water_dew_C:.2f}")
    print(f"lean_teg_purity_wt_pct={lean_teg_wt:.2f}")
    print(f"still_vent_NMVOC_kg_hr={still_vent['NMVOC']:.2f}")
    print(f"still_vent_methane_kg_hr={still_vent['methane']:.2f}")
    print(f"still_vent_benzene_kg_hr={still_vent['benzene']:.4f}")
    print(f"still_vent_water_kg_hr={still_vent['water']:.2f}")


if __name__ == "__main__":
    main()
