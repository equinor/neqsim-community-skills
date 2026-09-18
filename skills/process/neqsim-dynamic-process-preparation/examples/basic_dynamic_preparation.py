from dynamic_process_preparation import DynamicProcessPreparationModel


model = DynamicProcessPreparationModel()
plan = model.evaluate(
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
        },
        {"name": "LCV-001", "equipment_type": "valve"},
    ],
)

print("dynamic ready:", plan.dynamic_ready)
print("estimated volumes:", plan.estimated_volumes_m3)
for step in plan.neqsim_sequence:
    print("-", step)
