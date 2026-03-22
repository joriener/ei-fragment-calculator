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

from itertools import product as cartesian_product
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

    for counts in cartesian_product(*(range(n + 1) for n in max_counts)):

        composition = {
            el: cnt
            for el, cnt in zip(elements, counts)
            if cnt > 0
        }

        if not composition:
            continue

        # --- mass window filter ---
        neutral  = exact_mass(composition)
        measured = ion_mass(neutral, electron_mode)
        delta    = measured - nominal_mz

        if abs(delta) > tolerance:
            continue

        # --- DBE filter ---
        dbe = calculate_dbe(composition)
        if not is_valid_dbe(dbe):
            continue

        entry: dict = {
            "formula":       hill_formula(composition),
            "neutral_mass":  round(neutral, 6),
            "ion_mass":      round(measured, 6),
            "delta_mass":    round(delta, 6),
            "dbe":           dbe,
            "electron_mode": electron_mode,
            "_composition":  composition,   # needed by filter pipeline
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
            )
            for c in candidates
        ]

    return candidates
