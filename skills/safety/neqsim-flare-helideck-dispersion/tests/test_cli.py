import json
from pathlib import Path

import numpy as np
import pytest
from flare_helideck_dispersion.cli import main

pytest.importorskip("matplotlib")

from matplotlib.image import imsave


def write_config(tmp_path: Path) -> Path:
    sectors = [f"S{i:03d}" for i in range(8)]
    bins = ["0-2", "2-6", ">6"]
    rng = np.random.default_rng(3)
    table = rng.random((8, 3))
    table = table / table.sum() * 100.0
    cfg = {
        "output_dir": "out",
        "geometry": {
            "flight_paths": {"distance_step_m": 100.0, "bearing_step_deg": 15.0}
        },
        "wind": {
            "table": {
                "sectors": sectors,
                "speed_bins": bins,
                "table": {
                    s: {b: float(table[i, k]) for k, b in enumerate(bins)}
                    for i, s in enumerate(sectors)
                },
            }
        },
        "releases": [
            {
                "name": "cold",
                "mass_flow_kg_s": 150.0,
                "composition": {"methane": 0.7, "ethane": 0.2, "propane": 0.1},
                "gamma": 1.25,
                "t0_k": 190.0,
            },
            {
                "name": "warm",
                "mass_flow_kg_s": 150.0,
                "mw_kg_mol": 0.0215,
                "gamma": 1.25,
                "t0_k": 273.15,
                "lfl_vol_frac": 0.04,
                "fuel_mole_frac": 0.96,
            },
        ],
        "sensitivity": {
            "cases": ["cold"],
            "tilt_scan_cases": ["cold"],
            "tilts": [30.0, 60.0],
            "n_samples": 2,
            "seed": 1,
            "ranges": {"tilt_deg": [40.0, 50.0]},
        },
        "benchmarks": [
            {
                "label": "cold 2 m/s",
                "case": {
                    "name": "b",
                    "mass_flow_kg_s": 150.0,
                    "mw_kg_mol": 0.0215,
                    "gamma": 1.25,
                    "t0_k": 190.0,
                    "lfl_vol_frac": 0.04,
                    "fuel_mole_frac": 0.96,
                },
                "speed_m_s": 2.0,
                "reference_pct_lfl_max": 0.0,
                "reference_source": "test",
            }
        ],
        "overlay": {
            "image": "sky.png",
            "anchor_px": [200, 180],
            "px_per_m": 0.1,
            "case": "cold",
            "wind_from_deg": 60.0,
            "speed_m_s": 3.0,
            "out": "out/figures/overlay.png",
        },
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    imsave(
        tmp_path / "sky.png",
        np.dstack([np.linspace(0.3, 0.7, 640)[None, :].repeat(360, 0)] * 3),
    )
    return path


def test_run_figures_and_overlay_commands(tmp_path, capsys):
    cfg = write_config(tmp_path)
    assert main(["run", str(cfg)]) == 0
    out = tmp_path / "out"
    assert (out / "study_results.json").exists() and (out / "study_arrays.npz").exists()
    assert (out / "uncertainty.json").exists()
    fragment = json.loads((out / "results_fragment.json").read_text(encoding="utf-8"))
    assert isinstance(fragment["conclusions"], str)
    assert "problem" not in capsys.readouterr().out
    assert main(["figures", str(cfg)]) == 0
    pngs = sorted((out / "figures").glob("fig*.png"))
    assert len(pngs) >= 11
    fragment = json.loads((out / "results_fragment.json").read_text(encoding="utf-8"))
    assert len(fragment["figure_captions"]) == len(pngs)
    assert main(["overlay", str(cfg)]) == 0
    assert (out / "figures" / "overlay.png").exists()


def test_figures_command_needs_a_saved_run(tmp_path):
    cfg = write_config(tmp_path)
    with pytest.raises(FileNotFoundError):
        main(["figures", str(cfg)])
