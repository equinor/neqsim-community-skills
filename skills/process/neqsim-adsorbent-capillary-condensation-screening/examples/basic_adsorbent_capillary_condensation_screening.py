"""Methanol limit for a mercury guard bed, by sorbent pore size.

The saturation mole fraction used here was computed with NeqSim SRK-CPA for a
rich natural gas at 20 C and 70 bara. Do not replace it with Psat/P.
"""

from adsorbent_capillary_condensation_screening import (
    CapillaryCondensationScreeningModel,
    micropore_filling_fraction,
)

TEMPERATURE = 293.15
SURFACE_TENSION = 0.0225
MOLAR_VOLUME = 40.7e-6
Y_SAT = 3.553e-3

SORBENTS = [
    ("Ag on molecular sieve", 0.45),
    ("S-impregnated activated carbon", 1.5),
    ("Metal sulphide on alumina", 6.0),
]


def main():
    model = CapillaryCondensationScreeningModel()
    print(f"Bulk methanol saturation: {Y_SAT * 1e6:.0f} ppmv\n")
    print(f"{'sorbent':32s} {'r [nm]':>7} {'a_c':>7} {'limit [ppmv]':>13} {'Kelvin ok':>10}")
    for name, radius in SORBENTS:
        result = model.evaluate(
            temperature=TEMPERATURE,
            surface_tension=SURFACE_TENSION,
            molar_volume=MOLAR_VOLUME,
            pore_radius_nm=radius,
            saturation_mole_fraction=Y_SAT,
        )
        print(f"{name:32s} {radius:7.2f} {result.onset_relative_saturation:7.3f} "
              f"{result.max_ppmv:13.0f} {str(result.kelvin_valid):>10}")

    print("\nMicropore volume filling (Dubinin-Radushkevich), beta*E0 = 8 kJ/mol:")
    for ppmv in (25, 100, 250, 500, 1000):
        activity = ppmv * 1e-6 / Y_SAT
        filling = micropore_filling_fraction(activity, TEMPERATURE, characteristic_energy=8000.0)
        print(f"  {ppmv:5d} ppmv -> activity {activity:6.4f} -> {filling * 100:5.1f} % of micropore volume filled")

    print("\nFor a microporous sorbent the micropore filling limit is one to two orders")
    print("of magnitude tighter than the Kelvin limit, which is why guard bed methanol")
    print("specifications sit in the tens to low hundreds of ppmv.")


if __name__ == "__main__":
    main()
