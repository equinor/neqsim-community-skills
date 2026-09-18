import pytest

from resource_classification_screening import ResourceClassificationModel


def test_resource_model_reserves_for_justified_development() -> None:
    result = ResourceClassificationModel().evaluate(
        maturity_stage="justified for development",
    )

    assert result.resource_category == "reserves"
    assert result.maturity_warning == "ok"
    assert result.prms_class_range == "reserves"
    assert result.prms_category == "reserves"
    assert result.sodir_resource_class == "RC3"
    assert result.sodir_resource_category == "reserves"
    assert result.assumptions


def test_resource_model_contingent_for_development_pending() -> None:
    result = ResourceClassificationModel().evaluate(
        maturity_stage="development pending",
    )

    assert result.resource_category == "contingent-resources"
    assert result.sodir_resource_class == "RC4F"


def test_resource_model_prospective_for_prospect() -> None:
    result = ResourceClassificationModel().evaluate(
        maturity_stage="prospect",
    )

    assert result.resource_category == "prospective-resources"
    assert result.sodir_resource_class == "RC8"
    assert result.sodir_resource_category == "undiscovered-resources"


def test_resource_model_historical_production_is_not_reserves() -> None:
    result = ResourceClassificationModel().evaluate(
        maturity_stage="produced and sold",
    )

    assert result.resource_category == "historical-production"
    assert result.sodir_resource_class == "RC0"


def test_resource_model_accepts_explicit_sodir_additional_recovery_class() -> None:
    result = ResourceClassificationModel().evaluate(maturity_stage="RC4A")

    assert result.resource_category == "contingent-resources"
    assert result.sodir_resource_class == "RC4A"
    assert result.prms_category == "contingent resources"


def test_prms_on_hold_does_not_invent_sodir_class() -> None:
    result = ResourceClassificationModel().evaluate(maturity_stage="development on hold")

    assert result.resource_category == "contingent-resources"
    assert result.sodir_resource_class == "unclassified"
    assert result.maturity_warning == "sodir-class-needs-evidence"


def test_maturity_does_not_infer_uncertainty_range() -> None:
    result = ResourceClassificationModel().evaluate(maturity_stage="RC2")

    assert "not inferred" in result.uncertainty_basis
    assert "1P/2P/3P" in result.uncertainty_basis


def test_resource_model_watch_when_reserves_not_commercial() -> None:
    result = ResourceClassificationModel().evaluate(
        maturity_stage="on production",
        commercial=False,
    )

    assert result.resource_category == "reserves"
    assert result.maturity_warning == "watch"


def test_resource_model_unclassified_for_unknown_stage() -> None:
    result = ResourceClassificationModel().evaluate(
        maturity_stage="something unknown",
    )

    assert result.resource_category == "unclassified"
    assert result.maturity_warning == "unclassified"


def test_resource_model_rejects_empty_stage() -> None:
    with pytest.raises(ValueError, match="maturity_stage"):
        ResourceClassificationModel().evaluate(maturity_stage="   ")
