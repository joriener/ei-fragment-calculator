"""
calculator.py
=============
Exact-mass calculation, DBE filtering, electron-mass correction,
and the core fragment enumerator with optional isotope pattern output.

Electron-mass correction
------------------------
In EI mass spectrometry the analyte is ionised by losing one electron:

    M  +  e⁻(fast)  →  M+•  +  2 e⁻

The detector measures the mass-to-charge ratio of the *ion*:

    m/z_measured  =  M_neutral  −  m_electron     (remove, default, EI+)
    m/z_measured  =  M_neutral  +  m_electron     (add, EI−)

The ``electron_mode`` parameter accepts:
    ``"remove"``  standard EI positive-ion mode  (**default**)
    ``"add"``     negative-ion EI
    ``"none"``    no electron-mass correction
"""

import math
from typing import Optional
from .constants import MONOISOTOPIC_MASSES, VALENCE, ELECTRON_MASS
from .formula   import hill_formula
from .isotope   import isotope_pattern, pattern_summary
from .filters   import FilterConfig, run_all_filters


# ---------------------------------------------------------------------------
# Exact mass (neutral)
# ---------------------------------------------------------------------------

def exact_mass(composition: dict[str, int]) -> float:
    """
    Return the neutral monoisotopic mass for an elemental composition.

    Uses only the monoisotopic (lowest-mass, most-abundant) isotope of each
    element.  For the full isotope distribution see :mod:`.isotope`.

    Parameters
    ----------
    composition : dict[str, int]   e.g. {'C': 7, 'H': 7, 'O': 1}

    Returns
    -------
    float  neutral monoisotopic mass (Da)
    """
    return sum(
        MONOISOTOPIC_MASSES[el] * cnt
        for el, cnt in composition.items()
        if cnt > 0
    )


def ion_mass(neutral_mass: float, electron_mode: str) -> float:
    """
    Apply the electron-mass correction to convert neutral mass to ion m/z.

    Parameters
    ----------
    neutral_mass  : float  Neutral formula mass (Da).
    electron_mode : str    ``"remove"`` | ``"add"`` | ``"none"``

    Returns
    -------
    float  Expected singly-charged ion m/z (Da).

    Raises
    ------
    ValueError  for unrecognised electron_mode.
    """
    if electron_mode == "remove":
        return neutral_mass - ELECTRON_MASS   # EI+: ion = molecule − e⁻
    elif electron_mode == "add":
        return neutral_mass + ELECTRON_MASS   # EI−: ion = molecule + e⁻
    elif electron_mode == "none":
        return neutral_mass                   # no correction
    else:
        raise ValueError(
            f"Invalid electron_mode '{electron_mode}'. "
            "Choose 'remove', 'add', or 'none'."
        )


# ---------------------------------------------------------------------------
# DBE (degree of unsaturation)
# ---------------------------------------------------------------------------

def calculate_dbe(composition: dict[str, int]) -> float:
    """
    Calculate the degree of unsaturation (rings + double bonds).

    Formula:
        DBE = 1 + Σ_i  count_i × (valence_i − 2) / 2

    Valid values are non-negative multiples of 0.5.
    """
    dbe = 1.0
    for el, cnt in composition.items():
        val = VALENCE.get(el, 2)
        dbe += cnt * (val - 2) / 2.0
    return dbe


def is_valid_dbe(dbe: float) -> bool:
    """Return True if DBE ≥ 0 and is a multiple of 0.5."""
    if dbe < 0:
        return False
    return abs(dbe * 2 - round(dbe * 2)) < 1e-6


# ---------------------------------------------------------------------------
# Branch-and-bound formula enumerator
# ---------------------------------------------------------------------------

def _enumerate_pruned(elements, max_counts, masses, target, tol):
    """
    Yield every combination of element counts whose total mass lies within
    [target − tol, target + tol], using branch-and-bound pruning.

    Elements should be sorted heaviest-first so the tightest mass bounds
    are applied at the earliest recursion levels, maximising pruning.

    Parameters
    ----------
    elements   : list[str]   Element symbols (unused here, kept for clarity).
    max_counts : list[int]   Per-element upper bounds (atom conservation).
    masses     : list[float] Per-element monoisotopic masses.
    target     : float       Target neutral mass.
    tol        : float       Allowed deviation (Da).

    Yields
    ------
    tuple[int, ...]  One count per element, same order as input lists.
    """
    n = len(masses)
    # max_tail[i] = maximum achievable mass from element i onwards
    max_tail = [0.0] * (n + 1)
    for i in range(n - 1, -1, -1):
        max_tail[i] = max_tail[i + 1] + max_counts[i] * masses[i]

    counts = [0] * n

    def recurse(idx, partial):
        if idx == n:
            if abs(partial - target) <= tol + 1e-9:
                yield tuple(counts)
            return
        m = masses[idx]
        # Lower bound: need at least this many to still reach target−tol
        lo = max(0, math.ceil((target - tol - partial - max_tail[idx + 1]) / m))
        # Upper bound: cannot exceed target+tol with this element alone
        hi = min(max_counts[idx], math.floor((target + tol - partial) / m))
        for c in range(lo, hi + 1):
            counts[idx] = c
            yield from recurse(idx + 1, partial + c * m)

    yield from recurse(0, 0.0)


# ---------------------------------------------------------------------------
# Core fragment enumerator
# ---------------------------------------------------------------------------

def find_fragment_candidates(
    nominal_mz: int,
    parent_composition: dict,
    tolerance: float = 0.5,
    electron_mode: str = "remove",
    include_isotope_pattern: bool = False,
    filter_config: Optional[FilterConfig] = None,
    observed_spectrum: Optional[dict] = None,
    parent_ring_count: Optional[int] = None,
) -> list:
    """
    Find all elemental compositions that could explain a given unit-mass peak.

    Constraints
    -----------
    1. Elements: only those present in the parent molecule.
    2. Upper bound: fragment count ≤ parent count per element (atom conservation).
    3. Mass window: ion m/z within ±tolerance of nominal_mz.
    4. DBE: must be ≥ 0 and a multiple of 0.5.

    Parameters
    ----------
    nominal_mz              : int    Integer m/z from the unit-mass spectrum.
    parent_composition      : dict   Elemental composition of the intact molecule.
    tolerance               : float  Mass window in Da (default 0.5).
    electron_mode           : str    ``"remove"`` | ``"add"`` | ``"none"``
    include_isotope_pattern : bool   If True, calculate and attach the
                                     theoretical isotope pattern for each candidate.

    Returns
    -------
    list[dict]  Sorted by ion m/z, each entry:
        ``formula``          : str    Hill-notation formula
        ``neutral_mass``     : float  Neutral monoisotopic mass (Da)
        ``ion_mass``         : float  Expected ion m/z after electron correction
        ``delta_mass``       : float  ion_mass − nominal_mz (signed, Da)
        ``dbe``              : float  Degree of unsaturation
        ``electron_mode``    : str    Correction mode used
        ``isotope_pattern``  : list   (only if include_isotope_pattern=True)
                                      Output of isotope.isotope_pattern()
        ``isotope_summary``  : str    (only if include_isotope_pattern=True)
                                      Compact one-line pattern string
    """
    elements   = list(parent_composition.keys())
    max_counts = [parent_composition[el] for el in elements]
    candidates: list[dict] = []

    if not elements:
        return candidates

    # ------------------------------------------------------------------
    # Parent mass-defect-per-Da (mDa/Da): used as a ranking heuristic.
    # EI fragment ions tend to have a similar per-Da mass defect to their
    # parent compound (same elemental balance).  Storing the deviation of
    # each candidate from the parent's value lets rank_candidates() prefer
    # chemically plausible formulas (e.g. C6H5 over C5HO at m/z 77 for an
    # aromatic parent) even when a spurious O-rich formula is numerically
    # closer to the integer nominal m/z.
    # ------------------------------------------------------------------
    _parent_neutral = exact_mass(parent_composition)
    _parent_ion     = ion_mass(_parent_neutral, electron_mode)
    _parent_nominal = round(_parent_ion)
    _parent_mdd     = ((_parent_ion - _parent_nominal) / _parent_nominal * 1000.0
                       if _parent_nominal > 0 else None)

    # ------------------------------------------------------------------
    # Branch-and-bound enumeration
    # ------------------------------------------------------------------
    # Sort elements heaviest-first — this maximises early pruning because
    # the mass constraint becomes tight at the first recursion levels.
    order      = sorted(range(len(elements)),
                        key=lambda i: MONOISOTOPIC_MASSES[elements[i]],
                        reverse=True)
    elements   = [elements[i]   for i in order]
    max_counts = [max_counts[i] for i in order]
    masses     = [MONOISOTOPIC_MASSES[el] for el in elements]

    # Target *neutral* mass that would place the ion within ±tolerance
    if electron_mode == "remove":
        target = nominal_mz + ELECTRON_MASS
    elif electron_mode == "add":
        target = nominal_mz - ELECTRON_MASS
    else:
        target = float(nominal_mz)

    for combo in _enumerate_pruned(elements, max_counts, masses, target, tolerance):

        composition = {
            el: cnt
            for el, cnt in zip(elements, combo)
            if cnt > 0
        }

        if not composition:
            continue

        # --- mass window filter (floating-point exact check after B&B) ---
        neutral  = exact_mass(composition)
        measured = ion_mass(neutral, electron_mode)
        delta    = measured - nominal_mz

        if abs(delta) > tolerance:
            continue

        # --- DBE filter ---
        dbe = calculate_dbe(composition)
        if not is_valid_dbe(dbe):
            continue

        # per-Da mass defect deviation from parent (mDa/Da)
        if _parent_mdd is not None and nominal_mz > 0:
            _cand_mdd = (measured - nominal_mz) / nominal_mz * 1000.0
            _mdd_dev  = abs(_cand_mdd - _parent_mdd)
        else:
            _mdd_dev  = None

        entry: dict = {
            "formula":        hill_formula(composition),
            "neutral_mass":   round(neutral, 6),
            "ion_mass":       round(measured, 6),
            "delta_mass":     round(delta, 6),
            "dbe":            dbe,
            "electron_mode":  electron_mode,
            "_composition":   composition,  # needed by filter pipeline
            "_mdd_deviation": _mdd_dev,     # mass-defect similarity score
        }

        # --- optional isotope pattern ---
        if include_isotope_pattern:
            pattern = isotope_pattern(composition)
            entry["isotope_pattern"] = pattern
            entry["isotope_summary"] = pattern_summary(pattern)

        candidates.append(entry)

    candidates.sort(key=lambda x: x["ion_mass"])

    # --- optional filter pipeline ---
    if filter_config is not None:
        candidates = [
            run_all_filters(
                c, nominal_mz, filter_config,
                observed_spectrum, parent_ring_count,
                intensity_map=None,
                parent_composition=parent_composition,
            )
            for c in candidates
        ]

    return candidates
