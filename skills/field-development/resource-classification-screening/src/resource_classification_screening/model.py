from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec

# Public SODIR maturity stages mapped independently from SPE-PRMS categories.
_RESERVES_STAGES = {
    "on_production": "RC1",
    "approved_for_development": "RC2",
    "decided_for_production": "RC3",
    "justified_for_development": "RC3",
}
_CONTINGENT_STAGES = {
    "development_pending": "RC4F",
    "improved_recovery_pending": "RC4A",
    "development_likely_but_unclarified": "RC5F",
    "improved_recovery_likely_but_unclarified": "RC5A",
    "recovery_unlikely": "RC6",
    "discovery_under_evaluation": "RC7F",
    "possible_future_improved_recovery": "RC7A",
}
_PROSPECTIVE_STAGES = {
    "prospect": "RC8",
    "lead": "RC9",
    "play": "RC9",
}
_HISTORICAL_STAGES = {"historical_production", "produced_and_sold", "sold_and_delivered"}
_PRMS_ONLY_CONTINGENT_STAGES = {"development_on_hold", "development_unclarified"}
_SODIR_CLASSES = {
    "rc0": ("historical-production", "not applicable"),
    "rc1": ("reserves", "reserves"),
    "rc2": ("reserves", "reserves"),
    "rc3": ("reserves", "reserves"),
    "rc4f": ("contingent-resources", "contingent resources"),
    "rc4a": ("contingent-resources", "contingent resources"),
    "rc5f": ("contingent-resources", "contingent resources"),
    "rc5a": ("contingent-resources", "contingent resources"),
    "rc6": ("contingent-resources", "contingent resources"),
    "rc7f": ("contingent-resources", "contingent resources"),
    "rc7a": ("contingent-resources", "contingent resources"),
    "rc8": ("undiscovered-resources", "prospective resources"),
    "rc9": ("undiscovered-resources", "prospective resources"),
}


@dataclass(frozen=True)
class ResourceClassificationResult:
    resource_class: str
    resource_category: str
    prms_class_range: str
    sodir_resource_class: str
    sodir_resource_category: str
    prms_category: str
    uncertainty_basis: str
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

        if normalized in _SODIR_CLASSES:
            sodir_category, prms_category = _SODIR_CLASSES[normalized]
            category = prms_category.replace(" ", "-")
            if sodir_category == "historical-production":
                category = "historical-production"
            sodir_class = normalized.upper()
            warning = "ok"
        elif normalized in _HISTORICAL_STAGES:
            category = "historical-production"
            prms_category = "not applicable"
            sodir_category = "historical-production"
            sodir_class = "RC0"
            warning = "ok"
        elif normalized in _RESERVES_STAGES:
            category = "reserves"
            prms_category = "reserves"
            sodir_category = "reserves"
            sodir_class = _RESERVES_STAGES[normalized]
            warning = "watch" if commercial is False else "ok"
        elif normalized in _CONTINGENT_STAGES:
            category = "contingent-resources"
            prms_category = "contingent resources"
            sodir_category = "contingent-resources"
            sodir_class = _CONTINGENT_STAGES[normalized]
            warning = "ok"
        elif normalized in _PRMS_ONLY_CONTINGENT_STAGES:
            category = "contingent-resources"
            prms_category = "contingent resources"
            sodir_category = "contingent-resources"
            sodir_class = "unclassified"
            warning = "sodir-class-needs-evidence"
        elif normalized in _PROSPECTIVE_STAGES:
            category = "prospective-resources"
            prms_category = "prospective resources"
            sodir_category = "undiscovered-resources"
            sodir_class = _PROSPECTIVE_STAGES[normalized]
            warning = "ok"
        else:
            category = "unclassified"
            prms_category = "unclassified"
            sodir_category = "unclassified"
            sodir_class = "unclassified"
            warning = "unclassified"

        return ResourceClassificationResult(
            resource_class=normalized,
            resource_category=category,
            prms_class_range=prms_category,
            sodir_resource_class=sodir_class,
            sodir_resource_category=sodir_category,
            prms_category=prms_category,
            uncertainty_basis=(
                "not inferred; report quantity uncertainty independently as "
                "1P/2P/3P, 1C/2C/3C, or low/best/high as applicable"
            ),
            maturity_warning=warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only.",
                "Rule-based mapping of project maturity, not a volumetric estimate.",
                "SODIR resource classes and PRMS categories are separate classification axes.",
                "Reserves require discovered, commercial, recoverable volumes covered by a production decision.",
                "Move to a formal SPE-PRMS or SODIR estimate with qualified subsurface review.",
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
