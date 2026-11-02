"""Catalog of the ANP well-production open-data families and model readiness.

Verified against the live ANP pages and files on 2026-11-02. Header names and
URLs change, so the catalog records what each family contains and how to find its
links; the reader still checks every header.
"""

from __future__ import annotations

from typing import Any, Dict, List

VERIFIED_ON = "2026-11-02"

ANP_FILES_BASE = "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos"

FAMILIES: Dict[str, Dict[str, Any]] = {
    "well_monthly_rates": {
        "title": "Produção de petróleo e gás natural por poço (monthly files, 2005 onward)",
        "page": "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/producao-de-petroleo-e-gas-natural-por-poco",
        "link_marker": "arquivos-producao-de-petroleo-e-gas-natural-por-poco",
        "link_suffix": ".zip",
        "format": "zip per month holding three semicolon CSV files: Mar (offshore), PreSal (subset of Mar), Terra (onshore)",
        "encoding": "cp1252",
        "number_format": "decimal comma, no thousands separator, leading zero omitted (',878')",
        "granularity": "monthly, one row per well",
        "units": "oil, condensate, petroleum and water in bbl/dia; gas in Mm3/dia (= thousand m3/d); hours on stream per month",
        "rate_definition": "monthly volume divided by calendar days of the month",
        "extras": "API gravity, distillate fractions, gas composition (% by volume C1-C11, O2, N2, CO2), gross calorific value, installation, contract number",
        "lag": "two months after the production month",
        "coverage": "annual zips 2005-2020, monthly zips 2021-2023 (last verified file: 2023-12). The page heading '2024 em diante' links the 2023 folder: from 2024 the by-well data are in the CDP query portal or in the well_monthly_volumes family, which has no API gravity, composition or hours on stream.",
        "metadata": "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/arquivos-producao-de-petroleo-e-gas-natural-por-poco/metadados-dados-producao-poco.pdf",
    },
    "well_monthly_volumes": {
        "title": "Fase de desenvolvimento e produção, Produção de petróleo e gás natural nacional",
        "page": "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/fase-de-desenvolvimento-e-producao",
        "link_marker": "arquivos-producao-de-petroleo-e-gas-natural-nacional",
        "link_suffix": ".csv",
        "format": "comma CSV, bracketed headers; offshore (pm/producao-mar-*), onshore by quarter (pt/*)",
        "encoding": "utf-8",
        "number_format": "quoted, decimal comma, dot thousands ('3.127,441')",
        "granularity": "monthly, one row per well",
        "units": "oil, condensate, water in m3 per month; gas in Mm3 per month (= thousand m3); injection of gas, water, CO2, N2, steam, polymer",
        "rate_definition": "monthly volume; divide by calendar days for a rate",
        "extras": "injection volumes; history reaches back to 1941 offshore",
        "lag": "two months after the production month",
        "coverage": "offshore 1941 to the latest month, onshore by quarter; verified files reach 2026",
        "metadata": "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/arquivos-fase-de-desenvolvimento-e-producao/arquivos-producao-de-petroleo-e-gas-natural-nacional/metadados-mar.docx",
    },
    "zone_daily_rates": {
        "title": "Produção por zona (from October 2014)",
        "page": "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/fase-de-desenvolvimento-e-producao",
        "link_marker": "producao-por-zona",
        "link_suffix": ".csv",
        "format": "comma CSV, one file per month, quoted decimal-comma numbers",
        "encoding": "utf-8",
        "number_format": "quoted, decimal comma",
        "granularity": "monthly, one row per well and reservoir zone",
        "units": "m3/d for liquids and water, Mil m3/d for gas, injection rates for water, gas, CO2, N2, steam",
        "rate_definition": "daily average of the month",
        "extras": "zone code, injection per zone",
        "lag": "monthly update; check the page date",
        "metadata": "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/arquivos-fase-de-desenvolvimento-e-producao/producao-por-zona/metadados-producao-zona.docx",
    },
    "well_status": {
        "title": "Informações sobre poços: Situação de poços (1939 onward)",
        "page": "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/fase-de-desenvolvimento-e-producao",
        "link_marker": "informacoes-sobre-pocos",
        "link_suffix": ".csv",
        "format": "comma CSV with underscore headers; one row per drilled well",
        "encoding": "utf-8",
        "number_format": "coordinates as degrees:minutes:seconds with decimal comma; dates dd/mm/yyyy",
        "granularity": "one row per well",
        "units": "dates and categories",
        "rate_definition": "not a production file",
        "extras": "drilling, completion and first/last production dates, status, lift method, last intervention, base coordinates",
        "lag": "refreshed monthly",
        "metadata": "https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/arquivos-fase-de-desenvolvimento-e-producao/informacoes-sobre-pocos/metadado-situacao-de-poco.docx",
    },
}
"""The four public well-level file families and their verified traits."""

MODEL_READINESS: Dict[str, Dict[str, Any]] = {
    "decline_and_eur": {
        "public": ["monthly rate history per well and field", "hours on stream", "well status and lift method"],
        "missing": ["reservoir pressure", "completion and workover timing per well beyond status dates"],
        "next": "Fit with neqsim-norwegian-continental-shelf-data fit_arps_decline on decline_series; label as screening.",
    },
    "gor_and_water_cut_trends": {
        "public": ["gas, oil and water per well and month", "API gravity", "gas composition"],
        "missing": ["separator conditions", "allocation basis between wells on one installation"],
        "next": "Use ratios and aggregate; check well_flags for shut-in and partial months first.",
    },
    "field_aggregation": {
        "public": ["field, basin, installation and operator per well row"],
        "missing": ["fiscal or allocated volumes (these differ from ANP statistics)"],
        "next": "Use merge_environments before aggregate; never add the pre-salt file to the offshore file.",
    },
    "material_balance": {
        "public": ["production history", "zone production from October 2014"],
        "missing": ["static and flowing reservoir pressure", "PVT (Bo, Rs, Bg, saturation pressure)", "aquifer data"],
        "next": "Pressure and PVT need operator data or ANP BDEP (some items confidential or paid); hand the history to neqsim-reservoir-material-balance only with that data.",
    },
    "well_flow_and_vfp": {
        "public": ["lift method", "base coordinates", "installation"],
        "missing": ["tubing and casing geometry", "wellhead pressure and temperature", "choke settings", "reservoir pressure"],
        "next": "Geometry and pressures come from the operator or BDEP well records; without them only a declared-assumption model is possible.",
    },
    "process_feed_fluid": {
        "public": ["API gravity", "gas composition C1-C11, N2, CO2, O2", "gross calorific value", "GOR from rates"],
        "missing": ["separator P and T", "C7+ properties", "recombined wellstream composition", "PVT report"],
        "next": "Use fluid_basis and hand it to fluid-characterization-agent; state that the basis is a declared best guess.",
    },
}
"""What the open data supports for each downstream NeqSim model, and what is missing."""


def readiness(model: str) -> Dict[str, Any]:
    """Return the readiness record of a model type.

    Args:
        model: Key of :data:`MODEL_READINESS`.

    Returns:
        Dict with ``public``, ``missing`` and ``next``.

    Raises:
        KeyError: Unknown model; the message lists the known keys.
    """
    try:
        return MODEL_READINESS[model]
    except KeyError:
        raise KeyError("Unknown model %r; known: %s" % (model, ", ".join(sorted(MODEL_READINESS))))


def families() -> List[str]:
    """Return the family names in catalog order.

    Returns:
        List of family keys.
    """
    return list(FAMILIES)
