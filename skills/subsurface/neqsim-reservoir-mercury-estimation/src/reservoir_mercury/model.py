"""Statistical model for log10 mercury in gas: ridge regression with shrunk group effects.

The model is deliberately simple and transparent. Categorical predictors (for example stratigraphic epoch, group or
structural province) become indicator columns whose coefficients are shrunk towards zero with a ridge penalty, so a
group with few tests moves only a little from the overall mean and an unseen group predicts the overall mean.
Numeric predictors (for example reservoir temperature) are centred and lightly penalised. Prediction uncertainty is the
leave-one-cluster-out residual standard deviation (cluster = well), which is the honest error for a new well.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

#: Standard normal quantile of the 90 % point (P10/P90 of a normal distribution lie at -/+ Z90 sigma).
Z90 = 1.2815515655446004


def _is_missing(value: Any) -> bool:
    """Return True for None, NaN and empty strings."""
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return isinstance(value, str) and not value.strip()


@dataclass
class ShrinkageModel:
    """Ridge model of a log10 quantity with categorical and numeric predictors.

    Attributes:
        categorical: Names of the categorical predictors.
        numeric: Names of the numeric predictors.
        ridge: Ridge penalty on the indicator columns (about the number of tests a group needs before its own mean
            counts as much as the overall mean).
        numeric_ridge: Ridge penalty on the standardised numeric columns.
    """

    categorical: Sequence[str] = ()
    numeric: Sequence[str] = ()
    ridge: float = 3.0
    numeric_ridge: float = 0.5
    intercept: float = 0.0
    levels: dict[str, list[str]] = field(default_factory=dict)
    effects: dict[str, dict[str, float]] = field(default_factory=dict)
    numeric_center: dict[str, float] = field(default_factory=dict)
    numeric_scale: dict[str, float] = field(default_factory=dict)
    numeric_coef: dict[str, float] = field(default_factory=dict)
    residual_sd: float = float("nan")
    cv_sd: float = float("nan")
    n: int = 0
    counts: dict[str, dict[str, int]] = field(default_factory=dict)

    # ------------------------------------------------------------------ design matrix
    def _design(self, rows: Sequence[Mapping[str, Any]]) -> np.ndarray:
        """Build the design matrix (intercept, indicators, standardised numerics) for fitted levels."""
        cols = [np.ones(len(rows))]
        for name in self.categorical:
            for level in self.levels.get(name, []):
                cols.append(
                    np.array(
                        [
                            (
                                1.0
                                if str(r.get(name)) == level
                                and not _is_missing(r.get(name))
                                else 0.0
                            )
                            for r in rows
                        ]
                    )
                )
        for name in self.numeric:
            c, s = self.numeric_center[name], self.numeric_scale[name]
            cols.append(
                np.array(
                    [
                        0.0 if _is_missing(r.get(name)) else (float(r[name]) - c) / s
                        for r in rows
                    ]
                )
            )
        return np.column_stack(cols)

    def fit(self, rows: Sequence[Mapping[str, Any]], target: str) -> ShrinkageModel:
        """Fit the model.

        Args:
            rows: One mapping per test with the predictors and the target (log10 value). Missing predictors are
                allowed: a missing category gets no group effect and a missing numeric takes the mean.
            target: Name of the target column.

        Returns:
            The fitted model (self).

        Raises:
            ValueError: If fewer than three rows have a target.
        """
        rows = [r for r in rows if not _is_missing(r.get(target))]
        if len(rows) < 3:
            raise ValueError("at least three rows with a target are needed")
        y = np.array([float(r[target]) for r in rows])
        self.levels, self.counts = {}, {}
        for name in self.categorical:
            values = [str(r[name]) for r in rows if not _is_missing(r.get(name))]
            self.levels[name] = sorted(set(values))
            self.counts[name] = {lv: values.count(lv) for lv in self.levels[name]}
        for name in self.numeric:
            v = np.array([float(r[name]) for r in rows if not _is_missing(r.get(name))])
            self.numeric_center[name] = float(v.mean()) if len(v) else 0.0
            self.numeric_scale[name] = (
                float(v.std()) if len(v) > 1 and v.std() > 0 else 1.0
            )
        x = self._design(rows)
        penalty = [0.0]
        for name in self.categorical:
            penalty += [self.ridge] * len(self.levels[name])
        penalty += [self.numeric_ridge] * len(self.numeric)
        beta = np.linalg.solve(x.T @ x + np.diag(penalty), x.T @ y)
        self.intercept = float(beta[0])
        k = 1
        self.effects = {}
        for name in self.categorical:
            self.effects[name] = {
                lv: float(beta[k + i]) for i, lv in enumerate(self.levels[name])
            }
            k += len(self.levels[name])
        self.numeric_coef = {
            name: float(beta[k + i]) for i, name in enumerate(self.numeric)
        }
        resid = y - x @ beta
        self.n = len(rows)
        self.residual_sd = float(np.sqrt(np.sum(resid**2) / max(len(rows) - 1, 1)))
        return self

    def predict(self, row: Mapping[str, Any]) -> dict[str, Any]:
        """Predict the log10 value for one case and list the contribution of each predictor.

        Args:
            row: Predictors of the case; missing or unseen values contribute nothing.

        Returns:
            ``{"log10", "contributions", "unseen"}`` where ``contributions`` maps each predictor to its additive
            effect in log10 units and ``unseen`` lists categorical values that were not in the calibration data.
        """
        value = self.intercept
        contributions: dict[str, float] = {}
        unseen: list[str] = []
        for name in self.categorical:
            v = row.get(name)
            if _is_missing(v):
                contributions[name] = 0.0
                continue
            eff = self.effects.get(name, {}).get(str(v))
            if eff is None:
                unseen.append(f"{name}={v}")
                eff = 0.0
            contributions[name] = eff
            value += eff
        for name in self.numeric:
            v = row.get(name)
            eff = (
                0.0
                if _is_missing(v)
                else self.numeric_coef[name]
                * (float(v) - self.numeric_center[name])
                / self.numeric_scale[name]
            )
            contributions[name] = eff
            value += eff
        return {"log10": value, "contributions": contributions, "unseen": unseen}

    # ------------------------------------------------------------------ persistence
    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable description of the fitted model."""
        return {
            "categorical": list(self.categorical),
            "numeric": list(self.numeric),
            "ridge": self.ridge,
            "numeric_ridge": self.numeric_ridge,
            "intercept": self.intercept,
            "levels": self.levels,
            "effects": self.effects,
            "numeric_center": self.numeric_center,
            "numeric_scale": self.numeric_scale,
            "numeric_coef": self.numeric_coef,
            "residual_sd": self.residual_sd,
            "cv_sd": self.cv_sd,
            "n": self.n,
            "counts": self.counts,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ShrinkageModel:
        """Rebuild a model from :meth:`to_dict` output."""
        model = cls(
            categorical=tuple(data["categorical"]),
            numeric=tuple(data["numeric"]),
            ridge=data["ridge"],
            numeric_ridge=data["numeric_ridge"],
        )
        for key in (
            "intercept",
            "levels",
            "effects",
            "numeric_center",
            "numeric_scale",
            "numeric_coef",
            "residual_sd",
            "cv_sd",
            "n",
            "counts",
        ):
            setattr(model, key, data[key])
        return model


def cross_validate(
    rows: Sequence[Mapping[str, Any]],
    target: str,
    cluster: str,
    categorical: Sequence[str] = (),
    numeric: Sequence[str] = (),
    ridge: float = 3.0,
    numeric_ridge: float = 0.5,
) -> dict[str, Any]:
    """Leave-one-cluster-out cross-validation (cluster = well or field) of a :class:`ShrinkageModel`.

    Args:
        rows: Calibration rows.
        target: Target column (log10 value).
        cluster: Column that identifies the cluster left out together (all tests of one well).
        categorical: Categorical predictors.
        numeric: Numeric predictors.
        ridge: Ridge penalty on indicator columns.
        numeric_ridge: Ridge penalty on numeric columns.

    Returns:
        ``{"rmse", "mae", "bias", "within_factor_3", "within_factor_10", "n", "clusters", "predictions"}`` in log10
        units, with ``predictions`` a list of ``(observed, predicted, cluster)``.
    """
    rows = [r for r in rows if not _is_missing(r.get(target))]
    clusters = sorted({str(r.get(cluster)) for r in rows})
    preds = []
    for c in clusters:
        train = [r for r in rows if str(r.get(cluster)) != c]
        test = [r for r in rows if str(r.get(cluster)) == c]
        if len(train) < 3:
            continue
        model = ShrinkageModel(
            categorical=categorical,
            numeric=numeric,
            ridge=ridge,
            numeric_ridge=numeric_ridge,
        ).fit(train, target)
        for r in test:
            preds.append((float(r[target]), model.predict(r)["log10"], c))
    err = np.array([p[1] - p[0] for p in preds])
    return {
        "rmse": float(np.sqrt(np.mean(err**2))),
        "mae": float(np.mean(np.abs(err))),
        "bias": float(np.mean(err)),
        "within_factor_3": float(np.mean(np.abs(err) <= math.log10(3.0))),
        "within_factor_10": float(np.mean(np.abs(err) <= 1.0)),
        "n": len(preds),
        "clusters": len(clusters),
        "predictions": preds,
    }


def interval_coverage(errors: Sequence[float], log10_sd: float) -> dict[str, float]:
    """Share of prediction errors inside, above and below a stated P10 to P90 range.

    Args:
        errors: Measured minus predicted log10 values (predictions made with the cluster left out).
        log10_sd: Standard deviation used for the stated range.

    Returns:
        ``{"inside", "above", "below"}`` as fractions; a calibrated range gives 0.8, 0.1 and 0.1.
    """
    err = np.asarray(list(errors), dtype=float)
    half = Z90 * log10_sd
    return {
        "inside": float((np.abs(err) <= half).mean()),
        "above": float((err > half).mean()),
        "below": float((err < -half).mean()),
    }


def lognormal_quantiles(log10_mean: float, log10_sd: float) -> dict[str, float]:
    """Return P10, P50, P90 and the mean of a lognormal quantity given the mean and sd of its log10.

    Args:
        log10_mean: Mean of log10(value).
        log10_sd: Standard deviation of log10(value).

    Returns:
        ``{"p10", "p50", "p90", "mean"}`` in the unit of the value (P10 is the low value, P90 the high value).
    """
    return {
        "p10": 10 ** (log10_mean - Z90 * log10_sd),
        "p50": 10**log10_mean,
        "p90": 10 ** (log10_mean + Z90 * log10_sd),
        "mean": 10**log10_mean * math.exp(0.5 * (math.log(10.0) * log10_sd) ** 2),
    }


def save_registry(registry: Mapping[str, Any], path: str) -> None:
    """Write a calibration registry (models, statistics, provenance) as UTF-8 JSON."""
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(registry, handle, indent=1, ensure_ascii=False, default=str)


def load_registry(path: str) -> dict[str, Any]:
    """Read a calibration registry written by :func:`save_registry`."""
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def group_statistics(
    rows: Iterable[Mapping[str, Any]], key: str, target: str, cluster: str
) -> list[dict[str, Any]]:
    """Summarise the target per group: tests, wells, geometric mean, log10 sd, minimum and maximum.

    Args:
        rows: Calibration rows.
        key: Grouping column.
        target: Target column (log10 value).
        cluster: Column that identifies the well.

    Returns:
        One record per group, sorted by decreasing geometric mean.
    """
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for r in rows:
        if _is_missing(r.get(key)) or _is_missing(r.get(target)):
            continue
        groups.setdefault(str(r[key]), []).append(r)
    out = []
    for name, items in groups.items():
        y = np.array([float(r[target]) for r in items])
        out.append(
            {
                "group": name,
                "tests": len(items),
                "wells": len({str(r.get(cluster)) for r in items}),
                "geometric_mean": float(10 ** y.mean()),
                "log10_sd": float(y.std(ddof=1)) if len(y) > 1 else None,
                "min": float(10 ** y.min()),
                "max": float(10 ** y.max()),
                "median": float(10 ** np.median(y)),
            }
        )
    return sorted(out, key=lambda d: -d["geometric_mean"])
