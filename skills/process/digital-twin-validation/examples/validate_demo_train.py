from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from digital_twin_validation import (
    ChannelSpec,
    Tolerance,
    ValidationReport,
    evaluate_point,
)


def main() -> None:
    specs = [
        ChannelSpec("suction_pressure", Tolerance(0.5, "abs"), unit="bara"),
        ChannelSpec("discharge_temperature", Tolerance(2.0, "abs"), unit="C"),
        ChannelSpec("power", Tolerance(5.0, "pct"), unit="MW"),
    ]

    report = ValidationReport(name="demo-train")
    report.add(evaluate_point(
        "case_A",
        measured={"suction_pressure": 60.0, "discharge_temperature": 95.0, "power": 12.0},
        simulated={"suction_pressure": 60.3, "discharge_temperature": 96.2, "power": 12.4},
        specs=specs,
    ))
    report.add(evaluate_point(
        "case_B",
        measured={"suction_pressure": 58.0, "discharge_temperature": 90.0, "power": 11.0},
        simulated={"suction_pressure": 59.2, "discharge_temperature": 90.5},
        specs=specs,
    ))

    rate = report.pass_rate()
    print(f"overall status: {report.status}")
    print(f"pass rate: {'n/a' if rate is None else f'{rate * 100:.1f}%'}")
    for row in report.summary_rows():
        verdict = "SKIP" if row["passed"] is None else ("PASS" if row["passed"] else "FAIL")
        print(f"  {row['point_id']:<8} {row['channel']:<22} {verdict}")

    out = Path(__file__).resolve().parent / "demo_validation_report.html"
    out.write_text(report.to_html(), encoding="utf-8")
    print(f"HTML report written to {out.name}")


if __name__ == "__main__":
    main()
