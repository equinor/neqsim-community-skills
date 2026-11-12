"""Allow-listed BSEE Data Center raw files (anonymous HTTPS GET, verified 2026-11-12)."""

from __future__ import annotations

from typing import Any, Dict

HOST = "https://www.data.bsee.gov"
DATA_CENTER_PAGE = f"{HOST}/Main/RawData.aspx"

TERMS = (
    "US Department of the Interior BSEE Data Center, updated daily; provided as is. The Data Center page asks "
    "users to read the BSEE disclaimer before downloading. Cite 'BSEE Data Center' with the retrieval date."
)

SOURCES: Dict[str, Dict[str, Any]] = {
    "investigations": {
        "path": "/Other/Files/IncInvRawData.zip",
        "member": "mv_acc_investigations.txt",
        "columns": ["DATE_OCCURRED", "MILITARY_TIME", "LEASE_NUMBER", "AREA_BLOCK", "ACCIDENT_TYPE",
                    "PANEL_DISTRICT", "STATUS"],
        "describes": "Accident investigations on the US Outer Continental Shelf (about 2000 rows, 1995 to date).",
    },
    "structures": {
        "path": "/Platform/Files/PlatStrucRawData.zip",
        "member": "mv_platstruc_structures.txt",
        "columns": ["AREA_CODE", "BLOCK_NUMBER", "STRUCTURE_NUMBER", "STRUC_TYPE_CODE", "MAJ_STRUC_FLAG",
                    "INSTALL_DATE", "REMOVAL_DATE", "WATER_DEPTH", "MANNED_24_HR_FL"],
        "describes": "Platform structure inventory with install and removal dates (blank removal = still installed).",
    },
}
