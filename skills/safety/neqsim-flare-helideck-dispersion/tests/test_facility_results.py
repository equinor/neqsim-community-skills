import json
from pathlib import Path

import numpy as np
import pytest
from flare_helideck_dispersion import StudySettings
from flare_helideck_dispersion.cli import main
from flare_helideck_dispersion.facility import (
    FacilityRelease,
    Receptor,
    Source,
    facility_tilt_scan,
    run_facility_study,
)
from flare_helideck_dispersion.facility_results import (
    build_facility_results,
    validate_fragment,
)
from flare_release_cases import release_cases

pytest.importorskip("matplotlib")

from flare_helideck_dispersion.facility_figures import make_facility_figures


@pytest.fixture(scope="module")
def study(wind):
    flare = Source("flare", 0.0, 0.0, 60.0, "flare_tip", tilt_deg=30.0)
    vent = Source("cold_vent", 120.0, 30.0, 45.0, "cold_vent", tilt_deg=90.0)
    cases = release_cases()
    receptors = [
        Receptor.point(
            "hvac", "air_intake", 40.0, -40.0, 35.0, criterion_source="design basis"
        ),
        Receptor.rectangle(
            "muster", "muster_area", 60.0, -90.0, 90.0, -60.0, 12.0, 15.0
        ),
        Receptor.polyline(
            "escape", "escape_route", [(0, -60, 20), (80, -60, 20), (80, 20, 20)], 10.0
        ),
    ]
    return run_facility_study(
        [FacilityRelease(cases[1], flare), FacilityRelease(cases[2], vent)],
        wind,
        receptors,
        StudySettings(),
    )


def test_fragment_is_valid_and_traceable(study, wind):
    scans = {
        fr.case.name: facility_tilt_scan(
            fr, wind, study.receptors, study.settings, (30.0, 90.0)
        )
        for fr in study.freleases
    }
    fragment = build_facility_results(study, (), scans, None, 0.01, 2.0)
    assert validate_fragment(fragment) == [], validate_fragment(fragment)
    assert isinstance(fragment["conclusions"], str)
    assert "conditional" in fragment["conclusions"].lower()
    assert fragment["annual_exposure"]
    worst = study.ranking(20.0)[0]
    assert fragment["key_results"]["most_exposed_receptor"] == worst["receptor"]
    assert all(
        p["status"] == "pass" for p in fragment["benchmark_validation"]["points"]
    )
    assert any(
        "tilt" in t["title"].lower() or "inclination" in t["title"].lower()
        for t in fragment["tables"]
    )


def test_facility_figures_have_no_layout_problems(study, tmp_path):
    records = make_facility_figures(study, str(tmp_path))
    assert [r.name for r in records] == [
        "facility_layout.png",
        "facility_exceedance.png",
    ]
    for r in records:
        assert r.problems == [], (r.name, r.problems)
        assert Path(r.paths[0]).exists()
    fragment = build_facility_results(study, records)
    assert validate_fragment(fragment) == []
    assert len(fragment["figure_discussion"]) == 2


def test_facility_command_with_helideck_preset(tmp_path, capsys):
    sectors = [f"S{i:03d}" for i in range(8)]
    bins = ["0-2", "2-6", ">6"]
    table = np.random.default_rng(5).random((8, 3))
    table = table / table.sum() * 100.0
    cfg = {
        "output_dir": "out",
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
        "sources": [
            {
                "name": "flare",
                "east_m": 0,
                "north_m": 0,
                "height_asl_m": 124,
                "kind": "flare_tip",
            }
        ],
        "helideck": {
            "source": "flare",
            "flight_paths": {"distance_step_m": 100.0, "bearing_step_deg": 15.0},
        },
        "receptors": [
            {
                "name": "accommodation door",
                "kind": "accommodation",
                "shape": "point",
                "east_m": -120,
                "north_m": -80,
                "height_asl_m": 40,
                "criterion_source": "design basis",
            }
        ],
        "releases": [
            {
                "name": "cold",
                "mass_flow_kg_s": 150.0,
                "mw_kg_mol": 0.0215,
                "gamma": 1.25,
                "t0_k": 190.0,
                "lfl_vol_frac": 0.04,
                "fuel_mole_frac": 0.96,
                "source": "flare",
            }
        ],
        "sensitivity": {"tilts": [30.0, 60.0]},
    }
    path = tmp_path / "facility.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    assert main(["facility", str(path), "--figures"]) == 0
    out = tmp_path / "out"
    assert (out / "facility_results.json").exists()
    assert (out / "facility_sensitivity.json").exists()
    assert (out / "figures" / "facility_layout.png").exists()
    fragment = json.loads((out / "facility_fragment.json").read_text(encoding="utf-8"))
    names = {r["receptor"] for r in fragment["ranking"]}
    assert names == {
        "accommodation door",
        "helideck",
        "any_flight_path",
        "into_wind_path",
    }
    assert "problem" not in capsys.readouterr().out


def test_section_command_writes_a_plane_with_marks(tmp_path, capsys):
    cfg = {
        "output_dir": "out",
        "wind": {
            "table": {
                "sectors": ["N"],
                "speed_bins": ["0-2"],
                "table": {"N": {"0-2": 100.0}},
            }
        },
        "sources": [{"name": "flare", "height_asl_m": 40, "tilt_deg": 20}],
        "receptors": [
            {
                "name": "muster",
                "kind": "muster_area",
                "shape": "point",
                "east_m": 50,
                "north_m": -50,
                "height_asl_m": 25,
            }
        ],
        "releases": [
            {
                "name": "c",
                "mass_flow_kg_s": 100.0,
                "mw_kg_mol": 0.0215,
                "gamma": 1.25,
                "t0_k": 190.0,
                "lfl_vol_frac": 0.04,
                "fuel_mole_frac": 0.96,
            }
        ],
        "section": {
            "case": "c",
            "wind_from_deg": 315.0,
            "speed_m_s": 1.5,
            "s_range_m": [-20, 150],
            "z_range_m": [2, 80],
        },
    }
    path = tmp_path / "section.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    assert main(["section", str(path)]) == 0
    data = json.loads((tmp_path / "out" / "section.json").read_text(encoding="utf-8"))
    assert [m["label"] for m in data["marks"]] == ["muster"]
    assert "mark: " in capsys.readouterr().out


def test_facility_command_rejects_an_unknown_source(tmp_path):
    cfg = {
        "wind": {
            "table": {
                "sectors": ["N"],
                "speed_bins": ["0-2"],
                "table": {"N": {"0-2": 100.0}},
            }
        },
        "sources": [{"name": "flare", "height_asl_m": 50}],
        "receptors": [
            {
                "name": "p",
                "shape": "point",
                "east_m": 10,
                "north_m": 0,
                "height_asl_m": 30,
            }
        ],
        "releases": [
            {
                "name": "c",
                "mass_flow_kg_s": 10.0,
                "mw_kg_mol": 0.0215,
                "gamma": 1.25,
                "t0_k": 280.0,
                "lfl_vol_frac": 0.04,
                "fuel_mole_frac": 0.96,
                "source": "missing",
            }
        ],
    }
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    with pytest.raises(ValueError):
        main(["facility", str(path)])
