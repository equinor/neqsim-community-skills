"""Run the OLGA multiphase flow simulator and read its results.

Public entry points:

- :func:`find_olga` / :func:`find_olga_installations` — locate OLGA on this machine.
- :class:`OlgaRunner` — rule-check and run a case in batch, with exit-code decoding.
- :mod:`~olga_multiphase_simulator.genkey` helpers — edit case parameters for sweeps.
- :func:`read_tpl` / :func:`read_ppl` — read trend and profile results.
"""

from .casegen import (
    STEEL,
    FlowlineCaseSpec,
    Material,
    RouteProfile,
    WallLayer,
    build_mesh,
    equivalent_insulation_thickness,
    load_route_profile,
    overall_u_inner,
    render_genkey,
    simplify_route,
)
from .compare import (
    ComparisonRow,
    compare_rows,
    dominant_period,
    slug_statistics,
    to_csv,
    to_markdown,
)
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
    ensure_statement,
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
    "LICENSE_ENV_VARS",
    "STEEL",
    "ComparisonRow",
    "FlowlineCaseSpec",
    "GenkeyStatement",
    "Material",
    "OlgaBranch",
    "OlgaInstallation",
    "OlgaNotFoundError",
    "OlgaResultError",
    "OlgaRunResult",
    "OlgaRunner",
    "OlgaVariable",
    "ProfileData",
    "RouteProfile",
    "TrendData",
    "WallLayer",
    "apply_parameters",
    "build_mesh",
    "compare_rows",
    "describe_exit_code",
    "dominant_period",
    "ensure_statement",
    "equivalent_insulation_thickness",
    "find_olga",
    "find_olga_installations",
    "get_parameter",
    "iter_statements",
    "license_environment",
    "list_keywords",
    "load_route_profile",
    "olgas_point_model_roots",
    "overall_u_inner",
    "parameter_overview",
    "read_ppl",
    "read_tpl",
    "render_genkey",
    "set_parameter",
    "simplify_route",
    "slug_statistics",
    "to_csv",
    "to_markdown",
    "write_variant",
]
