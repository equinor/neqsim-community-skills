"""Ownership records and the net-equity arithmetic used by field evaluation and economics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

TOLERANCE_PCT = 0.01
Series = Union[Sequence[float], Mapping[Any, float]]


class OwnershipError(ValueError):
    """Raised when a name or company cannot be resolved to exactly one object."""


@dataclass(frozen=True)
class Stake:
    """One company's interest in an owner (licence or business arrangement area)."""

    company: str
    company_id: Optional[int]
    interest_pct: float
    sdfi_pct: Optional[float] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    is_operator: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {"company": self.company, "company_id": self.company_id, "interest_pct": self.interest_pct,
                "sdfi_pct": self.sdfi_pct, "valid_from": _iso(self.valid_from), "valid_to": _iso(self.valid_to),
                "is_operator": self.is_operator}


def _iso(value: Optional[date]) -> Optional[str]:
    return value.isoformat() if value else None


@dataclass
class OwnershipRecord:
    """Equity of one field, discovery, licence or prospect on a given date.

    ``basis`` says how trustworthy the numbers are: ``sodir_public`` (read from Sodir),
    ``licence_proxy`` (the licence a prospect sits in, not the prospect) or ``user_provided``.
    """

    kind: str
    name: str
    as_of: date
    basis: str
    stakes: List[Stake]
    npdid: Optional[int] = None
    owner_kind: Optional[str] = None
    owner_name: Optional[str] = None
    operator: Optional[str] = None
    included_in_field: Optional[str] = None
    last_updated: Optional[date] = None
    source: str = ""
    warnings: List[str] = field(default_factory=list)

    @property
    def total_pct(self) -> float:
        return round(sum(s.interest_pct for s in self.stakes), 6)

    @property
    def is_complete(self) -> bool:
        """True when the interests add up to 100 % within tolerance."""
        return abs(self.total_pct - 100.0) <= TOLERANCE_PCT

    def fractions(self) -> Dict[str, float]:
        """Equity fractions by company, normalised by 100 (not by the total)."""
        out: Dict[str, float] = {}
        for stake in self.stakes:
            out[stake.company] = out.get(stake.company, 0.0) + stake.interest_pct / 100.0
        return out

    def find(self, company: str) -> Stake:
        """Return the stake of one company; raises if the text matches none or several."""
        wanted = company.casefold().strip()
        hits = [s for s in self.stakes if s.company.casefold() == wanted]
        if not hits:
            hits = [s for s in self.stakes if wanted in s.company.casefold()]
        names = sorted({s.company for s in hits})
        if len(names) != 1:
            raise OwnershipError(
                f"'{company}' matches {names or 'no partner'} in {self.name}; partners: "
                f"{sorted({s.company for s in self.stakes})}")
        return hits[0]

    def fraction_of(self, company: str) -> float:
        return self.find(company).interest_pct / 100.0

    def allocate(self, gross: Series) -> Dict[str, Series]:
        """Split a gross series (volumes, revenue, capex, opex) into each partner's net share."""
        return {name: scale(gross, frac) for name, frac in self.fractions().items()}

    def net(self, gross: Series, company: str) -> Series:
        """One company's net share of a gross series."""
        return scale(gross, self.fraction_of(company))

    def to_economics_handoff(self, company: Optional[str] = None) -> Dict[str, Any]:
        """Dict a field-economics or NPV step can consume (equity fractions plus caveats)."""
        data: Dict[str, Any] = {
            "asset": self.name, "kind": self.kind, "as_of": self.as_of.isoformat(), "basis": self.basis,
            "owner": {"kind": self.owner_kind, "name": self.owner_name}, "operator": self.operator,
            "equity_fraction": self.fractions(), "total_pct": self.total_pct, "complete": self.is_complete,
            "included_in_field": self.included_in_field, "warnings": list(self.warnings),
            "scaling_note": ("Scale gross volumes, revenue, capex and opex by the equity fraction; "
                             "tax is computed per company on its net cash flow, not scaled."),
        }
        if company:
            stake = self.find(company)
            data["company"] = stake.company
            data["company_fraction"] = stake.interest_pct / 100.0
        return data

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "name": self.name, "npdid": self.npdid, "as_of": self.as_of.isoformat(),
                "basis": self.basis, "owner_kind": self.owner_kind, "owner_name": self.owner_name,
                "operator": self.operator, "included_in_field": self.included_in_field,
                "last_updated": _iso(self.last_updated), "source": self.source,
                "total_pct": self.total_pct, "complete": self.is_complete,
                "stakes": [s.to_dict() for s in self.stakes], "warnings": list(self.warnings)}


def scale(series: Series, factor: float) -> Series:
    """Multiply a list or a mapping of numbers by ``factor``."""
    if isinstance(series, Mapping):
        return {key: value * factor for key, value in series.items()}
    return [value * factor for value in series]


def portfolio_net(items: Sequence[tuple], company: str) -> Series:
    """Sum one company's net share over several ``(OwnershipRecord, gross_series)`` pairs.

    All series must be of the same kind: lists of equal length, or mappings (missing keys count as 0).
    """
    total: Any = None
    for record, gross in items:
        part = record.net(gross, company)
        if total is None:
            total = dict(part) if isinstance(part, Mapping) else list(part)
        elif isinstance(total, dict) and isinstance(part, Mapping):
            for key, value in part.items():
                total[key] = total.get(key, 0.0) + value
        elif isinstance(total, list) and not isinstance(part, Mapping):
            if len(total) != len(part):
                raise OwnershipError("portfolio series must have equal length")
            total = [a + b for a, b in zip(total, part)]
        else:
            raise OwnershipError("portfolio series must all be lists or all be mappings")
    if total is None:
        raise OwnershipError("portfolio_net needs at least one asset")
    return total


def check_prospect_stakes(stakes: Mapping[str, float], allow_partial: bool) -> List[str]:
    """Validate user-supplied prospect interests and return warnings."""
    warnings: List[str] = []
    if not stakes:
        raise OwnershipError("a prospect needs at least one partner")
    if any(v < 0 for v in stakes.values()):
        raise OwnershipError("interest cannot be negative")
    total = sum(stakes.values())
    if abs(total - 100.0) > TOLERANCE_PCT:
        if not allow_partial:
            raise OwnershipError(f"prospect interests add up to {total:.4f} %, not 100 %")
        warnings.append(f"interests add up to {total:.4f} %, not 100 %; the rest is unallocated")
    return warnings
