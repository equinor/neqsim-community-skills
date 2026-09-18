import pytest

from dynamic_process_preparation import DynamicProcessPreparationModel


def test_dynamic_preparation_returns_ready_plan_for_public_separator_case() -> None:
    plan = DynamicProcessPreparationModel().evaluate(
        process_name="public separator train",
        process_kind="ProcessSystem",
        time_step_seconds=10.0,
        total_time_seconds=600.0,
        equipment=[
            {
                "name": "V-001",
                "equipment_type": "separator",
                "length_m": 4.0,
                "diameter_m": 1.0,
                "liquid_level_fraction": 0.25,
                "requires_mechanical_design": True,
            }
        ],
    )

    assert plan.dynamic_ready is True
    assert plan.estimated_volumes_m3["V-001"] == pytest.approx(3.141593)
    assert plan.equipment_actions[0].liquid_holdup_m3 == pytest.approx(0.785398)
    assert any("storeInitialState" in step for step in plan.neqsim_sequence)


def test_dynamic_preparation_flags_missing_vessel_geometry() -> None:
    plan = DynamicProcessPreparationModel().evaluate(
        process_name="public separator train",
        process_kind="ProcessSystem",
        time_step_seconds=10.0,
        equipment=[{"name": "V-001", "equipment_type": "separator"}],
    )

    assert plan.dynamic_ready is False
    assert "no equipment volume estimate is available" in plan.warnings
    assert "vessel geometry is missing" in plan.equipment_actions[0].warnings[0]


def test_dynamic_preparation_rejects_bad_process_kind() -> None:
    with pytest.raises(ValueError, match="process_kind"):
        DynamicProcessPreparationModel().evaluate(
            process_name="public separator train",
            process_kind="FlowSheet",
            time_step_seconds=10.0,
            equipment=[{"name": "V-001", "equipment_type": "separator"}],
        )
