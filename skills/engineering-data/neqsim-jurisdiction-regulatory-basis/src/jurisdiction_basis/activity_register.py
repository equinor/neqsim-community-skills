"""Well and SURF regulatory register per jurisdiction (public orientation data).

Each row names an instrument the design must be checked against for one design topic
(well integrity, subsea equipment, flowlines, risers, ...). Rows carry no clause text and
no limits. ``status`` says how far the row was checked:

* ``verified-public-source``: the title and structure were read at the official source on
  ``verified_on``.
* ``orientation-verify``: curated from public knowledge; fetch the current text before use.

The register supports the three-layer rule of the skill: law and regulation, recognised
standards referenced by the regulation, and company or project requirements. Company
requirements are NOT held here; enterprise overlays add them.
"""

VERIFIED = "verified-public-source"
ORIENTATION = "orientation-verify"

TOPICS = {
    "well_design_integrity": "Well design, well barriers and integrity management",
    "well_control_bop": "Well control, BOP and drilling/well facilities",
    "subsea_equipment": "Subsea wellheads, trees, manifolds, controls and production safety systems",
    "flowlines_pipelines": "Rigid flowlines and pipelines (design, installation, operation)",
    "risers": "Steel and flexible risers, riser-to-host connection",
    "flexibles_umbilicals_cables": "Flexible pipe, umbilicals and power cables",
    "materials_sour_chemicals": "Materials selection, sour service and chemical use",
    "flaring_venting_discharges": "Flaring, venting, well testing and discharges to sea",
    "decommissioning_pa": "Plugging and abandonment and decommissioning",
    "approvals_verification": "Approvals, consents, notifications and independent verification",
}

ACTIVITY_TOPICS = {
    "well": (
        "well_design_integrity",
        "well_control_bop",
        "subsea_equipment",
        "materials_sour_chemicals",
        "flaring_venting_discharges",
        "decommissioning_pa",
        "approvals_verification",
    ),
    "surf": (
        "subsea_equipment",
        "flowlines_pipelines",
        "risers",
        "flexibles_umbilicals_cables",
        "materials_sour_chemicals",
        "decommissioning_pa",
        "approvals_verification",
    ),
}

DESIGN_QUESTIONS = {
    "well_design_integrity": [
        "Is the regime goal-setting or prescriptive, and which standard defines the barrier envelopes and their acceptance tests?",
        "Is a well-integrity management system and independent well examination or verification required before and during operation?",
    ],
    "well_control_bop": [
        "Which BOP configuration, testing frequency and well-control training does the regulation or the operator's licence require?",
    ],
    "subsea_equipment": [
        "Which equipment standard (API 17-series, ISO 13628, NORSOK U-001) is named by the regulation or the contract, and is third-party certification required?",
    ],
    "flowlines_pipelines": [
        "Which authority approves the pipeline route and design, and is the design code mandated (DNV-ST-F101, ASME B31.4/B31.8, API RP 1111, 49 CFR 192/195)?",
    ],
    "risers": [
        "Which riser code applies (DNV-ST-F201, API STD 2RD, ISO 13628-7) and does local law fix the wall-thickness basis or the environmental load case?",
    ],
    "flexibles_umbilicals_cables": [
        "Which flexible-pipe and umbilical standards apply and are there region-only requirements (for example a safety-level requirement set for one continental shelf)?",
    ],
    "materials_sour_chemicals": [
        "Which sour-service standard governs and which chemical approval or notification scheme must the injected chemicals pass?",
    ],
    "flaring_venting_discharges": [
        "Is a flaring or venting consent required for well test, clean-up or process, and what discharge permit applies to produced water and test fluids?",
    ],
    "decommissioning_pa": [
        "What is the barrier standard for permanent abandonment and which authority approves the decommissioning programme?",
    ],
    "approvals_verification": [
        "Which consents, notifications, safety case or verification-scheme steps precede spud, installation and first production?",
        "Is the asset operated by Equinor or by a partner, and whose design basis and authority interface governs?",
    ],
}


def _row(instrument, authority, layer, note, status=ORIENTATION, source="", verified_on=""):
    """Build one register row.

    Args:
        instrument: law, regulation, guideline or standard name.
        authority: authority that issues or enforces it.
        layer: ``law``, ``regulation``, ``guidance``, ``standard-referenced`` or ``contract``.
        note: one-line scope statement; never a limit or clause text.
        status: ``verified-public-source`` or ``orientation-verify``.
        source: URL or document the row was checked against.
        verified_on: ISO date of the check, empty for orientation rows.

    Returns:
        The row as a dict.
    """
    return {
        "instrument": instrument,
        "authority": authority,
        "layer": layer,
        "note": note,
        "status": status,
        "source": source,
        "verified_on": verified_on,
    }


_NO_HAVTIL = "Havtil"
_NO_SRC = "https://www.havtil.no/en/regulations/all-acts/"

REGISTER = {
    "NO": {
        "well_design_integrity": [
            _row("Management Regulations - barrier requirements (section 5)", _NO_HAVTIL, "regulation",
                 "Barriers shall be established and their function known; basis for the well barrier philosophy", source=_NO_SRC),
            _row("Activities Regulations - well activity provisions", _NO_HAVTIL, "regulation",
                 "Well barriers, well control, well integrity monitoring during drilling and well activities; check section numbers at source", source=_NO_SRC),
            _row("Facilities Regulations - drilling and well facility and well design provisions", _NO_HAVTIL, "regulation",
                 "Design of wells and well facilities; guidelines point to NORSOK D-010", source=_NO_SRC),
            _row("NORSOK D-010 Well integrity in drilling and well operations", "Standards Norway", "standard-referenced",
                 "Two well barrier envelopes, barrier element acceptance criteria, well design pressure basis, P&A barriers"),
            _row("ISO 16530-1 Well integrity - life cycle governance; API TR 5C3 / ISO/TR 10400", "ISO / API", "standard-referenced",
                 "Life-cycle integrity management and tubular performance formulas used with D-010"),
        ],
        "well_control_bop": [
            _row("NORSOK D-001 Drilling facilities; Facilities Regulations on BOP and well control equipment", "Standards Norway / " + _NO_HAVTIL,
                 "standard-referenced", "Drilling facility and BOP requirements; verify edition"),
        ],
        "subsea_equipment": [
            _row("NORSOK U-001 Subsea production systems", "Standards Norway", "standard-referenced",
                 "Functional requirements for subsea trees, manifolds, controls; read with ISO 13628"),
            _row("ISO 13628 series and API 17-series subsea equipment specifications", "ISO / API", "standard-referenced",
                 "Wellhead/tree, control systems, flexible pipe, umbilicals"),
        ],
        "flowlines_pipelines": [
            _row("Facilities Regulations - pipeline and subsea facility design provisions", _NO_HAVTIL, "regulation",
                 "Guidelines refer to DNV-ST-F101 for submarine pipeline systems", source=_NO_SRC),
            _row("DNV-ST-F101 Submarine pipeline systems and DNV-RP-F101/F105/F109/F110/F114", "DNV", "standard-referenced",
                 "Pipeline limit states, corroded pipe, free span, on-bottom stability, global buckling, pipe-soil"),
            _row("Petroleum Act - plan for development and operation (PDO/PIO)", "Ministry of Energy", "law",
                 "Pipeline and subsea concept approved as part of the development plan"),
        ],
        "risers": [
            _row("DNV-ST-F201 Riser systems; NORSOK N-003 actions and action effects; NORSOK N-001 structural design", "DNV / Standards Norway",
                 "standard-referenced", "Riser design; environmental load conditions follow N-003 on the Norwegian shelf"),
        ],
        "flexibles_umbilicals_cables": [
            _row("API 17J / 17B / 17L flexible pipe; ISO 13628-5 / API 17E umbilicals; DNV-RP-F401 power cables", "API / ISO / DNV",
                 "standard-referenced", "Flexible pipe, umbilical and subsea power cable design"),
        ],
        "materials_sour_chemicals": [
            _row("NORSOK M-001 Materials selection; NORSOK M-506 CO2 corrosion model; ISO 15156 sour service", "Standards Norway / ISO",
                 "standard-referenced", "Material selection, corrosion rate and sour-service limits"),
            _row("Activities Regulations (environment provisions) and chemical notification under the Pollution Control Act", "Norwegian Environment Agency",
                 "regulation", "Chemical use and discharge permits; HOCNF/PLONOR categorisation practice; verify current text"),
        ],
        "flaring_venting_discharges": [
            _row("Petroleum Act flaring consent; Pollution Control Act discharge permit; CO2 tax and EU ETS", "Ministry of Energy / Norwegian Environment Agency / Tax Administration",
                 "law", "Flaring beyond safety needs needs consent; well test and clean-up flaring and discharges need permits"),
        ],
        "decommissioning_pa": [
            _row("Petroleum Act - cessation plan and decommissioning; OSPAR Decision 98/3", "Ministry of Energy / OSPAR", "law",
                 "Disposal of installations and pipelines; wells plugged to NORSOK D-010 permanent barrier criteria"),
        ],
        "approvals_verification": [
            _row("Havtil consent (samtykke) before drilling and use of facilities; PDO/PIO approval", _NO_HAVTIL + " / Ministry of Energy", "regulation",
                 "Consent applications describe how the Management Regulations are met"),
        ],
    },
    "GB": {
        "well_design_integrity": [
            _row("Offshore Installations and Wells (Design and Construction, etc.) Regulations 1996 (DCR) - wells provisions", "HSE", "regulation",
                 "Well design, well-operator duties, well examination by an independent competent person; check regulation numbers at source",
                 source="https://www.legislation.gov.uk/uksi/1996/913/contents"),
            _row("Offshore Installations (Offshore Safety Directive) (Safety Case etc.) Regulations 2015 (SCR 2015)", "HSE", "regulation",
                 "Safety case, notification of well operations, verification scheme for safety and environmental critical elements"),
            _row("OEUK Well Life Cycle Integrity Guidelines", "Offshore Energies UK", "guidance",
                 "Industry guidance accepted as relevant good practice; check the current issue"),
        ],
        "well_control_bop": [
            _row("DCR 1996 and PFEER 1995 provisions for well control and emergency response", "HSE", "regulation",
                 "Well-control equipment and emergency response; verify at source"),
        ],
        "subsea_equipment": [
            _row("API 17-series and ISO 13628 subsea equipment standards under the ALARP safety-case argument", "API / ISO", "standard-referenced",
                 "No mandated code: the duty-holder demonstrates relevant good practice"),
        ],
        "flowlines_pipelines": [
            _row("Pipelines Safety Regulations 1996 (PSR)", "HSE", "regulation",
                 "Design, construction, operation and decommissioning of pipelines; major accident hazard pipelines",
                 source="https://www.legislation.gov.uk/uksi/1996/825/contents"),
            _row("Petroleum Act 1998 Part III pipeline authorisation; Pipeline Works (Environmental Impact Assessment) Regulations 2000", "NSTA / OPRED", "law",
                 "Pipeline authorisation and environmental assessment"),
            _row("DNV-ST-F101, PD 8010, IGEM/EI guidance", "DNV / BSI / EI", "standard-referenced",
                 "Typical relevant good practice for submarine pipelines; the duty-holder chooses and justifies"),
        ],
        "risers": [
            _row("PSR 1996 and DCR 1996 for risers; DNV-ST-F201, API STD 2RD", "HSE / DNV / API", "regulation",
                 "Riser integrity within the safety case"),
        ],
        "flexibles_umbilicals_cables": [
            _row("PSR 1996 for flexible pipelines; API 17J/17B; Energy Institute and OEUK flexible riser integrity guidance", "HSE / API / OEUK", "guidance",
                 "Flexible pipe integrity management"),
        ],
        "materials_sour_chemicals": [
            _row("Offshore Chemicals Regulations 2002 (OCR) chemical permits", "OPRED", "regulation",
                 "Chemical use and discharge permits, hazard assessment (CHARM-type ranking)"),
            _row("ISO 15156 sour service; NACE/EFC guidance", "ISO", "standard-referenced", "Sour-service materials"),
        ],
        "flaring_venting_discharges": [
            _row("Flaring and venting consent under the licence; Offshore Petroleum Activities (Oil Pollution Prevention and Control) Regulations 2005; UK ETS", "NSTA / OPRED",
                 "regulation", "Consent for flaring and venting, permits for oil in water and well-test discharges"),
        ],
        "decommissioning_pa": [
            _row("Petroleum Act 1998 Part IV decommissioning programmes; OEUK Well Decommissioning Guidelines", "OPRED / OEUK", "law",
                 "Approved decommissioning programme; well abandonment to industry guidelines"),
        ],
        "approvals_verification": [
            _row("Well operation notification, independent well examination and SECE verification scheme", "HSE", "regulation",
                 "Notification before well operations; independent third-party examination and verification are statutory"),
        ],
    },
    "US": {
        "well_design_integrity": [
            _row("30 CFR Part 250 Subpart D Oil and Gas Drilling Operations (Sections 250.400-250.490)", "BSEE", "regulation",
                 "Application for permit to drill, casing and cementing, well control", VERIFIED,
                 "https://www.law.cornell.edu/cfr/text/30/part-250", "2026-11-08"),
            _row("30 CFR Part 250 Subpart E Well-Completion and Subpart F Well-Workover Operations", "BSEE", "regulation",
                 "Completion and workover permits and equipment", VERIFIED, "https://www.law.cornell.edu/cfr/text/30/part-250", "2026-11-08"),
            _row("30 CFR Part 250 Subpart G Well Operations and Equipment (Sections 250.700-250.760)", "BSEE", "regulation",
                 "Well operations and equipment including BOP system requirements; read the sections at source", VERIFIED,
                 "https://www.law.cornell.edu/cfr/text/30/part-250", "2026-11-08"),
            _row("API Standard 65-2 isolating potential flow zones; API RP 90 annular casing pressure; API TR 5C3", "API", "standard-referenced",
                 "Standards incorporated by reference or used as accepted practice; verify the incorporation list in Part 250"),
        ],
        "well_control_bop": [
            _row("API Standard 53 Well control equipment systems for drilling wells", "API", "standard-referenced",
                 "BOP requirements incorporated by reference through Part 250; verify edition"),
        ],
        "subsea_equipment": [
            _row("30 CFR Part 250 Subpart H Oil and Gas Production Safety Systems (Sections 250.800-250.899)", "BSEE", "regulation",
                 "Production safety systems including subsea safety devices", VERIFIED, "https://www.law.cornell.edu/cfr/text/30/part-250", "2026-11-08"),
            _row("API Spec 6A, 16A, 17D, 17G and related; API RP 17A", "API", "standard-referenced", "Subsea wellhead, tree and equipment"),
        ],
        "flowlines_pipelines": [
            _row("30 CFR Part 250 Subpart J Pipelines and Pipeline Rights-of-Way (Sections 250.1000-250.1019)", "BSEE", "regulation",
                 "Lease-term production and injection pipelines on the OCS", VERIFIED, "https://www.law.cornell.edu/cfr/text/30/part-250", "2026-11-08"),
            _row("49 CFR Part 192 (gas) and Part 195 (hazardous liquids)", "PHMSA", "regulation",
                 "Transmission and export pipelines; design pressure and wall thickness rules"),
            _row("API RP 1111 Offshore hydrocarbon pipelines (limit state design)", "API", "standard-referenced",
                 "Accepted as an alternative internal-pressure design basis only through the authority's alternate-compliance process"),
        ],
        "risers": [
            _row("API STD 2RD Dynamic risers for floating production systems", "API", "standard-referenced", "Riser design code"),
            _row("30 CFR Part 250 Subpart J for production risers; 49 CFR 192/195 for export risers", "BSEE / PHMSA", "regulation",
                 "Regulation governing the riser depends on the service"),
        ],
        "flexibles_umbilicals_cables": [
            _row("API 17J, 17B, 17E, 17K and related", "API", "standard-referenced", "Flexible pipe, umbilicals; regulation reaches them through Subparts H and J"),
        ],
        "materials_sour_chemicals": [
            _row("NACE MR0175 / ISO 15156 sour service; 30 CFR 250 H2S provisions (Subpart B/D/H)", "BSEE / ISO", "regulation",
                 "H2S contingency and materials requirements; verify sections"),
        ],
        "flaring_venting_discharges": [
            _row("30 CFR Part 250 Subpart K flaring and venting limits; EPA NPDES permits for discharges; Clean Air Act OCS air rules", "BSEE / EPA / BOEM", "regulation",
                 "Flaring and venting approval; discharge and air permits"),
        ],
        "decommissioning_pa": [
            _row("30 CFR Part 250 Subpart Q Decommissioning Activities (Sections 250.1700-250.1754)", "BSEE", "regulation",
                 "Well plugging, platform and pipeline decommissioning", VERIFIED, "https://www.law.cornell.edu/cfr/text/30/part-250", "2026-11-08"),
        ],
        "approvals_verification": [
            _row("30 CFR Part 250 Subpart B Plans and Information; Subpart S SEMS; third-party verification of safety and pollution prevention equipment", "BSEE / BOEM", "regulation",
                 "Exploration and development plans, SEMS management system", VERIFIED, "https://www.law.cornell.edu/cfr/text/30/part-250", "2026-11-08"),
        ],
    },
    "BR": {
        "well_design_integrity": [
            _row("ANP Resolution 46/2016 - Well Integrity Management System (SGIP)", "ANP", "regulation",
                 "Well integrity management; verify the resolution number and current text at ANP"),
            _row("ANP safety regime: performance-based, predominantly preventive and non-prescriptive, drawn from Norwegian and UK practice", "ANP", "guidance",
                 "The operator proves risks are controlled through the ANP management systems", VERIFIED,
                 "https://www.gov.br/anp/pt-br/assuntos/exploracao-e-producao-de-oleo-e-gas/seguranca-operacional", "2026-11-08"),
        ],
        "well_control_bop": [
            _row("ANP Resolution 43/2007 - SGSO Operational Safety Management System for offshore installations", "ANP", "regulation",
                 "Applies to installations including drilling units"),
        ],
        "subsea_equipment": [
            _row("ANP Resolution 41/2015 - SGSS Subsea Systems Operational Safety Management System", "ANP", "regulation",
                 "Subsea systems including wells' subsea equipment, flowlines, risers and umbilicals"),
        ],
        "flowlines_pipelines": [
            _row("ANP Resolution 41/2015 SGSS for subsea flowlines and pipelines", "ANP", "regulation", "Design basis, integrity management and inspection"),
            _row("DNV-ST-F101, ISO and API pipeline standards accepted under the performance-based regime", "DNV / ISO / API", "standard-referenced",
                 "Choose and justify the code in the SGSS documentation"),
        ],
        "risers": [
            _row("ANP Resolution 41/2015 SGSS; Navy navigation-safety rules (Law 9.537/1997, Decree 2.596/1998)", "ANP / Brazilian Navy", "regulation",
                 "Riser integrity and navigation safety around installations"),
        ],
        "flexibles_umbilicals_cables": [
            _row("ANP Resolution 41/2015 SGSS; API 17J/17B and ISO 13628 for flexible pipe and umbilicals", "ANP / API / ISO", "regulation",
                 "Flexible pipe integrity is a large part of the Brazilian subsea fleet; verify ANP technical requirements"),
        ],
        "materials_sour_chemicals": [
            _row("ISO 15156 sour service; IBAMA licensing and chemical use conditions", "IBAMA", "regulation",
                 "Pre-salt fluids carry high CO2 and some H2S; environmental licence conditions apply to chemicals"),
        ],
        "flaring_venting_discharges": [
            _row("ANP technical regulation on natural gas flaring and losses (verify current resolution number); CONAMA produced-water discharge resolution", "ANP / CONAMA / IBAMA", "regulation",
                 "Flaring authorisation and limits; produced-water discharge limits"),
        ],
        "decommissioning_pa": [
            _row("ANP regulation on decommissioning of E&P installations (verify current resolution)", "ANP", "regulation",
                 "Decommissioning programme and well abandonment", status=ORIENTATION,
                 source="https://www.gov.br/anp/pt-br/assuntos/exploracao-e-producao-de-oleo-e-gas/seguranca-operacional/descomissionamento-de-instalacoes"),
        ],
        "approvals_verification": [
            _row("IBAMA environmental licensing (Ordinance MMA 422/2011 for offshore activities); Navy approvals; ANP document submission under SGSO/SGSS/SGIP", "IBAMA / ANP / Navy", "regulation",
                 "Licences and ANP management-system submissions precede drilling and installation"),
        ],
    },
    "AO": {
        "approvals_verification": [
            _row("Block production sharing agreement and ANPG technical approvals", "ANPG", "contract",
                 "Design requirements are set mainly in the block contract and approved operator procedures; obtain them. Non-operated assets follow the operator's design basis"),
            _row("Petroleum Activities Law (Law 10/04); environmental regulation for petroleum operations (Decree 39/00)", "MIREMPET / ANPG / Ministry of Environment", "law",
                 "Verify current text and any later decrees"),
        ],
        "well_design_integrity": [
            _row("API, ISO and NORSOK/DNV standards named in the block contract or operator well-integrity policy", "Operator / ANPG", "contract",
                 "No public prescriptive well regulation was verified"),
        ],
        "flaring_venting_discharges": [
            _row("ANPG flaring approval and environmental licence conditions", "ANPG / Ministry of Environment", "regulation", "Verify per block"),
        ],
    },
    "CA": {
        "well_design_integrity": [
            _row("Newfoundland Offshore Area Petroleum Drilling and Production Regulations", "C-NLOER", "regulation",
                 "Drilling, well design, approval to drill a well, production; verify the current regulations at the Justice Laws site",
                 source="https://laws-lois.justice.gc.ca"),
        ],
        "approvals_verification": [
            _row("Atlantic Accord Implementation Acts; operations authorisation and certificate of fitness; Impact Assessment Act", "C-NLOER / Impact Assessment Agency", "law",
                 "Authorisations, certificate of fitness for installations and federal impact assessment"),
        ],
        "flaring_venting_discharges": [
            _row("Offshore Waste Treatment Guidelines", "C-NLOER / ECCC / DFO", "guidance", "Produced water and waste discharge limits"),
        ],
    },
    "EU": {
        "approvals_verification": [
            _row("Offshore Safety Directive 2013/30/EU as transposed (for example Denmark, Netherlands)", "National competent authority", "law",
                 "Report on major hazards, well notification, independent verification; national text governs"),
        ],
        "well_design_integrity": [
            _row("National mining or petroleum act well provisions and the well-integrity standards they cite (NORSOK D-010, ISO 16530-1)", "National competent authority", "regulation",
                 "Add the member-state instrument"),
        ],
        "flowlines_pipelines": [
            _row("National pipeline regulation and Pressure Equipment Directive 2014/68/EU for in-scope equipment; DNV-ST-F101", "National authority", "regulation", "Add the member-state instrument"),
        ],
    },
}
