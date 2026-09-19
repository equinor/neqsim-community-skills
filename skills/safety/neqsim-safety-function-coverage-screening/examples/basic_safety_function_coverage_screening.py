from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from safety_function_coverage_screening import SafetyFunctionCoverageModel


def main() -> None:
    model = SafetyFunctionCoverageModel()
    result = model.evaluate(
        component_type="separator",
        provided_functions=["PSH", "PSL", "PSV", "LSH"],
    )

    print("Safety function coverage screening result")
    print(f"component_type={result.component_type}")
    print(f"required_functions={result.required_functions}")
    print(f"provided_functions={result.provided_functions}")
    print(f"missing_functions={result.missing_functions}")
    print(f"coverage_ratio={result.coverage_ratio}")
    print(f"coverage_warning={result.coverage_warning}")
    print(f"neqsim_available={result.neqsim_available}")


if __name__ == "__main__":
    main()
