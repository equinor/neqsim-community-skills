"""Resolve who owns Norwegian Continental Shelf fields, discoveries and licences from Sodir."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

from .model import OwnershipError, OwnershipRecord, Stake, check_prospect_stakes
from .sodir import (LICENCE_TASK_LAYER, SODIR_FACTMAPS, Fetch, SodirClient, default_fetch, sql_quote, to_date,
                    to_local_date)

PRODUCTION_LICENCE = "PRODUCTION LICENCE"
BUSINESS_AREA = "BUSINESS ARRANGEMENT AREA"
PROSPECT_NOTE = ("Sodir does not publish prospect-level equity. The partners shown are the licence's; "
                 "confirm the prospect's own sharing with the licence group before using it in economics.")


@dataclass
class PortfolioItem:
    """One asset in which a company holds an interest."""

    kind: str
    name: str
    interest_pct: float
    owner_kind: Optional[str]
    owner_name: Optional[str]
    status: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


def _valid(row: Mapping[str, Any], from_key: str, to_key: str, on: date) -> bool:
    """Sodir period test: ``to`` is the inclusive last day, an empty end is open."""
    start, end = to_date(row.get(from_key)), to_date(row.get(to_key))
    return (start is None or start <= on) and (end is None or on <= end)


def _latest(rows: Sequence[Mapping[str, Any]], from_key: str) -> List[Mapping[str, Any]]:
    """Rows of the most recent period, used when nothing is valid on the requested date."""
    if not rows:
        return []
    best = max((to_date(r.get(from_key)) or date.min) for r in rows)
    return [r for r in rows if (to_date(r.get(from_key)) or date.min) == best]


def _id_from_url(url: Optional[str]) -> Optional[int]:
    match = re.search(r"/(\d+)$", url or "")
    return int(match.group(1)) if match else None


def _latest_date(rows: Iterable[Mapping[str, Any]], key: str) -> Optional[date]:
    dates = [d for d in (to_date(r.get(key)) for r in rows) if d]
    return max(dates) if dates else None


class OwnershipReader:
    """Read ownership from Sodir. Pass ``fetch`` to run offline."""

    def __init__(self, fetch: Fetch = default_fetch, **client_options: Any) -> None:
        self.client = SodirClient(fetch, **client_options)

    # ------------------------------------------------------------------ fields

    def field(self, name: str, as_of: Optional[date] = None) -> OwnershipRecord:
        """Equity of a producing or past field on ``as_of`` (default today)."""
        on = as_of or date.today()
        fld = self._resolve("field", "fldName", "fldNpdidField", name, "field")
        fid = int(fld["fldNpdidField"])
        rows = [r for r in self.client.query("field_licensee_hst", f"fldNpdidField={fid}")
                if int(r["fldNpdidField"]) == fid]
        warnings: List[str] = []
        active = [r for r in rows if _valid(r, "fldLicenseeFrom", "fldLicenseeTo", on)]
        if not active:
            active = _latest(rows, "fldLicenseeFrom")
            warnings.append(f"no interests are valid on {on}; showing the most recent period")
        operator_id, operator = self._operator("field_operator_hst", f"fldNpdidField={fid}", "fldNpdidField", fid,
                                               "fldOperatorFrom", "fldOperatorTo", on, fld)
        stakes = [Stake(r["cmpLongName"], r.get("cmpNpdidCompany"), float(r["fldCompanyShare"] or 0.0),
                        r.get("fldSdfiShare"), to_date(r.get("fldLicenseeFrom")), to_date(r.get("fldLicenseeTo")),
                        r.get("cmpNpdidCompany") == operator_id) for r in active]
        owners = {(r.get("fldOwnerKind"), r.get("fldOwnerName")) for r in active}
        if len(owners) > 1:
            warnings.append(f"interests come from several owners {sorted(map(str, owners))}")
        owner_kind, owner_name = next(iter(owners)) if owners else (None, None)
        record = OwnershipRecord("field", str(fld["fldName"]), on, "sodir_public", stakes, fid, owner_kind,
                                 owner_name, operator, None, _latest_date(active, "fldLicenseeDateUpdated"),
                                 "Sodir field_licensee_hst (layer 7108)", warnings)
        return self._finish(record)

    # --------------------------------------------------------------- discoveries

    def discovery(self, name: str, as_of: Optional[date] = None) -> OwnershipRecord:
        """Equity of a discovery: its owner licence or unit, then that owner's licensees."""
        on = as_of or date.today()
        dsc = self._resolve("discovery", "dscName", "dscNpdidDiscovery", name, "discovery")
        did = int(dsc["dscNpdidDiscovery"])
        owners = [r for r in self.client.query("discovery_owner_hst", f"dscNpdidDiscovery={did}")
                  if int(r["dscNpdidDiscovery"]) == did]
        if not owners:
            raise OwnershipError(f"Sodir lists no owner for discovery '{dsc['dscName']}'")
        warnings: List[str] = []
        current = [r for r in owners if _valid(r, "dscOwnershipFromDate", "dscOwnershipToDate", on)]
        if not current:
            current = _latest(owners, "dscOwnershipFromDate")
            warnings.append(f"no owner is valid on {on}; showing the most recent owner")
        owner = current[0]
        owner_id = _id_from_url(owner.get("dscOwnerFactPageUrl"))
        if owner_id is None:
            raise OwnershipError(f"cannot read the owner id for discovery '{dsc['dscName']}'")
        stakes, updated, extra = self._licensee_stakes(owner["dscOwnerKind"], owner_id, on)
        warnings.extend(extra)
        operator_id, operator = self._operator("discovery_operator_hst", f"dscNpdidDiscovery={did}",
                                               "dscNpdidDiscovery", did, "dscOperatorFrom", "dscOperatorTo", on, dsc)
        stakes = [self._mark_operator(s, operator_id) for s in stakes]
        included = dsc.get("fldName")
        if included:
            warnings.append(f"discovery is included in field {included}; the field's equity governs production "
                            f"(use field('{included}'))")
        record = OwnershipRecord("discovery", str(dsc["dscName"]), on, "sodir_public", stakes, did,
                                 owner["dscOwnerKind"], owner["dscOwnerName"], operator, included, updated,
                                 "Sodir discovery_owner_hst (7007) + licensee history (3007/3304)", warnings)
        return self._finish(record)

    # ------------------------------------------------------------------ licences

    def licence(self, name: str, as_of: Optional[date] = None) -> OwnershipRecord:
        """Equity of a production licence, e.g. ``'537'``."""
        on = as_of or date.today()
        key = name.strip().upper()
        rows = [r for r in self.client.query("licence_licensee_hst", f"UPPER(prlName)={sql_quote(key)}")
                if str(r["prlName"]).upper() == key]
        ids = {int(r["prlNpdidLicence"]) for r in rows}
        if not ids:
            raise OwnershipError(f"no production licence named '{name}'")
        if len(ids) > 1:
            raise OwnershipError(f"licence name '{name}' is ambiguous: {sorted(ids)}")
        lid = ids.pop()
        stakes, updated, warnings = self._licensee_stakes(PRODUCTION_LICENCE, lid, on)
        operators = [s for s in stakes if s.is_operator]
        record = OwnershipRecord("licence", str(rows[0]["prlName"]), on, "sodir_public", stakes, lid,
                                 PRODUCTION_LICENCE, str(rows[0]["prlName"]),
                                 operators[0].company if operators else None, None, updated,
                                 "Sodir licence_licensee_hst (layer 3007)", warnings)
        return self._finish(record)

    def licence_milestones(self, name: str) -> List[Dict[str, Any]]:
        """Work obligations of a production licence with local (Europe/Oslo) deadlines.

        Returns one dict per task (``code``, ``task``, ``category``, ``status``, ``deadline``
        as an ISO date), ordered by deadline. Typical codes are the drill-or-drop decision,
        the decision to continue, and the plan for development and operation.

        Raises:
            OwnershipError: when the licence name is unknown or ambiguous.
        """
        key = name.strip().upper()
        rows = [r for r in self.client.query("licence_licensee_hst", f"UPPER(prlName)={sql_quote(key)}")
                if str(r["prlName"]).upper() == key]
        ids = {int(r["prlNpdidLicence"]) for r in rows}
        if len(ids) != 1:
            raise OwnershipError(f"licence name '{name}' is unknown or ambiguous: {sorted(ids)}")
        lid = ids.pop()
        tasks = self.client.query(LICENCE_TASK_LAYER, f"prlNpdidLicence={lid}", service=SODIR_FACTMAPS)
        out = []
        for t in tasks:
            deadline = to_local_date(t.get("prlTaskExpiryDate"))
            out.append({"code": t.get("prlTaskTypeCode"), "task": t.get("prlTaskTypeEn"),
                        "category": t.get("prlTaskCategory"), "status": t.get("prlTaskStatusEn"),
                        "deadline": deadline.isoformat() if deadline else None})
        return sorted(out, key=lambda r: r["deadline"] or "")

    # ----------------------------------------------------------------- prospects

    def prospect_from_licence(self, prospect: str, licence: str, as_of: Optional[date] = None) -> OwnershipRecord:
        """Public proxy for a prospect: the equity of the licence it sits in, labelled as a proxy."""
        record = self.licence(licence, as_of)
        record.kind, record.name, record.basis = "prospect", prospect, "licence_proxy"
        record.warnings.append(PROSPECT_NOTE)
        return record

    @staticmethod
    def prospect(name: str, stakes: Mapping[str, float], *, operator: Optional[str] = None,
                 source: str = "user supplied", as_of: Optional[date] = None,
                 allow_partial: bool = False) -> OwnershipRecord:
        """Prospect equity entered by the user, e.g. from the licence group's own records."""
        warnings = check_prospect_stakes(stakes, allow_partial)
        warnings.append("user-supplied: not verified against a public database")
        listed = [Stake(c, None, float(p), is_operator=(c == operator)) for c, p in stakes.items()]
        return OwnershipRecord("prospect", name, as_of or date.today(), "user_provided", listed,
                               operator=operator, source=source, warnings=warnings)

    # ------------------------------------------------------------------- history

    def history(self, kind: str, name: str) -> List[Dict[str, Any]]:
        """Ownership periods, oldest first: ``{from, to, owner, total_pct, stakes}``."""
        if kind == "field":
            fld = self._resolve("field", "fldName", "fldNpdidField", name, "field")
            fid = int(fld["fldNpdidField"])
            rows = [r for r in self.client.query("field_licensee_hst", f"fldNpdidField={fid}")
                    if int(r["fldNpdidField"]) == fid]
            return self._periods(rows, "fldLicenseeFrom", "fldLicenseeTo", "fldCompanyShare", "fldOwnerName")
        if kind == "licence":
            lid = self.licence(name).npdid
            rows = [r for r in self.client.query("licence_licensee_hst", f"prlNpdidLicence={lid}")
                    if int(r["prlNpdidLicence"]) == lid]
            return self._periods(rows, "prlLicenseeDateValidFrom", "prlLicenseeDateValidTo", "prlLicenseeInterest",
                                 "prlName")
        raise OwnershipError("history supports kind 'field' or 'licence'; a discovery's history is its owner's")

    # ----------------------------------------------------------------- portfolio

    def portfolio(self, company: Union[str, int], as_of: Optional[date] = None,
                  include_discoveries_in_fields: bool = False) -> Dict[str, Any]:
        """Every field and discovery in which one company holds an interest on ``as_of``."""
        on = as_of or date.today()
        company_id, company_name = self._resolve_company(company)
        items: List[PortfolioItem] = []
        for r in self.client.query("field_licensee_hst", f"cmpNpdidCompany={company_id}"):
            if r.get("cmpNpdidCompany") == company_id and _valid(r, "fldLicenseeFrom", "fldLicenseeTo", on):
                items.append(PortfolioItem("field", str(r["fldName"]), float(r["fldCompanyShare"] or 0.0),
                                           r.get("fldOwnerKind"), r.get("fldOwnerName")))
        held: Dict[Tuple[str, int], float] = {}
        for layer, id_key, from_key, to_key, pct_key, kind in (
                ("licence_licensee_hst", "prlNpdidLicence", "prlLicenseeDateValidFrom", "prlLicenseeDateValidTo",
                 "prlLicenseeInterest", PRODUCTION_LICENCE),
                ("bsns_arr_area_licensee_hst", "baaNpdidBsnsArrArea", "baaLicenseeDateValidFrom",
                 "baaLicenseeDateValidTo", "baaLicenseeInterest", BUSINESS_AREA)):
            for r in self.client.query(layer, f"cmpNpdidCompany={company_id}"):
                if r.get("cmpNpdidCompany") == company_id and _valid(r, from_key, to_key, on):
                    key = (kind, int(r[id_key]))
                    held[key] = held.get(key, 0.0) + float(r[pct_key] or 0.0)
        discoveries = {int(r["dscNpdidDiscovery"]): r for r in self.client.query("discovery")}
        for r in self.client.query("discovery_owner_hst"):
            if not _valid(r, "dscOwnershipFromDate", "dscOwnershipToDate", on):
                continue
            owner_id = _id_from_url(r.get("dscOwnerFactPageUrl"))
            pct = held.get((r["dscOwnerKind"], owner_id))
            dsc = discoveries.get(int(r["dscNpdidDiscovery"]))
            if pct is None or dsc is None or (dsc.get("fldName") and not include_discoveries_in_fields):
                continue
            items.append(PortfolioItem("discovery", str(dsc["dscName"]), pct, r["dscOwnerKind"],
                                       r["dscOwnerName"], dsc.get("dscCurrentActivityStatus")))
        items.sort(key=lambda i: (i.kind, -i.interest_pct, i.name))
        return {"company": company_name, "company_id": company_id, "as_of": on.isoformat(),
                "items": [i.to_dict() for i in items], "source": "Sodir layers 7108, 3007, 3304, 7007, 7000"}

    # ------------------------------------------------------------------ internals

    def _resolve(self, layer: str, name_attr: str, id_attr: str, name: str, label: str) -> Dict[str, Any]:
        key = name.strip().upper()
        rows = self.client.query(layer, f"UPPER({name_attr})={sql_quote(key)}")
        if not rows:
            rows = self.client.query(layer, f"UPPER({name_attr}) LIKE {sql_quote('%' + key + '%')}")
        found = {int(r[id_attr]): r for r in rows if key in str(r[name_attr]).upper()}
        if len(found) > 1:
            exact = [r for r in found.values() if str(r[name_attr]).upper() == key]
            if len(exact) == 1:
                return exact[0]
            raise OwnershipError(f"'{name}' matches several {label}s: {sorted(str(r[name_attr]) for r in found.values())}")
        if not found:
            raise OwnershipError(f"no {label} matches '{name}'")
        return next(iter(found.values()))

    def _operator(self, layer: str, where: str, id_key: str, ident: int, from_key: str, to_key: str, on: date,
                  fallback: Mapping[str, Any]) -> Tuple[Optional[int], Optional[str]]:
        rows = [r for r in self.client.query(layer, where) if int(r[id_key]) == ident]
        rows = [r for r in rows if _valid(r, from_key, to_key, on)] or _latest(rows, from_key)
        if rows:
            return rows[0].get("cmpNpdidCompany"), rows[0].get("cmpLongName")
        return fallback.get("cmpNpdidCompany"), fallback.get("cmpLongName")

    def _licensee_stakes(self, owner_kind: str, owner_id: int, on: date) -> Tuple[List[Stake], Optional[date], List[str]]:
        if owner_kind == PRODUCTION_LICENCE:
            layer, id_key, f_key, t_key, p_key, s_key = ("licence_licensee_hst", "prlNpdidLicence",
                                                          "prlLicenseeDateValidFrom", "prlLicenseeDateValidTo",
                                                          "prlLicenseeInterest", "prlLicenseeSdfi")
        elif owner_kind == BUSINESS_AREA:
            layer, id_key, f_key, t_key, p_key, s_key = ("bsns_arr_area_licensee_hst", "baaNpdidBsnsArrArea",
                                                          "baaLicenseeDateValidFrom", "baaLicenseeDateValidTo",
                                                          "baaLicenseeInterest", "baaLicenseeSdfi")
        else:
            raise OwnershipError(f"unsupported owner kind '{owner_kind}'")
        rows = [r for r in self.client.query(layer, f"{id_key}={owner_id}") if int(r[id_key]) == owner_id]
        warnings: List[str] = []
        active = [r for r in rows if _valid(r, f_key, t_key, on)]
        if not active:
            active = _latest(rows, f_key)
            warnings.append(f"no licensee interests are valid on {on}; showing the most recent period")
        stakes = [Stake(r["cmpLongName"], r.get("cmpNpdidCompany"), float(r[p_key] or 0.0), r.get(s_key),
                        to_date(r.get(f_key)), to_date(r.get(t_key)),
                        bool(r.get("prlOperDateValidFrom") and _valid(r, "prlOperDateValidFrom",
                                                                      "prlOperDateValidTo", on)))
                  for r in active]
        return stakes, _latest_date(active, "prlLicenseeDateUpdated" if layer.startswith("licence")
                                    else "baaLicenseeDateUpdated"), warnings

    @staticmethod
    def _mark_operator(stake: Stake, operator_id: Optional[int]) -> Stake:
        if operator_id is None or stake.company_id != operator_id or stake.is_operator:
            return stake
        return Stake(stake.company, stake.company_id, stake.interest_pct, stake.sdfi_pct, stake.valid_from,
                     stake.valid_to, True)

    @staticmethod
    def _finish(record: OwnershipRecord) -> OwnershipRecord:
        if not record.is_complete:
            record.warnings.append(f"interests add up to {record.total_pct} %, not 100 %")
        if any(s.sdfi_pct for s in record.stakes):
            record.warnings.append("sdfi_pct is the state's direct interest inside a partner's share; "
                                   "it is informational and not additive")
        return record

    @staticmethod
    def _periods(rows: Sequence[Mapping[str, Any]], f_key: str, t_key: str, p_key: str,
                 owner_key: str) -> List[Dict[str, Any]]:
        grouped: Dict[Tuple[Optional[date], Optional[date], Any], Dict[str, float]] = {}
        for r in rows:
            key = (to_date(r.get(f_key)), to_date(r.get(t_key)), r.get(owner_key))
            grouped.setdefault(key, {})
            grouped[key][r["cmpLongName"]] = grouped[key].get(r["cmpLongName"], 0.0) + float(r[p_key] or 0.0)
        out = [{"from": a.isoformat() if a else None, "to": b.isoformat() if b else None, "owner": o,
                "total_pct": round(sum(s.values()), 6), "stakes": s} for (a, b, o), s in grouped.items()]
        return sorted(out, key=lambda p: p["from"] or "")

    def _resolve_company(self, company: Union[str, int]) -> Tuple[int, str]:
        if isinstance(company, int):
            rows = self.client.query("licence_licensee_hst", f"cmpNpdidCompany={company}")
            rows = [r for r in rows if r.get("cmpNpdidCompany") == company]
            if not rows:
                raise OwnershipError(f"no licensee with company id {company}")
            return company, str(max(rows, key=lambda r: r.get("prlLicenseeDateValidFrom") or 0)["cmpLongName"])
        key = company.strip().upper()
        rows = self.client.query("licence_licensee_hst", f"UPPER(cmpLongName) LIKE {sql_quote('%' + key + '%')}")
        rows = [r for r in rows if key in str(r["cmpLongName"]).upper()]
        names: Dict[int, Dict[str, Any]] = {}
        for r in rows:
            cur = names.setdefault(int(r["cmpNpdidCompany"]), {"name": r["cmpLongName"], "open": False})
            cur["open"] = cur["open"] or r.get("prlLicenseeDateValidTo") is None
        if not names:
            raise OwnershipError(f"no company matches '{company}'")
        if len(names) > 1:
            exact = [i for i, v in names.items() if str(v["name"]).upper() == key]
            active = [i for i, v in names.items() if v["open"]]
            pick = exact if len(exact) == 1 else active if len(active) == 1 else []
            if not pick:
                raise OwnershipError(f"'{company}' matches several companies: "
                                     f"{sorted((v['name'], i) for i, v in names.items())}; pass the id")
            return pick[0], str(names[pick[0]]["name"])
        only = next(iter(names))
        return only, str(names[only]["name"])
