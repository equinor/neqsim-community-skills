"""Ownership value objects: one company interest and an equity table for a field, discovery,
licence or prospect, with validation that keeps wrong shares out of economics."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

_EPOCH = datetime(1970, 1, 1)

# Sodir publishes shares with up to five decimals; 0.05 pct absorbs rounding only.
SUM_TOLERANCE_PCT = 0.05


def ms_to_date(value: Any) -> Optional[date]:
    """Convert a Sodir epoch-millisecond timestamp to a date (None stays None)."""
    if value is None or value == "":
        return None
    return (_EPOCH + timedelta(milliseconds=float(value))).date()


def norm(text: Any) -> str:
    """Case- and whitespace-insensitive key for company and entity names."""
    return re.sub(r"\s+", " ", str(text or "").strip()).casefold()


@dataclass
class Interest:
    """One company's interest in an entity for one validity period."""

    company: str
    share_pct: float
    company_id: Optional[int] = None
    group: Optional[str] = None
    sdfi_pct: Optional[float] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    basis: str = ""
    owner: str = ""
    note: str = ""
    source_url: Optional[str] = None

    def active_on(self, on: date) -> bool:
        """True when the interest is valid on the date (both ends inclusive)."""
        if self.valid_from is not None and on < self.valid_from:
            return False
        return self.valid_to is None or on <= self.valid_to

    def to_dict(self) -> Dict[str, Any]:
        out = dict(self.__dict__)
        out["valid_from"] = self.valid_from.isoformat() if self.valid_from else None
        out["valid_to"] = self.valid_to.isoformat() if self.valid_to else None
        return out


@dataclass
class EquityTable:
    """Ownership of one entity on one date, with provenance and data-quality flags."""

    entity_type: str
    name: str
    as_of: date
    interests: List[Interest] = field(default_factory=list)
    entity_id: Optional[int] = None
    operator: Optional[str] = None
    status: str = "sodir_public"
    history: List[Interest] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    provenance: List[Dict[str, Any]] = field(default_factory=list)
    included_in_field: Optional[str] = None

    def owners(self) -> List[str]:
        """Distinct owner labels (licence or business arrangement area), in order."""
        seen: List[str] = []
        for item in self.interests:
            if item.owner not in seen:
                seen.append(item.owner)
        return seen

    def _select(self, owner: Optional[str]) -> List[Interest]:
        owners = self.owners()
        if owner is None:
            if len(owners) > 1:
                raise ValueError(
                    f"{self.name} has several owners {owners}; pass owner=... because shares of "
                    "different owners must not be added")
            return list(self.interests)
        return [i for i in self.interests if norm(i.owner) == norm(owner)]

    def total_pct(self, owner: Optional[str] = None) -> float:
        return sum(i.share_pct for i in self._select(owner))

    def is_complete(self, owner: Optional[str] = None) -> bool:
        """True when active shares sum to 100 pct within rounding."""
        return bool(self.interests) and abs(self.total_pct(owner) - 100.0) <= SUM_TOLERANCE_PCT

    def by_company(self, owner: Optional[str] = None) -> Dict[str, float]:
        """Active share per company in pct, merging repeated rows of one company."""
        out: Dict[str, float] = {}
        for item in self._select(owner):
            out[item.company] = out.get(item.company, 0.0) + item.share_pct
        return out

    def by_group(self, owner: Optional[str] = None) -> Dict[str, float]:
        """Active share per parent group in pct; companies without a group keep their own name."""
        out: Dict[str, float] = {}
        for item in self._select(owner):
            key = item.group or item.company
            out[key] = out.get(key, 0.0) + item.share_pct
        return out

    def find_company(self, query: Any, owner: Optional[str] = None) -> List[Interest]:
        """Resolve a company by id, exact name or unique substring; raise when ambiguous."""
        items = self._select(owner)
        q = norm(query)
        exact = [i for i in items if q == norm(i.company) or q == str(i.company_id)]
        if exact:
            return exact
        part = [i for i in items if q and q in norm(i.company)]
        keys = {i.company_id if i.company_id is not None else norm(i.company) for i in part}
        if len(keys) > 1:
            raise ValueError(f"'{query}' matches several partners: {sorted({i.company for i in part})}")
        return part

    def share_of(self, company: Any, owner: Optional[str] = None, group: bool = False) -> float:
        """Share in pct of a company (or parent group). Unknown names raise instead of returning 0."""
        items = self._select(owner)
        if group:
            matched = [i for i in items if norm(i.group) == norm(company)]
        else:
            matched = self.find_company(company, owner)
        if not matched:
            raise LookupError(f"'{company}' holds no active interest in {self.name} on {self.as_of}; "
                              f"partners: {sorted({i.company for i in items})}")
        return sum(i.share_pct for i in matched)

    def share_on(self, company: Any, on: date, owner: Optional[str] = None) -> float:
        """Share in pct on a past or future date from the loaded history (0.0 when not a partner)."""
        if not self.history:
            raise ValueError("no history loaded; call the reader with history=True")
        q = norm(company)
        rows = [i for i in self.history
                if (q == norm(i.company) or q == str(i.company_id)) and i.active_on(on)
                and (owner is None or norm(i.owner) == norm(owner))]
        return sum(i.share_pct for i in rows)

    def confidence(self) -> str:
        """high = complete public record; medium = proxy or incomplete; low = user supplied."""
        if self.status == "user_provided":
            return "low"
        if self.status == "sodir_public" and self.is_complete_all():
            return "high"
        return "medium"

    def is_complete_all(self) -> bool:
        return bool(self.interests) and all(self.is_complete(o) for o in self.owners())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_type": self.entity_type, "name": self.name, "entity_id": self.entity_id,
            "as_of": self.as_of.isoformat(), "operator": self.operator, "status": self.status,
            "confidence": self.confidence(), "owners": self.owners(),
            "total_pct": {o or "all": round(self.total_pct(o), 6) for o in self.owners()},
            "interests": [i.to_dict() for i in self.interests],
            "warnings": list(self.warnings), "gaps": list(self.gaps),
            "included_in_field": self.included_in_field, "provenance": list(self.provenance),
        }
