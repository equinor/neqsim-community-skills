"""Public standard equipment size tables and round-up-to-standard helpers.

Pipe outside diameters follow ASME B36.10M/B36.19M (NPS) and EN 10220 (DN); the
relief valve orifice grid follows API 526; the flange classes follow ASME B16.5.
The motor power series and the vessel and tube conventions are typical practice and
must be confirmed against the project, company or vendor specification.
"""

# NPS -> outside diameter in mm (ASME B36.10M). The wall thickness depends on the schedule.
NPS_OD_MM = {
    0.5: 21.3, 0.75: 26.7, 1.0: 33.4, 1.5: 48.3, 2.0: 60.3, 3.0: 88.9, 4.0: 114.3,
    6.0: 168.3, 8.0: 219.1, 10.0: 273.1, 12.0: 323.9, 14.0: 355.6, 16.0: 406.4,
    18.0: 457.2, 20.0: 508.0, 24.0: 609.6, 30.0: 762.0, 36.0: 914.4, 42.0: 1066.8,
    48.0: 1219.2,
}

# Sizes often avoided in process piping specifications (typical practice, not a standard).
NON_PREFERRED_NPS = (1.25, 2.5, 3.5, 5.0)

# NPS -> DN (ISO 6708).
NPS_TO_DN = {
    0.5: 15, 0.75: 20, 1.0: 25, 1.5: 40, 2.0: 50, 3.0: 80, 4.0: 100, 6.0: 150,
    8.0: 200, 10.0: 250, 12.0: 300, 14.0: 350, 16.0: 400, 18.0: 450, 20.0: 500,
    24.0: 600, 30.0: 750, 36.0: 900, 42.0: 1050, 48.0: 1200,
}

# API 526 effective orifice areas in in2 (letter designations D to T).
API526_ORIFICE_IN2 = {
    "D": 0.110, "E": 0.196, "F": 0.307, "G": 0.503, "H": 0.785, "J": 1.287,
    "K": 1.838, "L": 2.853, "M": 3.60, "N": 4.34, "P": 6.38, "Q": 11.05,
    "R": 16.00, "T": 26.00,
}
IN2_TO_MM2 = 645.16

# ASME B16.5 classes and ambient (-29 to 38 C) pressure rating of group 1.1 carbon steel, barg.
B165_CLASS_AMBIENT_BARG = (
    (150, 19.6), (300, 51.0), (600, 102.0), (900, 153.1), (1500, 255.3), (2500, 425.4),
)

# Typical IEC motor rated powers in kW.
MOTOR_KW_SERIES = (
    0.75, 1.1, 1.5, 2.2, 3.0, 4.0, 5.5, 7.5, 11.0, 15.0, 18.5, 22.0, 30.0, 37.0, 45.0,
    55.0, 75.0, 90.0, 110.0, 132.0, 160.0, 200.0, 250.0, 315.0, 355.0, 400.0, 450.0,
    500.0, 560.0, 630.0, 710.0, 800.0, 900.0, 1000.0,
)

# TEMA-style straight tube lengths in m (8, 10, 12, 16, 20 ft) and common tube outside diameters in mm.
TUBE_LENGTHS_M = (2.44, 3.05, 3.66, 4.88, 6.10)
TUBE_OD_MM = (19.05, 25.4)


def nps_od_mm(nps):
    """Return the outside diameter in mm for a nominal pipe size.

    Args:
        nps: nominal pipe size in inches, for example 4.0 or 0.75.

    Returns:
        Outside diameter in mm.

    Raises:
        ValueError: if the NPS is not in the table.
    """
    if nps not in NPS_OD_MM:
        raise ValueError("NPS %s is not a tabulated size" % nps)
    return NPS_OD_MM[nps]


def select_pipe_nps(required_inside_diameter_mm, wall_thickness_mm):
    """Select the smallest preferred NPS whose inside diameter meets the requirement.

    The same wall thickness is assumed for every size, which is conservative for
    small sizes and optimistic for large ones; recheck with the actual schedule.

    Args:
        required_inside_diameter_mm: required inside diameter in mm.
        wall_thickness_mm: assumed wall thickness in mm.

    Returns:
        Dict with nps, dn, outside_diameter_mm and inside_diameter_mm.

    Raises:
        ValueError: if an input is not positive or no tabulated size is large enough.
    """
    if required_inside_diameter_mm <= 0 or wall_thickness_mm <= 0:
        raise ValueError("diameter and wall thickness must be positive")
    for nps in sorted(NPS_OD_MM):
        inside = NPS_OD_MM[nps] - 2.0 * wall_thickness_mm
        if inside >= required_inside_diameter_mm:
            return {
                "nps": nps,
                "dn": NPS_TO_DN[nps],
                "outside_diameter_mm": NPS_OD_MM[nps],
                "inside_diameter_mm": round(inside, 1),
            }
    raise ValueError("no tabulated NPS meets the required inside diameter")


def select_api526_orifice(required_area_mm2):
    """Select the smallest API 526 orifice letter that meets a required effective area.

    Args:
        required_area_mm2: required effective orifice area in mm2.

    Returns:
        Dict with letter, area_mm2 and margin_fraction, or letter None when the
        requirement exceeds orifice T and several valves are needed.

    Raises:
        ValueError: if the required area is not positive.
    """
    if required_area_mm2 <= 0:
        raise ValueError("required area must be positive")
    for letter, area_in2 in API526_ORIFICE_IN2.items():
        area_mm2 = area_in2 * IN2_TO_MM2
        if area_mm2 >= required_area_mm2:
            return {
                "letter": letter,
                "area_mm2": round(area_mm2, 1),
                "margin_fraction": round(area_mm2 / required_area_mm2 - 1.0, 3),
            }
    return {"letter": None, "area_mm2": None, "margin_fraction": None}


def next_motor_kw(required_shaft_kw, margin_fraction=0.0):
    """Return the next typical IEC motor rating at or above the required power.

    Args:
        required_shaft_kw: required shaft power in kW.
        margin_fraction: design margin on top of the power, for example 0.1.

    Returns:
        Motor rating in kW.

    Raises:
        ValueError: if the power is not positive, the margin is negative, or the
            power exceeds the series.
    """
    if required_shaft_kw <= 0 or margin_fraction < 0:
        raise ValueError("power must be positive and the margin not negative")
    target = required_shaft_kw * (1.0 + margin_fraction)
    for rating in MOTOR_KW_SERIES:
        if rating >= target:
            return rating
    raise ValueError("required power exceeds the tabulated motor series")


def lowest_b165_class_ambient(design_pressure_barg):
    """Return the lowest ASME B16.5 class whose ambient group 1.1 rating covers the pressure.

    The rating falls with temperature and depends on the material group, so this is
    only a first screen. Use the B16.5 pressure-temperature table at the design temperature.

    Args:
        design_pressure_barg: design pressure in barg.

    Returns:
        Flange class number.

    Raises:
        ValueError: if the pressure is not positive or exceeds class 2500.
    """
    if design_pressure_barg <= 0:
        raise ValueError("design pressure must be positive")
    for flange_class, rating in B165_CLASS_AMBIENT_BARG:
        if rating >= design_pressure_barg:
            return flange_class
    raise ValueError("pressure exceeds class 2500 at ambient temperature")


def next_tube_length_m(required_length_m):
    """Return the shortest standard straight tube length that covers the requirement.

    Args:
        required_length_m: required tube length in m.

    Returns:
        Standard tube length in m.

    Raises:
        ValueError: if the length is not positive or exceeds the longest standard length.
    """
    if required_length_m <= 0:
        raise ValueError("length must be positive")
    for length in TUBE_LENGTHS_M:
        if length >= required_length_m:
            return length
    raise ValueError("required length exceeds the longest standard tube length")


def round_up_vessel_diameter_mm(required_inside_diameter_mm, step_mm=100.0):
    """Round a vessel inside diameter up to the next fabrication step.

    The step is a convention (commonly 50 or 100 mm, or 6 in); take it from the
    company or fabricator specification.

    Args:
        required_inside_diameter_mm: required inside diameter in mm.
        step_mm: rounding step in mm.

    Returns:
        Rounded inside diameter in mm.

    Raises:
        ValueError: if the diameter or the step is not positive.
    """
    if required_inside_diameter_mm <= 0 or step_mm <= 0:
        raise ValueError("diameter and step must be positive")
    steps = -(-required_inside_diameter_mm // step_mm)
    return float(steps * step_mm)
