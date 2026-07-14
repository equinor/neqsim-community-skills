"""Universal Paraffinic-Aromatic (P/A) heavy-end split factor helpers.

Plant-agnostic, dependency-free implementation of the universal P/A
characterisation split of Uleberg (2026) -- the "Legacy Common-Slate vs.
Universal Paraffinic-Aromatic Fluid Characterisation" method. A single fixed
component set (10 light + N paraffinic + N aromatic heavy lumps) represents any
feed; the feed's heavy-end character is carried by a split factor ``S`` -- the
paraffinic fraction of each heavy lump -- rather than by re-tuned properties.

For heavy lump ``i`` with total mole fraction ``Z_i`` the split factor ``S_i``
divides its moles between the paraffinic copy ``P_i`` and the aromatic copy
``A_i`` (paper Eq. 3)::

    P_i = S_i * Z_i
    A_i = (1 - S_i) * Z_i        so   P_i + A_i = Z_i  (moles conserved)

The recommended operational form is a single constant ``S`` per feed applied to
every heavy lump. A more general two-endpoint form interpolates ``S_i`` linearly
in molecular weight between ``S1`` (lightest heavy lump) and ``Sn`` (heaviest),
clipped to ``[eps, 1 - eps]`` (paper Eq. 4). For a feed with no separator
calibration, ``S`` is assigned provisionally from a screening correlation with
the C7+ molecular weight.

These are screening-level helpers. The critical properties, acentric factors,
volume shifts and BIPs of the paraffinic and aromatic families are fixed by the
universal EOS (for example the FluidMagic ``pa_universal.e300`` merged
Paraffin_Base + Aromatic_Base slate); this module only performs the molar split.

Reference:
    K. Uleberg, "Legacy Common-Slate vs. Universal Paraffinic-Aromatic Fluid
    Characterisation in Process Simulation: A Sleipner A Multi-Feed Case Study",
    Equinor ASA, June 2026 (Eqs. 3-4, Section 2.2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

# Screening C7+ molecular-weight correlation for the constant split factor
# (paper Section 2.2): S ~= C7PLUS_INTERCEPT - C7PLUS_SLOPE * MW_C7+ (g/mol),
# R^2 = 0.76 over n = 19 NCS fields.
C7PLUS_INTERCEPT = 1.3298
C7PLUS_SLOPE = 0.003531
DEFAULT_EPS = 0.02


def _clip(value: float, eps: float) -> float:
    """Clip a split factor to the open interval ``[eps, 1 - eps]``.

    :param value: candidate split factor.
    :param eps: small margin keeping the split strictly two-sided, in ``(0, 0.5)``.
    :returns: ``value`` clipped to ``[eps, 1 - eps]``.
    :raises ValueError: if ``eps`` is not in ``(0, 0.5)``.
    """
    if not 0.0 < eps < 0.5:
        raise ValueError("eps must be in the open interval (0, 0.5)")
    lo, hi = eps, 1.0 - eps
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def c7plus_split_correlation(mw_c7plus: float, eps: float = DEFAULT_EPS) -> float:
    """Return the provisional constant split factor from the C7+ molar mass.

    Implements the paper's screening correlation
    ``S ~= 1.3298 - 0.003531 * MW_C7+`` (MW in g/mol), clipped to
    ``[eps, 1 - eps]``. Heavier C7+ fractions get a smaller paraffinic split.
    Use this only when a feed has no field separator calibration.

    :param mw_c7plus: C7+ (plus-fraction) molecular weight in g/mol, must be
        positive.
    :param eps: clip margin, in ``(0, 0.5)``. Default 0.02.
    :returns: the provisional constant split factor ``S`` in ``[eps, 1 - eps]``.
    :raises ValueError: if ``mw_c7plus`` is not positive or ``eps`` is invalid.
    """
    if not mw_c7plus > 0.0:
        raise ValueError("mw_c7plus must be a positive molecular weight (g/mol)")
    return _clip(C7PLUS_INTERCEPT - C7PLUS_SLOPE * mw_c7plus, eps)


def constant_pa_split(
    core_totals: Sequence[float],
    split_factor: float,
) -> Tuple[List[float], List[float]]:
    """Split each heavy-lump total into paraffinic and aromatic copies.

    Applies a single constant split factor ``S`` to every heavy lump (paper
    Eq. 3): ``P_i = S * Z_i`` and ``A_i = (1 - S) * Z_i``.

    :param core_totals: total mole fraction ``Z_i`` of each heavy lump, each
        non-negative.
    :param split_factor: constant paraffinic fraction ``S`` in ``[0, 1]``.
    :returns: a ``(paraffinic, aromatic)`` tuple of per-lump mole-fraction lists.
    :raises ValueError: if ``split_factor`` is outside ``[0, 1]``, ``core_totals``
        is empty, or any total is negative.
    """
    if not 0.0 <= split_factor <= 1.0:
        raise ValueError("split_factor must be in [0, 1]")
    totals = [float(z) for z in core_totals]
    if not totals:
        raise ValueError("core_totals must be non-empty")
    if any(z < 0.0 for z in totals):
        raise ValueError("core_totals mole fractions must be non-negative")
    paraffinic = [split_factor * z for z in totals]
    aromatic = [(1.0 - split_factor) * z for z in totals]
    return paraffinic, aromatic


def two_endpoint_pa_split(
    core_totals: Sequence[float],
    core_molecular_weights: Sequence[float],
    split_light: float,
    split_heavy: float,
    eps: float = DEFAULT_EPS,
) -> Tuple[List[float], List[float]]:
    """Split heavy lumps with an MW-interpolated two-endpoint split factor.

    Implements the general form (paper Eq. 4): the per-lump split factor is
    interpolated linearly in molecular weight between ``split_light`` at the
    lightest heavy lump and ``split_heavy`` at the heaviest, clipped to
    ``[eps, 1 - eps]``. Reduces to :func:`constant_pa_split` when
    ``split_light == split_heavy``.

    :param core_totals: total mole fraction ``Z_i`` of each heavy lump.
    :param core_molecular_weights: molecular weight (g/mol) of each heavy lump,
        aligned with ``core_totals``; the min and max define the endpoints.
    :param split_light: split factor ``S1`` at the lightest heavy lump.
    :param split_heavy: split factor ``Sn`` at the heaviest heavy lump.
    :param eps: clip margin, in ``(0, 0.5)``. Default 0.02.
    :returns: a ``(paraffinic, aromatic)`` tuple of per-lump mole-fraction lists.
    :raises ValueError: if lengths differ, inputs are empty, a split endpoint is
        outside ``[0, 1]``, or a total is negative.
    """
    totals = [float(z) for z in core_totals]
    mws = [float(m) for m in core_molecular_weights]
    if not totals or not mws:
        raise ValueError("core_totals and core_molecular_weights must be non-empty")
    if len(totals) != len(mws):
        raise ValueError("core_totals and core_molecular_weights must have equal length")
    if any(z < 0.0 for z in totals):
        raise ValueError("core_totals mole fractions must be non-negative")
    for name, value in (("split_light", split_light), ("split_heavy", split_heavy)):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be in [0, 1]")
    mw_lo, mw_hi = min(mws), max(mws)
    span = mw_hi - mw_lo
    paraffinic: List[float] = []
    aromatic: List[float] = []
    for z, mw in zip(totals, mws):
        if span <= 0.0:
            s_i = split_light
        else:
            s_i = split_light + (split_heavy - split_light) * (mw - mw_lo) / span
        s_i = _clip(s_i, eps)
        paraffinic.append(s_i * z)
        aromatic.append((1.0 - s_i) * z)
    return paraffinic, aromatic


@dataclass(frozen=True)
class CoreLumpMap:
    """Pairing of paraffinic/aromatic copies back to their heavy-lump totals.

    :ivar core_labels: the heavy-lump base labels, in first-seen order (for
        example ``["C7", "C8", "C10-14", ...]``).
    :ivar core_totals: total mole fraction ``Z_i`` of each heavy lump
        (paraffinic copy + aromatic copy), aligned with ``core_labels``.
    :ivar paraffinic_index: index in the full component vector of each lump's
        paraffinic copy, aligned with ``core_labels``.
    :ivar aromatic_index: index in the full component vector of each lump's
        aromatic copy, aligned with ``core_labels``.
    :ivar light_index: indices of the shared light components (passed through
        unchanged by the split).
    """

    core_labels: List[str]
    core_totals: List[float]
    paraffinic_index: List[int]
    aromatic_index: List[int]
    light_index: List[int]


def recombine_core_totals(
    component_names: Sequence[str],
    mole_fractions: Sequence[float],
    paraffinic_suffix: str = "P",
    aromatic_suffix: str = "A",
) -> CoreLumpMap:
    """Recover heavy-lump totals ``Z_i`` from a P/A component vector.

    Pairs each paraffinic copy (name ending in ``paraffinic_suffix``) with its
    aromatic copy (same base label ending in ``aromatic_suffix``) and sums their
    mole fractions to the lump total ``Z_i = P_i + A_i``. Components that match
    neither suffix are treated as shared light components and reported in
    ``light_index``. This lets a caller re-apply a new constant ``S`` to a fluid
    already expressed on the universal 26-component P/A set (for example a
    ``pa_universal.e300`` ZI block) without any external lump table.

    :param component_names: the full component names of the P/A set, in order
        (for example ``["N2", "CO2", ..., "C7P", "C7A", "C8P", "C8A", ...]``).
    :param mole_fractions: mole fraction of each component, aligned with
        ``component_names``.
    :param paraffinic_suffix: suffix marking a paraffinic heavy copy. Default
        ``"P"``.
    :param aromatic_suffix: suffix marking an aromatic heavy copy. Default
        ``"A"``.
    :returns: a :class:`CoreLumpMap` pairing copies to lump totals.
    :raises ValueError: if lengths differ, a suffix is empty, or a paraffinic
        copy has no matching aromatic copy (or vice versa).
    """
    names = [str(n) for n in component_names]
    fractions = [float(x) for x in mole_fractions]
    if len(names) != len(fractions):
        raise ValueError("component_names and mole_fractions must have equal length")
    if not paraffinic_suffix or not aromatic_suffix:
        raise ValueError("paraffinic_suffix and aromatic_suffix must be non-empty")

    par_by_label: Dict[str, int] = {}
    aro_by_label: Dict[str, int] = {}
    light_index: List[int] = []
    order: List[str] = []
    par_suffix = paraffinic_suffix.upper()
    aro_suffix = aromatic_suffix.upper()
    for idx, name in enumerate(names):
        upper = name.upper()
        if upper.endswith(par_suffix):
            label = name[: -len(paraffinic_suffix)].upper()
            if label in par_by_label:
                raise ValueError(f"duplicate paraffinic copy for lump '{label}'")
            par_by_label[label] = idx
            if label not in order:
                order.append(label)
        elif upper.endswith(aro_suffix):
            label = name[: -len(aromatic_suffix)].upper()
            if label in aro_by_label:
                raise ValueError(f"duplicate aromatic copy for lump '{label}'")
            aro_by_label[label] = idx
            if label not in order:
                order.append(label)
        else:
            light_index.append(idx)

    core_labels: List[str] = []
    core_totals: List[float] = []
    paraffinic_index: List[int] = []
    aromatic_index: List[int] = []
    for label in order:
        if label not in par_by_label:
            raise ValueError(f"aromatic copy '{label}{aromatic_suffix}' has no paraffinic pair")
        if label not in aro_by_label:
            raise ValueError(f"paraffinic copy '{label}{paraffinic_suffix}' has no aromatic pair")
        p_idx = par_by_label[label]
        a_idx = aro_by_label[label]
        core_labels.append(label)
        core_totals.append(fractions[p_idx] + fractions[a_idx])
        paraffinic_index.append(p_idx)
        aromatic_index.append(a_idx)

    return CoreLumpMap(
        core_labels=core_labels,
        core_totals=core_totals,
        paraffinic_index=paraffinic_index,
        aromatic_index=aromatic_index,
        light_index=light_index,
    )


def apply_constant_split_to_vector(
    component_names: Sequence[str],
    mole_fractions: Sequence[float],
    split_factor: float,
    paraffinic_suffix: str = "P",
    aromatic_suffix: str = "A",
) -> List[float]:
    """Re-split a P/A component vector with a new constant split factor ``S``.

    Recovers each heavy-lump total from the current paraffinic/aromatic pair
    (see :func:`recombine_core_totals`), then rewrites the paraffinic copy to
    ``S * Z_i`` and the aromatic copy to ``(1 - S) * Z_i``. Light components pass
    through unchanged. Total moles are conserved, so a normalized input stays
    normalized.

    :param component_names: full P/A component names, in order.
    :param mole_fractions: mole fraction of each component, aligned with
        ``component_names``.
    :param split_factor: new constant paraffinic fraction ``S`` in ``[0, 1]``.
    :param paraffinic_suffix: suffix marking a paraffinic heavy copy. Default ``"P"``.
    :param aromatic_suffix: suffix marking an aromatic heavy copy. Default ``"A"``.
    :returns: a new mole-fraction list with the heavy end re-split by ``S``.
    :raises ValueError: if ``split_factor`` is outside ``[0, 1]`` or the P/A
        pairing is inconsistent.
    """
    if not 0.0 <= split_factor <= 1.0:
        raise ValueError("split_factor must be in [0, 1]")
    lump_map = recombine_core_totals(
        component_names, mole_fractions, paraffinic_suffix, aromatic_suffix
    )
    out = [float(x) for x in mole_fractions]
    for total, p_idx, a_idx in zip(
        lump_map.core_totals, lump_map.paraffinic_index, lump_map.aromatic_index
    ):
        out[p_idx] = split_factor * total
        out[a_idx] = (1.0 - split_factor) * total
    return out


@dataclass(frozen=True)
class SourceToPaMap:
    """Result of mapping a source composition onto a universal P/A set.

    :ivar light_fractions: mole fraction assigned to each shared light component,
        keyed by the normalized light label.
    :ivar core_totals: total heavy-lump mole fraction ``Z_i`` assigned to each
        universal core label (before the paraffinic/aromatic split).
    :ivar unmatched_light: normalized source light labels that did not match any
        target light component (their moles are dropped; reported for review).
    :ivar sum_in: total mole fraction of the (normalized) source composition.
    """

    light_fractions: Dict[str, float]
    core_totals: Dict[str, float]
    unmatched_light: List[str]
    sum_in: float


def _nearest_index(value: float, references: Sequence[float]) -> int:
    """Return the index of the reference closest to ``value``.

    :param value: the query value (for example a molecular weight).
    :param references: reference values to compare against, non-empty.
    :returns: the index of the nearest reference.
    :raises ValueError: if ``references`` is empty.
    """
    refs = [float(r) for r in references]
    if not refs:
        raise ValueError("references must be non-empty")
    best_idx = 0
    best_dist = abs(value - refs[0])
    for idx in range(1, len(refs)):
        dist = abs(value - refs[idx])
        if dist < best_dist:
            best_idx = idx
            best_dist = dist
    return best_idx


def map_source_to_pa_core_totals(
    source_names: Sequence[str],
    source_fractions: Sequence[float],
    source_molecular_weights: Sequence[float],
    light_names: Sequence[str],
    core_labels: Sequence[str],
    core_molecular_weights: Sequence[float],
    heavy_min_molecular_weight: float = 90.0,
    normalize: bool = True,
) -> SourceToPaMap:
    """Map an arbitrary source composition onto the universal P/A lumps.

    Implements the paper's nearest-molecular-weight mapping (Section 2.2): each
    source component that matches a shared light component (by name, case- and
    space-insensitive) is assigned to that light slot; every remaining (heavy)
    source component is accumulated into the universal **core lump whose
    molecular weight is nearest** to the source component's molecular weight. The
    returned core totals are the heavy-lump ``Z_i`` to which a split factor ``S``
    is later applied (:func:`constant_pa_split`).

    :param source_names: source component names (for example a reservoir E300 or
        a Fluid Symphony sample composition).
    :param source_fractions: source mole fractions, aligned with ``source_names``.
    :param source_molecular_weights: source molecular weights (g/mol), aligned
        with ``source_names``.
    :param light_names: the target shared light component names (for example the
        universal set's first ten: N2, CO2, C1-C6).
    :param core_labels: the target universal heavy-lump labels (for example
        ``["C7", "C8", "C9", "C10-14", ...]``).
    :param core_molecular_weights: representative molecular weight of each core
        lump, aligned with ``core_labels``.
    :param heavy_min_molecular_weight: components at or below this MW that do not
        match a light name are still treated as heavy and mapped to the nearest
        core; used only as a guard. Default 90.0.
    :param normalize: when ``True``, normalize the source fractions to sum to 1
        before mapping.
    :returns: a :class:`SourceToPaMap` with per-light fractions and per-core totals.
    :raises ValueError: if the source arrays differ in length, or the core arrays
        differ in length or are empty.
    """
    names = [str(n) for n in source_names]
    fractions = [float(x) for x in source_fractions]
    mws = [float(m) for m in source_molecular_weights]
    if not (len(names) == len(fractions) == len(mws)):
        raise ValueError("source_names, source_fractions, source_molecular_weights must align")
    labels = [str(c) for c in core_labels]
    core_mws = [float(m) for m in core_molecular_weights]
    if not labels or len(labels) != len(core_mws):
        raise ValueError("core_labels and core_molecular_weights must be non-empty and aligned")

    def norm(text: str) -> str:
        return "".join(str(text).split()).upper()

    light_lookup = {norm(n): norm(n) for n in light_names}
    total_in = sum(fractions)
    if normalize and total_in > 0.0:
        fractions = [f / total_in for f in fractions]

    light_fractions: Dict[str, float] = {}
    core_totals: Dict[str, float] = {label: 0.0 for label in labels}
    unmatched_light: List[str] = []
    _ = heavy_min_molecular_weight  # reserved guard; heavy set is "not a light name"
    for name, frac, mw in zip(names, fractions, mws):
        key = norm(name)
        if key in light_lookup:
            light_fractions[key] = light_fractions.get(key, 0.0) + frac
        else:
            idx = _nearest_index(mw, core_mws)
            core_totals[labels[idx]] += frac

    return SourceToPaMap(
        light_fractions=light_fractions,
        core_totals=core_totals,
        unmatched_light=unmatched_light,
        sum_in=total_in,
    )
