"""Lifetime check of an existing item against the tie-in horizon: replace, refurbish, life-extend, monitor or ok."""
from __future__ import annotations


def lifetime_check(item, horizon_end_year, as_of_year):
    """Screen remaining life against the end of the tie-in horizon.

    Args:
        item: normalized inventory item (``remaining_life_years``, ``condition``).
        horizon_end_year: last year the tie-in must operate (for example plateau end plus margin).
        as_of_year: year of the assessment.

    Returns:
        dict with ``remaining_life_years``, ``required_years``, ``gap_years``, ``covers_horizon``, ``action`` (ok, monitor,
        life-extend, refurbish, replace, data-gap) and ``basis``. Screening only: the owner's lifetime programme
        (technical lifetime cases, integrity data) decides.
    """
    required = float(horizon_end_year) - float(as_of_year)
    remaining = item.get("remaining_life_years")
    cond = item.get("condition", "unknown")
    if remaining is None:
        return {"remaining_life_years": None, "required_years": required, "gap_years": None, "covers_horizon": None, "action": "data-gap",
                "basis": "no install year / design life / remaining life: obtain the lifetime case and inspection history"}
    gap = required - remaining
    if gap <= 0:
        margin = -gap
        action = "monitor" if (margin < 2.0 or cond in ("fair", "poor")) else "ok"
        basis = "remaining life covers the horizon with %.1f years margin" % margin
    elif gap <= 10.0 and cond != "poor":
        action, basis = "life-extend", "shortfall %.1f years: life-extension assessment (integrity data, inspection) before commitment" % gap
    elif gap <= 20.0:
        action, basis = "refurbish", "shortfall %.1f years: refurbishment / requalification scope needed" % gap
    else:
        action, basis = "replace", "shortfall %.1f years: plan replacement (new-build cost basis)" % gap
    if cond == "poor" and action in ("ok", "monitor", "life-extend"):
        action, basis = "refurbish", basis + "; poor condition raises the action to refurbish"
    return {"remaining_life_years": remaining, "required_years": required, "gap_years": round(gap, 1), "covers_horizon": gap <= 0, "action": action, "basis": basis}
