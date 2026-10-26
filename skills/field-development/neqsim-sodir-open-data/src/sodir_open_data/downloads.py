"""Static entry points of the Sodir open data page (no network access in this module).

Source: https://www.sodir.no/fakta/data-og-analyser/apne-data/ (the page itself answers
HTTP 403 to scripted clients, so the services below are the machine-readable routes).
All data are published under the Norwegian Licence for Open Government Data (NLOD) 2.0.
"""

from __future__ import annotations

from typing import Dict, List

OPEN_DATA_PAGE = "https://www.sodir.no/fakta/data-og-analyser/apne-data/"
LICENCE = "NLOD 2.0 (Norwegian Licence for Open Government Data) - reuse with attribution to Sodir"
ATTRIBUTION = "Source: Norwegian Offshore Directorate (Sokkeldirektoratet, Sodir), factpages.sodir.no, NLOD 2.0"

REST_ROOT = "https://factmaps.sodir.no/api/rest/services"
DATASERVICE_DATA = REST_ROOT + "/DataService/Data/MapServer"
DATASERVICE_METADATA = REST_ROOT + "/DataService/Metadata/MapServer"
FACTMAPS_WGS84 = REST_ROOT + "/Factmaps/FactMapsWGS84/MapServer"
FACTMAPS_ED50_UTM32 = REST_ROOT + "/Factmaps/FactMapsED50UTM32/MapServer"
THEMES_ROOT = REST_ROOT + "/Themes"
FACTPAGES = "https://factpages.sodir.no/"
FACTPAGES_TABLEVIEW_CSV = (
    "https://factpages.sodir.no/public?/Factpages/external/tableview/{table}"
    "&rs:Command=Render&rc:Toolbar=false&rc:Parameters=f&IpAddress=not_used"
    "&CultureCode=en&rs:Format=CSV&Top100=false"
)
FACTPAGES_DOWNLOAD = "https://factpages.sodir.no/downloads/{fmt}/{name}.zip"
FGDB_FACTMAPS = "https://factpages.sodir.no/downloads/fgdb/SODIR_FactMaps_data_v3_0.zip"
FGDB_CCS_ATLAS = "https://factpages.sodir.no/downloads/fgdb/SODIR_CCS_StorageAtlas.zip"
GEONORGE = "https://www.geonorge.no/"

# Web viewers on the open data page (human tools; not machine APIs).
VIEWERS: Dict[str, str] = {
    "factmaps": "https://factmaps.sodir.no/map",
    "survey_map_ongoing_planned": "https://sodir.maps.arcgis.com/apps/webappviewer/index.html?id=cf38b97ad4624bb4bee933cbafbd19f7",
    "deep_sea_surveys": "https://experience.arcgis.com/experience/2debb5536b5a4a35b1ddb16d1888f39a/",
    "co2_atlas": "https://sodir.maps.arcgis.com/apps/webappviewer/index.html?id=663ebb1c3c5241db935bc751254c9578",
}

# Bulk datasets published as <fmt>/<name>.zip with fmt in {"shape", "csv"}. CSV carries WKT geometry.
# Shape/CSV files do not contain every attribute: use the FGDB or the REST services for complete data.
BULK_DATASETS: Dict[str, str] = {
    "afxAreaCurrent": "AFEX (area-fee exemption), only current has geometry",
    "afxAreaSplitByBlock": "AFEX, all periods, all affected blocks and licences",
    "prlAreaCurrent": "Production licences, active, overall geometry (CO2 licences are in baaArea)",
    "prlAreaSplitByBlock": "Production licences, full area history split by block; filter dtValTo IS NULL for active",
    "apaAreaGross": "APA (awards in predefined areas) gross areas, updated",
    "apaAreaNet": "APA net area, only active rounds",
    "baaAreaCurrent": "Business arrangement areas (BAA), includes CO2 licences",
    "baaAreaSplitByBlock": "BAA with full area history split by block",
    "wlbPoint": "Wellbores - exploration, development and shallow",
    "fldArea": "Field outlines",
    "dscArea": "Discovery outlines, including field outlines",
    "fclPoint": "Facilities - fixed, floating production and onshore",
    "seaArea": "Planned surveys since 2009 - gross (incl. turning area) and net (acquisition)",
    "pipLine": "Main pipelines from TUF; infield pipelines are NOT included",
    "blkArea": "All blocks on the NCS",
    "qadArea": "All quadrants on the NCS",
    "subArea": "All sub-areas on the NCS",
}

OTHER_DATA: List[Dict[str, str]] = [
    {"topic": "CO2", "name": "CO2 storage atlas surfaces (FGDB)", "url": FGDB_CCS_ATLAS},
    {"topic": "CO2", "name": "CO2 surfaces (zmap, 2019)",
     "url": "https://www.sodir.no/4a612b/globalassets/1-sodir/fakta/co-to/20190906_co2_surfaces.zip"},
    {"topic": "Deep sea", "name": "Seabed-minerals deep-sea data: order from Sodir",
     "url": "https://www.sodir.no/fakta/havbunnsmineraler/bestill-dyphavsdata/"},
    {"topic": "Status reports", "name": "Licence status / relinquishment reports (shape, irregular update)",
     "url": "https://www.sodir.no/4a1cb3/globalassets/1-sodir/om-oss/informasjonstjenester/karttjenester/licence_relinquishment_reports.zip"},
    {"topic": "Structural elements", "name": "Main structural elements (shape)",
     "url": "https://www.sodir.no/4ae6d9/globalassets/1-sodir/fakta/geologi-eng/structural_elements.zip"},
]

# PDFs worth reading before building complex joins.
DOCS: Dict[str, str] = {
    "factpages_vs_dataservice_tables": "https://www.sodir.no/4aea6d/globalassets/1-sodir/om-oss/informasjonstjenester/karttjenester/factpages_dataservice.pdf",
    "api_user_guide": "https://www.sodir.no/491e86/globalassets/1-sodir/om-oss/informasjonstjenester/karttjenester/factmaps_api_no.pdf",
}


def bulk_download_url(name: str, fmt: str = "csv") -> str:
    """Return the FactPages bulk-download URL of a dataset (``fmt`` is ``csv`` or ``shape``)."""
    if name not in BULK_DATASETS:
        raise KeyError(f"unknown bulk dataset {name!r}; known: {sorted(BULK_DATASETS)}")
    if fmt not in ("csv", "shape"):
        raise ValueError("fmt must be 'csv' or 'shape'")
    return FACTPAGES_DOWNLOAD.format(fmt=fmt, name=name)


def factpages_table_url(table: str) -> str:
    """Return the FactPages CSV table-view URL (``table`` is a FactPages view such as ``field_reserves``)."""
    return FACTPAGES_TABLEVIEW_CSV.format(table=table)
