import pytest

from cfd_coupling import (
    CfdDesignBasis,
    build_design_basis,
    required_fields,
)


def _sources():
    return [
        {
            "source": "pid",
            "reference": "P&ID 20-PID-001 rev C",
            "values": {"inside_diameter_m": 0.30, "service": "wet gas"},
        },
        {
            "source": "stid",
            "reference": "STID line 20-P-001",
            "values": {"inside_diameter_m": 0.3048, "length_m": 6.0},
        },
        {
            "source": "process_datasheet",
            "reference": "20-DS-014 rev 2",
            "values": {
                "temperature_c": 45.0,
                "pressure_bara": 65.0,
                "mass_flow_kg_per_h": 120_000.0,
            },
        },
    ]


def test_higher_precedence_source_wins() -> None:
    basis = build_design_basis(tag="20-P-001", component_kind="pipe", sources=_sources())

    # STID outranks the P&ID, so the tag register diameter is the accepted value.
    assert basis.value("inside_diameter_m") == pytest.approx(0.3048)
    assert basis.source_of("inside_diameter_m") == "stid"
    assert basis.ready_for_meshing


def test_disagreement_beyond_tolerance_is_reported_as_a_conflict() -> None:
    sources = _sources()
    sources[0]["values"]["inside_diameter_m"] = 0.20

    basis = build_design_basis(tag="20-P-001", component_kind="pipe", sources=sources)

    assert len(basis.conflicts) == 1
    conflict = basis.conflicts[0]
    assert conflict.field == "inside_diameter_m"
    assert conflict.accepted_source == "stid"
    assert conflict.rejected_source == "pid"
    # A conflict blocks meshing even though nothing is missing.
    assert not basis.ready_for_meshing


def test_missing_fields_block_meshing_and_are_named() -> None:
    basis = build_design_basis(
        tag="20-VG-001",
        component_kind="separator",
        sources=[
            {
                "source": "mechanical_datasheet",
                "reference": "20-MDS-002",
                "values": {"inside_diameter_m": 2.4},
            }
        ],
    )

    assert "tangent_length_m" in basis.missing_fields
    assert "temperature_c" in basis.missing_fields
    assert not basis.ready_for_meshing


def test_none_values_are_ignored_so_partial_extractions_can_be_passed_through() -> None:
    sources = _sources()
    sources.append(
        {"source": "plant_data", "reference": "historian", "values": {"length_m": None}}
    )

    basis = build_design_basis(tag="20-P-001", component_kind="pipe", sources=sources)

    assert basis.value("length_m") == pytest.approx(6.0)
    assert basis.source_of("length_m") == "stid"


def test_unknown_component_kind_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown component_kind"):
        required_fields("mystery-device")


def test_unknown_source_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown source"):
        build_design_basis(
            tag="20-P-001",
            component_kind="pipe",
            sources=[{"source": "hearsay", "values": {"length_m": 1.0}}],
        )


def test_traceability_rows_carry_source_and_confidence() -> None:
    basis: CfdDesignBasis = build_design_basis(
        tag="20-P-001", component_kind="pipe", sources=_sources()
    )

    rows = {row["field"]: row for row in basis.traceability_rows()}
    assert rows["inside_diameter_m"]["confidence"] == "medium"
    assert rows["pressure_bara"]["confidence"] == "high"
    assert rows["pressure_bara"]["unit"] == "bara"
