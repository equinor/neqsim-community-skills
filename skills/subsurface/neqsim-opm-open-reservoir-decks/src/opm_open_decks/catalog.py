"""Catalog of the open reservoir decks in the OPM ``opm-data`` repository (verified 2026-11-12, no login)."""

from __future__ import annotations

from typing import Any, Dict, List

REPO = "OPM/opm-data"
RAW_HOST = "https://raw.githubusercontent.com"
API_HOST = "https://api.github.com"

LICENCE_ODBL = (
    "Open Database License 1.0 (deck) + Database Contents License 1.0 (contents); "
    "attribution and share-alike apply. Texts: odbl-10.txt and dbcl-10.txt in the repository root."
)
LICENCE_SLEIPNER = (
    "Sleipner CO2 Reference Dataset License (CC BY 4.0 based, but the material may NOT be sold and the owners "
    "must be credited; adapted parts such as the history-matched permeabilities must stay under the same terms). "
    "Not ODbL. See sleipner/COPYING and sleipner/license.pdf."
)

CASES: Dict[str, Dict[str, Any]] = {
    "spe1": {
        "title": "SPE1 - black-oil gas injection, 10x10x3",
        "reference": "Odeh A.S., J. Pet. Technol. 33(1), 1981 (First SPE CSP)",
        "kind": "black-oil",
        "directory": "spe1",
        "decks": ["SPE1CASE1.DATA", "SPE1CASE2.DATA", "SPE1CASE2_2P.DATA", "SPE1CASE2_OILGAS.DATA"],
        "licence": LICENCE_ODBL,
        "use_for": "Smallest end-to-end black-oil case: PVTO/PVDG tables, Rs and Bo checks, material-balance demos.",
        "large_files": {},
    },
    "spe3": {
        "title": "SPE3 - gas cycling of a retrograde condensate reservoir",
        "reference": "Kenyon D.E., Behie G.A., J. Pet. Technol. 39(8), 1987 (Third SPE CSP)",
        "kind": "gas-condensate (black-oil with vaporised oil, PVTG/PVTO)",
        "directory": "spe3",
        "decks": ["SPE3CASE1.DATA", "SPE3CASE2.DATA"],
        "licence": LICENCE_ODBL,
        "use_for": "Condensate yield (Rv) and dew-point behaviour versus a NeqSim CVD on a matching fluid.",
        "large_files": {},
    },
    "spe5": {
        "title": "SPE5 - miscible flood simulators",
        "reference": "Killough J.E., Kossack C.A., SPE 16000, 1987 (Fifth SPE CSP)",
        "kind": "miscible / solvent",
        "directory": "spe5",
        "decks": ["SPE5CASE1.DATA", "SPE5.BASE"],
        "licence": LICENCE_ODBL,
        "use_for": "Solvent-oil PVT and miscibility checks (Copyright 2016 IRIS per deck header).",
        "large_files": {},
    },
    "spe9": {
        "title": "SPE9 - black-oil waterflood, 24x25x15",
        "reference": "Killough J.E., J. Pet. Technol. 47(12), 1995 (Ninth SPE CSP)",
        "kind": "black-oil",
        "directory": "spe9",
        "decks": ["SPE9.DATA", "SPE9_CP.DATA", "SPE9_CP_GROUP.DATA", "SPE9_CP_SHORT.DATA"],
        "licence": LICENCE_ODBL,
        "use_for": "Heterogeneous black-oil benchmark with many wells; permeability and tops come from side files.",
        "large_files": {},
    },
    "spe10model1": {
        "title": "SPE10 model 1 - upscaling, 100x1x20",
        "reference": "Christie M.A., Blunt M.J., SPE Reservoir Eval. Eng. 4(4), 2001 (Tenth SPE CSP)",
        "kind": "black-oil (upscaling)",
        "directory": "spe10model1",
        "decks": ["SPE10_MODEL1.DATA", "SPE10_MODEL1_CP.DATA"],
        "licence": LICENCE_ODBL,
        "use_for": "Small heterogeneity study; includes PERM_SPE10MODEL1.INC (about 61 kB).",
        "large_files": {},
    },
    "spe10model2": {
        "title": "SPE10 model 2 - 60x220x85 fine grid",
        "reference": "Christie M.A., Blunt M.J., SPE Reservoir Eval. Eng. 4(4), 2001",
        "kind": "black-oil (upscaling)",
        "directory": "spe10model2",
        "decks": ["SPE10_MODEL2.DATA"],
        "licence": LICENCE_ODBL,
        "use_for": "Large reference model. WARNING: SPE10MODEL2_PERM.INC is about 58 MB, SPE10MODEL2_PHI.INC about 19 MB.",
        "large_files": {"SPE10MODEL2_PERM.INC": 57946924, "SPE10MODEL2_PHI.INC": 19287206},
    },
    "norne": {
        "title": "Norne full-field model (SPE ATW 2013), 46x112x22",
        "reference": "Norne benchmark case, NTNU/IPT (Statoil-licensed deck, Copyright 2015 Statoil per header)",
        "kind": "black-oil, real North Sea field",
        "directory": "norne",
        "decks": ["NORNE_ATW2013.DATA"],
        "licence": LICENCE_ODBL,
        "use_for": ("Realistic field deck: wells, VFP tables, regions, PVT-WET-GAS.INC, history schedule. "
                    "The INCLUDE tree holds tens of MB (for example GRID/IRAP_1005.GRDECL about 11 MB)."),
        "large_files": {"INCLUDE/GRID/IRAP_1005.GRDECL": 11318913, "INCLUDE/PETRO/SWINITIAL.INC": 1983942},
    },
    "sleipner": {
        "title": "Sleipner 2019 CO2 benchmark model",
        "reference": "Equinor ASA for the Sleipner Group, https://co2datashare.org/dataset/sleipner-2019-benchmark-model",
        "kind": "CO2 storage",
        "directory": "sleipner",
        "decks": ["SLEIPNER_ORG.DATA"],
        "licence": LICENCE_SLEIPNER,
        "use_for": "CO2 plume and storage cases. WARNING: PORO.INC is about 34 MB and the gzipped grid about 27 MB.",
        "large_files": {"PORO.INC": 34168687, "Sleipner_Reference_Model_cleaned.grdecl.gz": 26905193},
    },
}

# Informational pointer, not fetched by the client: the page states no licence.
EXTERNAL: List[Dict[str, str]] = [
    {
        "name": "SPE10 model 2 original archive (SPE CSP)",
        "url": "https://www.spe.org/web/csp/datasets/set02.htm",
        "note": "Anonymous download of por_perm_case2a.zip (about 19 MB); the page carries no licence text, so cite SPE CSP.",
    },
]


def case_names() -> List[str]:
    """Return the catalog case names."""
    return sorted(CASES)


def get_case(name: str) -> Dict[str, Any]:
    """Return one catalog entry; raises ``KeyError`` with the valid names for an unknown case."""
    try:
        return CASES[name]
    except KeyError:
        raise KeyError(f"unknown case {name!r}; choose from {case_names()}") from None
