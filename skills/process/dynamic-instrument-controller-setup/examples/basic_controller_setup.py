from dynamic_instrument_controller_setup import DynamicInstrumentControllerModel


model = DynamicInstrumentControllerModel()
loop = model.evaluate(
    loop_name="LC-001",
    controlled_variable="level",
    transmitter_target="V-001",
    manipulated_equipment="LCV-001",
    setpoint=0.3,
    minimum_value=0.01,
    maximum_value=0.99,
    reverse_acting=True,
    kp=25.8,
    ti=400.1,
    td=0.0,
)

print("loop ready:", loop.loop_ready)
print("transmitter:", loop.transmitter_class)
for step in loop.controller_steps:
    print("-", step)
