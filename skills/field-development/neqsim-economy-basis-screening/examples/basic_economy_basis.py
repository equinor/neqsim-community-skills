"""Minimal example for the economy-basis screening skill."""

from economy_basis_screening import EconomyBasisModel


def main() -> None:
    model = EconomyBasisModel()
    result = model.evaluate(
        gas_price_per_sm3=0.30,
        oil_price_per_bbl=70.0,
        discount_rate=0.08,
        currency="USD",
        inflation_rate=0.02,
        real_terms=True,
        tax_regime="norwegian-ncs",
    )

    print(f"Currency:             {result.currency}")
    print(f"Discount rate:        {result.discount_rate:.3f} [{result.discount_rate_flag}]")
    print(f"Tax regime:           {result.tax_regime} (recognized={result.tax_regime_recognized})")
    print(f"Basis warning:        {result.basis_warning}")
    if result.flags:
        print("Flags:")
        for flag in result.flags:
            print(f"  - {flag}")


if __name__ == "__main__":
    main()
