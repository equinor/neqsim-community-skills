"""Gas deviation factor and polytropic compression for lean sweet gas (dependency-free)."""

from __future__ import annotations

import math

R = 8.314462618  # J/mol/K
P_STD = 1.01325  # bara
T_STD = 288.15  # K

_CRIT = {  # name -> (MW g/mol, Tc K, Pc bara)
    "N2": (28.013, 126.2, 33.94), "CO2": (44.01, 304.2, 73.76), "C1": (16.043, 190.6, 46.0),
    "C2": (30.07, 305.4, 48.84), "C3": (44.097, 369.8, 42.46), "iC4": (58.123, 408.1, 36.48),
    "nC4": (58.123, 425.2, 38.0), "iC5": (72.15, 460.4, 33.84), "nC5": (72.15, 469.6, 33.74),
    "C6": (86.177, 507.4, 29.69),
}
_A = (0.3265, -1.0700, -0.5339, 0.01569, -0.05165, 0.5475, -0.7361, 0.1844, 0.1056, 0.6134, 0.7210)


def z_factor(p_bara: float, t_k: float, tc: float, pc: float) -> float:
    """Dranchuk-Abou-Kassem Z by bisection on reduced density; 1.0 outside the correlation range."""
    ppr = max(p_bara / pc, 1e-6)
    tpr = t_k / tc
    a = _A
    c1 = a[0] + a[1] / tpr + a[2] / tpr**3 + a[3] / tpr**4 + a[4] / tpr**5
    c2 = a[5] + a[6] / tpr + a[7] / tpr**2
    c3 = a[8] * (a[6] / tpr + a[7] / tpr**2)

    def f(rho: float) -> float:
        c4 = a[9] * (1 + a[10] * rho**2) * rho**2 / tpr**3 * math.exp(-a[10] * rho**2)
        return 1 + c1 * rho + c2 * rho**2 - c3 * rho**5 + c4 - 0.27 * ppr / (rho * tpr)

    lo, hi = 1e-6, 3.0
    flo, fhi = f(lo), f(hi)
    if flo * fhi > 0:
        return 1.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        fm = f(mid)
        if flo * fm <= 0:
            hi = mid
        else:
            lo, flo = mid, fm
    rho = 0.5 * (lo + hi)
    return 0.27 * ppr / (rho * tpr)


class Gas:
    """Dry gas with Kay's-rule pseudo-critical constants from a mole-fraction dict (names N2, CO2, C1 ... C6)."""

    def __init__(self, composition: dict[str, float], kappa: float = 1.30):
        w = {k: v for k, v in composition.items() if k in _CRIT and v > 0}
        total = sum(w.values())
        if total <= 0:
            raise ValueError("composition has no supported components")
        w = {k: v / total for k, v in w.items()}
        self.mw = sum(w[k] * _CRIT[k][0] for k in w)
        self.tc = sum(w[k] * _CRIT[k][1] for k in w)
        self.pc = sum(w[k] * _CRIT[k][2] for k in w)
        self.kappa = kappa

    def z(self, p_bara: float, t_k: float) -> float:
        return z_factor(p_bara, t_k, self.tc, self.pc)

    def polytropic(self, p_in: float, p_out: float, t_in_k: float, eta_p: float) -> tuple[float, float]:
        """Polytropic head (J/kg) and discharge temperature (K), Z at the mean of inlet and outlet."""
        m1 = (self.kappa - 1.0) / (self.kappa * eta_p)
        t_out = t_in_k * (p_out / p_in) ** m1
        zm = 0.5 * (self.z(p_in, t_in_k) + self.z(p_out, t_out))
        rs = R / (self.mw * 1e-3)
        return zm * rs * t_in_k / m1 * ((p_out / p_in) ** m1 - 1.0), t_out

    def power_mw(self, mdot_kg_s: float, p_in: float, p_out: float, t_in_k: float, eta_p: float) -> float:
        head, _ = self.polytropic(p_in, p_out, t_in_k, eta_p)
        return mdot_kg_s * head / eta_p / 1e6


def static_bottomhole_pressure(whp_barg: float, gas: Gas, tvd_m: float, t_mean_k: float) -> float:
    """Bottom-hole pressure (bara) of a shut-in gas well from the static column equation."""
    pwh = whp_barg + P_STD
    pbh = pwh
    for _ in range(40):
        zbar = gas.z(0.5 * (pwh + pbh), t_mean_k)
        pbh = pwh * math.exp(gas.mw * 1e-3 * 9.80665 * tvd_m / (zbar * R * t_mean_k))
    return pbh
