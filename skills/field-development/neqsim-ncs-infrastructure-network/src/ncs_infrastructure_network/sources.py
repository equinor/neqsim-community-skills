"""Registry of data sources for NCS value-chain work: what exists, how open it
is, how to read it, and which skill owns the read.

Open sources are read directly by this skill. Enterprise sources are listed so
an agent knows they exist and which enterprise skill reads them; this skill
never authenticates to them.
"""

from __future__ import annotations

from typing import Dict, List, Optional

SOURCE_REGISTRY: List[Dict[str, object]] = [
    # ------------------------------------------------------------------ open, API
    {"id": "sodir-dataservice", "tier": "open", "access": "api", "auth": "none",
     "url": "https://factmaps.sodir.no/api/rest/services/DataService/Data/MapServer",
     "provides": ["fields", "discoveries", "facilities", "pipelines", "reserves", "field descriptions",
                  "yearly and monthly production", "licences", "TUF"],
     "licence": "NLOD 2.0 - reuse with attribution", "refresh": "daily (Sodir)",
     "owner_skill": "neqsim-ncs-infrastructure-network", "client": "open_api.SodirDataService"},
    {"id": "sodir-factpages-csv", "tier": "open", "access": "api", "auth": "none",
     "url": "https://factpages.sodir.no/public?/Factpages/external/tableview/{table}",
     "provides": ["all FactPages tables as CSV"], "licence": "NLOD 2.0",
     "refresh": "daily", "owner_skill": "neqsim-ncs-infrastructure-network", "client": "open_api.SodirFactPages",
     "notes": "some tables (e.g. pipLine, field_reserves_company) answer HTTP 500; use the DataService layer"},
    {"id": "entsog-transparency", "tier": "open", "access": "api", "auth": "none",
     "url": "https://transparency.entsog.eu/api/v1",
     "provides": ["daily physical flow and firm capacity at Norwegian entry points (UK, BE, FR, DE, DK)"],
     "licence": "ENTSOG Transparency Platform terms", "refresh": "daily (gas day 06:00 CET)",
     "owner_skill": "neqsim-ncs-infrastructure-network", "client": "open_api.EntsogTransparency",
     "notes": "values in kWh/d; 404 means no data for the window"},
    {"id": "norskpetroleum-tables", "tier": "open", "access": "download", "auth": "none",
     "url": "https://www.norskpetroleum.no/en/production-and-exports/the-oil-and-gas-pipeline-system/",
     "provides": ["pipeline capacities (gas MSm3/d, oil Sm3/d)", "headline NCS facts"],
     "licence": "reuse with attribution and link", "refresh": "irregular",
     "owner_skill": "neqsim-ncs-infrastructure-network",
     "notes": "'csv' generator links return xlsx; header row is the one with Operator/From/To"},
    {"id": "gassco-plant-pages", "tier": "open", "access": "web", "auth": "none",
     "url": "https://gassco.eu/en/about-us/where-we-are/processing-plants/",
     "provides": ["plant capacities (Kollsnes, Nyhamna, Karsto products)", "terminal list", "transport map"],
     "licence": "public web page - cite", "refresh": "irregular", "owner_skill": "neqsim-ncs-infrastructure-network"},
    {"id": "gassco-umm", "tier": "open", "access": "user-export", "auth": "terms acceptance",
     "url": "https://umm.gassco.no/",
     "provides": ["planned and unplanned capacity outages (REMIT UMM)"],
     "licence": "Gassco terms", "refresh": "event driven",
     "owner_skill": "neqsim-ncs-value-chain-optimization",
     "notes": "click-through terms page; no API. Do not automate acceptance - the user exports and supplies it"},
    {"id": "norwegian-carbon-cost", "tier": "open", "access": "bundled", "auth": "none",
     "url": "https://www.norskpetroleum.no/en/environment-and-technology/emissions-to-air/",
     "provides": ["CO2 tax, EU ETS, NOx fund basis"], "licence": "attribution",
     "owner_skill": "neqsim-norwegian-continental-shelf-data"},
    # ------------------------------------------------------------------ enterprise
    {"id": "pdm-internal-api", "tier": "enterprise", "access": "api", "auth": "APIM key + Entra ID",
     "provides": ["daily allocated production per field/well"], "owner_skill": "enterprise-pdm-api"},
    {"id": "centuries-rnb", "tier": "enterprise", "access": "api", "auth": "Entra ID",
     "provides": ["RNB / corporate production forecasts per field"], "owner_skill": "enterprise-acquire-api"},
    {"id": "gassled-tariffs", "tier": "enterprise", "access": "governed input", "auth": "commercial",
     "provides": ["transport tariffs, processing fees, capacity booking"], "owner_skill": "enterprise-gassled-tariff"},
    {"id": "gas-quality-specs", "tier": "enterprise", "access": "governed input", "auth": "commercial",
     "provides": ["entry/exit gas quality specifications"],
     "owner_skill": "enterprise-gas-quality-specification"},
    {"id": "ots-historian", "tier": "enterprise", "access": "api", "auth": "Entra ID",
     "provides": ["metered export and terminal flows"], "owner_skill": "enterprise-ots-timeseries"},
    {"id": "emisoft", "tier": "enterprise", "access": "api/sql", "auth": "Entra ID",
     "provides": ["reported emissions and energy per installation"], "owner_skill": "enterprise-emisoft-api"},
]


def sources_for(what: Optional[str] = None, tier: Optional[str] = None) -> List[Dict[str, object]]:
    """Filter the registry by a keyword in ``provides`` and/or tier ('open'/'enterprise')."""
    out = []
    for src in SOURCE_REGISTRY:
        if tier and src["tier"] != tier:
            continue
        if what and not any(what.lower() in str(p).lower() for p in src.get("provides", [])):
            continue
        out.append(src)
    return out
