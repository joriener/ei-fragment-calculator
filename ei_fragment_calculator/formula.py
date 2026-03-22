"""
formula.py
==========
Molecular formula parsing and Hill-notation formatting.
"""

import re
from .constants import MONOISOTOPIC_MASSES


def parse_formula(formula: str) -> dict[str, int]:
    """
    Parse a molecular formula string into an element → count dict.

    Uses Hill notation: one uppercase letter optionally followed by one
    lowercase letter, then an optional integer (absent = 1).

    Parameters
    ----------
    formula : str
        e.g. "C10H12O2", "C6H5BrN", "C20H25ClN2O3S"

    Returns
    -------
    dict[str, int]
        e.g. {'C': 10, 'H': 12, 'O': 2}

    Raises
    ------
    ValueError
        If the formula is empty, unparseable, or contains an unsupported element.
    """
    token_pattern = re.compile(r"([A-Z][a-z]?)(\d*)")
    result: dict[str, int] = {}

    for match in token_pattern.finditer(formula):
        element   = match.group(1)
        count_str = match.group(2)
        count     = int(count_str) if count_str else 1

        if element not in MONOISOTOPIC_MASSES:
            raise ValueError(
                f"Unknown or unsupported element '{element}' in formula '{formula}'.\n"
                f"Supported elements: {', '.join(sorted(MONOISOTOPIC_MASSES))}"
            )
        result[element] = result.get(element, 0) + count

    if not result:
        raise ValueError(f"Could not parse any element from formula '{formula}'.")

    return result


def hill_formula(composition: dict[str, int]) -> str:
    """
    Format an elemental composition dict as a Hill-notation formula string.

    Hill order: C first, H second, remaining elements alphabetically.

    Parameters
    ----------
    composition : dict[str, int]
        e.g. {'O': 1, 'H': 7, 'C': 3, 'N': 1}

    Returns
    -------
    str
        e.g. 'C3H7NO'
    """
    parts: list[str] = []

    if "C" in composition and composition["C"] > 0:
        n = composition["C"]
        parts.append("C" if n == 1 else f"C{n}")

    if "H" in composition and composition["H"] > 0:
        n = composition["H"]
        parts.append("H" if n == 1 else f"H{n}")

    for el in sorted(composition.keys()):
        if el in ("C", "H"):
            continue
        n = composition[el]
        if n > 0:
            parts.append(el if n == 1 else f"{el}{n}")

    return "".join(parts)
