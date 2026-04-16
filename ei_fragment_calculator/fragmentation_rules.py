"""
fragmentation_rules.py
======================
Two-tier EI fragmentation rule engine.

Tier 1 — Formula-based (always available, no 2-D structure needed)
    Checks whether a peak m/z can be explained by a common EI neutral loss
    from the molecular ion.  Requires only the molecular formula.

Tier 2 — Structure-based (requires a parsed V2000 MOL block)
    Enumerates actual bond cleavages (homolytic, α-cleavage, inductive
    cleavage) from the 2-D connectivity graph produced by
    :func:`mol_parser.parse_mol_block_full`.

Integration
-----------
Call :func:`annotate_candidate` to attach fragmentation-rule information to
any candidate dict returned by :func:`find_fragment_candidates`.  Candidates
that match a known EI pathway receive a ``fragmentation_rule`` key and a
lower ``rule_score`` (lower = better, same convention as ``isotope_score``).

References
----------
McLafferty & Turecek (1993) Interpretation of Mass Spectra, 4th ed.
Gross J.H. (2017) Mass Spectrometry: A Textbook, 3rd ed.
Budzikiewicz H. & Grigsby R.D. (2006) J. Am. Soc. Mass Spectrom. 17:1161.
"""

import math
from collections import deque
from typing import Optional

from .constants import MONOISOTOPIC_MASSES, ELECTRON_MASS
from .formula import hill_formula


# ---------------------------------------------------------------------------
# Tier 1 — Neutral-loss table
# ---------------------------------------------------------------------------

#: Common EI neutral losses.
#:
#: Format: ``name → (exact_neutral_loss_mass_Da, composition_dict, description)``
#: Masses are monoisotopic exact masses (Da).
NEUTRAL_LOSSES: dict[str, tuple[float, dict, str]] = {
    # Small inorganic / heteroatom losses
    "H2O":   (18.010565, {"H": 2, "O": 1},       "Water loss — alcohols, acids, sugars"),
    "CO":    (27.994915, {"C": 1, "O": 1},        "CO loss — carbonyl, aromatic C=O"),
    "CO2":   (43.989829, {"C": 1, "O": 2},        "CO2 loss — carboxylic acids, esters"),
    "NH3":   (17.026549, {"N": 1, "H": 3},        "NH3 loss — amines, amides"),
    "HCN":   (27.010899, {"H": 1, "C": 1, "N": 1}, "HCN loss — aromatic N, nitriles"),
    "HCl":   (35.976678, {"H": 1, "Cl": 1},       "HCl loss — organochlorines (pesticides)"),
    "HBr":   (79.926160, {"H": 1, "Br": 1},       "HBr loss — organobromines"),
    "HF":    (20.006228, {"H": 1, "F": 1},        "HF loss — organofluorines"),
    "SO2":   (63.961901, {"S": 1, "O": 2},        "SO2 loss — sulfones, sulfoxides"),
    "H2S":   (33.987721, {"H": 2, "S": 1},        "H2S loss — thiols, thioethers"),
    "NO":    (29.997989, {"N": 1, "O": 1},        "NO loss — nitrosyl, nitrite esters"),
    "NO2":   (45.992903, {"N": 1, "O": 2},        "NO2 radical loss — nitro compounds"),
    "SO3":   (79.956815, {"S": 1, "O": 3},        "SO3 loss — sulfonic acids"),
    "COS":   (59.966986, {"C": 1, "O": 1, "S": 1}, "COS loss — thiocarbamates"),
    # Hydrocarbon / alkyl radical losses
    "CH3":   (15.023475, {"C": 1, "H": 3},        "Methyl radical loss (alpha-cleavage)"),
    "C2H5":  (29.039125, {"C": 2, "H": 5},        "Ethyl radical loss"),
    "C3H7":  (43.054775, {"C": 3, "H": 7},        "Propyl radical loss"),
    "C4H9":  (57.070425, {"C": 4, "H": 9},        "Butyl radical loss"),
    # Small molecule losses
    "CH2O":  (30.010565, {"C": 1, "H": 2, "O": 1}, "Formaldehyde loss — methyl ethers"),
    "C2H2":  (26.015650, {"C": 2, "H": 2},        "Acetylene loss — aromatic rings"),
    "C2H4":  (28.031300, {"C": 2, "H": 4},        "Ethylene loss — alkyl chains"),
    "C3H6":  (42.046950, {"C": 3, "H": 6},        "Propylene/cyclopropane loss"),
    "C4H8":  (56.062600, {"C": 4, "H": 8},        "Butylene/isobutylene loss"),
    # Halogen + heteroatom combinations (common in pesticides)
    "Cl":    (34.968853, {"Cl": 1},               "Chlorine radical loss"),
    "Br":    (78.918338, {"Br": 1},               "Bromine radical loss"),
    "CH2Cl": (48.985528, {"C": 1, "H": 2, "Cl": 1}, "CH2Cl radical loss"),
    "CHCl2": (82.946453, {"C": 1, "H": 1, "Cl": 2}, "CHCl2 radical loss"),
    "CCl3":  (116.907378, {"C": 1, "Cl": 3},     "CCl3 radical loss — chloroalkanes"),
    "CF3":   (68.994934, {"C": 1, "F": 3},        "CF3 radical loss — fluoroalkanes"),
    # Phosphorus (common in organophosphate pesticides)
    "PO3H":  (79.966331, {"P": 1, "O": 3, "H": 1}, "PO3H loss — phosphates"),
    "H3PO4": (97.976895, {"H": 3, "P": 1, "O": 4}, "H3PO4 loss — phosphate esters"),
    "OPCl":  (98.936978, {"O": 1, "P": 1, "Cl": 1}, "OPCl loss — chlorophosphates"),
    # Silicon (common in GC-MS with TMS derivatisation)
    "Si(CH3)3": (73.046928, {"Si": 1, "C": 3, "H": 9}, "TMS group loss — derivatised GC-MS"),
}

# Heteroatoms that direct alpha-cleavage
_ALPHA_HETEROATOMS = {"N", "O", "S", "F", "Cl", "Br", "I", "P"}

# Standard valence for implicit H calculation
_IMPLICIT_VALENCE = {
    "C": 4, "N": 3, "O": 2, "S": 2, "P": 5,
    "F": 1, "Cl": 1, "Br": 1, "I": 1, "Si": 4,
}


def _add_implicit_h(comp: dict, atoms: list, bonds: list,
                    frag_indices: frozenset) -> dict:
    """
    Adjust a fragment composition to include implicit hydrogens.

    For each atom in the fragment, compute valence used by bonds within
    the fragment, then add implicit H to satisfy standard valence.

    Parameters
    ----------
    comp : dict  Current composition (may or may not have H already).
    atoms : list  Atom list from mol_data.
    bonds : list  Bond list from mol_data.
    frag_indices : frozenset  Indices of atoms in this fragment.

    Returns
    -------
    dict  Updated composition with implicit H added.
    """
    h_count = 0
    for idx in frag_indices:
        el = atoms[idx]["element"]
        valence = _IMPLICIT_VALENCE.get(el, 0)
        if valence == 0:
            continue  # Unknown element, skip
        # Sum bond orders for bonds within the fragment
        used_valence = sum(b["type"] for b in bonds
                           if (b["a1"] == idx and b["a2"] in frag_indices) or
                              (b["a2"] == idx and b["a1"] in frag_indices))
        h_count += max(0, valence - used_valence)

    result = dict(comp)
    if h_count:
        result["H"] = result.get("H", 0) + h_count
    return result


# ---------------------------------------------------------------------------
# Tier 1 helpers
# ---------------------------------------------------------------------------

def _composition_contains(parent: dict, loss: dict) -> bool:
    """Return True if parent composition has ≥ loss atoms for every element."""
    return all(parent.get(el, 0) >= cnt for el, cnt in loss.items())


def _subtract_composition(parent: dict, loss: dict) -> dict:
    """Return parent − loss as a dict (only elements with count > 0)."""
    result: dict = {}
    for el, cnt in parent.items():
        new_cnt = cnt - loss.get(el, 0)
        if new_cnt > 0:
            result[el] = new_cnt
    return result


def annotate_neutral_losses(
    mz: int,
    parent_neutral_mass: float,
    parent_composition: dict,
    electron_mode: str,
    tolerance: float,
) -> list[dict]:
    """
    Check whether *mz* could result from a common neutral loss from the
    molecular ion.

    For each entry in :data:`NEUTRAL_LOSSES`, the expected fragment ion mass
    is computed as::

        fragment_neutral = parent_neutral_mass − loss_mass
        fragment_ion     = fragment_neutral ± m_electron   (per electron_mode)

    A match is reported when ``|fragment_ion − mz| ≤ tolerance`` AND the
    loss formula is a valid elemental subset of the parent composition.

    Parameters
    ----------
    mz                  : int    Nominal unit-mass m/z of the observed peak.
    parent_neutral_mass : float  Neutral monoisotopic mass of the intact molecule.
    parent_composition  : dict   Elemental composition of the intact molecule.
    electron_mode       : str    ``"remove"`` | ``"add"`` | ``"none"``
    tolerance           : float  Mass window in Da.

    Returns
    -------
    list[dict]  One entry per matched neutral loss::

        {
          "rule":                 "neutral_loss",
          "rule_name":            "[M-H2O]",
          "description":          "Water loss — alcohols, acids, sugars",
          "loss_formula":         "H2O",
          "loss_mass":            18.010565,
          "expected_ion_mass":    105.034,
          "delta":                -0.002,
          "fragment_composition": {"C": 6, "H": 6, "O": 0, ...},
        }
    """
    matches: list[dict] = []

    for loss_name, (loss_mass, loss_comp, description) in NEUTRAL_LOSSES.items():
        # Parent must contain all atoms of this loss
        if not _composition_contains(parent_composition, loss_comp):
            continue

        fragment_neutral = parent_neutral_mass - loss_mass
        if fragment_neutral <= 0.0:
            continue

        if electron_mode == "remove":
            fragment_ion = fragment_neutral - ELECTRON_MASS
        elif electron_mode == "add":
            fragment_ion = fragment_neutral + ELECTRON_MASS
        else:
            fragment_ion = fragment_neutral

        delta = fragment_ion - mz
        if abs(delta) > tolerance:
            continue

        fragment_comp = _subtract_composition(parent_composition, loss_comp)
        matches.append({
            "rule":                 "neutral_loss",
            "rule_name":            "[M-{}]".format(loss_name),
            "description":          description,
            "loss_formula":         loss_name,
            "loss_mass":            loss_mass,
            "expected_ion_mass":    round(fragment_ion, 6),
            "delta":                round(delta, 6),
            "fragment_composition": fragment_comp,
        })

    # Sort by |delta| ascending
    matches.sort(key=lambda x: abs(x["delta"]))
    return matches


# ---------------------------------------------------------------------------
# Tier 2 — Structure-based helpers
# ---------------------------------------------------------------------------

def _connected_component(
    adjacency: dict,
    start: int,
    exclude_edge: Optional[tuple] = None,
) -> frozenset:
    """
    BFS from *start* in the adjacency graph, skipping one directed edge.

    Parameters
    ----------
    adjacency    : dict  Adjacency list {atom_idx: [neighbor_idxs]}.
    start        : int   Starting atom index.
    exclude_edge : tuple (a, b) — both directions (a→b and b→a) are skipped.

    Returns
    -------
    frozenset[int]  Indices of all atoms reachable from *start*.
    """
    ea, eb = (exclude_edge[0], exclude_edge[1]) if exclude_edge else (-1, -2)
    visited: set[int] = set()
    queue: deque = deque([start])
    while queue:
        node = queue.popleft()
        if node in visited:
            continue
        visited.add(node)
        for nb in adjacency.get(node, []):
            if (node == ea and nb == eb) or (node == eb and nb == ea):
                continue
            if nb not in visited:
                queue.append(nb)
    return frozenset(visited)


def _atoms_to_composition(atoms: list, indices) -> dict:
    """Sum element counts for a set of atom indices."""
    comp: dict = {}
    for i in indices:
        el = atoms[i]["element"]
        comp[el] = comp.get(el, 0) + 1
    return comp


def _is_ring_bond(bonds: list, adjacency: dict, a1: int, a2: int,
                  n_atoms: int) -> bool:
    """Return True if bond (a1,a2) is part of a ring (removing it keeps graph connected)."""
    frag = _connected_component(adjacency, a1, exclude_edge=(a1, a2))
    return a2 in frag


# ---------------------------------------------------------------------------
# Tier 2 — Fragmentation rule functions
# ---------------------------------------------------------------------------

def enumerate_homolytic_cleavages(mol_data: dict) -> list[dict]:
    """
    Break every non-aromatic, non-ring single bond and enumerate the two
    resulting fragment formulas.

    Parameters
    ----------
    mol_data : dict  Output of :func:`mol_parser.parse_mol_block_full`.

    Returns
    -------
    list[dict]  One entry per cleavable bond::

        {
          "rule":        "homolytic_cleavage",
          "bond":        (a1_idx, a2_idx),
          "frag1_comp":  {"C": 4, "H": 9},
          "frag2_comp":  {"C": 3, "H": 7, "Cl": 1},
          "frag1_formula": "C4H9",
          "frag2_formula": "C3H7Cl",
        }
    """
    atoms     = mol_data["atoms"]
    bonds     = mol_data["bonds"]
    adjacency = mol_data["adjacency"]
    results: list[dict] = []

    for bond in bonds:
        btype = bond["type"]
        if btype != 1:   # only cleave single bonds
            continue
        a1, a2 = bond["a1"], bond["a2"]
        if _is_ring_bond(bonds, adjacency, a1, a2, len(atoms)):
            continue    # ring bonds don't produce separate fragments on homolysis

        frag1_atoms = _connected_component(adjacency, a1, exclude_edge=(a1, a2))
        frag2_atoms = frozenset(range(len(atoms))) - frag1_atoms

        frag1_comp = _atoms_to_composition(atoms, frag1_atoms)
        frag2_comp = _atoms_to_composition(atoms, frag2_atoms)

        # Add implicit H to each fragment
        frag1_comp = _add_implicit_h(frag1_comp, atoms, bonds, frag1_atoms)
        frag2_comp = _add_implicit_h(frag2_comp, atoms, bonds, frag2_atoms)

        results.append({
            "rule":          "homolytic_cleavage",
            "bond":          (a1, a2),
            "frag1_comp":    frag1_comp,
            "frag2_comp":    frag2_comp,
            "frag1_formula": hill_formula(frag1_comp),
            "frag2_formula": hill_formula(frag2_comp),
        })

    return results


def apply_alpha_cleavage(mol_data: dict) -> list[dict]:
    """
    α-Cleavage: break the C–C (or C–X) bond that is α (one bond away) to a
    heteroatom.  This is the most common EI pathway for amines, ethers,
    ketones, and organohalogens.

    The charge is assumed to remain with the heteroatom-containing fragment.

    Parameters
    ----------
    mol_data : dict  Output of :func:`mol_parser.parse_mol_block_full`.

    Returns
    -------
    list[dict]  One entry per α-cleavage pathway (duplicates removed)::

        {
          "rule":             "alpha_cleavage",
          "heteroatom_idx":   5,
          "heteroatom":       "O",
          "alpha_atom_idx":   4,
          "cleaved_bond":     (4, 7),
          "charged_frag_comp":   {...},  # contains heteroatom
          "neutral_frag_comp":   {...},
          "charged_frag_formula": "C2H5O",
          "neutral_frag_formula": "C4H9",
        }
    """
    atoms     = mol_data["atoms"]
    bonds     = mol_data["bonds"]
    adjacency = mol_data["adjacency"]
    results: list[dict] = []
    seen_bonds: set = set()

    for h_idx, atom in enumerate(atoms):
        if atom["element"] not in _ALPHA_HETEROATOMS:
            continue

        # For each α-atom bonded to this heteroatom
        for alpha_idx in adjacency.get(h_idx, []):
            # For each bond from the α-atom to another atom (not the heteroatom)
            for beta_idx in adjacency.get(alpha_idx, []):
                if beta_idx == h_idx:
                    continue
                # Find the actual bond type
                bond_type = 1
                for b in bonds:
                    if (b["a1"] == alpha_idx and b["a2"] == beta_idx) or \
                       (b["a1"] == beta_idx  and b["a2"] == alpha_idx):
                        bond_type = b["type"]
                        break
                if bond_type != 1:
                    continue  # α-cleavage is a single-bond homolysis
                if _is_ring_bond(bonds, adjacency, alpha_idx, beta_idx, len(atoms)):
                    continue

                bond_key = (min(alpha_idx, beta_idx), max(alpha_idx, beta_idx))
                if bond_key in seen_bonds:
                    continue
                seen_bonds.add(bond_key)

                # Charged fragment: side containing the heteroatom
                frag_h = _connected_component(
                    adjacency, h_idx, exclude_edge=(alpha_idx, beta_idx))
                frag_n = frozenset(range(len(atoms))) - frag_h

                comp_h = _atoms_to_composition(atoms, frag_h)
                comp_n = _atoms_to_composition(atoms, frag_n)

                # Add implicit H to each fragment
                comp_h = _add_implicit_h(comp_h, atoms, bonds, frag_h)
                comp_n = _add_implicit_h(comp_n, atoms, bonds, frag_n)

                results.append({
                    "rule":                   "alpha_cleavage",
                    "heteroatom_idx":         h_idx,
                    "heteroatom":             atom["element"],
                    "alpha_atom_idx":         alpha_idx,
                    "cleaved_bond":           (alpha_idx, beta_idx),
                    "charged_frag_comp":      comp_h,
                    "neutral_frag_comp":      comp_n,
                    "charged_frag_formula":   hill_formula(comp_h),
                    "neutral_frag_formula":   hill_formula(comp_n),
                })

    return results


def apply_inductive_cleavage(mol_data: dict) -> list[dict]:
    """
    Inductive (i-) cleavage: the charge located on a heteroatom induces
    cleavage of the β-bond (the bond one further away from the heteroatom
    than α-cleavage).  Common in ethers, thioethers, and haloalkanes.

    Parameters
    ----------
    mol_data : dict  Output of :func:`mol_parser.parse_mol_block_full`.

    Returns
    -------
    list[dict]  Same structure as :func:`apply_alpha_cleavage`.
    """
    atoms     = mol_data["atoms"]
    bonds     = mol_data["bonds"]
    adjacency = mol_data["adjacency"]
    results: list[dict] = []
    seen_bonds: set = set()

    for h_idx, atom in enumerate(atoms):
        if atom["element"] not in _ALPHA_HETEROATOMS:
            continue
        for alpha_idx in adjacency.get(h_idx, []):
            for beta_idx in adjacency.get(alpha_idx, []):
                if beta_idx == h_idx:
                    continue
                for gamma_idx in adjacency.get(beta_idx, []):
                    if gamma_idx in (h_idx, alpha_idx):
                        continue
                    bond_type = 1
                    for b in bonds:
                        if (b["a1"] == beta_idx  and b["a2"] == gamma_idx) or \
                           (b["a1"] == gamma_idx and b["a2"] == beta_idx):
                            bond_type = b["type"]
                            break
                    if bond_type != 1:
                        continue
                    if _is_ring_bond(bonds, adjacency, beta_idx, gamma_idx, len(atoms)):
                        continue

                    bond_key = (min(beta_idx, gamma_idx), max(beta_idx, gamma_idx))
                    if bond_key in seen_bonds:
                        continue
                    seen_bonds.add(bond_key)

                    frag_h = _connected_component(
                        adjacency, h_idx, exclude_edge=(beta_idx, gamma_idx))
                    frag_n = frozenset(range(len(atoms))) - frag_h

                    comp_h = _atoms_to_composition(atoms, frag_h)
                    comp_n = _atoms_to_composition(atoms, frag_n)

                    # Add implicit H to each fragment
                    comp_h = _add_implicit_h(comp_h, atoms, bonds, frag_h)
                    comp_n = _add_implicit_h(comp_n, atoms, bonds, frag_n)

                    results.append({
                        "rule":                 "inductive_cleavage",
                        "heteroatom_idx":       h_idx,
                        "heteroatom":           atom["element"],
                        "cleaved_bond":         (beta_idx, gamma_idx),
                        "charged_frag_comp":    comp_h,
                        "neutral_frag_comp":    comp_n,
                        "charged_frag_formula": hill_formula(comp_h),
                        "neutral_frag_formula": hill_formula(comp_n),
                    })

    return results


def apply_mclafferty(mol_data: dict) -> list[dict]:
    """
    McLafferty rearrangement: a γ-hydrogen migrates via a 6-membered
    transition state to a C=O group, followed by β-bond cleavage.  Common in
    aldehydes, ketones, esters, and carboxylic acids.

    The search pattern (atom numbering from C=O outward):
        O=C–Cα–Cβ–Cγ–H   (H migrates to O; Cα–Cβ bond cleaves)

    Parameters
    ----------
    mol_data : dict  Output of :func:`mol_parser.parse_mol_block_full`.

    Returns
    -------
    list[dict]::

        {
          "rule":              "mclafferty",
          "carbonyl_C_idx":    3,
          "carbonyl_O_idx":    8,
          "alpha_C_idx":       4,
          "beta_C_idx":        5,
          "gamma_idx":         6,
          "H_count_at_gamma":  2,
          "enol_comp":         {"C": 3, "H": 6, "O": 1},
          "neutral_comp":      {"C": 5, "H": 10},
          "enol_formula":      "C3H6O",
          "neutral_formula":   "C5H10",
        }
    """
    atoms     = mol_data["atoms"]
    bonds     = mol_data["bonds"]
    adjacency = mol_data["adjacency"]
    results: list[dict] = []
    seen: set = set()

    def _bond_type(a, b):
        for bnd in bonds:
            if (bnd["a1"] == a and bnd["a2"] == b) or \
               (bnd["a1"] == b and bnd["a2"] == a):
                return bnd["type"]
        return 0

    # Find all C=O bonds (carbonyl)
    for bnd in bonds:
        if bnd["type"] != 2:
            continue
        a1, a2 = bnd["a1"], bnd["a2"]
        c_idx = o_idx = None
        if atoms[a1]["element"] == "C" and atoms[a2]["element"] == "O":
            c_idx, o_idx = a1, a2
        elif atoms[a1]["element"] == "O" and atoms[a2]["element"] == "C":
            c_idx, o_idx = a2, a1
        if c_idx is None:
            continue

        # Walk: C=O → Cα (bonded to carbonyl C via single bond) →
        #       Cβ (bonded to Cα, single bond) → Cγ (must have H)
        for alpha_idx in adjacency.get(c_idx, []):
            if alpha_idx == o_idx:
                continue
            if _bond_type(c_idx, alpha_idx) != 1:
                continue
            if atoms[alpha_idx]["element"] != "C":
                continue

            for beta_idx in adjacency.get(alpha_idx, []):
                if beta_idx in (c_idx, o_idx):
                    continue
                if _bond_type(alpha_idx, beta_idx) != 1:
                    continue
                if atoms[beta_idx]["element"] != "C":
                    continue

                for gamma_idx in adjacency.get(beta_idx, []):
                    if gamma_idx in (alpha_idx, c_idx):
                        continue
                    if _bond_type(beta_idx, gamma_idx) != 1:
                        continue

                    # γ-atom must have at least one H neighbour
                    h_count = sum(
                        1 for nb in adjacency.get(gamma_idx, [])
                        if atoms[nb]["element"] == "H"
                    )
                    if h_count == 0:
                        continue

                    key = (c_idx, alpha_idx, beta_idx)
                    if key in seen:
                        continue
                    seen.add(key)

                    # Cleavage: α–β bond breaks
                    enol_atoms = _connected_component(
                        adjacency, c_idx, exclude_edge=(alpha_idx, beta_idx))
                    neutral_atoms = frozenset(range(len(atoms))) - enol_atoms

                    # Add implicit H, then adjust for H migration
                    enol_comp  = _add_implicit_h(
                        _atoms_to_composition(atoms, enol_atoms),
                        atoms, bonds, enol_atoms)
                    neut_comp  = _add_implicit_h(
                        _atoms_to_composition(atoms, neutral_atoms),
                        atoms, bonds, neutral_atoms)
                    # One H migrates from γ to O
                    enol_comp["H"]  = enol_comp.get("H", 0) + 1
                    neut_comp["H"]  = max(0, neut_comp.get("H", 0) - 1)

                    results.append({
                        "rule":             "mclafferty",
                        "carbonyl_C_idx":   c_idx,
                        "carbonyl_O_idx":   o_idx,
                        "alpha_C_idx":      alpha_idx,
                        "beta_C_idx":       beta_idx,
                        "gamma_idx":        gamma_idx,
                        "H_count_at_gamma": h_count,
                        "enol_comp":        enol_comp,
                        "neutral_comp":     neut_comp,
                        "enol_formula":     hill_formula(enol_comp),
                        "neutral_formula":  hill_formula(neut_comp),
                    })

    return results


# ---------------------------------------------------------------------------
# Candidate annotation
# ---------------------------------------------------------------------------

def annotate_candidate(
    candidate: dict,
    neutral_loss_matches: list[dict],
    structure_frags: Optional[list[dict]] = None,
    strict_structure: bool = False,
) -> dict:
    """
    Attach fragmentation-rule information to a candidate dict.

    Checks whether the candidate's formula matches any neutral-loss
    annotation or structure-derived fragment formula, and sets:

    - ``fragmentation_rule``: name of the best matching rule, or ``""``
    - ``rule_description``:   human-readable rule description
    - ``rule_score``:         0.0 if matched (bonus), 1.0 if not matched

    Parameters
    ----------
    candidate            : dict   Candidate from :func:`find_fragment_candidates`.
    neutral_loss_matches : list   Output of :func:`annotate_neutral_losses`.
    structure_frags      : list   Combined output of structure-based rule functions
                                  (optional; None if no MOL block available).
    strict_structure     : bool   If True and structure_frags is provided but no match
                                  found, set filter_passed = False. (default: False)

    Returns
    -------
    dict  The same candidate dict, augmented in-place.
    """
    formula = candidate.get("formula", "")
    comp    = candidate.get("_composition", {})

    best_rule = ""
    best_desc = ""

    # Check Tier 1 neutral-loss matches
    for match in neutral_loss_matches:
        # Check if the candidate formula matches the expected fragment composition
        frag_comp = match.get("fragment_composition", {})
        if _compositions_equal(comp, frag_comp):
            best_rule = match["rule_name"]
            best_desc = match["description"]
            break

    # Check Tier 2 structure-derived fragment formulas
    if not best_rule and structure_frags:
        for frag in structure_frags:
            for comp_key in ("frag1_comp", "frag2_comp",
                             "charged_frag_comp", "enol_comp"):
                frag_comp = frag.get(comp_key)
                if frag_comp and _compositions_equal(comp, frag_comp):
                    rule_map = {
                        "homolytic_cleavage": "Homolytic cleavage",
                        "alpha_cleavage":     "α-Cleavage",
                        "inductive_cleavage": "i-Cleavage",
                        "mclafferty":         "McLafferty rearrangement",
                    }
                    best_rule = rule_map.get(frag["rule"], frag["rule"])
                    best_desc = "Bond cleavage — see mol block"
                    break
            if best_rule:
                break

    candidate["fragmentation_rule"] = best_rule
    candidate["rule_description"]   = best_desc
    candidate["rule_score"]         = 0.0 if best_rule else 1.0
    # Hard gate: if strict_structure is on, structure_frags is available, and no match, mark as failed
    if strict_structure and structure_frags and not best_rule:
        candidate["filter_passed"] = False
    return candidate


def _compositions_equal(a: dict, b: dict) -> bool:
    """Return True if two composition dicts represent the same formula."""
    a_clean = {el: cnt for el, cnt in a.items() if cnt > 0}
    b_clean = {el: cnt for el, cnt in b.items() if cnt > 0}
    return a_clean == b_clean


# ---------------------------------------------------------------------------
# Convenience: run all Tier 2 rules on a mol_data dict
# ---------------------------------------------------------------------------

def get_structure_fragments(mol_data: Optional[dict]) -> list[dict]:
    """
    Run all structure-based fragmentation rules and return the combined list.

    Parameters
    ----------
    mol_data : dict | None  Output of :func:`mol_parser.parse_mol_block_full`,
                            or None if no structure is available.

    Returns
    -------
    list[dict]  All predicted fragment entries from all rules.
    """
    if mol_data is None:
        return []

    results: list[dict] = []
    results.extend(enumerate_homolytic_cleavages(mol_data))
    results.extend(apply_alpha_cleavage(mol_data))
    results.extend(apply_inductive_cleavage(mol_data))
    results.extend(apply_mclafferty(mol_data))
    return results
