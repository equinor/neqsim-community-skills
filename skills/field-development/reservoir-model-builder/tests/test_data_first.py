"""The data ladder: best source first, simplification only when recorded."""

from __future__ import annotations

import pytest

from reservoir_model_builder.data_first import (
    DATA_LADDER,
    acquisition_plan,
    best_available,
    data_first_gate,
    rank_of,
)


FULL = {
    "geometry": [{"source": "published_grid", "outcome": "used"}],
    "petrophysics": [{"source": "grid_property_arrays", "outcome": "used"}],
    "fluid": [{"source": "pvt_report", "outcome": "used"}],
    "scal": [{"source": "scal_report", "outcome": "used"}],
    "contacts": [{"source": "pressure_gradient_intersection", "outcome": "used"}],
    "volumes": [{"source": "operator_volumetrics", "outcome": "used"}],
}


def test_every_ladder_is_ranked_without_gaps():
    for name, ladder in DATA_LADDER.items():
        ranks = [rung["rank"] for rung in ladder]
        assert ranks == sorted(ranks), name
        assert ranks == list(range(1, len(ranks) + 1)), name


def test_rank_of_finds_and_misses():
    assert rank_of("geometry", "published_grid") == 1
    assert rank_of("geometry", "assumed_block") == 5
    assert rank_of("geometry", "not_a_source") is None
    with pytest.raises(KeyError):
        rank_of("not_an_ingredient", "x")


def test_best_available_reports_what_was_given_up():
    summary = best_available("geometry", [
        {"source": "published_grid", "outcome": "blocked",
         "detail": "401 on maap/omegas"},
        {"source": "horizons_and_faults", "outcome": "blocked"},
        {"source": "structure_map", "outcome": "absent"},
        {"source": "well_tops", "outcome": "absent"},
        {"source": "assumed_block", "outcome": "used"},
    ])
    assert summary["used"] == "assumed_block"
    assert summary["isDowngraded"] is True
    assert summary["unattempted"] == []
    assert any("faults" in text for text in summary["lost"])


def test_unattempted_rung_blocks_the_build():
    attempts = dict(FULL)
    attempts["geometry"] = [{"source": "assumed_block", "outcome": "used"}]
    gate = data_first_gate(attempts)
    assert gate["decision"] == "blocked"
    assert any("published_grid" in text and "never attempted" in text
               for text in gate["blockers"])


def test_recorded_refusal_permits_the_downgrade():
    attempts = dict(FULL)
    attempts["geometry"] = [
        {"source": "published_grid", "outcome": "blocked", "detail": "401"},
        {"source": "horizons_and_faults", "outcome": "blocked"},
        {"source": "structure_map", "outcome": "absent"},
        {"source": "well_tops", "outcome": "absent"},
        {"source": "assumed_block", "outcome": "used"},
    ]
    gate = data_first_gate(attempts)
    assert gate["decision"] == "proceed"
    assert "geometry" in gate["downgraded"]
    assert any("gives up" in text for text in gate["mustDisclose"])


def test_all_best_sources_proceeds_with_nothing_to_disclose():
    gate = data_first_gate(FULL)
    assert gate["decision"] == "proceed"
    assert gate["mustDisclose"] == []
    assert gate["downgraded"] == []


def test_missing_ingredient_is_a_blocker():
    attempts = {k: v for k, v in FULL.items() if k != "scal"}
    gate = data_first_gate(attempts)
    assert gate["decision"] == "blocked"
    assert any("scal" in text for text in gate["blockers"])


def test_acquisition_plan_separates_access_from_acquisition():
    attempts = dict(FULL)
    attempts["geometry"] = [
        {"source": "published_grid", "outcome": "blocked", "detail": "401"},
        {"source": "horizons_and_faults", "outcome": "blocked"},
        {"source": "structure_map", "outcome": "absent"},
        {"source": "well_tops", "outcome": "absent"},
        {"source": "assumed_block", "outcome": "used"},
    ]
    attempts["scal"] = [
        {"source": "scal_report", "outcome": "absent"},
        {"source": "analogue_scal", "outcome": "absent"},
        {"source": "corey_assumed", "outcome": "used"},
    ]
    gate = data_first_gate(attempts)
    plan = acquisition_plan(gate)
    routes = {item["ingredient"]: item["route"] for item in plan}
    assert "access request" in routes["geometry"]
    assert "acquisition" in routes["scal"]
    # the biggest gap is addressed first
    assert plan[0]["priority"] == 1
    assert plan[0]["gap"] >= plan[-1]["gap"]


def test_no_downgrade_means_no_acquisition_plan():
    assert acquisition_plan(data_first_gate(FULL)) == []
