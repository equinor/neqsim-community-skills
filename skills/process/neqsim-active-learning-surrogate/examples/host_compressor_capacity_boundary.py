"""Learn where a tie-in overloads a host export compressor, with NeqSim.

Synthetic host: well stream + new tie-in gas -> mixer -> inlet separator ->
export compressor to 150 bara. Question: for which combinations of tie-in
rate, separator pressure and inlet temperature does the compressor need more
than its 6.5 MW driver, and how likely is that under the stated uncertainty?

The NeqSim flowsheet is run only a few dozen times, at points the limit-state
learner picks near the 6.5 MW boundary. The probability is then taken from
thousands of surrogate evaluations, and the result is spot-checked against
fresh NeqSim runs.

    python examples/host_compressor_capacity_boundary.py
"""

from __future__ import annotations

import time

import numpy as np
from active_learning_surrogate import ActiveLearner, Parameter, validate

DRIVER_LIMIT_KW = 6500.0

HOST = {
    "nitrogen": 0.5,
    "CO2": 1.5,
    "methane": 60.0,
    "ethane": 8.0,
    "propane": 5.0,
    "n-butane": 3.0,
    "n-pentane": 2.0,
    "n-hexane": 2.0,
}
TIE_IN = {
    "nitrogen": 1.0,
    "CO2": 3.0,
    "methane": 80.0,
    "ethane": 8.0,
    "propane": 4.0,
    "n-butane": 2.0,
    "n-pentane": 1.0,
    "n-hexane": 1.0,
}

PARAMETERS = [
    Parameter("tiein_rate_kgh", 0.0, 60000.0),
    Parameter("separator_pressure_bara", 30.0, 70.0),
    Parameter("inlet_temperature_c", 30.0, 70.0),
]


def _fluid(jneqsim, composition, c10, temperature_c, pressure_bara):
    fluid = jneqsim.thermo.system.SystemSrkEos(273.15 + temperature_c, pressure_bara)
    for name, amount in composition.items():
        fluid.addComponent(name, amount)
    fluid.addTBPfraction("C10", c10, 0.14, 0.79)
    fluid.setMixingRule("classic")
    return fluid


def host_model(values: dict[str, float]) -> dict[str, float]:
    """One NeqSim run of the synthetic host (about 0.5 s)."""
    from neqsim import jneqsim

    process = jneqsim.process
    t_c = values["inlet_temperature_c"]
    p_bar = values["separator_pressure_bara"]
    host = process.equipment.stream.Stream(
        "host", _fluid(jneqsim, HOST, 10.0, t_c, p_bar)
    )
    host.setFlowRate(150000.0, "kg/hr")
    tiein = process.equipment.stream.Stream(
        "tie-in", _fluid(jneqsim, TIE_IN, 0.5, t_c, p_bar)
    )
    tiein.setFlowRate(max(values["tiein_rate_kgh"], 1.0), "kg/hr")
    for stream in (host, tiein):
        stream.setTemperature(t_c, "C")
        stream.setPressure(p_bar, "bara")
    mixer = process.equipment.mixer.Mixer("inlet mixer")
    mixer.addStream(host)
    mixer.addStream(tiein)
    separator = process.equipment.separator.Separator(
        "inlet separator", mixer.getOutletStream()
    )
    compressor = process.equipment.compressor.Compressor(
        "export compressor", separator.getGasOutStream()
    )
    compressor.setOutletPressure(150.0)
    compressor.setIsentropicEfficiency(0.75)
    system = process.processmodel.ProcessSystem()
    for unit in (host, tiein, mixer, separator, compressor):
        system.add(unit)
    system.run()
    return {
        "compressor_power_kw": float(compressor.getPower("kW")),
        "export_gas_msm3d": float(separator.getGasOutStream().getFlowRate("MSm3/day")),
    }


def main() -> int:
    try:
        import neqsim  # noqa: F401
    except ImportError:
        print("SKIPPED: python -m pip install neqsim")
        return 0

    learner = ActiveLearner(
        model=host_model,
        parameters=PARAMETERS,
        outputs=["compressor_power_kw", "export_gas_msm3d"],
        mode="limit_state",
        limit_output="compressor_power_kw",
        threshold=DRIVER_LIMIT_KW,
        max_evaluations=40,
        pool_size=3000,
        callback=lambda r: print(
            f"  evaluations={r.evaluations:3d}  min U={r.min_u:6.2f}  "
            f"Q2(power)={r.q2['compressor_power_kw']:.4f}"
        ),
    )
    print("Learning the 6.5 MW boundary with NeqSim:")
    result = learner.run()
    surrogate = result.surrogate
    print(
        f"{result.stop_reason}; {result.evaluations} NeqSim runs "
        f"({result.model_time_s:.1f} s), {result.failures} failed"
    )

    # Uncertain operating envelope (synthetic): tie-in rate triangular
    # 10/35/55 t/h, separator 40-60 bara, inlet 35-60 C.
    rng = np.random.default_rng(1)
    n = 20000
    population = [
        {
            "tiein_rate_kgh": r,
            "separator_pressure_bara": p,
            "inlet_temperature_c": t,
        }
        for r, p, t in zip(
            rng.triangular(10000.0, 35000.0, 55000.0, n),
            rng.uniform(40.0, 60.0, n),
            rng.uniform(35.0, 60.0, n),
        )
    ]
    t0 = time.perf_counter()
    probability = surrogate.exceedance_probability(population)
    power = surrogate.predict(population)["compressor_power_kw"][0]
    elapsed = time.perf_counter() - t0
    p10, p50, p90 = np.percentile(power, [10, 50, 90])
    print(
        f"\n{n} surrogate evaluations in {elapsed:.2f} s "
        f"(direct NeqSim would take about {n * 0.5 / 3600:.1f} h)"
    )
    print(f"Compressor power P10/P50/P90: {p10:,.0f} / {p50:,.0f} / {p90:,.0f} kW")
    print(f"Probability of exceeding {DRIVER_LIMIT_KW:,.0f} kW: {probability:.1%}")

    # Highest tie-in rate that stays below the limit at the worst corner.
    worst = {"separator_pressure_bara": 40.0, "inlet_temperature_c": 60.0}
    rates = np.linspace(0.0, 60000.0, 601)
    mean = surrogate.predict([{**worst, "tiein_rate_kgh": r} for r in rates])[
        "compressor_power_kw"
    ][0]
    allowed = rates[mean <= DRIVER_LIMIT_KW]
    if len(allowed):
        print(
            f"Max tie-in rate at 40 bara / 60 C: {allowed.max() / 1000:.1f} t/h "
            "(surrogate)"
        )

    report = validate(surrogate, host_model, n=8, seed=5)
    print(
        f"\nSpot check vs {report.points} fresh NeqSim runs: "
        f"side-of-limit agreement {report.classification_agreement:.0%}, "
        f"max power error {report.max_abs_error['compressor_power_kw']:,.0f} kW"
    )

    try:
        from uncertainty_quantification import Triangular, UncertaintyStudy, Uniform
    except ImportError:
        return 0
    study = UncertaintyStudy(
        parameters=[
            Triangular(
                "tiein_rate_kgh", "kg/h", low=10000, base_value=35000, high=55000
            ),
            Uniform("separator_pressure_bara", "bara", low=40, high=60),
            Uniform("inlet_temperature_c", "C", low=35, high=60),
        ],
        output_name="compressor_power_kw",
        output_unit="kW",
        model=surrogate.as_model("compressor_power_kw"),
        simulation_engine="NeqSim via active-learning surrogate",
    )
    summary = study.run(2000).summary
    print(
        f"neqsim-uncertainty-quantification on the surrogate: "
        f"P10/P50/P90 = {summary.p10:,.0f} / {summary.p50:,.0f} / {summary.p90:,.0f} kW"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
