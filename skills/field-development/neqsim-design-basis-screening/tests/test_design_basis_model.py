import pytest

from design_basis_screening import DesignBasisModel, DesignBasisResult


def _ok_kwargs():
    return dict(
        operating_flow=100.0,
        design_flow=120.0,
        operating_pressure_bara=60.0,
        design_pressure_bara=70.0,
        operating_temperature_c=40.0,
        design_temperature_c=60.0,
        standards=("ASME VIII Div.1", "NORSOK P-001"),
    )


def test_adequate_margins_ok():
    model = DesignBasisModel()
    result = model.evaluate(**_ok_kwargs())
    assert isinstance(result, DesignBasisResult)
    assert result.flow_flag == "ok"
    assert result.pressure_flag == "ok"
    assert result.temperature_flag == "ok"
    assert result.design_warning == "ok"
    assert result.flags == ()


def test_low_flow_margin_flagged():
    model = DesignBasisModel()
    kwargs = _ok_kwargs()
    kwargs["design_flow"] = 102.0
    result = model.evaluate(**kwargs)
    assert result.flow_flag == "low"
    assert result.design_warning == "watch"
    assert any("flow margin" in f for f in result.flags)


def test_low_pressure_margin_flagged():
    model = DesignBasisModel()
    kwargs = _ok_kwargs()
    kwargs["design_pressure_bara"] = 62.0
    result = model.evaluate(**kwargs)
    assert result.pressure_flag == "low"
    assert any("pressure margin" in f for f in result.flags)


def test_low_temperature_margin_flagged():
    model = DesignBasisModel()
    kwargs = _ok_kwargs()
    kwargs["design_temperature_c"] = 45.0
    result = model.evaluate(**kwargs)
    assert result.temperature_flag == "low"
    assert any("temperature margin" in f for f in result.flags)


def test_missing_standards_flagged():
    model = DesignBasisModel()
    kwargs = _ok_kwargs()
    kwargs["standards"] = None
    result = model.evaluate(**kwargs)
    assert result.standards == ()
    assert any("standards basis" in f for f in result.flags)


def test_margins_computed():
    model = DesignBasisModel()
    result = model.evaluate(**_ok_kwargs())
    assert result.flow_margin == pytest.approx(1.2)
    assert result.pressure_margin == pytest.approx(70.0 / 60.0, abs=1e-3)
    assert result.temperature_margin_c == pytest.approx(20.0)


def test_standards_normalized():
    model = DesignBasisModel()
    kwargs = _ok_kwargs()
    kwargs["standards"] = ["  ASME VIII  ", "", "API 521"]
    result = model.evaluate(**kwargs)
    assert result.standards == ("ASME VIII", "API 521")


def test_custom_thresholds():
    model = DesignBasisModel(min_flow_margin=1.5)
    result = model.evaluate(**_ok_kwargs())
    assert result.flow_flag == "low"


def test_neqsim_flag_is_boolean():
    model = DesignBasisModel()
    result = model.evaluate(**_ok_kwargs())
    assert isinstance(result.neqsim_available, bool)
    assert len(result.assumptions) >= 4


def test_invalid_operating_flow_rejected():
    model = DesignBasisModel()
    kwargs = _ok_kwargs()
    kwargs["operating_flow"] = 0.0
    with pytest.raises(ValueError):
        model.evaluate(**kwargs)


def test_invalid_threshold_rejected():
    with pytest.raises(ValueError):
        DesignBasisModel(min_pressure_margin=0.0)
