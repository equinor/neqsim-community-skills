"""Global sensitivity with the optional SALib and chaospy backends.

Both are optional. Without them the example explains how to install them and
exits cleanly; the dependency-free tornado in ``monte_carlo_npv_study.py``
remains the fallback.

The point of this example is what a tornado cannot show: the Ishigami function
has a parameter (x3) with **no** first-order effect but a large total-order
effect, so a one-at-a-time tornado ranks it as irrelevant while Sobol' does not.
"""

from __future__ import annotations

import json
import math

from uncertainty_quantification import Uniform
from uncertainty_quantification.backends import (
    CHAOSPY_INSTALL_HINT,
    SALIB_INSTALL_HINT,
    chaospy_available,
    fit_polynomial_chaos,
    saltelli_samples,
    salib_available,
    sobol_indices,
)

PARAMETERS = [
    Uniform(name="x1", low=-math.pi, high=math.pi),
    Uniform(name="x2", low=-math.pi, high=math.pi),
    Uniform(name="x3", low=-math.pi, high=math.pi),
]


def ishigami(values):
    """Ishigami test function — the standard global-sensitivity benchmark."""
    x1, x2, x3 = values["x1"], values["x2"], values["x3"]
    return math.sin(x1) + 7.0 * math.sin(x2) ** 2 + 0.1 * x3**4 * math.sin(x1)


def main() -> None:
    if salib_available():
        design = saltelli_samples(PARAMETERS, 1024, seed=42)
        outputs = [ishigami(point) for point in design]
        indices = sobol_indices(PARAMETERS, outputs)
        print("Sobol' indices from {} evaluations:".format(len(outputs)))
        print(json.dumps(indices, indent=2))
        print(
            "\nNote: x3 has S1 near zero but a large ST — a pure interaction "
            "effect that a one-at-a-time tornado cannot see.\n"
        )
    else:
        print("SALib is not installed — {}".format(SALIB_INSTALL_HINT))

    if chaospy_available():
        fit = fit_polynomial_chaos(PARAMETERS, ishigami, order=6, seed=42)
        print(
            "Polynomial chaos: mean={:.4f}, std={:.4f} from {} evaluations".format(
                fit["mean"], fit["std"], fit["evaluations"]
            )
        )
        print("First-order indices: {}".format([round(v, 4) for v in fit["S1"]]))
        print("Analytical Ishigami mean is 3.5.")
    else:
        print("chaospy is not installed — {}".format(CHAOSPY_INSTALL_HINT))


if __name__ == "__main__":
    main()
