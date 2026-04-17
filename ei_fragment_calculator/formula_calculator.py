"""
formula_calculator.py
====================
Interactive formula calculator for mass-to-formula lookup.

Provides reverse lookup: given a mass (m/z) and parent formula,
finds all valid fragment formulas that match within tolerance.

Two modes:
  - Standard (A3): Unit mass, ±0.5 Da tolerance, nominal m/z
  - High-resolution (A5): Exact mass, ppm tolerance, electron state tracking
"""

from typing import Optional
from .formula import parse_formula, hill_formula
from .calculator import exact_mass, ion_mass, calculate_dbe
from .constants import ELECTRON_MASS, MONOISOTOPIC_MASSES
from .filters import (
    nitrogen_rule, hd_check, lewis_senior, ring_check
)


def find_formulas_at_mass(
    target_mz: float,
    parent_composition: dict,
    tolerance: float = 0.5,
    electron_mode: str = "remove",
    max_depth: int = 3,
) -> list[dict]:
    """
    Find all valid fragment formulas for a given nominal m/z.

    Parameters
    ----------
    target_mz : float
        Target nominal m/z (rounded to nearest integer for standard mode)
    parent_composition : dict
        Parent molecule composition {"C": 6, "H": 12, "O": 1, ...}
    tolerance : float
        Mass window ±Da for candidate matching (default 0.5)
    electron_mode : str
        "remove" (EI+), "add" (EI-), or "none"
    max_depth : int
        Maximum recursion depth for generating fragments (default: 3)

    Returns
    -------
    list[dict]
        Each dict contains:
          - "formula": Hill formula string (e.g., "C6H5")
          - "composition": dict with elemental counts
          - "exact_mass": monoisotopic exact mass
          - "ion_mass": exact mass after electron correction
          - "delta_mass": difference from target_mz
          - "dbe": degree of unsaturation
          - "filter_tags": list of filters passed
    """
    results = []
    target_nominal = int(round(target_mz))

    # Determine max element counts from parent (fragments can't exceed parent)
    max_counts = {el: count for el, count in parent_composition.items()}

    # Generate all possible compositions up to max_depth
    candidates = _generate_fragment_compositions(max_counts, max_depth=max_depth)

    for comp in candidates:
        # Calculate masses
        neutral_mass = exact_mass(comp)
        if electron_mode == "remove":
            calc_mz = neutral_mass - ELECTRON_MASS
        elif electron_mode == "add":
            calc_mz = neutral_mass + ELECTRON_MASS
        else:
            calc_mz = neutral_mass

        delta = abs(calc_mz - target_mz)
        if delta > tolerance:
            continue

        # Basic chemical validity checks
        dbe = calculate_dbe(comp)
        if dbe is None or dbe < 0:
            continue

        # Calculate target nominal m/z for nitrogen rule
        target_nominal = int(round(target_mz))

        # Apply filters — REJECT if any fail
        if not nitrogen_rule(comp, target_nominal, dbe):
            continue
        if not hd_check(comp, dbe, max_ring_ratio=1.0):
            continue
        if not lewis_senior(comp, dbe):
            continue

        formula = hill_formula(comp)
        results.append({
            "formula": formula,
            "composition": dict(comp),
            "exact_mass": neutral_mass,
            "ion_mass": calc_mz,
            "delta_mass": delta,
            "dbe": dbe,
            "filter_tags": ["nitrogen_rule", "hd_check", "lewis_senior"],
            "matches_parent": all(comp.get(el, 0) <= parent_composition.get(el, 0)
                                   for el in comp),
        })

    # Sort by delta_mass ascending (closest match first)
    results.sort(key=lambda x: x["delta_mass"])
    return results


def find_formulas_at_exact_mass(
    target_mass: float,
    parent_composition: dict,
    ppm_tolerance: float = 5.0,
    electron_mode: str = "remove",
    max_depth: int = 3,
) -> list[dict]:
    """
    Find all valid fragment formulas for a given exact mass (high-resolution).

    [NEW] A5: High-Resolution Formula Calculator
    Supports exact-mass spectra (ORBITRAP, QTOF) with ppm-level precision.

    Parameters
    ----------
    target_mass : float
        Target exact mass (with decimals), e.g., 123.0457
    parent_composition : dict
        Parent molecule composition
    ppm_tolerance : float
        Mass window in ppm (default: 5.0 ppm)
    electron_mode : str
        "remove" (EI+), "add" (EI-), or "none"
    max_depth : int
        Maximum recursion depth for generating fragments (default: 3)

    Returns
    -------
    list[dict]
        Each dict contains:
          - "formula": Hill formula string
          - "composition": dict with elemental counts
          - "exact_mass": monoisotopic exact mass
          - "ion_mass": exact mass after electron correction
          - "delta_ppm": difference in ppm
          - "dbe": degree of unsaturation
          - "electron_state": "even" or "odd" (for radical cation detection)
          - "filter_tags": list of filters passed
    """
    results = []

    # Calculate absolute ppm window
    ppm_window = target_mass * ppm_tolerance / 1e6

    # Determine max element counts from parent
    max_counts = {el: count for el, count in parent_composition.items()}

    # Generate all possible compositions up to max_depth
    candidates = _generate_fragment_compositions(max_counts, max_depth=max_depth)

    for comp in candidates:
        # Calculate masses
        neutral_mass = exact_mass(comp)
        if electron_mode == "remove":
            calc_mass = neutral_mass - ELECTRON_MASS
        elif electron_mode == "add":
            calc_mass = neutral_mass + ELECTRON_MASS
        else:
            calc_mass = neutral_mass

        # Check if within ppm tolerance
        if calc_mass <= 0:
            continue

        delta_ppm = abs(calc_mass - target_mass) / calc_mass * 1e6
        if delta_ppm > ppm_tolerance:
            continue

        # Calculate chemical validity
        dbe = calculate_dbe(comp)
        if dbe is None or dbe < 0:
            continue

        # Determine electron state (even vs odd electron)
        # Odd-electron fragments have half-integer DBE
        dbe_frac = abs(dbe - round(dbe))
        electron_state = "odd" if dbe_frac > 0.4 else "even"

        # Calculate target nominal m/z for nitrogen rule
        target_nominal = int(round(target_mass))

        # Apply filters — REJECT if any fail
        if not nitrogen_rule(comp, target_nominal, dbe):
            continue
        if not hd_check(comp, dbe, max_ring_ratio=1.0):
            continue
        if not lewis_senior(comp, dbe):
            continue

        formula = hill_formula(comp)
        results.append({
            "formula": formula,
            "composition": dict(comp),
            "exact_mass": neutral_mass,
            "ion_mass": calc_mass,
            "delta_ppm": delta_ppm,
            "dbe": dbe,
            "electron_state": electron_state,
            "filter_tags": ["nitrogen_rule", "hd_check", "lewis_senior"],
            "matches_parent": all(comp.get(el, 0) <= parent_composition.get(el, 0)
                                   for el in comp),
        })

    # Sort by delta_ppm ascending (closest match first)
    results.sort(key=lambda x: x["delta_ppm"])
    return results


def _generate_fragment_compositions(
    max_counts: dict,
    max_depth: int = 3,
) -> list[dict]:
    """
    Generate all valid fragment compositions up to max_depth recursion.

    Parameters
    ----------
    max_counts : dict
        Maximum element counts (from parent composition)
    max_depth : int
        Maximum recursion depth

    Returns
    -------
    list[dict]
        All valid fragment compositions
    """
    results = []

    def _recurse(current: dict, depth: int):
        if depth == 0:
            return
        results.append(dict(current))

        # Try removing one atom at a time
        for element in list(current.keys()):
            if current[element] > 0:
                current[element] -= 1
                _recurse(current, depth - 1)
                current[element] += 1

    # Start with full parent composition
    _recurse(max_counts, max_depth)

    # Also add minimal compositions (single atoms)
    for element in max_counts:
        if max_counts[element] > 0:
            results.append({element: 1})

    # Remove duplicates (convert to tuples for set operations)
    unique = set()
    for comp in results:
        comp_tuple = tuple(sorted((el, cnt) for el, cnt in comp.items() if cnt > 0))
        unique.add(comp_tuple)

    # Convert back to dicts and filter out empty
    final_results = []
    for comp_tuple in unique:
        comp_dict = dict(comp_tuple)
        if comp_dict:  # Skip empty compositions
            final_results.append(comp_dict)

    return final_results


def format_formula_result(result: dict, hr_mode: bool = False) -> str:
    """
    Format a formula result for display.

    Parameters
    ----------
    result : dict
        Result from find_formulas_at_mass or find_formulas_at_exact_mass
    hr_mode : bool
        If True, use high-resolution formatting (ppm, electron state)

    Returns
    -------
    str
        Formatted result string
    """
    formula = result["formula"]
    dbe = result["dbe"]
    tags = ", ".join(result["filter_tags"]) if result["filter_tags"] else "—"

    if hr_mode:
        delta = result.get("delta_ppm", 0)
        e_state = result.get("electron_state", "?")
        return (f"{formula:12s} | "
                f"DBE={dbe:5.1f} | "
                f"Δ={delta:+6.2f}ppm | "
                f"e-={e_state:3s} | "
                f"Filters: {tags}")
    else:
        delta = result.get("delta_mass", 0)
        return (f"{formula:12s} | "
                f"DBE={dbe:5.1f} | "
                f"Δ={delta:+6.3f}Da | "
                f"Filters: {tags}")
