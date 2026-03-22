"""
ei_fragment_calculator
======================
Python package for calculating possible exact masses for every peak in an
EI (electron ionisation) unit-mass spectrum, constrained by the molecular
formula of the intact compound.

Quick start
-----------
>>> from ei_fragment_calculator import find_fragment_candidates, parse_formula
>>> parent = parse_formula("C8H8O")
>>> candidates = find_fragment_candidates(105, parent, electron_mode="remove", include_isotope_pattern=True)
>>> for c in candidates:
...     print(c["formula"], c["ion_mass"], c["dbe"], c["isotope_summary"])
"""

from .preflight  import run_preflight_checks
from .formula    import parse_formula, hill_formula
from .calculator import exact_mass, ion_mass, calculate_dbe, find_fragment_candidates
from .isotope    import isotope_pattern, pattern_summary
from .sdf_parser import parse_sdf, parse_peaks, find_field
from .constants  import ELECTRON_MASS, MONOISOTOPIC_MASSES, ISOTOPE_DATA

__version__ = "1.2.0"
__author__  = "Your Name"
__license__ = "MIT"

__all__ = [
    "parse_formula",
    "hill_formula",
    "exact_mass",
    "ion_mass",
    "calculate_dbe",
    "find_fragment_candidates",
    "isotope_pattern",
    "pattern_summary",
    "parse_sdf",
    "parse_peaks",
    "find_field",
    "run_preflight_checks",
    "ELECTRON_MASS",
    "MONOISOTOPIC_MASSES",
    "ISOTOPE_DATA",
]
