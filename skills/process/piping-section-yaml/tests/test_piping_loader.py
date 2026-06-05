import pytest

from piping_section_yaml import (
    FITTING_LD,
    fittings_equivalent_length,
    inspect_section,
    load_section,
    total_elevation,
    total_length,
    validate_section,
)


def _demo_data() -> dict:
    return {
        "section_id": "demo_inlet",
        "description": "test section",
        "flow_path": [
            {"type": "node", "id": "header", "pressure_bara": 90.0},
            {
                "type": "segment", "id": "S1", "length_m": 57.8,
                "inner_diameter_m": 0.467, "elevation_m": 3.5,
                "fittings": [{"type": "elbow_90", "count": 4},
                             {"type": "tee_branch", "count": 1}],
            },
            {"type": "equipment", "id": "scrubber", "equipment_type": "gas_scrubber"},
            {
                "type": "parallel", "split_factors": [0.5, 0.5],
                "branches": [
                    [{"type": "segment", "id": "A1", "length_m": 20.0,
                      "inner_diameter_m": 0.30}],
                    [{"type": "segment", "id": "B1", "length_m": 20.0,
                      "inner_diameter_m": 0.30}],
                ],
            },
            {"type": "node", "id": "outlet"},
        ],
    }


def test_load_section_extracts_nodes_segments_equipment() -> None:
    section = load_section(_demo_data())

    assert section.section_id == "demo_inlet"
    # 1 main segment + 2 parallel branch segments
    assert len(section.segments) == 3
    assert len(section.equipment) == 1
    assert set(section.nodes) == {"header", "outlet"}


def test_totals_use_physical_lengths() -> None:
    section = load_section(_demo_data())

    assert total_length(section) == pytest.approx(57.8 + 20.0 + 20.0)
    assert total_elevation(section) == pytest.approx(3.5)


def test_fittings_equivalent_length_matches_crane_ld() -> None:
    # 4 x elbow_90 (L/D 20) + 1 x tee_branch (L/D 60), D = 0.467 m
    expected = (4 * FITTING_LD["elbow_90"] + 1 * FITTING_LD["tee_branch"]) * 0.467
    result = fittings_equivalent_length(
        [{"type": "elbow_90", "count": 4}, {"type": "tee_branch", "count": 1}],
        inner_diameter_m=0.467,
    )

    assert result == pytest.approx(expected)


def test_unknown_fitting_contributes_zero_length() -> None:
    result = fittings_equivalent_length(
        [{"type": "not_a_real_fitting", "count": 3}], inner_diameter_m=0.3
    )

    assert result == 0.0


def test_inspect_section_includes_fitting_equiv_and_parallel_markers() -> None:
    rows = inspect_section(load_section(_demo_data()))
    kinds = [r["kind"] for r in rows]

    assert "parallel_start" in kinds
    assert "parallel_end" in kinds
    s1 = next(r for r in rows if r.get("id") == "S1")
    assert s1["fitting_equiv_length_m"] > 0.0


def test_validate_section_rejects_missing_section_id() -> None:
    data = _demo_data()
    del data["section_id"]
    with pytest.raises(ValueError, match="section_id"):
        validate_section(data)


def test_validate_section_rejects_non_positive_diameter() -> None:
    data = _demo_data()
    data["flow_path"][1]["inner_diameter_m"] = 0.0
    with pytest.raises(ValueError, match="inner_diameter_m"):
        validate_section(data)


def test_validate_section_rejects_unknown_equipment_type() -> None:
    data = _demo_data()
    data["flow_path"][2]["equipment_type"] = "reactor"
    with pytest.raises(ValueError, match="equipment_type"):
        validate_section(data)
