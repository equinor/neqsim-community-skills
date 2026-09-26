"""Curated NCS topology that no single open table provides.

The open tables give pipelines (norskpetroleum capacity tables, Sodir pipeline
segments) and fields/discoveries/facilities (Sodir). They do not give:

* the node kind of a pipeline endpoint (hub platform, processing plant,
  receiving terminal, downstream market),
* plant capacities (published on gassco.eu plant pages),
* field lines that carry no capacity row (Troll A -> Kollsnes, Ormen Lange ->
  Nyhamna, Snohvit -> Melkoya),
* the Baltic Pipe tie-in on Europipe II,
* aliases that let free-text routes ("the Asgard Transport System (ATS)")
  resolve to graph nodes.

Every curated number carries ``source_url`` and ``basis``. Estimates are marked
``confidence: "low"`` so reports can flag them.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, List

GASSCO = "https://gassco.eu/en/prosessanlegg/"
NP_GAS = "https://www.norskpetroleum.no/en/production-and-exports/the-oil-and-gas-pipeline-system/"


def norm(text: str) -> str:
    """Upper-case ASCII key: Aa/Oe/Ae for Norwegian letters, punctuation to spaces."""
    if text is None:
        return ""
    t = str(text)
    for a, b in (("Å", "AA"), ("å", "aa"), ("Ø", "OE"), ("ø", "oe"), ("Æ", "AE"), ("æ", "ae")):
        t = t.replace(a, b)
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")
    t = re.sub(r"\((D|F|B|UK|DK)\)", " ", t)
    t = re.sub(r"[^A-Za-z0-9]+", " ", t).strip().upper()
    return re.sub(r"\s+", " ", t)


def node_id(text: str) -> str:
    return norm(text).replace(" ", "_")


# kind: hub (offshore riser/processing platform on the trunk system),
# plant (onshore processing / LNG / methanol / refinery), terminal (receiving
# terminal or downstream-system entry), market (sink), sink (non-sales sink).
CURATED_NODES: List[Dict] = [
    # --- onshore processing plants -------------------------------------------
    {"id": "KOLLSNES", "name": "Kollsnes", "kind": "plant", "country": "NO",
     "gas_capacity_msm3d": 143.0, "gas_capacity_range_msm3d": [143.0, 144.5],
     "condensate_capacity_sm3d": 9000.0,
     "source_url": GASSCO + "kollsnes/", "basis": "Gassco plant page: 143-144.5 MSm3/d gas, 9000 Sm3/d condensate"},
    {"id": "NYHAMNA", "name": "Nyhamna", "kind": "plant", "country": "NO", "gas_capacity_msm3d": 84.0,
     "source_url": GASSCO + "nyhamna/", "basis": "Gassco plant page: export capacity 84 MSm3/d"},
    {"id": "KARSTO", "name": "Kårstø", "kind": "plant", "country": "NO", "gas_capacity_msm3d": None,
     "ngl_capacity_t_per_h": {"ethane": 112, "propane": 358, "i_butane": 76, "n_butane": 145,
                              "naphtha": 106, "condensate": 351},
     "source_url": GASSCO + "karsto/",
     "basis": "Gassco publishes product rates only; dry-gas export bounded by Statpipe dry gas + Europipe II"},
    {"id": "HAMMERFEST_LNG", "name": "Hammerfest LNG (Melkøya)", "kind": "plant", "country": "NO",
     "gas_capacity_msm3d": 18.0, "confidence": "medium",
     "source_url": "https://factpages.sodir.no/field/pageview/all/2053062",
     "basis": "calibrated: Snohvit peak annual-average sales gas 17.7 MSm3/d (2018, Sodir profiles) + margin"},
    {"id": "TJELDBERGODDEN", "name": "Tjeldbergodden", "kind": "plant", "country": "NO",
     "source_url": NP_GAS, "basis": "methanol plant fed by Haltenpipe"},
    {"id": "MONGSTAD", "name": "Mongstad", "kind": "plant", "country": "NO",
     "source_url": NP_GAS, "basis": "crude oil terminal and refinery"},
    {"id": "STURE", "name": "Sture", "kind": "plant", "country": "NO",
     "source_url": NP_GAS, "basis": "crude oil terminal (Oseberg Transport System, Grane Oil Pipeline)"},
    # --- receiving terminals / downstream entries -----------------------------
    {"id": "EMDEN", "name": "Emden", "kind": "terminal", "country": "DE",
     "entsog_points": ["ITP-00209", "ITP-00210"], "source_url": "https://gassco.eu/en/mottaksterminaler/germany/"},
    {"id": "DORNUM", "name": "Dornum", "kind": "terminal", "country": "DE",
     "entsog_points": ["ITP-00208", "ITP-00525"], "source_url": "https://gassco.eu/en/mottaksterminaler/germany/"},
    {"id": "ZEEBRUGGE", "name": "Zeebrugge", "kind": "terminal", "country": "BE", "entsog_points": ["ITP-00106"],
     "source_url": "https://gassco.eu/en/mottaksterminaler/belgium-and-france/"},
    {"id": "DUNKERQUE", "name": "Dunkerque", "kind": "terminal", "country": "FR", "entsog_points": ["ITP-00045"],
     "source_url": "https://gassco.eu/en/mottaksterminaler/belgium-and-france/"},
    {"id": "ST_FERGUS", "name": "St Fergus", "kind": "terminal", "country": "UK", "entsog_points": ["ITP-00022"],
     "source_url": "https://gassco.eu/en/mottaksterminaler/the-united-kingdom/"},
    {"id": "EASINGTON", "name": "Easington", "kind": "terminal", "country": "UK", "entsog_points": ["ITP-00091"],
     "source_url": "https://gassco.eu/en/mottaksterminaler/the-united-kingdom/"},
    {"id": "NYBRO", "name": "Nybro (Baltic Pipe)", "kind": "terminal", "country": "DK", "entsog_points": ["ITP-00630"],
     "source_url": "https://www.baltic-pipe.eu/"},
    {"id": "FLAGS_UK", "name": "FLAGS (UK)", "kind": "terminal", "country": "UK",
     "source_url": NP_GAS, "basis": "entry to the UK FLAGS system (lands at St Fergus, UK side not modelled)"},
    {"id": "SAGE_UK", "name": "SAGE (UK)", "kind": "terminal", "country": "UK",
     "source_url": NP_GAS, "basis": "entry to the UK SAGE system (lands at St Fergus, UK side not modelled)"},
    {"id": "TEESSIDE", "name": "Teesside", "kind": "terminal", "country": "UK",
     "source_url": NP_GAS, "basis": "Norpipe oil terminal"},
    {"id": "FUKA_SEGAL", "name": "FUKA / SEGAL (UK)", "kind": "terminal", "country": "UK",
     "basis": "Frigg UK Association pipeline to the SEGAL terminal at St Fergus (UK system)"},
    {"id": "CATS_UK", "name": "CATS (UK)", "kind": "terminal", "country": "UK",
     "basis": "Central Area Transmission System to Teesside (UK system)"},
    {"id": "FORTIES_UK", "name": "Forties Pipeline System / Cruden Bay (UK)", "kind": "terminal",
     "commodity": "liquid", "country": "UK"},
    {"id": "UK_OFFSHORE_BUYER", "name": "UK offshore host (gas sold offshore)", "kind": "terminal", "country": "UK"},
    {"id": "DANISH_SYSTEM", "name": "Danish offshore system (Tyra)", "kind": "terminal", "country": "DK"},
    # --- junctions -------------------------------------------------------------
    {"id": "EUROPIPE_II_BALTIC_TIE_IN", "name": "Europipe II / Baltic Pipe tie-in", "kind": "junction",
     "source_url": "https://www.baltic-pipe.eu/", "basis": "Baltic Pipe tie-in on Europipe II (2022)"},
    {"id": "STATPIPE_RICH_GAS", "name": "Statpipe rich gas (tie-in section)", "kind": "junction",
     "source_url": NP_GAS,
     "basis": "tie-ins (Johan Sverdrup, Balder, Brage...) join Statpipe rich gas downstream of Statfjord"},
    # --- markets / sinks -------------------------------------------------------
    {"id": "MARKET_DE", "name": "Germany gas market", "kind": "market", "commodity": "gas", "country": "DE"},
    {"id": "MARKET_BE", "name": "Belgium gas market", "kind": "market", "commodity": "gas", "country": "BE"},
    {"id": "MARKET_FR", "name": "France gas market", "kind": "market", "commodity": "gas", "country": "FR"},
    {"id": "MARKET_UK", "name": "UK gas market", "kind": "market", "commodity": "gas", "country": "UK"},
    {"id": "MARKET_DK_PL", "name": "Denmark / Poland gas market", "kind": "market", "commodity": "gas",
     "country": "DK"},
    {"id": "MARKET_LNG", "name": "LNG export", "kind": "market", "commodity": "gas"},
    {"id": "MARKET_NO_GAS", "name": "Domestic gas use (methanol, industry)", "kind": "market", "commodity": "gas",
     "country": "NO"},
    {"id": "GAS_REINJECTION", "name": "Gas delivered for reinjection", "kind": "sink", "commodity": "gas"},
    {"id": "MARKET_CRUDE", "name": "Crude oil / condensate market", "kind": "market", "commodity": "liquid"},
    {"id": "TANKER_EXPORT", "name": "Offshore loading to shuttle tankers", "kind": "terminal", "commodity": "liquid",
     "basis": "buoy/FPSO offloading; no pipeline capacity"},
]

# Free-text and table aliases -> node id.  Longest alias wins in the parser.
ALIASES: Dict[str, str] = {
    "Åsgard Transport System": "ASGARD", "Åsgard Transport": "ASGARD", "ÅTS": "ASGARD", "Åsgard": "ASGARD",
    "Åsgard A": "ASGARD", "Åsgard B": "ASGARD", "Åsgard C": "ASGARD",
    "Draupner E": "DRAUPNER", "Draupner S": "DRAUPNER", "Draupner": "DRAUPNER",
    "Emden": "EMDEN", "Norsea Gas Terminal Emden": "EMDEN", "Norsea Gas Terminal": "EMDEN",
    "Dornum": "DORNUM", "Dunkerque": "DUNKERQUE", "Dunkirk": "DUNKERQUE", "Zeebrugge": "ZEEBRUGGE",
    "St. Fergus": "ST_FERGUS", "St Fergus": "ST_FERGUS", "Easington": "EASINGTON", "Teesside": "TEESSIDE",
    "FLAGS": "FLAGS_UK", "Far North Liquids and Associated Gas System": "FLAGS_UK",
    "SAGE": "SAGE_UK", "Scottish Area Gas Evacuation": "SAGE_UK",
    "Kårstø": "KARSTO", "Karsto": "KARSTO", "Kollsnes": "KOLLSNES", "Nyhamna": "NYHAMNA",
    "Melkøya": "HAMMERFEST_LNG", "Hammerfest LNG": "HAMMERFEST_LNG", "Hammerfest": "HAMMERFEST_LNG",
    "Tjeldbergodden": "TJELDBERGODDEN", "Mongstad": "MONGSTAD", "Sture": "STURE", "Sture Terminal": "STURE",
    "Statpipe": "STATPIPE_RICH_GAS", "Statpipe rich gas": "STATPIPE_RICH_GAS",
    "reinjected": "GAS_REINJECTION", "reinjection": "GAS_REINJECTION", "re-injected": "GAS_REINJECTION",
    "Ekofisk Complex": "EKOFISK", "Ekofisk Centre": "EKOFISK", "Ekofisk Center": "EKOFISK",
    "Ekofisk Y": "EKOFISK", "Ekofisk J": "EKOFISK", "Ekofisk": "EKOFISK", "Norpipe": "EKOFISK",
    "Oseberg A": "OSEBERG", "Oseberg Field Centre": "OSEBERG", "Oseberg": "OSEBERG",
    "Oseberg Transport System": "OSEBERG", "OTS": "OSEBERG", "Oseberg Gas Transport": "OSEBERG",
    "Sleipner A": "SLEIPNER", "Sleipner": "SLEIPNER", "Langeled": "NYHAMNA",
    "Troll A": "TROLL", "Troll B": "TROLL_B", "Troll C": "TROLL_C", "Troll": "TROLL",
    "Troll Oil Pipeline II": "TROLL_C", "Troll Oil Pipeline I": "TROLL_B",
    "Grane oljerør": "GRANE", "Grane Oil Pipeline": "GRANE", "Grane": "GRANE",
    "Polarled": "AASTA_HANSTEEN", "Aasta Hansteen": "AASTA_HANSTEEN",
    "Heimdal": "HEIMDAL", "Heidrun": "HEIDRUN", "Norne": "NORNE", "Norne FPSO": "NORNE",
    "Norne pipeline": "NORNE", "Draugen": "DRAUGEN", "Gjøa": "GJOA", "Knarr": "KNARR",
    "Kvitebjørn": "KVITEBJORN", "Valemon": "VALEMON", "Edvard Grieg": "EDVARD_GRIEG",
    "Johan Sverdrup": "JOHAN_SVERDRUP", "Statfjord": "STATFJORD", "Statfjord C": "STATFJORD",
    "Statfjord B": "STATFJORD", "Statfjord A": "STATFJORD", "Tampen Link": "STATFJORD",
    "Vesterled": "HEIMDAL", "Gassled": "GASSLED_GENERIC",
    "Frigg UK": "FUKA_SEGAL", "FUKA": "FUKA_SEGAL", "SEGAL": "FUKA_SEGAL",
    "Shell-Esso Gas and Liquid": "FUKA_SEGAL", "CATS": "CATS_UK",
    "Central Area Transmission System": "CATS_UK", "Cruden Bay": "FORTIES_UK",
    "Forties Pipeline System": "FORTIES_UK", "Forties": "FORTIES_UK", "Brae": "UK_OFFSHORE_BUYER",
    "Brae A": "UK_OFFSHORE_BUYER", "Tyra": "DANISH_SYSTEM", "Danish pipeline system": "DANISH_SYSTEM",
    "Danish pipeline": "DANISH_SYSTEM", "Harald": "DANISH_SYSTEM",
    "shuttle tanker": "TANKER_EXPORT", "shuttle tankers": "TANKER_EXPORT", "tankers": "TANKER_EXPORT",
    "tanker": "TANKER_EXPORT", "loading buoy": "TANKER_EXPORT", "loading-buoy": "TANKER_EXPORT",
    "offloaded": "TANKER_EXPORT",
}

# Arcs that no capacity table lists but are physically required.
CURATED_ARCS: List[Dict] = [
    {"id": "TROLL_A_KOLLSNES", "name": "Troll A gas lines", "from": "TROLL", "to": "KOLLSNES", "medium": "gas",
     "capacity": None, "capacity_unit": "MSm3/d", "source_url": GASSCO + "kollsnes/",
     "basis": "field lines; bounded by the Kollsnes plant capacity"},
    {"id": "ORMEN_LANGE_NYHAMNA", "name": "Ormen Lange multiphase lines", "from": "ORMEN_LANGE", "to": "NYHAMNA",
     "medium": "gas", "capacity": None, "capacity_unit": "MSm3/d", "source_url": GASSCO + "nyhamna/",
     "basis": "field lines; bounded by the Nyhamna plant capacity"},
    {"id": "SNOHVIT_MELKOYA", "name": "Snøhvit multiphase line", "from": "SNOHVIT", "to": "HAMMERFEST_LNG",
     "medium": "gas", "capacity": None, "capacity_unit": "MSm3/d",
     "source_url": "https://www.norskpetroleum.no/en/facts/field/snohvit/",
     "basis": "143 km multiphase line; bounded by the LNG plant"},
    {"id": "BALTIC_PIPE", "name": "Baltic Pipe", "from": "EUROPIPE_II_BALTIC_TIE_IN", "to": "NYBRO",
     "medium": "gas", "capacity": 27.4, "capacity_unit": "MSm3/d", "confidence": "medium",
     "source_url": "https://www.baltic-pipe.eu/", "basis": "10 bcm/yr design capacity to Poland / 365"},
    {"id": "GRANE_REINJECTION", "name": "Grane gas injection", "from": "GRANE", "to": "GAS_REINJECTION",
     "medium": "gas", "capacity": None, "capacity_unit": "MSm3/d", "source_url": NP_GAS,
     "basis": "Grane Gas Pipeline delivers injection gas from Heimdal"},
]

# terminal/plant -> market arcs (uncapacitated; capacity sits upstream)
MARKET_LINKS: List[Dict] = [
    {"from": "EMDEN", "to": "MARKET_DE", "medium": "gas"},
    {"from": "DORNUM", "to": "MARKET_DE", "medium": "gas"},
    {"from": "ZEEBRUGGE", "to": "MARKET_BE", "medium": "gas"},
    {"from": "DUNKERQUE", "to": "MARKET_FR", "medium": "gas"},
    {"from": "ST_FERGUS", "to": "MARKET_UK", "medium": "gas"},
    {"from": "EASINGTON", "to": "MARKET_UK", "medium": "gas"},
    {"from": "FLAGS_UK", "to": "MARKET_UK", "medium": "gas"},
    {"from": "SAGE_UK", "to": "MARKET_UK", "medium": "gas"},
    {"from": "NYBRO", "to": "MARKET_DK_PL", "medium": "gas"},
    {"from": "HAMMERFEST_LNG", "to": "MARKET_LNG", "medium": "gas"},
    {"from": "TJELDBERGODDEN", "to": "MARKET_NO_GAS", "medium": "gas"},
    {"from": "STURE", "to": "MARKET_CRUDE", "medium": "liquid"},
    {"from": "MONGSTAD", "to": "MARKET_CRUDE", "medium": "liquid"},
    {"from": "TEESSIDE", "to": "MARKET_CRUDE", "medium": "liquid"},
    {"from": "FUKA_SEGAL", "to": "MARKET_UK", "medium": "gas"},
    {"from": "CATS_UK", "to": "MARKET_UK", "medium": "gas"},
    {"from": "UK_OFFSHORE_BUYER", "to": "MARKET_UK", "medium": "gas"},
    {"from": "FORTIES_UK", "to": "MARKET_CRUDE", "medium": "liquid"},
    {"from": "UK_OFFSHORE_BUYER", "to": "MARKET_CRUDE", "medium": "liquid"},
    {"from": "DANISH_SYSTEM", "to": "MARKET_DK_PL", "medium": "gas"},
    {"from": "DANISH_SYSTEM", "to": "MARKET_CRUDE", "medium": "liquid"},
    {"from": "HAMMERFEST_LNG", "to": "MARKET_CRUDE", "medium": "liquid"},
    {"from": "NYHAMNA", "to": "MARKET_CRUDE", "medium": "liquid"},
    {"from": "KARSTO", "to": "MARKET_CRUDE", "medium": "liquid"},
    {"from": "TANKER_EXPORT", "to": "MARKET_CRUDE", "medium": "liquid"},
    {"from": "KOLLSNES", "to": "MONGSTAD", "medium": "liquid"},
]

# Table rows whose endpoint must be redirected (e.g. to split a shared trunk).
ARC_OVERRIDES: Dict[str, Dict] = {
    # Europipe II carries Baltic Pipe volumes up to the tie-in, then continues to Dornum.
    "Europipe II": {"to": "EUROPIPE_II_BALTIC_TIE_IN", "continue_to": "DORNUM"},
    # Statfjord -> junction (Statfjord's own share) -> Karsto (shared by all tie-ins).
    "Statpipe (rich gas)": {"to": "STATPIPE_RICH_GAS", "continue_to": "KARSTO"},
}
