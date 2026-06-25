---
name: neqsim-dynamic-instrument-controller-setup
version: "0.1.0"
description: "Set up measurement devices and PID-style controllers for NeqSim dynamic process simulations. USE WHEN: a task needs to add transmitters, controller devices, valve manipulation, setpoints, controller action, and autotuning workflow guidance before runTransient calculations."
last_verified: "2026-06-25"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Dynamic Instrument Controller Setup

Use this skill when an agent must add instruments and controllers to a NeqSim dynamic process model. It documents transmitter selection, controller configuration, valve or equipment manipulation, direct/reverse action checks, and transient validation.

## When to Use

- When a dynamic NeqSim model needs level, pressure, temperature, or flow measurement devices.
- When a process valve or unit should be manipulated by a controller during `runTransient()`.
- When an agent needs to create public controller setup guidance with setpoints, min/max transmitter ranges, and PID parameters.
- When controller event logs and `autoTuneFromEventLog(False)` should be used for tuning studies.

## Inputs

- `loop_name`: public loop identifier such as `LC-001` or `PC-001`.
- `controlled_variable`: measured variable such as `level`, `pressure`, `temperature`, or `flow`.
- `transmitter_target`: NeqSim unit or stream that the transmitter measures.
- `manipulated_equipment`: valve or equipment receiving the controller.
- `setpoint`: controller setpoint in the same basis as the transmitter.
- `minimum_value` and `maximum_value`: transmitter validation range.
- `reverse_acting`: whether controller output decreases when measured value increases.
- `kp`, `ti`, `td`: PID parameters for `ControllerDeviceBaseClass#setControllerParameters(...)`.

## Outputs

- `loop_ready`: boolean indicator for whether the supplied loop metadata is complete and internally consistent.
- `transmitter_class`: recommended NeqSim transmitter class.
- `controller_steps`: NeqSim API sequence for creating and attaching the control loop.
- `validation_warnings`: missing range, action, setpoint, or tuning issues.
- `autotune_steps`: optional event-log and setpoint-step workflow.

## Engineering Method

The Python class `DynamicInstrumentControllerModel` is a public control-loop setup checker. It does not tune or run NeqSim. It maps a controlled variable to a known NeqSim measurement-device class and validates that the controller metadata is sufficient for a dynamic simulation workflow.

The controller guidance uses NeqSim's dynamic control pattern:

1. Create a measurement device for the measured unit or stream.
2. Set transmitter minimum and maximum values.
3. Create `ControllerDeviceBaseClass`.
4. Attach the transmitter.
5. Set direct or reverse action.
6. Set controller setpoint and PID parameters.
7. Attach the controller to the manipulated valve or equipment.
8. Run transient simulation and inspect response, saturation, and stability.

## Python Usage Pattern

```python
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

print(loop.loop_ready)
print(loop.transmitter_class)
print(loop.controller_steps)
```

NeqSim implementation pattern:

```python
lt01 = ns.process.measurementdevice.LevelTransmitter(v001)
lt01.setMaximumValue(0.99)
lt01.setMinimumValue(0.01)

lc01 = ns.process.controllerdevice.ControllerDeviceBaseClass()
lc01.setTransmitter(lt01)
lc01.setReverseActing(True)
lc01.setControllerSetPoint(0.3)
lc01.setControllerParameters(25.8, 400.1, 0.0)

lcv001.setCalculateSteadyState(False)
lcv001.setController(lc01)
process.add(lt01)
process.run()
process.storeInitialState()
process.runTransient()
```

Pressure control example:

```python
pt01 = ns.process.measurementdevice.PressureTransmitter(v001.getGasOutStream())
pc01 = ns.process.controllerdevice.ControllerDeviceBaseClass()
pc01.setTransmitter(pt01)
pc01.setReverseActing(False)
pc01.setControllerSetPoint(5.0)
pc01.setControllerParameters(1.0, 2000.0, 0.0)
pcv001.setController(pc01)
```

Autotuning workflow:

```python
lc01.resetEventLog()
lc01.setControllerSetPoint(0.33)
# run transient steps and collect response
lc01.setControllerSetPoint(0.27)
# run transient steps and collect response
tuned = lc01.autoTuneFromEventLog(False)
print(lc01.getKp(), lc01.getTi(), lc01.getTd())
```

## Validation Checklist

- [ ] Controlled variable is mapped to the correct NeqSim transmitter class.
- [ ] Transmitter minimum and maximum values bracket the setpoint and expected operating range.
- [ ] Controller action is documented as reverse or direct acting.
- [ ] Manipulated equipment supports controller attachment and dynamic mode.
- [ ] PID parameters are finite and appropriate for a first transient trial.
- [ ] Transient response is checked for saturation, instability, and nonphysical states.
- [ ] Autotuning is only applied after a deliberate event-log excitation sequence.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Controller drives the valve in the wrong direction | Reverse/direct action is wrong | Check process cause and effect, then set `setReverseActing(True/False)` correctly |
| Controller never responds | Transmitter or controller was not added or attached | Add the measurement device to the process and attach the controller to manipulated equipment |
| Output saturates at valve limit | Transmitter range, setpoint, or PID gain is unrealistic | Check min/max range, setpoint basis, valve opening limits, and PID parameters |
| Autotune gives poor parameters | Event log does not contain a clear response | Reset event log, apply deliberate setpoint steps, and run enough transient time |

## Limitations

- The Python helper does not run NeqSim and does not replace controller tuning.
- No proprietary control narratives, operating procedures, or safety instrumented functions are included.
- PID parameters are setup metadata, not a guarantee of stable operation.
- Human review is required before engineering or operational decisions.

## Related NeqSim Functionality

- `neqsim.process.measurementdevice.LevelTransmitter` — separator/vessel level measurement.
- `neqsim.process.measurementdevice.PressureTransmitter` — pressure measurement on streams or equipment outlets.
- `neqsim.process.measurementdevice.TemperatureTransmitter` and `VolumeFlowTransmitter` — stream temperature and volume-flow measurements.
- `neqsim.process.controllerdevice.ControllerDeviceBaseClass` — transmitter-based dynamic controller with setpoint, action, PID parameters, response, event log, and autotuning support.
- `neqsim.process.equipment.valve.ThrottlingValve#setController(...)` — attach a controller to a manipulated valve.
- `neqsim.process.processmodel.ProcessSystem#runTransient()` — execute the controlled dynamic process.

In Python these classes are reachable through the `neqsim` package, for example `from neqsim import jneqsim`.

## References

- NeqSim repository: https://github.com/equinor/neqsim
- NeqSim Skills Guide: https://github.com/equinor/neqsim/blob/master/docs/integration/skills_guide.md
- Public NeqSim dynamic separator and process-control examples.
