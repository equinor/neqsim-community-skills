"""Make the sibling ``neqsim-ncs-infrastructure-network`` package importable in a source checkout."""

import sys
from pathlib import Path

try:
    import ncs_infrastructure_network  # noqa: F401
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "neqsim-ncs-infrastructure-network" / "src"))
