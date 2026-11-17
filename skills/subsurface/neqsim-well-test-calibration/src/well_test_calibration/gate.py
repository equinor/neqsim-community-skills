"""Acceptance gate: use a calibration only when it predicts a test it has not seen better than the prior."""

from __future__ import annotations


def accept_calibration(tuned_error: float | None, prior_error: float | None, identifiable: bool,
                       n_tests: int, min_improvement: float = 0.0) -> dict[str, object]:
    """Decide whether tuned parameters replace the prior ones.

    ``tuned_error``/``prior_error`` are absolute errors on the held-out (latest) test, predicted by the model refitted
    without it and by the prior. Accept when the tuned model is better by more than ``min_improvement``. With a single
    test there is nothing to hold out; accept only when the fit is identifiable. Everything else keeps the prior, so a
    poor test can never make the model worse.
    """
    if n_tests >= 2 and tuned_error is not None and prior_error is not None:
        ok = tuned_error < prior_error - min_improvement
        reason = f"held-out error {tuned_error:.2f} vs prior {prior_error:.2f}"
    elif n_tests == 1:
        ok = bool(identifiable)
        reason = f"single test: accepted only if identifiable ({identifiable})"
    else:
        ok, reason = False, "no usable test"
    return {"accept": bool(ok), "reason": reason}
