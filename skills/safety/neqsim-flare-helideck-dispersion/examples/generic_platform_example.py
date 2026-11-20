"""Generic platform example: flare-tip release, helideck and flight paths (synthetic data).

Hypothetical platform: flare tip 124 m ASL, helideck 76 m ASL, 240 m apart, obstacle-free
sector 135-345 deg T. The wind record is synthetic. Nothing here is real site data.

Run it from any folder::

    <python> examples/generic_platform_example.py [output_dir]

It writes ``study_results.json``, ``study_arrays.npz``, ``uncertainty.json``,
``results_fragment.json`` and the figures into ``output_dir`` (default
``flare_helideck_example_output`` in the current folder).
"""

import sys
from pathlib import Path

import numpy as np
from flare_helideck_dispersion import (
    BenchmarkScenario,
    ModelParameters,
    PlatformGeometry,
    StudySettings,
    WindTable,
    api520_rated_mass_flow_kg_s,
    neqsim_available,
    release_case_from_composition,
    run_sensitivity,
    run_study,
    size_psv_api520_gas,
)
from flare_helideck_dispersion.figures import make_all_figures
from flare_helideck_dispersion.results import build_results, write_results_json
from flare_helideck_dispersion.sources import IN2_TO_M2, STANDARD_ORIFICES_IN2


def synthetic_wind(n_hours: int = 20000, seed: int = 7) -> WindTable:
    """Synthetic hourly record binned into a joint table."""
    rng = np.random.default_rng(seed)
    pick = rng.random(n_hours)
    direction = np.where(
        pick < 0.55,
        rng.vonmises(np.radians(210), 1.2, n_hours),
        np.where(
            pick < 0.80,
            rng.vonmises(np.radians(20), 1.5, n_hours),
            rng.uniform(-np.pi, np.pi, n_hours),
        ),
    )
    direction = np.degrees(direction) % 360.0
    speed = 9.5 * rng.weibull(2.2, n_hours)
    return WindTable.from_hourly(
        speed, direction, metadata={"source": "synthetic hourly record (example)"}
    )


def release_cases():
    """One rated-PSV case and two blowdown cases."""
    methane_rich = {
        "methane": 0.82,
        "ethane": 0.08,
        "propane": 0.04,
        "n-butane": 0.01,
        "CO2": 0.03,
        "nitrogen": 0.02,
    }
    heavier = {
        "methane": 0.70,
        "ethane": 0.12,
        "propane": 0.08,
        "n-butane": 0.03,
        "CO2": 0.05,
        "nitrogen": 0.02,
    }
    psv_flow = api520_rated_mass_flow_kg_s(
        STANDARD_ORIFICES_IN2["L"] * IN2_TO_M2, 50.0, 0.10, 323.15, 0.0212, 0.9, 1.2
    )
    return [
        release_case_from_composition(
            "PSV rated", psv_flow, methane_rich, 1.25, 323.15
        ),
        release_case_from_composition(
            "Blowdown warm", 150.0, methane_rich, 1.25, 273.15
        ),
        release_case_from_composition("Blowdown cold", 150.0, heavier, 1.25, 190.0),
    ]


def main(out_dir: str) -> None:
    out = Path(out_dir)
    wind = synthetic_wind()
    geometry = PlatformGeometry()
    cases = release_cases()
    settings = StudySettings(params=ModelParameters(tilt_deg=45.0))
    study = run_study(cases, wind, geometry, settings)
    study.save(out)
    for name, entry in study.summaries.items():
        m = entry["modes"]["briggs"]
        print(
            f"{name:<14} deck {m['peak_pct_lfl_helideck']:.2f} % LFL | "
            f"any path {m['peak_pct_lfl_any_path']:.0f} % LFL | "
            f">=20 % LFL on {m['exceed_pct_hours']['20']['any_path']:.2f} % of wind hours (given a release)"
        )

    sizing = size_psv_api520_gas(18.0, 50.0, 323.15, 0.0212, 0.9, 1.2)
    print(
        "NeqSim PSV sizing:",
        sizing if neqsim_available() else "skipped (NeqSim not importable)",
    )

    sens = run_sensitivity(
        cases,
        wind,
        study.receptors,
        settings,
        tilt_scan_cases=["Blowdown warm", "Blowdown cold"],
        uncertainty_cases=["Blowdown warm", "Blowdown cold"],
        n_samples=20,
        seed=42,
    )
    (out / "uncertainty.json").write_text(
        __import__("json").dumps(sens, indent=1), encoding="utf-8"
    )
    benchmarks = [
        BenchmarkScenario(
            "150 kg/s, 0 C, 4 m/s",
            cases[1],
            4.0,
            "illustrative: no gas at the deck",
            "placeholder for a project CFD study",
            0.0,
        ),
        BenchmarkScenario(
            "150 kg/s, -83 C, 2 m/s",
            cases[2],
            2.0,
            "illustrative: no gas at the deck",
            "placeholder for a project CFD study",
            0.0,
        ),
    ]
    figures = make_all_figures(study, str(out / "figures"), sens, benchmarks)
    for rec in figures:
        print(rec.name, "OK" if not rec.problems else rec.problems)
    results = build_results(study, figures, sens, benchmarks)
    write_results_json(out / "results_fragment.json", results, merge=False)
    print(results["conclusions"])


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "flare_helideck_example_output")
