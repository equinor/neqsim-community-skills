"""Guide-word/parameter seeds per equipment type for HAZOP node preparation.

The pairs are placeholders to challenge in a facilitated HAZOP, not findings. Guide words
follow IEC 61882 (NO, MORE, LESS, AS WELL AS, PART OF, REVERSE, OTHER THAN).
"""

from __future__ import annotations

# Equipment type -> seeded (guide word, parameter) deviation pairs.
EQUIPMENT_DEVIATION_SEEDS: dict[str, list[tuple[str, str]]] = {
    "separator": [("MORE", "LEVEL"), ("LESS", "LEVEL"), ("MORE", "PRESSURE")],
    "compressor": [("MORE", "PRESSURE"), ("LESS", "FLOW"), ("MORE", "TEMPERATURE")],
    "pump": [("NO", "FLOW"), ("MORE", "PRESSURE")],
    "heater": [("MORE", "TEMPERATURE"), ("LESS", "FLOW")],
    "heatexchanger": [("MORE", "TEMPERATURE"), ("LESS", "FLOW")],
    "cooler": [("LESS", "TEMPERATURE"), ("MORE", "FLOW")],
    "valve": [("MORE", "FLOW"), ("NO", "FLOW")],
    "throttlingvalve": [("MORE", "FLOW"), ("NO", "FLOW")],
    "pipeline": [("LESS", "FLOW"), ("MORE", "PRESSURE")],
    # A machine auxiliary is a separate node from the machine: its deviations are
    # supply-side and containment-side, not head/flow-side.
    "sealgas": [
        ("LESS", "FLOW"),
        ("NO", "FLOW"),
        ("REVERSE", "FLOW"),
        ("MORE", "PRESSURE"),
        ("LESS", "TEMPERATURE"),
        ("AS WELL AS", "CONTAMINATION"),
    ],
    "separationgas": [("NO", "FLOW"), ("LESS", "PRESSURE"), ("REVERSE", "FLOW")],
    "sealvent": [
        ("NO", "FLOW"),
        ("MORE", "PRESSURE"),
        ("LESS", "TEMPERATURE"),
        ("OTHER THAN", "DESTINATION"),
    ],
    "lubeoil": [
        ("NO", "FLOW"),
        ("MORE", "PRESSURE"),
        ("MORE", "TEMPERATURE"),
        ("AS WELL AS", "CONTAMINATION"),
    ],
    "flare": [("MORE", "PRESSURE"), ("NO", "FLOW"), ("LESS", "TEMPERATURE")],
    "vent": [("NO", "FLOW"), ("MORE", "PRESSURE"), ("LESS", "TEMPERATURE")],
}

# Aliases so a caller's natural wording resolves to the same seed set.
EQUIPMENT_TYPE_ALIASES: dict[str, str] = {
    "dry gas seal": "sealgas",
    "drygasseal": "sealgas",
    "dgs": "sealgas",
    "seal gas": "sealgas",
    "seal-gas": "sealgas",
    "sealgassystem": "sealgas",
    "separation gas": "separationgas",
    "buffer gas": "separationgas",
    "seal vent": "sealvent",
    "primary vent": "sealvent",
    "secondary vent": "sealvent",
    "lube oil": "lubeoil",
    "lubeoilconsole": "lubeoil",
    "heat exchanger": "heatexchanger",
    "throttling valve": "throttlingvalve",
}

# Fallback when the equipment type is not recognised.
DEFAULT_DEVIATION_SEEDS: list[tuple[str, str]] = [
    ("MORE", "PRESSURE"),
    ("MORE", "TEMPERATURE"),
]


def normalise_equipment_type(equipment_type: str) -> str:
    """Fold a caller-supplied equipment type onto a seeding key.

    Accepts spaced, hyphenated and abbreviated wording ("dry gas seal", "DGS") so a node
    does not silently fall back to the two-row default seed. An unknown type is returned
    lower-cased and otherwise unchanged.
    """
    key = str(equipment_type or "").strip().lower()
    if not key:
        return ""
    if key in EQUIPMENT_DEVIATION_SEEDS:
        return key
    if key in EQUIPMENT_TYPE_ALIASES:
        return EQUIPMENT_TYPE_ALIASES[key]
    collapsed = key.replace("-", " ").replace("_", " ")
    if collapsed in EQUIPMENT_TYPE_ALIASES:
        return EQUIPMENT_TYPE_ALIASES[collapsed]
    squeezed = collapsed.replace(" ", "")
    if squeezed in EQUIPMENT_DEVIATION_SEEDS:
        return squeezed
    return EQUIPMENT_TYPE_ALIASES.get(squeezed, key)
