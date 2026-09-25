"""Generic building blocks for NeqSim living tasks (continuous task solving).

* :class:`TagreaderAdapter` - historian source for ``cycle_plan.yaml`` (PI / IP.21 via tagreader);
* :func:`propose_next` - Gaussian-process Bayesian optimisation with expected improvement,
  for solve stages that tune setpoints on an expensive NeqSim model;
* :func:`enkf_update` / :func:`identifiability` - ensemble Kalman parameter update and a
  check of which parameters the measurements can actually determine.

None of these need enterprise access. Use them from a stage script or name the adapter in
the plan as ``continuous_improvement_toolkit.tagreader_adapter:TagreaderAdapter``.
"""

from .bayes_opt import expected_improvement, fit_gp, propose_next
from .enkf import enkf_update, identifiability
from .results import SourceResult
from .tagreader_adapter import TagreaderAdapter

__all__ = ["TagreaderAdapter", "SourceResult", "fit_gp", "expected_improvement", "propose_next",
           "enkf_update", "identifiability"]
