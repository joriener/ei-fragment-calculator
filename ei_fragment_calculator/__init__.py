"""
ei_fragment_calculator
======================
Python package for calculating possible exact masses for every peak in an
EI (electron ionisation) unit-mass spectrum, constrained by the molecular
formula of the intact compound.

Quick start
-----------
>>> from ei_fragment_calculator import find_fragment_candidates, parse_formula, rank_candidates
>>> parent = parse_formula("C8H8O")
>>> candidates = find_fragment_candidates(105, parent, electron_mode="remove", include_isotope_pattern=True)
>>> ranked = rank_candidates(candidates)   # best candidate first
>>> best = ranked[0]
>>> print(best["formula"], best["ion_mass"], best["dbe"])
"""

from .preflight  import run_preflight_checks
from .formula    import parse_formula, hill_formula
from .calculator import exact_mass, ion_mass, calculate_dbe, find_fragment_candidates
from .isotope    import isotope_pattern, pattern_summary
from .sdf_parser import parse_sdf, parse_peaks, find_field
from .constants  import ELECTRON_MASS, MONOISOTOPIC_MASSES, ISOTOPE_DATA
from .filters    import (FilterConfig, run_all_filters, rank_candidates,
                         apply_nitrogen_rule, apply_hd_check, apply_lewis_senior,
                         score_isotope_match, apply_smiles_constraints)
from .mol_parser import parse_mol_block, extract_mol_block, MolInfo
from .sdf_writer import write_exact_masses_sdf, write_exact_sdf, exact_sdf_path

__version__ = "1.5.0"
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
    "FilterConfig",
    "run_all_filters",
    "rank_candidates",
    "apply_nitrogen_rule",
    "apply_hd_check",
    "apply_lewis_senior",
    "score_isotope_match",
    "apply_smiles_constraints",
    "parse_mol_block",
    "extract_mol_block",
    "MolInfo",
    "write_exact_masses_sdf",
    "write_exact_sdf",
    "exact_sdf_path",
]
