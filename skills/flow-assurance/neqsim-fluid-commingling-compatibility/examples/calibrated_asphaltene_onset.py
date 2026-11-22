"""Calibrated equation-of-state asphaltene onset for a condensate tie-in.

The host oil of ``heavy_oil_condensate_tie_in.py`` with an asphaltene
pseudo-component (1000 g/mol, 1.15 g/cm3, Tc 1015 K, Pc 15.7 bar, omega 1.5)
and a synthetic measured onset of 150 bara at 80 C. The model is calibrated on
the host alone and then predicts the onset pressure of every blend with the
condensate. Public, invented data. Run with the neqsim package installed:

    python examples/calibrated_asphaltene_onset.py
"""

from __future__ import annotations

import dataclasses
import importlib.util
import time
from pathlib import Path

from fluid_commingling_compatibility import (
    CalibratedAsphalteneModel,
    MeasuredOnset,
    NeqSimBlendEvaluator,
    NeqSimUnavailableError,
    PseudoComponent,
    screen_commingling,
)

_SPEC = importlib.util.spec_from_file_location(
    "heavy_oil_condensate_tie_in",
    Path(__file__).with_name("heavy_oil_condensate_tie_in.py"),
)
BASE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(BASE)

HOST_WITH_ASPHALTENE = dataclasses.replace(
    BASE.HOST_OIL,
    pseudo_components=[
        *BASE.HOST_OIL.pseudo_components,
        PseudoComponent("Asphaltene", 0.4, 1.0, 1.15, 1015.0, 15.7, 1.5),
    ],
)
MEASURED = MeasuredOnset(temperature_c=80.0, pressure_bara=150.0)


def main() -> int:
    try:
        evaluator = NeqSimBlendEvaluator()
    except NeqSimUnavailableError:
        print("SKIPPED: python -m pip install neqsim")
        return 0
    t0 = time.perf_counter()
    model = CalibratedAsphalteneModel(HOST_WITH_ASPHALTENE, MEASURED)
    report = screen_commingling(
        HOST_WITH_ASPHALTENE,
        BASE.NEW_CONDENSATE,
        BASE.CONDITIONS,
        evaluator,
        fractions=(0.2, 0.4, 0.6, 0.8),
        asphaltene_model=model,
    )
    print(report.to_markdown())
    print(f"({time.perf_counter() - t0:.0f} s, {model.backend} backend)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
