from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec

# Public SPE-PRMS maturity stages mapped to high-level resource categories.
# Reserves: discovered, commercial, recoverable (PRMS classes 1-3).
# Contingent: discovered, sub-commercial, recoverable (PRMS classes 4-6).
# Prospective: undiscovered, recoverable (PRMS classes 7+).
_RESERVES_STAGES = {
    "on_production": "PRMS class 1 (on production)",
    "approved_for_development": "PRMS class 2 (approved for development)",
    "justified_for_development": "PRMS class 3 (justified for development)",
}
_CONTINGENT_STAGES = {
    "development_pending": "PRMS class 4 (development pending)",
    "development_on_hold": "PRMS class 5 (development on hold)",
    "development_unclarified": "PRMS class 6 (development unclarified or on hold)",
}
_PROSPECTIVE_STAGES = {
    "prospect": "PRMS class 7 (prospect)",
    "lead": "PRMS class 8 (lead)",
    "play": "PRMS class 9 (play)",
}


@dataclass(frozen=True)
class ResourceClassificationResult:
    resource_class: str
    resource_category: str
    prms_class_range: str
    maturity_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class ResourceClassificationModel:
    """Educational SPE-PRMS resource classification screening placeholder."""

    def evaluate(
        self,
        *,
        maturity_stage: str,
        commercial: bool | None = None,
    ) -> ResourceClassificationResult:
        if not isinstance(maturity_stage, str) or not maturity_stage.strip():
            raise ValueError("maturity_stage must be a non-empty string")

        normalized = self._normalize(maturity_stage)

        if normalized in _RESERVES_STAGES:
            category = "reserves"
            prms_range = _RESERVES_STAGES[normalized]
            warning = "watch" if commercial is False else "ok"
        elif normalized in _CONTINGENT_STAGES:
            category = "contingent-resources"
            prms_range = _CONTINGENT_STAGES[normalized]
            warning = "ok"
        elif normalized in _PROSPECTIVE_STAGES:
            category = "prospective-resources"
            prms_range = _PROSPECTIVE_STAGES[normalized]
            warning = "ok"
        else:
            category = "unrecoverable"
            prms_range = "unclassified"
            warning = "unclassified"

        return ResourceClassificationResult(
            resource_class=normalized,
            resource_category=category,
            prms_class_range=prms_range,
            maturity_warning=warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only.",
                "Rule-based mapping of SPE-PRMS maturity stages, not a volumetric estimate.",
                "Reserves require discovered, commercial, recoverable volumes (PRMS classes 1-3).",
                "Contingent resources are discovered but sub-commercial (PRMS classes 4-6).",
                "Move to a formal SPE-PRMS or NPD estimate with qualified subsurface review.",
            ),
        )

    @staticmethod
    def _normalize(maturity_stage: str) -> str:
        text = maturity_stage.strip().lower()
        for separator in (" ", "-", "/"):
            text = text.replace(separator, "_")
        while "__" in text:
            text = text.replace("__", "_")
        return text
