import pytest

from standard_equipment_sizes import (
    lowest_b165_class_ambient,
    next_motor_kw,
    next_tube_length_m,
    nps_od_mm,
    round_up_vessel_diameter_mm,
    select_api526_orifice,
    select_pipe_nps,
)
from standard_equipment_sizes.sizes import NPS_OD_MM, NPS_TO_DN


def test_known_nps_outside_diameters():
    assert nps_od_mm(4.0) == 114.3
    assert nps_od_mm(8.0) == 219.1
    assert nps_od_mm(12.0) == 323.9


def test_unknown_nps_rejected():
    with pytest.raises(ValueError):
        nps_od_mm(2.5)


def test_nps_and_dn_tables_cover_same_sizes():
    assert set(NPS_OD_MM) == set(NPS_TO_DN)


def test_select_pipe_nps_uses_only_preferred_sizes():
    result = select_pipe_nps(100.0, 6.0)
    assert result["nps"] == 4.0
    assert result["dn"] == 100
    assert result["inside_diameter_mm"] == pytest.approx(102.3)
    assert select_pipe_nps(110.0, 6.0)["nps"] == 6.0


def test_select_pipe_nps_invalid_and_too_large():
    with pytest.raises(ValueError):
        select_pipe_nps(-1.0, 5.0)
    with pytest.raises(ValueError):
        select_pipe_nps(5000.0, 10.0)


def test_api526_letters_and_margin():
    assert select_api526_orifice(500.0)["letter"] == "H"
    assert select_api526_orifice(70.0)["letter"] == "D"
    assert select_api526_orifice(16000.0)["letter"] == "T"
    assert select_api526_orifice(20000.0)["letter"] is None
    with pytest.raises(ValueError):
        select_api526_orifice(0.0)


def test_api526_area_matches_published_cm2_grid():
    assert select_api526_orifice(300.0)["area_mm2"] == pytest.approx(324.5, abs=0.5)


def test_motor_rating_rounds_up_with_margin():
    assert next_motor_kw(50.0) == 55.0
    assert next_motor_kw(50.0, 0.15) == 75.0
    with pytest.raises(ValueError):
        next_motor_kw(5000.0)


@pytest.mark.parametrize("pressure,flange_class", [(15.0, 150), (40.0, 300), (100.0, 600), (200.0, 1500)])
def test_b165_class_ambient(pressure, flange_class):
    assert lowest_b165_class_ambient(pressure) == flange_class


def test_b165_class_out_of_range():
    with pytest.raises(ValueError):
        lowest_b165_class_ambient(500.0)


def test_tube_length_and_vessel_rounding():
    assert next_tube_length_m(4.0) == 4.88
    assert round_up_vessel_diameter_mm(1234.0) == 1300.0
    assert round_up_vessel_diameter_mm(1234.0, 50.0) == 1250.0
    with pytest.raises(ValueError):
        next_tube_length_m(10.0)
