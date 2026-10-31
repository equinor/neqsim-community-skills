"""Run one or all of the four synthetic worked cases end to end.

Usage (shared NeqSim interpreter, from the skill folder):
    <python> examples/run_cases.py OUTPUT_FOLDER [case ...]

Cases: oil_producer_platform, gas_condensate_producer_subsea, water_injector_onshore, gas_injector_platform.
Every input is a synthetic demonstration assumption; the reports are stamped accordingly.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE.parents[1] / "neqsim-well-design-study" / "src"))

from integrated_well_planning import study  # noqa: E402
from integrated_well_planning.basis import load_basis  # noqa: E402
from integrated_well_planning.drawings_run import make_drawings  # noqa: E402
from integrated_well_planning.report import build_report  # noqa: E402
from integrated_well_planning.runtime import ensure_runtime  # noqa: E402

CASES = ["oil_producer_platform", "gas_condensate_producer_subsea", "water_injector_onshore", "gas_injector_platform"]


def run_case(name: str, out: Path) -> dict:
    """Run validate, model, alternatives, envelope, drawings and report for one case."""
    root = out / name
    study.init_study(root, basis=load_basis(HERE / (name + ".yaml")), overwrite=True)
    study.validate(root)
    study.run_model(root)
    study.alternatives(root, with_tornado=True, profile_years=[0.0, 5.0, 10.0])
    study.envelope(root)
    make_drawings(root)
    return build_report(root)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    rt = ensure_runtime()
    if not rt.wellplanning_available:
        raise SystemExit("NeqSim wellplanning classes unavailable: " + rt.reason)
    selected = sys.argv[2:] or CASES
    for case in selected:
        print(case, run_case(case, Path(sys.argv[1]))["readiness"])
