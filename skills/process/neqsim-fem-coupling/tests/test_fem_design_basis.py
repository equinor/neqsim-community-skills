import pytest

from fem_coupling import (
    SOURCE_PRECEDENCE,
    build_design_basis,
    required_fields,
)


def _sources():
    return [
        {
            "source": "pid",
            "reference": "P&ID 20-PID-001 rev C",
            "values": {"inside_diameter_m": 0.30, "wall_material": "carbon-steel"},
        },
        {
            "source": "stid",
            "reference": "STID line 20-P-001",
            "values": {"inside_diameter_m": 0.254, "wall_thickness_m": 0.0127},
        },
        {
            "source": "insulation_specification",
            "reference": "SPEC-INS-004 rev 1",
            "values": {
                "insulation_thickness_m": 0.05,
                "insulation_material": "polyurethane-insulation",
            },
        },
        {
            "source": "process_datasheet",
            "reference": "20-DS-014 rev 2",
            "values": {
                "internal_temperature_c": 45.0,
                "external_temperature_c": 4.0,
                "external_film_coefficient_w_per_m2k": 300.0,
            },
        },
    ]


def test_required_fields_rejects_unknown_model_kind():
    with pytest.raises(ValueError, match="unknown model_kind"):
        required_fields("space station")


def test_stress_fields_are_only_required_when_asked_for():
    thermal_only = required_fields("pipe_wall")
    with_stress = required_fields("pipe_wall", include_stress=True)
    assert "design_pressure_bara" not in thermal_only
    assert "design_pressure_bara" in with_stress


def test_higher_precedence_source_wins_and_raises_a_conflict():
    basis = build_design_basis(
        tag="20-P-001", model_kind="insulated_pipe", sources=_sources()
    )
    # STID outranks the P&ID, so the STID diameter is the accepted value.
    assert basis.value("inside_diameter_m") == pytest.approx(0.254)
    assert basis.source_of("inside_diameter_m") == "stid"
    conflicts = [c.field for c in basis.conflicts]
    assert "inside_diameter_m" in conflicts
    assert not basis.ready_for_meshing


def test_complete_consistent_basis_is_ready_for_meshing():
    sources = _sources()
    sources[0]["values"]["inside_diameter_m"] = 0.254
    basis = build_design_basis(
        tag="20-P-001", model_kind="insulated_pipe", sources=sources
    )
    assert basis.ready_for_meshing
    assert basis.missing_fields == ()
    assert basis.conflicts == ()


def test_missing_fields_are_reported_rather_than_invented():
    basis = build_design_basis(
        tag="20-P-001",
        model_kind="insulated_pipe",
        sources=[
            {
                "source": "stid",
                "values": {"inside_diameter_m": 0.254, "wall_thickness_m": 0.0127},
            }
        ],
    )
    assert "insulation_thickness_m" in basis.missing_fields
    assert not basis.ready_for_meshing


def test_material_grade_disagreement_is_always_a_conflict():
    basis = build_design_basis(
        tag="V-100",
        model_kind="vessel_wall",
        sources=[
            {
                "source": "material_certificate",
                "values": {"wall_material": "duplex-22cr"},
            },
            {"source": "pid", "values": {"wall_material": "carbon-steel"}},
        ],
    )
    assert any(conflict.field == "wall_material" for conflict in basis.conflicts)
    assert basis.value("wall_material") == "duplex-22cr"


def test_unknown_source_is_rejected():
    with pytest.raises(ValueError, match="unknown source"):
        build_design_basis(
            tag="X",
            model_kind="plate",
            sources=[{"source": "rumour", "values": {"thickness_m": 0.01}}],
        )


def test_traceability_rows_carry_source_and_reference():
    basis = build_design_basis(
        tag="20-P-001", model_kind="pipe_wall", sources=_sources()
    )
    rows = {row["field"]: row for row in basis.traceability_rows()}
    assert rows["wall_thickness_m"]["source"] == "stid"
    assert rows["wall_thickness_m"]["reference"] == "STID line 20-P-001"
    assert rows["wall_thickness_m"]["unit"] == "m"


def test_precedence_order_is_stated_highest_first():
    assert SOURCE_PRECEDENCE[0] == "measurement"
    assert SOURCE_PRECEDENCE[-1] == "assumption"
