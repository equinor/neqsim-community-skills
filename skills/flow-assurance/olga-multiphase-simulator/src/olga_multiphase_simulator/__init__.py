"""Run the OLGA multiphase flow simulator and read its results.

Public entry points:

- :func:`find_olga` / :func:`find_olga_installations` — locate OLGA on this machine.
- :class:`OlgaRunner` — rule-check and run a case in batch, with exit-code decoding.
- :mod:`~olga_multiphase_simulator.genkey` helpers — edit case parameters for sweeps.
- :func:`read_tpl` / :func:`read_ppl` — read trend and profile results.
"""

from .discovery import (
    LICENSE_ENV_VARS,
    OlgaInstallation,
    OlgaNotFoundError,
    find_olga,
    find_olga_installations,
    license_environment,
    olgas_point_model_roots,
)
from .genkey import (
    GenkeyStatement,
    apply_parameters,
    get_parameter,
    iter_statements,
    list_keywords,
    parameter_overview,
    set_parameter,
    write_variant,
)
from .results import (
    OlgaBranch,
    OlgaResultError,
    OlgaVariable,
    ProfileData,
    TrendData,
    read_ppl,
    read_tpl,
)
from .runner import EXIT_CODES, OlgaRunner, OlgaRunResult, describe_exit_code

__version__ = "0.1.0"

__all__ = [
    "EXIT_CODES",
    "GenkeyStatement",
    "LICENSE_ENV_VARS",
    "OlgaBranch",
    "OlgaInstallation",
    "OlgaNotFoundError",
    "OlgaResultError",
    "OlgaRunResult",
    "OlgaRunner",
    "OlgaVariable",
    "ProfileData",
    "TrendData",
    "apply_parameters",
    "describe_exit_code",
    "find_olga",
    "find_olga_installations",
    "get_parameter",
    "iter_statements",
    "license_environment",
    "list_keywords",
    "olgas_point_model_roots",
    "parameter_overview",
    "read_ppl",
    "read_tpl",
    "set_parameter",
    "write_variant",
]
