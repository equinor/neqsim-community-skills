"""Example: split a C7+ plus fraction and delump a lumped composition.

Run with:  python examples/split_example.py
"""

import math

from pseudocomponent_split import (
    calculate_split_factor,
    delump_composition,
    gamma_mole_split,
)


def main() -> None:
    split = gamma_mole_split(
        z_plus=0.05,
        m_plus=220.0,
        boundaries=[90.0, 140.0, 200.0, 300.0, math.inf],
        alpha=1.0,
        eta=90.0,
    )
    print("Pseudocomponent mole fractions:", [round(x, 5) for x in split.mole_fractions])
    print("Pseudocomponent molar masses  :", [round(x, 1) for x in split.molar_masses])

    full = [0.70, 0.10, 0.06, 0.04, 0.03, 0.07]
    scheme = [[0], [1, 2], [3, 4, 5]]
    sf = calculate_split_factor(full, scheme)
    detailed = delump_composition(list(sf.lump_totals), sf.split_factors, scheme)
    print("Split factors                 :", [round(x, 4) for x in sf.split_factors])
    print("Delumped detailed composition :", [round(x, 4) for x in detailed])


if __name__ == "__main__":
    main()
