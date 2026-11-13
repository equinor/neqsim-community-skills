"""Registry of the open, keyless map services the skill may read (host allow-list plus layer catalogue)."""

from __future__ import annotations

from typing import Any, Dict, List

FISKERIDIR = "https://gis.fiskeridir.no/server/rest/services/Yggdrasil"
MILJODIR = "https://kart.miljodirektoratet.no/arcgis/rest/services"
NVE = "https://gis3.nve.no/map/rest/services/Mapservices"
NOAA_HAZARDS = "https://gis.ngdc.noaa.gov/arcgis/rest/services/web_mercator/hazards/MapServer"
EMODNET_HA = "https://ows.emodnet-humanactivities.eu/wfs"
USGS = "https://earthquake.usgs.gov/fdsnws/event/1/query"

ALLOWED_HOSTS = frozenset(
    {
        "gis.fiskeridir.no",
        "kart.miljodirektoratet.no",
        "gis3.nve.no",
        "gis.ngdc.noaa.gov",
        "ows.emodnet-humanactivities.eu",
        "earthquake.usgs.gov",
    }
)

TERMS = (
    "Open public map services; licences differ by owner (Fiskeridirektoratet, Miljodirektoratet and NVE: NLOD 2.0; "
    "EMODnet: free with attribution; NOAA and USGS: public domain). Cite owner and retrieval date."
)


def _wfs(type_name: str, theme: str, what: str) -> Dict[str, Any]:
    return {"kind": "wfs", "url": EMODNET_HA, "type_name": type_name, "theme": theme, "what": what, "owner": "EMODnet"}


def _arcgis(base: str, layer: int, theme: str, what: str, owner: str) -> Dict[str, Any]:
    return {"kind": "arcgis", "url": base, "layer": layer, "theme": theme, "what": what, "owner": owner}


def _raster(layer: int, service: str, theme: str, what: str) -> Dict[str, Any]:
    return {
        "kind": "raster",
        "url": f"{FISKERIDIR}/{service}/MapServer",
        "layer": layer,
        "theme": theme,
        "what": what,
        "owner": "Fiskeridirektoratet",
    }


SOURCES: Dict[str, Dict[str, Any]] = {
    # Fishing and trawling exposure (drives trawl pull-over, burial and rock-dump scope)
    "fishing_bottom_otter_trawls": _wfs("emodnet:fishingbottomottertrawls", "fishing", "Bottom otter trawl effort, 0.05 deg C-squares, European seas"),
    "fishing_beam_trawls": _wfs("emodnet:fishingbeamtrawls", "fishing", "Beam trawl effort, C-squares"),
    "fishing_bottom_seines": _wfs("emodnet:fishingbottomseines", "fishing", "Bottom seine effort, C-squares"),
    "fishing_dredges": _wfs("emodnet:fishingdredges", "fishing", "Dredge effort, C-squares"),
    "fishing_static_gears": _wfs("emodnet:fishingstaticgears", "fishing", "Static gear effort (nets, pots), C-squares"),
    "no_bottom_trawl_intensity": _raster(23, "Bunntråling_1x1km", "fishing", "Norwegian bottom-trawl track density 2025, 1x1 km raster (class value from legend)"),
    "no_fishing_norwegian_vessels_2022_k1": _raster(3, "Fiskeriintensitet_norske_fiskefartøy", "fishing", "Norwegian vessels fishing intensity 2022 quarter 1 (raster)"),
    "no_fishing_foreign_vessels_2022": _raster(4, "Fiskeriintensitet_utenlandske_fiskefartøy", "fishing", "Foreign vessels fishing intensity 2022 (raster)"),
    "no_fixed_gear": _arcgis(f"{FISKERIDIR}/Faststående_redskap_klikkbar/MapServer", 0, "fishing", "Fixed fishing gear (nets, lines, pots)", "Fiskeridirektoratet"),
    "no_lost_gear_2022": _arcgis(f"{FISKERIDIR}/Tapte_redskap/MapServer", 5, "fishing", "Lost fishing gear reports 2022", "Fiskeridirektoratet"),
    # Environmental sensitivity and protection
    "no_coral_reef_ban": _arcgis(f"{FISKERIDIR}/Korallrev/MapServer", 0, "environment", "Coral reef protected (no bottom fishing) areas", "Fiskeridirektoratet"),
    "no_marine_protected": _arcgis(f"{FISKERIDIR}/Marine_verneområder/MapServer", 0, "environment", "Marine protected areas", "Fiskeridirektoratet"),
    "no_svo_bottom_communities": _arcgis(f"{FISKERIDIR}/SVO_miljøverdier/MapServer", 0, "environment", "Particularly valuable and vulnerable areas: bottom communities", "Fiskeridirektoratet / HI"),
    "no_svo_spawning": _arcgis(f"{FISKERIDIR}/SVO_miljøverdier/MapServer", 1, "environment", "Particularly valuable and vulnerable areas: fish spawning", "Fiskeridirektoratet / HI"),
    "no_svo_seabirds": _arcgis(f"{FISKERIDIR}/SVO_miljøverdier/MapServer", 10, "environment", "Particularly valuable and vulnerable areas: seabirds", "Fiskeridirektoratet / HI"),
    "no_mareano_observed_hard_coral_forest": _arcgis(f"{FISKERIDIR}/Sårbare_naturtyper_Mareano/MapServer", 4, "environment", "MAREANO observed hard-bottom coral forest (points)", "Fiskeridirektoratet / MAREANO"),
    "no_mareano_observed_sponge_forest": _arcgis(f"{FISKERIDIR}/Sårbare_naturtyper_Mareano/MapServer", 6, "environment", "MAREANO observed sponge forest (points)", "Fiskeridirektoratet / MAREANO"),
    "no_mareano_glass_sponge": _arcgis(f"{FISKERIDIR}/Sårbare_naturtyper_Mareano/MapServer", 11, "environment", "MAREANO modelled glass sponge communities (polygons)", "Fiskeridirektoratet / MAREANO"),
    "no_mareano_hard_bottom_coral_forest": _arcgis(f"{FISKERIDIR}/Sårbare_naturtyper_Mareano/MapServer", 12, "environment", "MAREANO modelled hard-bottom coral forest (polygons)", "Fiskeridirektoratet / MAREANO"),
    "no_mareano_sea_pen": _arcgis(f"{FISKERIDIR}/Sårbare_naturtyper_Mareano/MapServer", 13, "environment", "MAREANO modelled sea-pen and burrowing megafauna (polygons)", "Fiskeridirektoratet / MAREANO"),
    "no_mareano_sponge_forest": _arcgis(f"{FISKERIDIR}/Sårbare_naturtyper_Mareano/MapServer", 14, "environment", "MAREANO modelled sponge forest (polygons)", "Fiskeridirektoratet / MAREANO"),
    "no_nature_reserves": _arcgis(f"{MILJODIR}/vern/MapServer", 0, "environment", "Norwegian protected nature areas (coastal and island reserves)", "Miljodirektoratet"),
    "no_marine_habitats_hb19": _arcgis(f"{MILJODIR}/naturtyper_marine_hb19/MapServer", 0, "environment", "Marine habitat types (kelp, coral, soft bottom), coastal", "Miljodirektoratet"),
    "eu_marine_protected_areas": _wfs("emodnet:marineprotectedareas", "environment", "Marine protected areas, EU seas"),
    "eu_natura2000": _wfs("emodnet:natura2000areas", "environment", "Natura 2000 areas"),
    # Other sea users and obstacles
    "eu_pipelines": _wfs("emodnet:pipelines", "infrastructure", "Pipelines (diameter in inches, medium, operator, year); check status per feature"),
    "eu_platforms": _wfs("emodnet:platforms", "infrastructure", "Offshore platforms"),
    "eu_windfarms_poly": _wfs("emodnet:windfarmspoly", "wind", "Offshore wind farm areas"),
    "eu_windfarms": _wfs("emodnet:windfarms", "wind", "Offshore wind farm points"),
    "eu_munitions_poly": _wfs("emodnet:munitionspoly", "hazard", "Dumped munitions areas"),
    "eu_shipwrecks": _wfs("emodnet:wwshipwrecks", "hazard", "Shipwrecks (worldwide wrecks)"),
    "eu_military_areas": _wfs("emodnet:militaryareaspoly", "restriction", "Military areas"),
    "eu_msp_zoning": _wfs("emodnet:mspzoningpoly", "restriction", "Maritime spatial planning zones"),
    # Offshore wind and grid (electrification, power from shore)
    "no_wind_areas_2023": _arcgis(f"{FISKERIDIR}/Identifiserte_området_for_havvind_2023/MapServer", 0, "wind", "Identified offshore wind areas 2023", "Fiskeridirektoratet / NVE"),
    "no_wind_areas_current": _arcgis(f"{NVE}/Havvind2025/MapServer", 12, "wind", "Current offshore wind areas", "NVE"),
    "no_grid_central": _arcgis(f"{NVE}/Nettanlegg2_label/MapServer", 0, "grid", "Central grid lines (420 and 300 kV)", "NVE"),
    "no_grid_regional": _arcgis(f"{NVE}/Nettanlegg2_label/MapServer", 2, "grid", "Regional grid lines (132 kV and 66 kV)", "NVE"),
    "no_grid_subsea_cables": _arcgis(f"{NVE}/Nettanlegg2_label/MapServer", 6, "grid", "Subsea power cables", "NVE"),
    "no_grid_substations": _arcgis(f"{NVE}/Nettanlegg2_label/MapServer", 9, "grid", "Transformer substations", "NVE"),
    "no_grid_planned_lines": _arcgis(f"{NVE}/NettanleggKonsesjon/MapServer", 0, "grid", "Licensed power lines not yet built", "NVE"),
    # Geohazards (global historic catalogues)
    "world_significant_earthquakes": _arcgis(NOAA_HAZARDS, 5, "hazard", "NOAA NCEI significant earthquakes (historic catalogue)", "NOAA NCEI"),
    "world_volcanoes": _arcgis(NOAA_HAZARDS, 7, "hazard", "Volcano locations (Smithsonian)", "NOAA NCEI"),
    "world_tsunami_events": _arcgis(NOAA_HAZARDS, 0, "hazard", "Historic tsunami events", "NOAA NCEI"),
}

THEMES = sorted({spec["theme"] for spec in SOURCES.values()})


def keys_for_theme(*themes: str) -> List[str]:
    """Return the registry keys whose theme is one of ``themes`` (sorted)."""
    return sorted(k for k, s in SOURCES.items() if s["theme"] in themes)
