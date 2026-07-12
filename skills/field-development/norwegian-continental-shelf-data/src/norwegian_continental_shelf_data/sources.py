"""Refresh helpers for the public NCS reference dataset.

Deterministic, offline builders for the official public download entry points
(norskpetroleum.no quick-downloads and the Norwegian Offshore Directorate
FactPages) used to refresh the bundled seed. These helpers only *construct and
return* URLs and a download plan; they perform no network access. Save an
exported CSV locally and load it with ``NcsDataset.ingest_sodir_production_csv``
or ``NcsDataset.ingest_sodir_field_reserves_csv``.
"""

from __future__ import annotations

from dataclasses import dataclass

# Verified public entry points (as reused-with-attribution open data).
NORSKPETROLEUM_QUICK_DOWNLOADS = (
    "https://www.norskpetroleum.no/en/interactive-map-quick-downloads/quick-downloads/"
)
SODIR_FACTPAGES = "https://factpages.sodir.no/"

# Known FactPages table identifiers relevant to NCS production analysis. The
# tableview pages expose an "Export -> CSV" action; the exact deep-link/query
# string of the CSV export can change, so the FactPages table page is treated as
# the canonical entry point and should be confirmed against the live site.
_TABLES: tuple[tuple[str, str, str], ...] = (
    (
        "field_production_yearly",
        "Field/aggregate yearly saleable production (oil, gas, NGL, condensate, o.e.)",
        "field/TableView/Production/Saleable/Yearly",
    ),
    (
        "field_reserves",
        "Per-field recoverable and remaining reserves (oil, gas, NGL, condensate, o.e.)",
        "field/TableView/Reserves",
    ),
    (
        "field_overview",
        "Field overview (operator, area, status, discovery/production year)",
        "field/TableView/Overview",
    ),
    (
        "discovery_overview",
        "Discovery overview (discoveries under consideration for development)",
        "discovery/TableView/Overview",
    ),
)


@dataclass(frozen=True)
class DownloadTarget:
    """A single public download entry point for refreshing the dataset."""

    dataset: str
    description: str
    factpages_page_url: str
    quick_downloads_url: str
    ingest_with: str
    note: str


def build_factpages_page_url(table_path: str) -> str:
    """Build a FactPages tableview page URL from a known relative table path."""
    return SODIR_FACTPAGES.rstrip("/") + "/en/" + table_path.lstrip("/")


def sodir_download_plan() -> list[DownloadTarget]:
    """Return the offline refresh plan (URLs + ingestion routing).

    No network access is performed. Use the returned entry points to download an
    official CSV export, then ingest it with the named ``NcsDataset`` method.
    """
    plan: list[DownloadTarget] = []
    for dataset, description, table_path in _TABLES:
        if "Reserves" in table_path:
            ingest = "NcsDataset.ingest_sodir_field_reserves_csv(path)"
        elif "Production" in table_path:
            ingest = "NcsDataset.ingest_sodir_production_csv(path)"
        else:
            ingest = "manual review (field/discovery attributes)"
        plan.append(
            DownloadTarget(
                dataset=dataset,
                description=description,
                factpages_page_url=build_factpages_page_url(table_path),
                quick_downloads_url=NORSKPETROLEUM_QUICK_DOWNLOADS,
                ingest_with=ingest,
                note=(
                    "Open the FactPages page (or the norskpetroleum.no "
                    "quick-downloads tables), export CSV, save locally, then "
                    "ingest. Verify the current export path against the live site."
                ),
            )
        )
    return plan


def refresh_instructions() -> str:
    """Return a short human-readable refresh recipe with attribution."""
    lines = [
        "Refresh the NCS reference data from official public sources:",
        f"  1. Quick-downloads tables: {NORSKPETROLEUM_QUICK_DOWNLOADS}",
        f"  2. FactPages: {SODIR_FACTPAGES}",
        "  3. Export the CSV, save it locally, and ingest with the matching",
        "     NcsDataset method (see sodir_download_plan()).",
        "  4. Keep the source attribution and reference year with reused figures:",
        "     Source: Norwegian Petroleum (www.norskpetroleum.no), Norwegian",
        "     Ministry of Energy and Norwegian Offshore Directorate.",
    ]
    return "\n".join(lines)
