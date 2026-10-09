from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from psc_bid_economics_screening import PscBidModel


def main() -> None:
    production = [10.0, 25.0, 30.0, 28.0, 24.0, 20.0, 16.0, 13.0, 10.0, 8.0]
    capex = [900.0, 900.0, 400.0, 0, 0, 0, 0, 0, 0, 0]
    opex = [20.0, 60.0, 80.0, 80.0, 75.0, 70.0, 65.0, 60.0, 55.0, 50.0]
    result = PscBidModel(oil_price=70.0, discount_rate=0.10).evaluate(
        production,
        capex,
        opex,
        profit_oil_share_offered=0.25,
        chance_of_discovery=0.45,
        working_interest=0.70,
        signature_bonus_musd=20.0,
        exploration_program_musd=60.0,
    )
    print("PSC bid screening result (synthetic example)")
    print(f"emv_musd={result.emv_musd:.1f}")
    print(f"break_even_profit_oil_share={result.break_even_profit_oil_share:.3f}")
    print(f"government_take={result.government_take:.3f}")
    print(f"bid_verdict={result.bid_verdict}")


if __name__ == "__main__":
    main()
