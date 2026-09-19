from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resource_classification_screening import ResourceClassificationModel


def main() -> None:
    model = ResourceClassificationModel()
    result = model.evaluate(
        maturity_stage="justified for development",
    )

    print("Resource classification screening result")
    print(f"resource_class={result.resource_class}")
    print(f"resource_category={result.resource_category}")
    print(f"sodir_resource_class={result.sodir_resource_class}")
    print(f"sodir_resource_category={result.sodir_resource_category}")
    print(f"prms_category={result.prms_category}")
    print(f"uncertainty_basis={result.uncertainty_basis}")
    print(f"maturity_warning={result.maturity_warning}")
    print(f"neqsim_available={result.neqsim_available}")


if __name__ == "__main__":
    main()
