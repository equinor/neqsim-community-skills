"""Public, curated jurisdiction profiles for offshore and onshore oil and gas studies.

The profiles name the authorities, governing laws and regulation families an engineer
must check. They are orientation data only: they carry no clause text, limits or
legal interpretation, and every profile must be verified against the current
revision at the authority before any compliance statement is made.
"""

PROFILES = {
    "NO": {
        "name": "Norway (Norwegian continental shelf and onshore petroleum facilities)",
        "authorities": [
            "Havtil (Norwegian Ocean Industry Authority, formerly the Petroleum Safety Authority) - safety, working environment, emergency preparedness",
            "Norwegian Environment Agency (Miljodirektoratet) - discharges, emissions, permits",
            "Norwegian Offshore Directorate (Sodir, formerly NPD) - resource management, data, flaring and resource consents",
            "Ministry of Energy - licences, PDO/PIO approval, flaring consent",
            "Norwegian Tax Administration - petroleum tax, CO2 tax",
        ],
        "laws": [
            "Petroleum Act (petroleumsloven)",
            "Working Environment Act (arbeidsmiljoloven), applied through the framework regulations",
            "Pollution Control Act (forurensningsloven)",
            "Greenhouse Gas Emission Trading Act (kvoteloven)",
            "Petroleum Taxation Act and CO2 tax on petroleum activity on the continental shelf",
        ],
        "safety_regulations": [
            "Framework Regulations (rammeforskriften)",
            "Management Regulations (styringsforskriften)",
            "Facilities Regulations (innretningsforskriften)",
            "Activities Regulations (aktivitetsforskriften)",
            "Technical and Operational Regulations (teknisk og operasjonell forskrift) for onshore facilities",
        ],
        "recognised_standards": [
            "NORSOK standards (Standards Norway), referenced from the regulation guidelines",
            "ISO, IEC, EN and DNV standards referenced by the guidelines",
        ],
        "pressure_equipment": "EEA-implemented pressure equipment rules onshore; offshore facilities follow the Facilities Regulations and referenced standards",
        "fiscal_note": "Cash-flow-based petroleum tax: 22 % ordinary plus 56 % special petroleum tax (78 % marginal); CO2 tax and EU ETS apply on top",
        "data_sources": [
            "https://lovdata.no (regulation text, official Norwegian and unofficial English)",
            "https://www.havtil.no (guidelines to the regulations)",
            "https://www.sodir.no and https://www.norskpetroleum.no",
        ],
    },
    "GB": {
        "name": "United Kingdom (UK continental shelf and onshore)",
        "authorities": [
            "Health and Safety Executive (HSE) - offshore and onshore safety",
            "North Sea Transition Authority (NSTA, formerly OGA) - licensing and resource stewardship",
            "OPRED (Offshore Petroleum Regulator for Environment and Decommissioning) - environmental permits and decommissioning",
            "HMRC - ring-fence corporation tax, supplementary charge, Energy Profits Levy",
        ],
        "laws": [
            "Health and Safety at Work etc. Act 1974",
            "Petroleum Act 1998",
            "UK Emissions Trading Scheme orders",
        ],
        "safety_regulations": [
            "Offshore Installations (Offshore Safety Directive) (Safety Case etc.) Regulations 2015 (SCR 2015)",
            "Offshore Installations (Prevention of Fire and Explosion, and Emergency Response) Regulations 1995 (PFEER)",
            "Offshore Installations and Wells (Design and Construction, etc.) Regulations 1996 (DCR)",
            "Pipelines Safety Regulations 1996 (PSR)",
            "Pressure Systems Safety Regulations 2000 (PSSR)",
            "Dangerous Substances and Explosive Atmospheres Regulations 2002 (DSEAR)",
            "COMAH Regulations 2015 for onshore major-hazard sites",
        ],
        "recognised_standards": [
            "Goal-setting regime: risk reduced as low as reasonably practicable (ALARP) and demonstrated in the safety case",
            "Relevant good practice: API, ISO, BS EN, Energy Institute guidance",
        ],
        "pressure_equipment": "Pressure Equipment (Safety) Regulations 2016 and UKCA marking for new equipment",
        "fiscal_note": "Ring-fence corporation tax plus supplementary charge plus the Energy Profits Levy; rates and expiry change, verify current rates",
        "data_sources": [
            "https://www.legislation.gov.uk",
            "https://www.hse.gov.uk/offshore",
            "https://www.nstauthority.co.uk",
        ],
    },
    "US": {
        "name": "United States (Outer Continental Shelf, onshore and pipelines)",
        "authorities": [
            "BSEE - OCS safety and environmental enforcement",
            "BOEM - OCS leasing and environmental review",
            "PHMSA - pipeline safety",
            "EPA - air emissions, methane, greenhouse gas reporting",
            "OSHA - workplace process safety (onshore)",
            "US Coast Guard - floating and manned OCS facilities",
            "State agencies for onshore activity (for example Texas Railroad Commission)",
        ],
        "laws": [
            "Outer Continental Shelf Lands Act",
            "Clean Air Act",
            "Pipeline Safety Act",
        ],
        "safety_regulations": [
            "30 CFR Part 250 (BSEE), including Subpart H production safety systems",
            "49 CFR Parts 192 (gas) and 195 (hazardous liquids) pipelines",
            "40 CFR Part 60 subparts OOOOb and OOOOc (oil and gas methane) and Part 98 subpart W (reporting)",
            "29 CFR 1910.119 process safety management (onshore)",
        ],
        "recognised_standards": [
            "API standards incorporated by reference (for example API RP 14C, API RP 14J, API 520/521)",
            "ASME BPVC and B31 piping codes",
        ],
        "pressure_equipment": "ASME BPVC stamping; state boiler and pressure vessel laws apply onshore",
        "fiscal_note": "Federal corporate income tax, royalties and state severance taxes; lease terms govern royalties, verify per lease",
        "data_sources": [
            "https://www.ecfr.gov",
            "https://www.bsee.gov",
            "https://www.phmsa.dot.gov",
        ],
    },
    "BR": {
        "name": "Brazil (offshore pre-salt and post-salt, onshore)",
        "authorities": [
            "ANP (National Agency for Petroleum, Natural Gas and Biofuels) - regulation, licensing, operational safety",
            "IBAMA - environmental licensing",
            "Brazilian Navy (Marinha) - maritime safety and vessel classification",
            "Ministry of Labour - regulatory norms (NR) for workplace safety",
            "PPSA - manager of production sharing contracts",
        ],
        "laws": [
            "Petroleum Law (Lei 9.478/1997)",
            "Pre-salt production sharing law (Lei 12.351/2010)",
        ],
        "safety_regulations": [
            "ANP Resolution 43/2007 - Operational Safety Management System (SGSO) for offshore installations",
            "NR-13 pressure vessels and boilers, NR-20 flammable and combustible liquids, NR-37 offshore platform safety and health",
            "ANP technical regulations on flaring and gas losses (verify the current resolution)",
        ],
        "recognised_standards": [
            "ABNT NBR standards; ANP accepts ISO, API, ASME and DNV standards where the regulation allows",
        ],
        "pressure_equipment": "NR-13 governs inspection and operation of pressure vessels; design codes ASME or equivalent",
        "fiscal_note": "Contract-dependent: concession (royalties, special participation) or production sharing (profit oil, royalties); local content commitments apply",
        "data_sources": [
            "https://www.gov.br/anp",
            "https://dados.gov.br (ANP open data)",
        ],
    },
    "EU": {
        "name": "European Union baseline (member-state transposition and national authority must be added)",
        "authorities": [
            "National competent authority of the member state (for example the Danish Energy Agency and Danish Working Environment Authority for Denmark)",
        ],
        "laws": [
            "Offshore Safety Directive 2013/30/EU",
            "Pressure Equipment Directive 2014/68/EU",
            "ATEX equipment directive 2014/34/EU and workplace directive 1999/92/EC",
            "Seveso III Directive 2012/18/EU (onshore)",
            "Industrial Emissions Directive 2010/75/EU",
            "EU ETS Directive 2003/87/EC",
            "Methane Regulation (EU) 2024/1787",
        ],
        "safety_regulations": ["National transposition of the directives above"],
        "recognised_standards": ["Harmonised EN standards under each directive"],
        "pressure_equipment": "CE marking under the Pressure Equipment Directive",
        "fiscal_note": "National regime per member state",
        "data_sources": ["https://eur-lex.europa.eu"],
    },
}

ALIASES = {
    "NO": "NO", "NORWAY": "NO", "NORGE": "NO", "NCS": "NO", "NORWEGIAN CONTINENTAL SHELF": "NO",
    "GB": "GB", "UK": "GB", "UKCS": "GB", "UNITED KINGDOM": "GB", "GREAT BRITAIN": "GB",
    "US": "US", "USA": "US", "UNITED STATES": "US", "GOM": "US", "GULF OF MEXICO": "US",
    "BR": "BR", "BRAZIL": "BR", "BRASIL": "BR",
    "EU": "EU", "DK": "EU", "DENMARK": "EU", "NL": "EU", "NETHERLANDS": "EU", "EUROPEAN UNION": "EU",
}
