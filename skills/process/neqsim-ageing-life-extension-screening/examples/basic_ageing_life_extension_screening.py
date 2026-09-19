from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ageing_life_extension_screening import AgeingLifeExtensionModel


def main() -> None:
    model = AgeingLifeExtensionModel()

    # A population observed for 18 years whose failures cluster towards the end.
    failures = [3.1, 6.4, 9.0, 11.2, 12.4, 13.1, 14.0, 14.8, 15.5, 16.1, 16.6, 17.0, 17.5, 17.9]

    result = model.evaluate(
        failure_times_years=failures,
        observation_years=18.0,
        target_year_offset=11.0,
        population_size=168,
        replacement_cost=1.0e7,
        corrective_cost_per_failure=1.5e5,
        annual_cost_of_ownership=3.0e5,
        discount_rate=0.07,
    )

    print("Failures observed:", result.n_failures)
    print("Laplace U:", round(result.laplace_u, 3), "->", result.laplace_verdict)
    print(
        "Crow-AMSAA beta:",
        round(result.crow_amsaa_beta, 3),
        f"[{result.beta_confidence_low:.3f}, {result.beta_confidence_high:.3f}]",
    )
    print("Rate now (per item-year):", round(result.rate_now_per_year, 5))
    print("Rate at target (per item-year):", round(result.rate_at_target_per_year, 5))
    print("Rate ratio target/now:", round(result.rate_ratio_target_over_now, 3))
    print("Expected failures to target:", round(result.expected_failures_to_target, 1))
    print("  of which excess from ageing:", round(result.excess_failures_from_ageing, 1))
    print("Ageing verdict:", result.ageing_verdict)
    print("Life-extension verdict:", result.life_extension_verdict)
    print("Replacement crossover (years):", result.replacement_crossover_year)
    print("Assumptions:")
    for line in result.assumptions:
        print("  -", line)


if __name__ == "__main__":
    main()
