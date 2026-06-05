from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from process_factory import build_plan, neqsim_available


def main() -> None:
    section = {
        "section_id": "demo",
        "flow_path": [
            {"type": "node", "id": "inlet"},
            {"type": "segment", "id": "S1", "length_m": 50.0, "inner_diameter_m": 0.45,
             "fittings": [{"type": "elbow_90", "count": 4}]},
            {"type": "equipment", "id": "scrubber", "equipment_type": "gas_scrubber"},
            {"type": "parallel", "split_factors": [0.5, 0.5], "branches": [
                [{"type": "segment", "id": "A1", "length_m": 20.0, "inner_diameter_m": 0.3}],
                [{"type": "segment", "id": "B1", "length_m": 20.0, "inner_diameter_m": 0.3}],
            ]},
            {"type": "node", "id": "outlet"},
        ],
    }

    plan = build_plan(section)
    print(f"neqsim available: {neqsim_available()}")
    print(f"planned units ({len(plan)}):")
    for unit in plan:
        detail = ""
        if unit.kind == "pipe":
            detail = f"  effective_length_m={unit.params['effective_length_m']}"
        print(f"  {unit.kind:<22} {unit.name}{detail}")


if __name__ == "__main__":
    main()
