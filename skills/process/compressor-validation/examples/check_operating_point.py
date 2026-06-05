from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from compressor_validation import (
    ChartTuning,
    CompressorCurve,
    Drivetrain,
    evaluate_operating_point,
    polytropic_head,
)


def main() -> None:
    curve = CompressorCurve(
        speed_lines={
            9000: [(5000, 80_000, 0.78), (7000, 72_000, 0.80), (9000, 60_000, 0.77)],
            10000: [(5500, 99_000, 0.78), (7700, 89_000, 0.80), (9900, 74_000, 0.77)],
        }
    )

    head = polytropic_head(
        p_in=60.0, p_out=120.0, T_in=313.0, MW=20.0, Z=0.9, k=1.28, eta_p=0.78
    )
    print(f"polytropic head [J/kg]: {head:.0f}")

    op = evaluate_operating_point(
        curve, flow=7000, speed=9500, mass_flow=90.0,
        p_in=60.0, p_out=120.0, T_in=313.0, MW=20.0, Z=0.9, k=1.28,
        tuning=ChartTuning(head_mult=1.02),
        drivetrain=Drivetrain(gear_ratio=1.0, mechanical_loss_frac=0.02),
    )
    print(f"curve head [J/kg]:    {op.curve_head:.0f}")
    print(f"measured head [J/kg]: {op.measured_head:.0f}")
    print(f"head deviation [%]:   {op.head_deviation_pct:.2f}")
    print(f"efficiency:           {op.efficiency:.3f}")
    print(f"gas power [MW]:       {op.gas_power_W / 1e6:.3f}")
    print(f"shaft power [MW]:     {op.shaft_power_W / 1e6:.3f}")
    print(f"extrapolated:         {op.extrapolated}")


if __name__ == "__main__":
    main()
