import pytest

from h2s_partitioning import (
    SeparatorStage,
    apply_e300_composition,
    load_e300_fluid,
    parse_e300_names_and_zi,
    recombine_to_gor_and_h2s,
    separator_gor_and_gas_h2s,
)

NAMES = ["C1", "C3", "C6", "F3", "F5", "H2S", "H2O"]
PROPS = {
    "TCRIT": [190.578, 369.822, 507.428, 604.916, 815.260, 373.2, 647.096],
    "PCRIT": [46.0432, 42.4924, 30.1232, 28.7528, 15.1363, 89.4, 220.6],
    "ACF": [0.0115, 0.1454, 0.2957, 0.32621, 0.75273, 0.0942, 0.344],
    "OMEGAA": [0.45724] * 6 + [0.42748],
    "OMEGAB": [0.0778] * 7,
    "MW": [16.043, 44.097, 86.178, 121.2006, 293.0651, 34.08, 18.0153],
    "TBOIL": [111.956, 230.115, 341.179, 411.638, 633.391, 212.8, 373.15],
    "VCRIT": [0.09925, 0.2029, 0.37017, 0.46532, 1.19568, 0.0985, 0.056],
    "ZCRIT": [0.28839, 0.28038, 0.26429, 0.266, 0.26699, 0.284, 0.29159],
    "SSHIFT": [-0.159, -0.086, -0.008232, -0.002275, 0.061067, -0.10, 0.084],
    "PARACHOR": [77.0, 150.3, 271.0, 370.561, 769.049, 80.0, 10.0],
}
BIC_ROWS = [[0.0], [0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 0.0], [0.08, 0.08, 0.05, 0.0, 0.0], [0.5, 0.5, 0.5, 0.5, 0.5, 0.2]]


def _write_e300(path, zi):
    lines = ["METRIC", "NCOMPS", "7 /", "EOS", "PR /", "RTEMP", "100.0 /", "STCOND", "15.0 1.01325 /", "CNAMES"]
    lines += NAMES[:-1] + [NAMES[-1] + " /"]
    for key, vals in PROPS.items():
        lines.append("-- " + key)
        lines.append(key)
        lines += ["%.6f" % v for v in vals[:-1]] + ["%.6f /" % vals[-1]]
    lines += ["-- Overall composition", "ZI"] + ["%.6f" % v for v in zi[:-1]] + ["%.6f /" % zi[-1]]
    lines += ["-- BIC", "BIC"] + ["  ".join("%.4f" % v for v in row) for row in BIC_ROWS] + ["/"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture(scope="module")
def e300_files(tmp_path_factory):
    pytest.importorskip("neqsim")
    d = tmp_path_factory.mktemp("e300")
    model = d / "model.e300"
    comp = d / "fluidmagic_composition.e300"
    _write_e300(model, [0.60, 0.06, 0.04, 0.09, 0.08, 1.0e-5, 0.1299])
    _write_e300(comp, [0.60, 0.06, 0.04, 0.09, 0.08, 2.0e-4, 0.1298])
    return model, comp


def test_parse_names_and_zi(e300_files):
    model, comp = e300_files
    names, zi = parse_e300_names_and_zi(str(comp))
    assert names == NAMES
    assert sum(zi) == pytest.approx(1.0, abs=1e-4)


def test_recombination_on_e300_model_keeps_the_eos(e300_files):
    model, comp = e300_files
    stage = SeparatorStage(70.0, 10.0, "HP")
    fluid = load_e300_fluid(str(model))
    eos_class = fluid.getClass().getSimpleName()
    assert "Pr" in str(eos_class)
    apply_e300_composition(fluid, str(model), str(comp))
    gor, y = separator_gor_and_gas_h2s(fluid, stage)
    start = load_e300_fluid(str(model))
    apply_e300_composition(start, str(model), {"C1": 0.60, "C3": 0.06, "C6": 0.04, "F3": 0.09, "F5": 0.08, "H2S": 1.0e-5, "H2O": 0.13})
    res = recombine_to_gor_and_h2s(start, stage, gor, y)
    assert res.converged, res.warnings
    assert res.fluid.getClass().getSimpleName() == eos_class
    assert list(res.fluid.getComponentNames()) == list(fluid.getComponentNames())
    assert res.wellstream_h2s_mol_fraction == pytest.approx(2.0e-4, rel=0.05)


def test_composition_name_mismatch_rejected(e300_files):
    model, _ = e300_files
    fluid = load_e300_fluid(str(model))
    with pytest.raises(ValueError):
        apply_e300_composition(fluid, str(model), {"C1": 1.0, "NOPE": 0.1})
    with pytest.raises(ValueError):
        apply_e300_composition(fluid, str(model), [1.0, 2.0])
