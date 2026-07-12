"""Public Norwegian Continental Shelf (NCS) reference dataset.

Loads a bundled, source-attributed snapshot of headline national facts and a
qualitative inventory of major NCS fields (from norskpetroleum.no and the
Norwegian Offshore Directorate FactPages), and provides offline query helpers
plus a tolerant ingestion path for the official Sodir yearly-production CSV
exports.

The bundled data is a *public seed*. Per-field production/reserves and the full
annual production time series must be refreshed by ingesting the official
FactPages / quick-download tables. No proprietary or confidential data is
included.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field as dc_field
from importlib import resources
from typing import Any, Iterable, Mapping, Sequence

_DATA_PACKAGE = "norwegian_continental_shelf_data.data"
_DATA_FILE = "ncs_reference.json"

_VALID_PRODUCTS = ("oil", "gas")

# Standard NCS oil-equivalent convention: 1 Sm3 o.e. = 1000 Sm3 gas, so gas in
# billion Sm3 is numerically equal to million Sm3 o.e. NGL and condensate are
# treated as already expressed in million Sm3 o.e. This mirrors the aggregation
# used in the Sodir/Norwegian Petroleum saleable-production tables.
GAS_BILL_SM3_TO_MILL_SM3_OE = 1.0

# Sodir/Norwegian Petroleum NGL conversion: 1 tonne NGL = 1.9 Sm3 o.e. So NGL in
# million tonnes multiplied by this factor gives million Sm3 o.e.
NGL_TONNE_TO_SM3_OE = 1.9


@dataclass(frozen=True)
class NcsField:
    """A single NCS field reference record (public).

    The qualitative attributes (operator, sea area, product, start year, status)
    come from the bundled public snapshot. The reserve/production volumes are
    optional and default to ``None``; they are populated by ingesting the
    official Sodir field-reserves export (no numbers are invented in the seed).
    """

    name: str
    operator: str
    sea_area: str
    main_product: str
    production_start_year: int
    status: str
    recoverable_oe_mill_sm3: float | None = None
    remaining_oe_mill_sm3: float | None = None
    cumulative_produced_oe_mill_sm3: float | None = None


@dataclass(frozen=True)
class AnnualProduction:
    """One year of aggregated NCS saleable production."""

    year: int
    oe_mill_sm3: float
    oil_mill_sm3: float | None = None
    gas_bill_sm3: float | None = None
    ngl_mill_sm3_oe: float | None = None
    condensate_mill_sm3: float | None = None
    source_url: str | None = None


@dataclass
class NcsDataset:
    """Query interface over the bundled NCS public reference snapshot.

    Load with :meth:`load`. Additional annual production years can be ingested
    from parsed rows (:meth:`ingest_annual_production`) or from a local Sodir
    yearly-production CSV export (:meth:`ingest_sodir_production_csv`). Ingestion
    reads local files only and performs no network access.
    """

    raw: Mapping[str, Any]
    _production: dict[int, AnnualProduction] = dc_field(default_factory=dict)
    _field_reserves: dict[str, dict[str, float]] = dc_field(default_factory=dict)

    # ---- construction -----------------------------------------------------
    @classmethod
    def load(cls) -> "NcsDataset":
        """Load the bundled public reference snapshot."""
        text = (
            resources.files(_DATA_PACKAGE).joinpath(_DATA_FILE).read_text("utf-8")
        )
        raw = json.loads(text)
        dataset = cls(raw=raw)
        for row in raw.get("annual_production_seed", []):
            record = AnnualProduction(
                year=int(row["year"]),
                oe_mill_sm3=float(row["oe_mill_sm3"]),
                source_url=row.get("source_url"),
            )
            dataset._production[record.year] = record
        return dataset

    # ---- metadata ---------------------------------------------------------
    @property
    def meta(self) -> Mapping[str, Any]:
        """Source, license, attribution, and snapshot metadata."""
        return self.raw.get("meta", {})

    @property
    def attribution(self) -> str:
        """Required attribution string for reused figures."""
        return str(self.meta.get("attribution", ""))

    @property
    def snapshot_date(self) -> str:
        """Date the bundled snapshot was captured."""
        return str(self.meta.get("snapshot_date", ""))

    # ---- national KPIs ----------------------------------------------------
    def national_summary(self) -> dict[str, Any]:
        """Return the headline national KPIs (value/unit/year/source each)."""
        return dict(self.raw.get("national", {}))

    def national_kpi(self, key: str) -> Mapping[str, Any]:
        """Return one national KPI record by key.

        Raises ``KeyError`` if the KPI is not present.
        """
        national = self.raw.get("national", {})
        if key not in national:
            raise KeyError(
                f"unknown national KPI {key!r}; available: {sorted(national)}"
            )
        return national[key]

    def resource_accounting(self) -> dict[str, Any]:
        """Return the total/produced/remaining resource accounting block."""
        return dict(self.raw.get("resource_accounting", {}))

    # ---- sea areas --------------------------------------------------------
    def sea_areas(self) -> list[dict[str, Any]]:
        """Return the list of sea-area reference records."""
        return [dict(a) for a in self.raw.get("sea_areas", [])]

    # ---- fields -----------------------------------------------------------
    def fields(self) -> list[NcsField]:
        """Return all bundled field reference records.

        Reserve/production volumes come from the field record itself (if present
        in the seed) and are overlaid by anything ingested via
        :meth:`ingest_field_reserves` / :meth:`ingest_sodir_field_reserves_csv`.
        """
        result: list[NcsField] = []
        for row in self.raw.get("fields", []):
            name = str(row["name"])
            reserves = dict(
                recoverable_oe_mill_sm3=_opt_float(row.get("recoverable_oe_mill_sm3")),
                remaining_oe_mill_sm3=_opt_float(row.get("remaining_oe_mill_sm3")),
                cumulative_produced_oe_mill_sm3=_opt_float(
                    row.get("cumulative_produced_oe_mill_sm3")
                ),
            )
            override = self._field_reserves.get(name.strip().lower())
            if override is not None:
                reserves.update(override)
            result.append(
                NcsField(
                    name=name,
                    operator=str(row["operator"]),
                    sea_area=str(row["sea_area"]),
                    main_product=str(row["main_product"]),
                    production_start_year=int(row["production_start_year"]),
                    status=str(row["status"]),
                    recoverable_oe_mill_sm3=reserves["recoverable_oe_mill_sm3"],
                    remaining_oe_mill_sm3=reserves["remaining_oe_mill_sm3"],
                    cumulative_produced_oe_mill_sm3=reserves[
                        "cumulative_produced_oe_mill_sm3"
                    ],
                )
            )
        return result

    def list_fields(
        self,
        *,
        sea_area: str | None = None,
        main_product: str | None = None,
        status: str | None = None,
        operator: str | None = None,
    ) -> list[NcsField]:
        """Return fields filtered by any combination of attributes."""
        result = self.fields()
        if sea_area is not None:
            area = self._normalize(sea_area)
            result = [f for f in result if f.sea_area == area]
        if main_product is not None:
            product = self._normalize_product(main_product)
            result = [f for f in result if f.main_product == product]
        if status is not None:
            want = str(status).strip().lower()
            result = [f for f in result if f.status.lower() == want]
        if operator is not None:
            want_op = str(operator).strip().lower()
            result = [f for f in result if f.operator.lower() == want_op]
        return result

    def find_field(self, name: str) -> NcsField | None:
        """Return the field whose name matches ``name`` (case-insensitive)."""
        want = str(name).strip().lower()
        for record in self.fields():
            if record.name.lower() == want:
                return record
        return None

    def field_counts(self) -> dict[str, dict[str, int]]:
        """Return field counts grouped by sea area, product, and status."""
        by_area: dict[str, int] = {}
        by_product: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for record in self.fields():
            by_area[record.sea_area] = by_area.get(record.sea_area, 0) + 1
            by_product[record.main_product] = (
                by_product.get(record.main_product, 0) + 1
            )
            by_status[record.status] = by_status.get(record.status, 0) + 1
        return {
            "by_sea_area": dict(sorted(by_area.items())),
            "by_main_product": dict(sorted(by_product.items())),
            "by_status": dict(sorted(by_status.items())),
        }

    # ---- annual production ------------------------------------------------
    def annual_production(self) -> list[AnnualProduction]:
        """Return the annual production series sorted by year."""
        return [self._production[year] for year in sorted(self._production)]

    def production_for_year(self, year: int) -> AnnualProduction | None:
        """Return the production record for ``year`` if present."""
        return self._production.get(int(year))

    def ingest_annual_production(
        self, rows: Iterable[Mapping[str, Any]]
    ) -> int:
        """Ingest parsed annual-production rows into the series.

        Each row must provide ``year`` and either ``oe_mill_sm3`` or enough
        component volumes (oil/gas/ngl/condensate) to derive it. Returns the
        number of years added or updated. Later rows overwrite earlier years.
        """
        added = 0
        for row in rows:
            record = self._build_annual_record(row)
            self._production[record.year] = record
            added += 1
        return added

    def ingest_sodir_production_csv(self, path: str) -> int:
        """Ingest a local Sodir yearly saleable-production CSV export.

        Reads a local file only (no network). Column names are matched
        tolerantly against common Sodir FactPages headers (``prfYear``,
        ``prfPrdOilNetMillSm3``, ``prfPrdGasNetBillSm3``,
        ``prfPrdNGLNetMillSm3``, ``prfPrdCondensateNetMillSm3``,
        ``prfPrdOeNetMillSm3``) and generic headers (``year``, ``oil``,
        ``gas``, ``ngl``, ``condensate``, ``oe``). Returns the number of years
        ingested.
        """
        with open(path, newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            rows = [self._map_sodir_row(raw) for raw in reader]
        rows = [row for row in rows if row is not None]
        return self.ingest_annual_production(rows)

    # ---- per-field reserves ----------------------------------------------
    def ingest_field_reserves(self, rows: Iterable[Mapping[str, Any]]) -> int:
        """Overlay per-field recoverable/remaining/produced volumes.

        Each row must provide ``name`` and any of ``recoverable_oe_mill_sm3``,
        ``remaining_oe_mill_sm3``, ``cumulative_produced_oe_mill_sm3``, or the
        component volumes needed to derive them (``oil_mill_sm3``,
        ``gas_bill_sm3``, ``ngl_mill_tonne``, ``condensate_mill_sm3`` for the
        recoverable set and the ``remaining_*`` equivalents). Values are matched
        to bundled fields by name (case-insensitive). Returns the number of
        fields updated. Missing fields are still stored so custom fields can be
        added.
        """
        added = 0
        for row in rows:
            if "name" not in row:
                raise ValueError("field reserves row must contain 'name'")
            key = str(row["name"]).strip().lower()
            record = self._build_field_reserves_record(row)
            self._field_reserves[key] = record
            added += 1
        return added

    def ingest_sodir_field_reserves_csv(self, path: str) -> int:
        """Ingest a local Sodir field-reserves CSV export.

        Reads a local file only (no network). Column names are matched
        tolerantly against common Sodir FactPages headers (``fldName``,
        ``fldRecoverableOil``, ``fldRecoverableGas``, ``fldRecoverableNGL``,
        ``fldRecoverableCondensate``, ``fldRecoverableOE`` and the
        ``fldRemaining*`` equivalents) and generic headers. NGL is taken in
        million tonnes and converted with :meth:`ngl_tonne_to_sm3_oe`. Returns
        the number of fields ingested.
        """
        with open(path, newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            rows = [self._map_sodir_field_reserves_row(raw) for raw in reader]
        rows = [row for row in rows if row is not None]
        return self.ingest_field_reserves(rows)

    # ---- helpers ----------------------------------------------------------
    def _build_annual_record(self, row: Mapping[str, Any]) -> AnnualProduction:
        if "year" not in row:
            raise ValueError("annual production row must contain 'year'")
        year = int(row["year"])
        oil = _opt_float(row.get("oil_mill_sm3"))
        gas = _opt_float(row.get("gas_bill_sm3"))
        ngl = _opt_float(row.get("ngl_mill_sm3_oe"))
        condensate = _opt_float(row.get("condensate_mill_sm3"))
        oe = _opt_float(row.get("oe_mill_sm3"))
        if oe is None:
            oe = self.oil_equivalent_mill_sm3(
                oil_mill_sm3=oil or 0.0,
                gas_bill_sm3=gas or 0.0,
                ngl_mill_sm3_oe=ngl or 0.0,
                condensate_mill_sm3=condensate or 0.0,
            )
        return AnnualProduction(
            year=year,
            oe_mill_sm3=float(oe),
            oil_mill_sm3=oil,
            gas_bill_sm3=gas,
            ngl_mill_sm3_oe=ngl,
            condensate_mill_sm3=condensate,
            source_url=row.get("source_url"),
        )

    @staticmethod
    def _map_sodir_row(raw: Mapping[str, str]) -> dict[str, Any] | None:
        lookup = {str(k).strip().lower(): v for k, v in raw.items()}

        def pick(*names: str) -> str | None:
            for name in names:
                if name in lookup and str(lookup[name]).strip() != "":
                    return lookup[name]
            return None

        year = pick("prfyear", "year")
        if year is None:
            return None
        return {
            "year": int(float(year)),
            "oil_mill_sm3": pick("prfprdoilnetmillsm3", "oil"),
            "gas_bill_sm3": pick("prfprdgasnetbillsm3", "gas"),
            "ngl_mill_sm3_oe": pick("prfprdnglnetmillsm3", "ngl"),
            "condensate_mill_sm3": pick("prfprdcondensatenetmillsm3", "condensate"),
            "oe_mill_sm3": pick("prfprdoenetmillsm3", "oe"),
        }

    def _build_field_reserves_record(
        self, row: Mapping[str, Any]
    ) -> dict[str, float]:
        recoverable = _opt_float(row.get("recoverable_oe_mill_sm3"))
        remaining = _opt_float(row.get("remaining_oe_mill_sm3"))
        produced = _opt_float(row.get("cumulative_produced_oe_mill_sm3"))
        if recoverable is None:
            recoverable = self._components_to_oe(row, prefix="")
        if remaining is None:
            remaining = self._components_to_oe(row, prefix="remaining_")
        if produced is None and recoverable is not None and remaining is not None:
            produced = round(recoverable - remaining, 4)
        record: dict[str, float] = {}
        if recoverable is not None:
            record["recoverable_oe_mill_sm3"] = round(recoverable, 4)
        if remaining is not None:
            record["remaining_oe_mill_sm3"] = round(remaining, 4)
        if produced is not None:
            record["cumulative_produced_oe_mill_sm3"] = round(produced, 4)
        return record

    @classmethod
    def _components_to_oe(
        cls, row: Mapping[str, Any], *, prefix: str
    ) -> float | None:
        oil = _opt_float(row.get(f"{prefix}oil_mill_sm3"))
        gas = _opt_float(row.get(f"{prefix}gas_bill_sm3"))
        ngl_tonne = _opt_float(row.get(f"{prefix}ngl_mill_tonne"))
        condensate = _opt_float(row.get(f"{prefix}condensate_mill_sm3"))
        if all(v is None for v in (oil, gas, ngl_tonne, condensate)):
            return None
        return (
            (oil or 0.0)
            + (gas or 0.0) * GAS_BILL_SM3_TO_MILL_SM3_OE
            + cls.ngl_tonne_to_sm3_oe(ngl_tonne or 0.0)
            + (condensate or 0.0)
        )

    @staticmethod
    def _map_sodir_field_reserves_row(
        raw: Mapping[str, str]
    ) -> dict[str, Any] | None:
        lookup = {str(k).strip().lower(): v for k, v in raw.items()}

        def pick(*names: str) -> str | None:
            for name in names:
                if name in lookup and str(lookup[name]).strip() != "":
                    return lookup[name]
            return None

        name = pick("fldname", "name", "field")
        if name is None:
            return None
        return {
            "name": str(name).strip(),
            "recoverable_oe_mill_sm3": pick("fldrecoverableoe", "recoverable_oe"),
            "remaining_oe_mill_sm3": pick("fldremainingoe", "remaining_oe"),
            "oil_mill_sm3": pick("fldrecoverableoil"),
            "gas_bill_sm3": pick("fldrecoverablegas"),
            "ngl_mill_tonne": pick("fldrecoverablengl"),
            "condensate_mill_sm3": pick("fldrecoverablecondensate"),
            "remaining_oil_mill_sm3": pick("fldremainingoil"),
            "remaining_gas_bill_sm3": pick("fldremaininggas"),
            "remaining_ngl_mill_tonne": pick("fldremainingngl"),
            "remaining_condensate_mill_sm3": pick("fldremainingcondensate"),
        }

    @staticmethod
    def ngl_tonne_to_sm3_oe(ngl_tonnes: float) -> float:
        """Convert NGL mass to oil equivalent using 1 tonne NGL = 1.9 Sm3 o.e.

        The factor is unit-agnostic: passing NGL in million tonnes returns
        million Sm3 o.e. Follows the Sodir/Norwegian Petroleum convention.
        """
        return float(ngl_tonnes) * NGL_TONNE_TO_SM3_OE

    @staticmethod
    def oil_equivalent_mill_sm3(
        *,
        oil_mill_sm3: float,
        gas_bill_sm3: float,
        ngl_mill_sm3_oe: float,
        condensate_mill_sm3: float,
    ) -> float:
        """Aggregate component volumes into million Sm3 o.e.

        Uses the NCS convention 1 Sm3 o.e. = 1000 Sm3 gas (so gas in billion
        Sm3 equals million Sm3 o.e.). NGL and condensate are assumed already in
        million Sm3 o.e.
        """
        return (
            float(oil_mill_sm3)
            + float(gas_bill_sm3) * GAS_BILL_SM3_TO_MILL_SM3_OE
            + float(ngl_mill_sm3_oe)
            + float(condensate_mill_sm3)
        )

    def _normalize(self, sea_area: str) -> str:
        want = str(sea_area).strip().lower().replace(" ", "_")
        known = {a["id"]: a["id"] for a in self.raw.get("sea_areas", [])}
        # accept display names too
        for area in self.raw.get("sea_areas", []):
            known[str(area["name"]).strip().lower().replace(" ", "_")] = area["id"]
        if want not in known:
            raise ValueError(
                f"unknown sea_area {sea_area!r}; known: {sorted(set(known.values()))}"
            )
        return known[want]

    @staticmethod
    def _normalize_product(product: str) -> str:
        want = str(product).strip().lower()
        if want not in _VALID_PRODUCTS:
            raise ValueError(
                f"main_product must be one of {_VALID_PRODUCTS}, got {product!r}"
            )
        return want


def _opt_float(value: Any) -> float | None:
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None
    return float(value)


def load_dataset() -> NcsDataset:
    """Convenience loader for the bundled NCS public reference snapshot."""
    return NcsDataset.load()
