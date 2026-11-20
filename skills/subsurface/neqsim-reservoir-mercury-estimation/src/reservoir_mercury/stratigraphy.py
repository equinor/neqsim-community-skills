"""Norwegian Continental Shelf lithostratigraphy lookup used to place a reservoir in a mercury source class.

The table maps formation names to their group and epoch (Norwegian Offshore Directorate lithostratigraphic
nomenclature). The source class lumps the epochs by their position relative to the Lower Jurassic interval, where
published work reports mercury-rich marine shales (Toarcian oceanic anoxic event, Karoo-Ferrar volcanism) and
coal-bearing coastal-plain deposits.
"""

from __future__ import annotations

import re
from typing import Any

#: formation key -> (group, epoch)
FORMATION_TABLE: dict[str, tuple[str, str]] = {
    # Norwegian Sea
    "GARN": ("FANGST GP.", "Jurassic Middle"),
    "NOT": ("FANGST GP.", "Jurassic Middle"),
    "ILE": ("FANGST GP.", "Jurassic Middle"),
    "ROR": ("BAAT GP.", "Jurassic Early"),
    "TOFTE": ("BAAT GP.", "Jurassic Early"),
    "TILJE": ("BAAT GP.", "Jurassic Early"),
    "AARE": ("BAAT GP.", "Jurassic Early"),
    "MELKE": ("VIKING GP.", "Jurassic Late"),
    "ROGN": ("VIKING GP.", "Jurassic Late"),
    "SPEKK": ("VIKING GP.", "Jurassic Late"),
    "LYSING": ("CROMER KNOLL GP.", "Cretaceous Late"),
    "LANGE": ("CROMER KNOLL GP.", "Cretaceous Late"),
    "NISE": ("SHETLAND GP.", "Cretaceous Late"),
    "SPRINGAR": ("SHETLAND GP.", "Cretaceous Late"),
    "KVITNOS": ("SHETLAND GP.", "Cretaceous Late"),
    "EGGA": ("ROGALAND GP.", "Paleocene"),
    "TANG": ("ROGALAND GP.", "Paleocene"),
    # North Sea
    "LUNDE": ("HEGRE GP.", "Triassic Late"),
    "LOMVI": ("HEGRE GP.", "Triassic Middle"),
    "SKAGERRAK": ("HEGRE GP.", "Triassic Late"),
    "STATFJORD": ("STATFJORD GP.", "Jurassic Early"),
    "EIRIKSSON": ("STATFJORD GP.", "Jurassic Early"),
    "NANSEN": ("STATFJORD GP.", "Jurassic Early"),
    "RAUDE": ("STATFJORD GP.", "Triassic Late"),
    "AMUNDSEN": ("DUNLIN GP.", "Jurassic Early"),
    "JOHANSEN": ("DUNLIN GP.", "Jurassic Early"),
    "BURTON": ("DUNLIN GP.", "Jurassic Early"),
    "COOK": ("DUNLIN GP.", "Jurassic Early"),
    "DRAKE": ("DUNLIN GP.", "Jurassic Early"),
    "BROOM": ("BRENT GP.", "Jurassic Middle"),
    "RANNOCH": ("BRENT GP.", "Jurassic Middle"),
    "ETIVE": ("BRENT GP.", "Jurassic Middle"),
    "NESS": ("BRENT GP.", "Jurassic Middle"),
    "TARBERT": ("BRENT GP.", "Jurassic Middle"),
    "OSEBERG": ("BRENT GP.", "Jurassic Middle"),
    "BRENT": ("BRENT GP.", "Jurassic Middle"),
    "HUGIN": ("VESTLAND GP.", "Jurassic Middle"),
    "SLEIPNER": ("VESTLAND GP.", "Jurassic Middle"),
    "SANDNES": ("VESTLAND GP.", "Jurassic Middle"),
    "BRYNE": ("VESTLAND GP.", "Jurassic Middle"),
    "ULA": ("VESTLAND GP.", "Jurassic Late"),
    "HEATHER": ("VIKING GP.", "Jurassic Late"),
    "DRAUPNE": ("VIKING GP.", "Jurassic Late"),
    "KROSSFJORD": ("VIKING GP.", "Jurassic Middle"),
    "FENSFJORD": ("VIKING GP.", "Jurassic Middle"),
    "SOGNEFJORD": ("VIKING GP.", "Jurassic Late"),
    "MANDAL": ("TYNE GP.", "Jurassic Late"),
    "FARSUND": ("TYNE GP.", "Jurassic Late"),
    "TOR": ("SHETLAND GP.", "Cretaceous Late"),
    "HOD": ("SHETLAND GP.", "Cretaceous Late"),
    "EKOFISK": ("SHETLAND GP.", "Paleocene"),
    "HEIMDAL": ("ROGALAND GP.", "Paleocene"),
    "HERMOD": ("ROGALAND GP.", "Paleocene"),
    "TY": ("ROGALAND GP.", "Paleocene"),
    "LISTA": ("ROGALAND GP.", "Paleocene"),
    "FORTIES": ("ROGALAND GP.", "Paleocene"),
    "BALDER": ("ROGALAND GP.", "Eocene"),
    "FRIGG": ("HORDALAND GP.", "Eocene"),
    "GRID": ("HORDALAND GP.", "Eocene"),
    "UTSIRA": ("NORDLAND GP.", "Miocene"),
    # Barents Sea
    "STOE": ("KAPP TOSCANA GP.", "Jurassic Middle"),
    "STO": ("KAPP TOSCANA GP.", "Jurassic Middle"),
    "NORDMELA": ("KAPP TOSCANA GP.", "Jurassic Early"),
    "TUBAAEN": ("KAPP TOSCANA GP.", "Jurassic Early"),
    "FRUHOLMEN": ("KAPP TOSCANA GP.", "Triassic Late"),
    "SNADD": ("KAPP TOSCANA GP.", "Triassic Late"),
    "KOBBE": ("SASSENDALEN GP.", "Triassic Middle"),
    "KLAPPMYSS": ("SASSENDALEN GP.", "Triassic Early"),
    "HAVERT": ("SASSENDALEN GP.", "Triassic Early"),
    "HEKKINGEN": ("ADVENTDALEN GP.", "Jurassic Late"),
    "KNURR": ("ADVENTDALEN GP.", "Cretaceous Early"),
    "KOLMULE": ("ADVENTDALEN GP.", "Cretaceous Early"),
    "FALK": ("GIPSDALEN GP.", "Carboniferous-Permian"),
    "OERN": ("GIPSDALEN GP.", "Carboniferous-Permian"),
    "ROEYE": ("TEMPELFJORDEN GP.", "Carboniferous-Permian"),
}

#: epoch -> source class used as predictor
SOURCE_CLASS: dict[str, str] = {
    "Jurassic Early": "Lower Jurassic / Upper Triassic",
    "Triassic Late": "Lower Jurassic / Upper Triassic",
    "Jurassic Middle": "Middle Jurassic",
    "Jurassic Late": "Upper Jurassic and younger",
    "Cretaceous Early": "Upper Jurassic and younger",
    "Cretaceous Late": "Upper Jurassic and younger",
    "Paleocene": "Upper Jurassic and younger",
    "Eocene": "Upper Jurassic and younger",
    "Miocene": "Upper Jurassic and younger",
    "Triassic Middle": "Middle Triassic and older",
    "Triassic Early": "Middle Triassic and older",
    "Carboniferous-Permian": "Middle Triassic and older",
}

_TRANSLATE = str.maketrans(
    {"Ø": "OE", "Å": "AA", "Æ": "AE", "ø": "OE", "å": "AA", "æ": "AE"}
)


def formation_key(name: Any) -> str:
    """Normalise a formation name to the key of :data:`FORMATION_TABLE`.

    Args:
        name: Formation name as written in a database or report, for example ``"Tilje Fm."`` or ``"STØ"``.

    Returns:
        Upper-case key without ``Fm.``, with Norwegian letters transliterated; empty when no name is given.
    """
    if not isinstance(name, str) or not name.strip():
        return ""
    key = name.translate(_TRANSLATE).upper()
    key = re.sub(r"\b(FM|FORMATION|SS|INTRA|UPPER|LOWER|MIDDLE)\b\.?", " ", key)
    key = re.split(r"[/,(]", key)[0].strip()
    return key.split()[0] if key else ""


def classify_formation(name: Any) -> dict[str, str | None]:
    """Look up group, epoch and mercury source class of a formation.

    Args:
        name: Formation name.

    Returns:
        ``{"formation_key", "group", "epoch", "source_class"}``; group, epoch and class are ``None`` for a formation
        that is not in the table (state the epoch directly in that case).
    """
    key = formation_key(name)
    group, epoch = FORMATION_TABLE.get(key, (None, None))
    return {
        "formation_key": key,
        "group": group,
        "epoch": epoch,
        "source_class": SOURCE_CLASS.get(epoch or ""),
    }


def source_class_of_epoch(epoch: Any) -> str | None:
    """Return the mercury source class of an epoch name such as ``"Jurassic Early"``.

    Args:
        epoch: Epoch in the form period plus Early, Middle or Late, or ``"Paleocene"``, ``"Carboniferous-Permian"``.

    Returns:
        Source class, or ``None`` when the epoch is unknown.
    """
    if not isinstance(epoch, str):
        return None
    return SOURCE_CLASS.get(epoch.strip())
