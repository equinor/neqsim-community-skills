"""Shared fixtures: runtime probe, scratch folders inside the skill (removed at session end) and Java skip marker."""

import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
WDS = ROOT.parent / "neqsim-well-design-study" / "src"
if WDS.is_dir():
    sys.path.insert(0, str(WDS))

OUT = Path(__file__).resolve().parent / "_out"


@pytest.fixture(scope="session", autouse=True)
def _cleanup_out():
    yield
    shutil.rmtree(OUT, ignore_errors=True)


@pytest.fixture()
def out_dir(request):
    d = OUT / request.node.name.replace("[", "_").replace("]", "")
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture(scope="session")
def runtime():
    from integrated_well_planning.runtime import ensure_runtime

    return ensure_runtime()


@pytest.fixture(scope="session")
def java(runtime):
    if not runtime.wellplanning_available:
        pytest.skip("NeqSim wellplanning classes unavailable: " + (runtime.reason or "no runtime"))
    return runtime
