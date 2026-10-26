"""Task-to-data recipes: which Sodir layers/tables answer which engineering question, and the traps."""

from __future__ import annotations

from typing import Any, Dict, List

GOTCHAS: List[str] = [
    "www.sodir.no pages return HTTP 403 to scripts: use factmaps.sodir.no (REST) and factpages.sodir.no (CSV/ZIP).",
    "DataService geometry is ED50 (EPSG:4230). Request out_sr=4326 for WGS84 before mixing with other maps.",
    "Server page limit is 2000 rows; the client pages automatically. Use where/bbox/out_fields to keep reads small.",
    "Dates are epoch milliseconds (local midnight is the previous UTC day): convert with Europe/Oslo.",
    "Join on the *Npdid* integer keys (e.g. wlbNpdidWellbore, fldNpdidField, prlNpdidLicence), never on names.",
    "Names are not unique over time (wells are renamed, fields merge): carry the Npdid key and the retrieval date.",
    "'_hst' tables hold history rows with valid-from/valid-to: filter on the date columns for 'current' ownership.",
    "Volumes: MillSm3/BillSm3 are standard m3; reserves are Sodir's official estimates, not company estimates.",
    "Shape/CSV bulk files omit attributes; the FGDB or REST services are complete. Infield pipelines are not in pipLine.",
    "Prospect equity/volumes, seismic data, well logs and reports are NOT in the open data (Diskos/licensees).",
    "Always record provenance (URL, rows, retrieval time) and cite: Norwegian Offshore Directorate, NLOD 2.0.",
]

USE_CASES: Dict[str, Dict[str, Any]] = {
    "wellbores": {
        "question": "Which wells exist near/within a field, block or box; type, status, depth, water depth, HC content?",
        "layers": ["wellbore (5000, point)"],
        "join_keys": ["wlbNpdidWellbore", "fldNpdidField", "dscNpdidDiscovery", "prlNpdidProductionLicence"],
        "tips": ["Filter wlbPurpose / wlbWellType / wlbContent / wlbStatus (use distinct()).",
                 "bbox query with out_sr=4326 for a distance screen.",
                 "wlbWith* flags tell which child tables have data for the wellbore."],
    },
    "pvt_and_reservoir_data": {
        "question": "What fluid and reservoir evidence exists for a discovery or field (no PVT report, but samples/tests)?",
        "layers": ["wellbore_dst (5008)", "wellbore_oil_sample (5013)", "wellbore_core (5003)",
                   "wellbore_formation_top (5009)", "wellbore_co2 (5002)", "wellbore_mud (5012)",
                   "wellbore_log (5011)"],
        "join_keys": ["wlbNpdidWellbore"],
        "tips": ["DST gives BHP, BHT, choke, oil/gas rates, densities and GOR (wlbDstGasOilRelation) - a fluid-basis prior.",
                 "wlbBottomHoleTemperature on the wellbore header and DST pressure bound reservoir P/T.",
                 "Oil-sample rows tell what was sampled, not the composition: composition needs the licensee report.",
                 "Formation tops give reservoir depth and TVD for hydrostatic pressure estimates."],
    },
    "production_history": {
        "question": "Yearly/monthly saleable oil, gas, NGL, condensate, produced water per field/discovery.",
        "layers": ["profiles (7300 table)", "FactPages: field_production_yearly / field_production_monthly"],
        "join_keys": ["prfNpdidInformationCarrier", "fldNpdidField"],
        "tips": ["prfInformationCarrierKind separates field/discovery/total series; prfPeriod gives year/month.",
                 "Feed Arps decline fitting (reservoir-forecasting-agent) and history matching."],
    },
    "reserves_and_resources": {
        "question": "Recoverable, remaining and in-place volumes; discovery resources and RC class.",
        "layers": ["field_reserves (7113)", "field_reserves_company (7114)", "discovery_reserves (7008)",
                   "field_description (7102)", "discovery_description (7001)"],
        "join_keys": ["fldNpdidField", "dscNpdidDiscovery"],
        "tips": ["field_reserves keeps archived versions (fldVersion, fldDateOffResEstDisplay): take the latest.",
                 "discovery_reserves carries the resource class (dscReservesRC) for the RC0-RC9 maturity ladder."],
    },
    "ownership_and_operators": {
        "question": "Who owns/operates a field, discovery or licence, and when did it change?",
        "layers": ["field_licensee_hst (7108)", "field_operator_hst (7110)", "field_owner_hst (7111)",
                   "discovery_owner_hst (7007)", "licence_licensee_hst (3007)", "licence_oper_hst (3008)",
                   "licence_transfer_hst (3003)", "company (1200)"],
        "join_keys": ["fldNpdidField", "dscNpdidDiscovery", "prlNpdidLicence", "cmpNpdidCompany"],
        "tips": ["Filter *_hst on the valid-to column being null for current partners.",
                 "For net-equity calculations use the neqsim-ncs-ownership-equity skill built on these tables."],
    },
    "facilities_and_pipelines": {
        "question": "Hosts, platforms, subsea facilities, pipelines (from/to, medium, dimension), owners, phase.",
        "layers": ["facility (6000, point)", "pipeline (6100, line)", "facility_function (6001)",
                   "facility_phase_hst (6002)", "tuf (6200)", "tuf_owner_hst (6202)", "tuf_operator_hst (6201)"],
        "join_keys": ["fclNpdidFacility", "pplNpdidPipeline", "fclNpdidFacilityFrom", "fclNpdidFacilityTo", "tufNpdidTuf"],
        "tips": ["Sodir pipelines are the main (TUF) pipelines; infield lines are missing.",
                 "Feed the graph builder in neqsim-ncs-infrastructure-network and tie-back screening."],
    },
    "licences_and_blocks": {
        "question": "Licence status/area/phase, licensing rounds, blocks and quadrants, APA/TFO areas, AFEX.",
        "layers": ["licence (3000)", "licence_phase_hst (3009)", "licence_task (3010)", "block (1001)",
                   "quadrant (1002)", "sub_area (1003)", "licensing_activity (3100)",
                   "licensing_activity_apa_gross (3102)", "licensing_activity_apa_open (3103)",
                   "bsns_arr_area (3300)", "afex_area (3200)"],
        "join_keys": ["prlNpdidLicence", "blcName"],
        "tips": ["Work obligations and deadlines are in licence_task (epoch ms, local midnight).",
                 "CO2 storage licences are business arrangement areas (bsns_arr_area), not production licences."],
    },
    "seismic_and_surveys": {
        "question": "Which geophysical/shallow/EM surveys were done or are planned, where, by whom, when?",
        "layers": ["seis_acquisition (4000, polygon)", "seis_acquisition_progress_notes (4011)",
                   "seis_acquisition_weekly_plan (4015)", "seis_acquisition_vessel (4013)", "sbm_survey_area (4502)"],
        "join_keys": ["seaNpdidSurvey"],
        "tips": ["Survey metadata only; the seismic data itself is in Diskos and needs a licence.",
                 "Ongoing/planned map: see VIEWERS['survey_map_ongoing_planned']."],
    },
    "co2_storage": {
        "question": "CO2 storage licences, injection history, storage depth/thickness/options themes.",
        "layers": ["csd_injection (9001 table)", "wellbore_co2 (5002)", "bsns_arr_area (3300)",
                   "Themes/CO2_storage_depths_1_0, CO2_storage_options_1_0, CO2_storage_thickness_1_0 (MapServer)"],
        "join_keys": ["cslNpdidLicence", "wlbNpdidWellbore"],
        "tips": ["Injection is tonnes per well and month: sum per project for ramp-up and cumulative mass.",
                 "Storage atlas surfaces: FGDB SODIR_CCS_StorageAtlas.zip (see downloads.OTHER_DATA)."],
    },
    "geology": {
        "question": "Stratigraphy, structural elements, plays.",
        "layers": ["strat_litho (2100)", "strat_litho_wellbore (2101)", "strat_chrono (2200)",
                   "str_structuralelements (2000)", "str_domes (2001)", "str_faultsandboundaries (2002)",
                   "play_current_public (7800)"],
        "join_keys": ["lsuNpdidLithoStrat", "wlbNpdidWellbore"],
        "tips": ["Use formation tops per wellbore (5009) with the lithostratigraphic parent for reservoir picks."],
    },
    "seabed_minerals": {
        "question": "Seabed-mineral surveys, samples and occurrences.",
        "layers": ["sbm_survey_area (4502)", "sbm_survey_line (4503)", "sbm_sample_point (4501)",
                   "sbm_occurence (8001)", "sbm_block (1004)", "sbm_play_resource_estimate_area (8002)"],
        "join_keys": [],
        "tips": ["Deep-sea raw data is ordered from Sodir (downloads.OTHER_DATA)."],
    },
    "bulk_and_gis": {
        "question": "Whole-shelf files for GIS or offline work.",
        "layers": ["downloads.BULK_DATASETS (shape/csv zip), FGDB SODIR_FactMaps_data_v3_0.zip"],
        "join_keys": [],
        "tips": ["CSV zips carry WKT geometry; FGDB is the only complete package.",
                 "OGC WMS/WFS: FactMapsWGS84 and FactMapsED50UTM32 MapServers (see downloads)."],
    },
}


def use_case(topic: str) -> Dict[str, Any]:
    """Return the recipe of a topic (key or unique prefix) with the global gotchas attached."""
    keys = [k for k in USE_CASES if k == topic or k.startswith(topic)]
    if len(keys) != 1:
        raise KeyError(f"topic {topic!r} is ambiguous or unknown; choose from {sorted(USE_CASES)}")
    return dict(USE_CASES[keys[0]], topic=keys[0], gotchas=GOTCHAS)
