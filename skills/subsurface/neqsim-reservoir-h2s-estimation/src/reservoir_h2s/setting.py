"""Depositional setting of a reservoir formation, as far as it matters for the pyrite and Fe-carbonate H2S buffer.

Marine and paralic sandstones of the Norwegian shelf carry pyrite and siderite or ankerite, so the buffer assemblage
is complete. Continental red beds are oxidised (hematite, little pyrite) and hold less H2S than the buffer. Carbonates
and evaporites can hold more when anhydrite reacts with hydrocarbons at high temperature. The lists use the public
lithostratigraphic names of the Norwegian Offshore Directorate.
"""

from __future__ import annotations

import re
from typing import Any

MARINE = "marine or paralic"
CONTINENTAL = "continental red beds"
CARBONATE = "carbonate or evaporite"
UNKNOWN = "unknown"
SETTINGS = (MARINE, CONTINENTAL, CARBONATE, UNKNOWN)

#: Triassic and Permian continental formations and groups (red beds, aeolian and alluvial deposits).
CONTINENTAL_KEYS = (
    "skagerrak",
    "lunde",
    "teist",
    "lomvi",
    "hegre",
    "smith bank",
    "rotliegend",
    "alke",
    "red beds",
)
#: Chalk, carbonate and evaporite units.
CARBONATE_KEYS = (
    "zechstein",
    "ekofisk",
    "tor",
    "hod",
    "chalk",
    "gipsdalen",
    "bjarmeland",
    "tempelfjorden",
    "oern",
    "ørn",
    "roeye",
    "røye",
    "isbjoern",
    "isbjørn",
)
_ALIASES = {
    "marine": MARINE,
    "paralic": MARINE,
    "marine / paralic": MARINE,
    "marine or paralic": MARINE,
    "continental": CONTINENTAL,
    "continental (triassic-permian)": CONTINENTAL,
    "continental red beds": CONTINENTAL,
    "red beds": CONTINENTAL,
    "carbonate": CARBONATE,
    "evaporite": CARBONATE,
    "chalk": CARBONATE,
    "carbonate or evaporite": CARBONATE,
}


def formation_key(formation: Any) -> str:
    """Return a formation name in lower case without ``Fm.`` and ``Gp.`` (first name of a semicolon list).

    Args:
        formation: Formation or group name, or a semicolon-separated list of names.

    Returns:
        Normalised name; an empty string for a missing value.
    """
    if not isinstance(formation, str) or not formation.strip():
        return ""
    first = formation.split(";")[0].lower()
    first = re.sub(r"\b(formation|group|fm|gp)\b\.?", " ", first)
    first = " ".join(first.split())
    return first.strip(" .")


def classify_setting(formation: Any = None, setting: Any = None) -> str:
    """Classify the depositional setting from a declared setting or from the formation name.

    Args:
        formation: Formation or group name.
        setting: Setting declared by the user or stored with a well; wins over the formation name.

    Returns:
        One of :data:`SETTINGS`. A formation that is named but not in the continental or carbonate lists is taken as
        marine or paralic, the setting of most sandstone reservoirs on the shelf.
    """
    if isinstance(setting, str) and setting.strip():
        text = setting.strip().lower()
        if text in _ALIASES:
            return _ALIASES[text]
        if text in SETTINGS:
            return text
    key = formation_key(formation)
    if not key:
        return UNKNOWN
    words = key.replace("/", " ").split()
    if any(k in key for k in CONTINENTAL_KEYS):
        return CONTINENTAL
    if any((k in words) if len(k) <= 3 else (k in key) for k in CARBONATE_KEYS):
        return CARBONATE
    return MARINE
