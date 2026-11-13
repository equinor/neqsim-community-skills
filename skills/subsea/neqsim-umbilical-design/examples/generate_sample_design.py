"""Generate the sample umbilical design JSON (the test fixture) with NeqSim.

Run: python generate_sample_design.py <output.json>
Needs a NeqSim that contains the umbilical physics (``Umbilical.setInjectionRate``). In a NeqSim
source checkout set NEQSIM_PROJECT_ROOT to use ``devtools/neqsim_dev_setup.py`` and the freshly
built classes; otherwise the installed ``neqsim`` package is used.
"""
import json
import os
import sys
from pathlib import Path

root = os.environ.get("NEQSIM_PROJECT_ROOT")
if root:
    sys.path.insert(0, str(Path(root) / "devtools"))
    from neqsim_dev_setup import neqsim_init

    ns = neqsim_init(project_root=root)
    Umbilical = ns.JClass("neqsim.process.equipment.subsea.Umbilical")
else:
    from neqsim import jneqsim

    Umbilical = jneqsim.process.equipment.subsea.Umbilical

u = Umbilical("Synthetic 15 km control umbilical")
u.setLength(15000.0)
u.setWaterDepth(100.0)
u.addHydraulicLine("LP hydraulic supply", 9.5, 345.0)
u.addHydraulicLine("HP hydraulic supply", 6.35, 690.0)
u.addChemicalLine("MEG", 25.4, 345.0)
u.addChemicalLine("Methanol", 12.7, 345.0)
u.addChemicalLine("Scale inhibitor", 12.7, 345.0)
u.addElectricalCable("Power", 3, 3300.0, 16.0)
u.addElectricalCable("Signal quad", 4, 100.0, 1.5)
u.addFiberOptic("Fibre", 12)
u.setInjectionRate("MEG", 0.5, "m3/hr")
u.setInjectionRate("Methanol", 0.3, "m3/hr")
u.setInjectionRate("Scale inhibitor", 0.05, "m3/hr")
u.setPowerLoad(0.05)
design = u.getMechanicalDesign()
design.calcDesign()
out = json.loads(str(design.toJson()))
target = Path(sys.argv[1])
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(out, indent=1), encoding="utf-8")
print(json.dumps(out["designChecks"], indent=1))
