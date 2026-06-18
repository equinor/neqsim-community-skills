import pytest

from resource_classification_screening import ResourceClassificationModel


def test_resource_model_reserves_for_justified_development() -> None:
    result = ResourceClassificationModel().evaluate(
        maturity_stage="justified for development",
    )

    assert result.resource_category == "reserves"
    assert result.maturity_warning == "ok"
    assert "PRMS class 3" in result.prms_class_range
    assert result.assumptions


def test_resource_model_contingent_for_development_pending() -> None:
    result = ResourceClassificationModel().evaluate(
        maturity_stage="development pending",
    )

    assert result.resource_category == "contingent-resources"


def test_resource_model_prospective_for_prospect() -> None:
    result = ResourceClassificationModel().evaluate(
        maturity_stage="prospect",
    )

    assert result.resource_category == "prospective-resources"


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

    assert result.resource_category == "unrecoverable"
    assert result.maturity_warning == "unclassified"


def test_resource_model_rejects_empty_stage() -> None:
    with pytest.raises(ValueError, match="maturity_stage"):
        ResourceClassificationModel().evaluate(maturity_stage="   ")
