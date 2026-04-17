"""
isotope.py
==========
Theoretical isotope pattern simulation using polynomial convolution.

Theory
------
For a molecule with composition C_a H_b N_c ..., the isotope distribution
is the product of the individual element distributions:

    P(molecule) = P(C)^a  ⊗  P(H)^b  ⊗  P(N)^c  ⊗  ...

where ⊗ denotes convolution and P(X)^n is the multinomial expansion of
(Σ_i abundance_i · x^mass_i)^n.

This is implemented by iteratively convolving a running result distribution
with each atom one at a time, which is equivalent to the full expansion.

Output
------
A list of (nominal_mass_offset, exact_mass, relative_abundance) tuples,
where relative_abundance is normalised to 100 for the most abundant peak.
The nominal_mass_offset is the integer difference from the monoisotopic mass
(0 = monoisotopic peak, 1 = M+1, 2 = M+2, ...).
"""

from .constants import ISOTOPE_DATA, MONOISOTOPIC_MASSES


def _convolve(
    dist_a: dict[float, float],
    dist_b: list[tuple[float, float]],
    mass_precision: int = 3,
) -> dict[float, float]:
    """
    Convolve distribution dict dist_a with a single-element isotope list dist_b.

    Parameters
    ----------
    dist_a         : dict  {rounded_mass: relative_abundance}  (running result)
    dist_b         : list  [(exact_mass, abundance), …]  (one element's isotopes)
    mass_precision : int   Decimal places for mass rounding to avoid float drift

    Returns
    -------
    dict  New convolved distribution.
    """
    result: dict[float, float] = {}
    for mass_a, abund_a in dist_a.items():
        for mass_b, abund_b in dist_b:
            combined_mass  = round(mass_a + mass_b, mass_precision)
            combined_abund = abund_a * abund_b
            result[combined_mass] = result.get(combined_mass, 0.0) + combined_abund
    return result


def isotope_pattern(
    composition: dict[str, int],
    min_abundance: float = 0.001,
    mass_precision: int = 3,
) -> list[dict]:
    """
    Calculate the theoretical isotope pattern for a molecular formula.

    Parameters
    ----------
    composition   : dict[str, int]   e.g. {'C': 7, 'H': 7, 'O': 1}
    min_abundance : float            Peaks below this relative abundance
                                     (0–1 scale) are pruned before normalisation.
                                     Default 0.001 = 0.1% relative.
    mass_precision: int              Decimal places for internal mass rounding.

    Returns
    -------
    list[dict]  Sorted by mass, each entry:
        ``mass``              : float  Exact centroid mass of the isotope peak
        ``relative_abundance``: float  Relative abundance normalised to 100
        ``nominal_offset``    : int    Integer mass offset from monoisotopic peak
                                       (0 = M, 1 = M+1, 2 = M+2, …)

    Notes
    -----
    - Elements not present in ISOTOPE_DATA are silently skipped
      (they contribute only their monoisotopic mass with abundance 1.0).
    - For large molecules (> 50 heavy atoms) the distribution can be slow;
      the min_abundance pruning helps keep the intermediate dict manageable.
    """
    if not composition:
        return []

    # Start: single peak at mass 0 with probability 1
    distribution: dict[float, float] = {0.0: 1.0}

    # Convolve one atom at a time for each element
    for element, count in composition.items():
        isotopes = ISOTOPE_DATA.get(element)

        if isotopes is None:
            # Element not in CSV: treat as monoisotopic only
            mono_mass = MONOISOTOPIC_MASSES.get(element, 0.0)
            isotopes  = [(mono_mass, 1.0)]

        for _ in range(count):
            distribution = _convolve(distribution, isotopes, mass_precision)

            # Prune very low-abundance peaks to keep memory bounded
            if not distribution:
                return []
            max_abund    = max(distribution.values())
            distribution = {
                m: a
                for m, a in distribution.items()
                if a / max_abund >= min_abundance
            }

    if not distribution:
        return []

    # Normalise to 100
    max_abund = max(distribution.values())
    normalised = {m: (a / max_abund) * 100.0 for m, a in distribution.items()}

    # Determine the monoisotopic mass to compute nominal offsets
    mono_mass = sum(
        MONOISOTOPIC_MASSES.get(el, 0.0) * cnt
        for el, cnt in composition.items()
    )

    results = []
    for mass, rel_abund in sorted(normalised.items()):
        offset = round(mass - mono_mass)   # integer nominal offset
        results.append({
            "mass":               round(mass, 6),
            "relative_abundance": round(rel_abund, 2),
            "nominal_offset":     offset,
        })

    return results


def pattern_summary(pattern: list[dict], max_peaks: int = 5) -> str:
    """
    Format an isotope pattern as a compact one-line summary string.

    Example output:  M(100%)  M+1(11.0%)  M+2(0.5%)

    Parameters
    ----------
    pattern   : list[dict]  Output of isotope_pattern()
    max_peaks : int         Maximum number of peaks to include (default 5)

    Returns
    -------
    str  Human-readable summary.
    """
    parts = []
    shown = 0
    for peak in sorted(pattern, key=lambda p: p["nominal_offset"]):
        if shown >= max_peaks:
            break
        offset = peak["nominal_offset"]
        label  = "M" if offset == 0 else f"M+{offset}"
        parts.append(f"{label}({peak['relative_abundance']:.1f}%)")
        shown += 1
    return "  ".join(parts) if parts else "—"
