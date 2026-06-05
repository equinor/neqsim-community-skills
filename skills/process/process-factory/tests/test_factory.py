import pytest

from process_factory import FITTING_LD, build_plan, build_process_system, neqsim_available


def _section() -> dict:
    return {
        "section_id": "demo",
        "flow_path": [
            {"type": "node", "id": "inlet"},
            {"type": "segment", "id": "S1", "length_m": 50.0, "inner_diameter_m": 0.45,
             "fittings": [{"type": "elbow_90", "count": 4}]},
            {"type": "equipment", "id": "scrubber", "equipment_type": "gas_scrubber"},
            {"type": "equipment", "id": "choke", "equipment_type": "valve"},
            {"type": "parallel", "split_factors": [0.5, 0.5], "branches": [
                [{"type": "segment", "id": "A1", "length_m": 20.0, "inner_diameter_m": 0.3}],
                [{"type": "segment", "id": "B1", "length_m": 20.0, "inner_diameter_m": 0.3}],
            ]},
            {"type": "node", "id": "outlet"},
        ],
    }


def test_build_plan_order_and_kinds() -> None:
    plan = build_plan(_section())
    kinds = [u.kind for u in plan]
    # pipe, scrubber, (valve skipped), splitter, pipe, pipe, mixer
    assert kinds == [
        "pipe", "gas_scrubber", "splitter", "pipe", "pipe", "mixer",
    ]


def test_pipe_effective_length_includes_fittings() -> None:
    plan = build_plan(_section())
    pipe = next(u for u in plan if u.kind == "pipe")
    expected_extra = 4 * FITTING_LD["elbow_90"] * 0.45
    assert pipe.params["fitting_equiv_length_m"] == pytest.approx(expected_extra)
    assert pipe.params["effective_length_m"] == pytest.approx(50.0 + expected_extra)


def test_parallel_creates_one_splitter_and_one_mixer() -> None:
    plan = build_plan(_section())
    assert sum(1 for u in plan if u.kind == "splitter") == 1
    assert sum(1 for u in plan if u.kind == "mixer") == 1


def test_valve_is_pass_through() -> None:
    plan = build_plan(_section())
    assert all(u.kind != "valve" for u in plan)


def test_cooler_with_cv_adds_dp_valve() -> None:
    section = {
        "section_id": "c",
        "flow_path": [
            {"type": "equipment", "id": "ac", "equipment_type": "cooler",
             "outlet_temperature_C": 30.0, "Cv": 120.0},
        ],
    }
    plan = build_plan(section)
    assert [u.kind for u in plan] == ["cooler", "valve"]
    assert plan[1].params["Cv"] == 120.0


def test_unknown_equipment_type_raises() -> None:
    section = {
        "section_id": "x",
        "flow_path": [{"type": "equipment", "id": "r", "equipment_type": "reactor"}],
    }
    with pytest.raises(ValueError, match="equipment_type"):
        build_plan(section)


def test_build_plan_rejects_empty_flow_path() -> None:
    with pytest.raises(ValueError, match="flow_path"):
        build_plan({"section_id": "x", "flow_path": []})


def test_build_process_system_without_neqsim_raises() -> None:
    if neqsim_available():
        pytest.skip("neqsim is installed; fallback path not exercised")
    with pytest.raises(RuntimeError, match="neqsim"):
        build_process_system(_section(), inlet_stream=None, process_system=None)
