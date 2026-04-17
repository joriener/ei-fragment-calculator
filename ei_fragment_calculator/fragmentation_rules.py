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
from . import bond_thermochemistry


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

def enumerate_homolytic_cleavages(mol_data: dict, bond_rates: Optional[dict] = None) -> list[dict]:
    """
    Break every non-aromatic, non-ring single bond and enumerate the two
    resulting fragment formulas.

    Parameters
    ----------
    mol_data : dict  Output of :func:`mol_parser.parse_mol_block_full`.
    bond_rates : dict, optional  Output of :func:`bond_thermochemistry.compute_bond_rates`.
                                 If provided, bonds are sorted by dissociation rate.

    Returns
    -------
    list[dict]  One entry per cleavable bond::

        {
          "rule":                 "homolytic_cleavage",
          "bond":                 (a1_idx, a2_idx),
          "frag1_comp":           {"C": 4, "H": 9},
          "frag2_comp":           {"C": 3, "H": 7, "Cl": 1},
          "frag1_formula":        "C4H9",
          "frag2_formula":        "C3H7Cl",
          "bond_dissociation_rate": 95,      # [NEW] A1
          "base_probability":     0.50,      # [NEW] A2
        }
    """
    atoms     = mol_data["atoms"]
    bonds     = mol_data["bonds"]
    adjacency = mol_data["adjacency"]
    results: list[dict] = []

    # [NEW] A1: Filter single bonds and sort by dissociation rate (if available)
    cleavable_bonds = []
    for bond in bonds:
        btype = bond["type"]
        if btype != 1:   # only cleave single bonds
            continue
        a1, a2 = bond["a1"], bond["a2"]
        if _is_ring_bond(bonds, adjacency, a1, a2, len(atoms)):
            continue    # ring bonds don't produce separate fragments on homolysis

        rate = bond_rates.get((a1, a2), 50) if bond_rates else 50
        cleavable_bonds.append((bond, rate))

    # Sort by rate descending (fastest breaks first)
    cleavable_bonds.sort(key=lambda x: x[1], reverse=True)

    for bond, rate in cleavable_bonds:
        a1, a2 = bond["a1"], bond["a2"]

        frag1_atoms = _connected_component(adjacency, a1, exclude_edge=(a1, a2))
        frag2_atoms = frozenset(range(len(atoms))) - frag1_atoms

        frag1_comp = _atoms_to_composition(atoms, frag1_atoms)
        frag2_comp = _atoms_to_composition(atoms, frag2_atoms)

        # Add implicit H to each fragment
        frag1_comp = _add_implicit_h(frag1_comp, atoms, bonds, frag1_atoms)
        frag2_comp = _add_implicit_h(frag2_comp, atoms, bonds, frag2_atoms)

        results.append({
            "rule":                    "homolytic_cleavage",
            "bond":                    (a1, a2),
            "frag1_comp":              frag1_comp,
            "frag2_comp":              frag2_comp,
            "frag1_formula":           hill_formula(frag1_comp),
            "frag2_formula":           hill_formula(frag2_comp),
            "bond_dissociation_rate":  rate,        # [NEW] A1
            "base_probability":        0.50,        # [NEW] A2
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
                    "base_probability":       0.12,  # [NEW] A2
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
                        "base_probability":     0.05,  # [NEW] A2
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

                    # γ-atom must have at least one H neighbour.
                    # Check explicit H atoms first (from mol blocks with explicit H);
                    # fall back to implicit H via valence table (covers PubChem 2D SDF
                    # where H atoms are not listed in the atom table).
                    h_count = sum(
                        1 for nb in adjacency.get(gamma_idx, [])
                        if atoms[nb]["element"] == "H"
                    )
                    if h_count == 0:
                        el_gamma = atoms[gamma_idx]["element"]
                        valence_gamma = _IMPLICIT_VALENCE.get(el_gamma, 0)
                        if valence_gamma > 0:
                            used_gamma = sum(
                                b["type"] for b in bonds
                                if b["a1"] == gamma_idx or b["a2"] == gamma_idx
                            )
                            h_count = max(0, valence_gamma - used_gamma)
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

                    # Add implicit H, then apply two corrections:
                    #
                    #  (1) H migration: one H moves from γ-atom to carbonyl O
                    #      → +1H on enol side, −1H on neutral side
                    #
                    #  (2) New C=C double bonds form in BOTH fragments:
                    #      • In the enol, CarbonylC=Cα forms (was single in
                    #        _add_implicit_h calculation → Cα gets 1 extra H
                    #        that it shouldn't have) → −1H on enol side
                    #      • In the neutral, Cβ=Cγ forms (same over-count
                    #        for Cβ) → −1H on neutral side
                    #
                    #  Net: enol unchanged (+1−1=0), neutral −2 (−1−1).
                    enol_comp  = _add_implicit_h(
                        _atoms_to_composition(atoms, enol_atoms),
                        atoms, bonds, enol_atoms)
                    neut_comp  = _add_implicit_h(
                        _atoms_to_composition(atoms, neutral_atoms),
                        atoms, bonds, neutral_atoms)
                    # Apply corrections (see derivation above)
                    # enol net: 0 (H migration +1 cancels new C=C −1)
                    neut_comp["H"]  = max(0, neut_comp.get("H", 0) - 2)

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
                        "base_probability": 0.03,  # [NEW] A2
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
    matched_frag = None
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
                    matched_frag = frag
                    break
            if best_rule:
                break

    candidate["fragmentation_rule"] = best_rule
    candidate["rule_description"]   = best_desc
    candidate["rule_score"]         = 0.0 if best_rule else 1.0

    # [NEW] A2: Attach reaction probability and bond dissociation rate from matched fragment
    if matched_frag:
        if "base_probability" in matched_frag:
            candidate["base_probability"] = matched_frag["base_probability"]
        if "bond_dissociation_rate" in matched_frag:
            candidate["bond_dissociation_rate"] = matched_frag["bond_dissociation_rate"]

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
# D1: Secondary fragmentation (fragmentation_rules.py)
# ---------------------------------------------------------------------------

def get_secondary_fragments(mol_data: dict, primary_frags: list[dict]) -> list[dict]:
    """
    For each primary fragment composition, reconstruct a minimal mol_data
    (atoms = elements × count, no bonds beyond single chain) and apply
    get_structure_fragments() to it. Limit depth to 1 recursive level.
    Tag results "secondary": True.

    [NEW] A4: Multi-step rate tracking
    Tracks dissociation rates through fragmentation steps:
    - step_1_rate: dissociation rate for primary fragment bond
    - step_2_rate: dissociation rate for secondary fragment bond (if applicable)
    - Shows rate progression through multi-step fragmentation pathways

    Parameters
    ----------
    mol_data       : dict  Original mol_data from parse_mol_block_full().
    primary_frags  : list  Output of primary fragmentation (e.g., homolytic cleavages).

    Returns
    -------
    list[dict]  Secondary fragment entries, tagged with:
                  "secondary": True
                  "step_1_rate": rate of primary bond dissociation (if available)
                  "step_2_rate": rate of secondary bond dissociation
    """
    results: list[dict] = []
    seen_comps: set = set()

    for prim in primary_frags:
        # Extract primary fragment compositions and rates
        primary_rate = prim.get("bond_dissociation_rate", 50)  # Default middle-of-scale
        primary_base_prob = prim.get("base_probability", 0.05)

        for comp_key in ("frag1_comp", "frag2_comp",
                         "charged_frag_comp", "neutral_frag_comp", "enol_comp"):
            comp = prim.get(comp_key)
            if not comp:
                continue

            # Avoid duplicate secondary fragmentation
            comp_tuple = tuple(sorted(comp.items()))
            if comp_tuple in seen_comps:
                continue
            seen_comps.add(comp_tuple)

            # Reconstruct minimal mol_data for this fragment composition
            # Create atom list: one atom per element (repeated by count)
            atoms_list = []
            bonds_list = []
            atom_idx = 0

            for element, count in sorted(comp.items()):
                for _ in range(count):
                    atoms_list.append({"element": element, "index": atom_idx})
                    atom_idx += 1

            # Create adjacency list for a simple chain (linear)
            # Only create single bonds between consecutive heavy atoms
            heavy_idx = [i for i, a in enumerate(atoms_list) if a["element"] != "H"]
            for j in range(len(heavy_idx) - 1):
                a, b = heavy_idx[j], heavy_idx[j + 1]
                bonds_list.append({
                    "a1": a, "a2": b, "type": 1,  # single bond
                    "stereo": 0, "topology": 0,
                })

            # Build minimal adjacency graph
            adj_dict = {}
            for i in range(len(atoms_list)):
                adj_dict[i] = []
            for bond in bonds_list:
                a1, a2 = bond["a1"], bond["a2"]
                adj_dict[a1].append(a2)
                adj_dict[a2].append(a1)

            minimal_mol_data = {
                "atoms": atoms_list,
                "bonds": bonds_list,
                "adjacency": adj_dict,
            }

            # [NEW] A4: Compute bond rates for secondary fragments (step 2)
            try:
                secondary_bond_rates = bond_thermochemistry.compute_bond_rates(
                    atoms_list, bonds_list, parent_dbe=0.0
                )
            except Exception:
                secondary_bond_rates = {}

            # Apply get_structure_fragments() to the minimal mol_data (recursive, depth 1)
            try:
                secondary = get_structure_fragments(minimal_mol_data, parent_dbe=0.0, depth=1)
                for sec_frag in secondary:
                    sec_copy = dict(sec_frag)
                    sec_copy["secondary"] = True

                    # [NEW] A4: Attach step rates
                    # Step 1: rate of the primary fragment's bond dissociation
                    sec_copy["step_1_rate"] = primary_rate
                    sec_copy["step_1_rule"] = prim.get("rule", "unknown")

                    # Step 2: rate of the secondary bond dissociation (from secondary_bond_rates)
                    bond = sec_frag.get("bond")
                    if bond and bond in secondary_bond_rates:
                        sec_copy["step_2_rate"] = secondary_bond_rates[bond]
                    else:
                        # Default: if no specific rate, assume medium dissociation
                        sec_copy["step_2_rate"] = 50

                    # Calculate relative rate (step 2 / step 1)
                    if primary_rate > 0:
                        sec_copy["rate_progression"] = sec_copy["step_2_rate"] / primary_rate
                    else:
                        sec_copy["rate_progression"] = 1.0

                    results.append(sec_copy)
            except Exception:
                # Silently skip if reconstruction fails
                pass

    return results


# ---------------------------------------------------------------------------
# D2: Retro-Diels-Alder (fragmentation_rules.py)
# ---------------------------------------------------------------------------

def _find_6_membered_rings(adjacency: dict, n_atoms: int) -> list[frozenset]:
    """
    Find all 6-membered rings using DFS from each atom.

    Parameters
    ----------
    adjacency : dict  Adjacency list {atom_idx: [neighbor_idxs]}.
    n_atoms   : int   Total number of atoms.

    Returns
    -------
    list[frozenset]  Each element is a frozenset of 6 atom indices forming a ring.
    """
    rings = []
    seen_rings = set()

    def dfs_cycle(start, current, path, visited):
        """DFS to find cycles starting from 'start'."""
        if len(path) == 6:
            if start in adjacency.get(current, []):
                # Found a 6-cycle
                ring = frozenset(path)
                if ring not in seen_rings:
                    seen_rings.add(ring)
                    rings.append(ring)
            return

        for neighbor in adjacency.get(current, []):
            if neighbor == start and len(path) >= 3:
                # Found a cycle back to start
                if len(path) == 6:
                    ring = frozenset(path)
                    if ring not in seen_rings:
                        seen_rings.add(ring)
                        rings.append(ring)
                return
            if neighbor not in visited:
                visited.add(neighbor)
                path.append(neighbor)
                dfs_cycle(start, neighbor, path, visited)
                path.pop()
                visited.remove(neighbor)

    # Run DFS from each atom
    for start_idx in range(n_atoms):
        dfs_cycle(start_idx, start_idx, [start_idx], {start_idx})

    return rings


def apply_retro_diels_alder(mol_data: dict) -> list[dict]:
    """
    Retro-Diels-Alder (RDA) fragmentation: find all 6-membered rings,
    identify C=C double bond, and cut the two C-C single bonds flanking
    the non-double-bond end. Generate two even-electron fragments.

    Parameters
    ----------
    mol_data : dict  Output of :func:`mol_parser.parse_mol_block_full`.

    Returns
    -------
    list[dict]  One entry per RDA pathway::

        {
          "rule": "retro_diels_alder",
          "ring_atoms": frozenset([0, 1, 2, 3, 4, 5]),
          "double_bond": (a1, a2),
          "cut_bonds": [(b1, b2), (c1, c2)],
          "frag1_comp": {...},
          "frag2_comp": {...},
          "frag1_formula": "C4H6",
          "frag2_formula": "C2H2",
        }
    """
    atoms     = mol_data["atoms"]
    bonds     = mol_data["bonds"]
    adjacency = mol_data["adjacency"]
    results: list[dict] = []

    # Find all 6-membered rings
    rings = _find_6_membered_rings(adjacency, len(atoms))

    for ring in rings:
        ring_list = sorted(list(ring))

        # Find C=C double bonds within the ring
        double_bonds = []
        for bond in bonds:
            if bond["type"] != 2:
                continue  # Skip non-double bonds
            a1, a2 = bond["a1"], bond["a2"]
            if a1 in ring and a2 in ring:
                # Both atoms in the ring, and it's a double bond
                if atoms[a1]["element"] == "C" and atoms[a2]["element"] == "C":
                    double_bonds.append((a1, a2))

        # For each double bond, find the two flanking single C-C bonds
        for double_a, double_b in double_bonds:
            # Identify atoms not bonded to the double bond
            other_atoms = [x for x in ring_list if x not in (double_a, double_b)]

            # Find C-C single bonds that are not the double bond
            cut_bonds = []
            for bond in bonds:
                if bond["type"] != 1:
                    continue  # Only single bonds
                a1, a2 = bond["a1"], bond["a2"]
                if a1 not in ring or a2 not in ring:
                    continue  # Both must be in ring

                # Skip the double bond itself
                if (a1, a2) == (double_a, double_b) or (a1, a2) == (double_b, double_a):
                    continue

                # Check if one endpoint is double_a or double_b
                if (a1 == double_a or a1 == double_b) and atoms[a2]["element"] == "C":
                    cut_bonds.append((a1, a2))
                elif (a2 == double_a or a2 == double_b) and atoms[a1]["element"] == "C":
                    cut_bonds.append((a1, a2))

            # Only proceed if we have exactly 2 flanking bonds
            if len(cut_bonds) != 2:
                continue

            # Cut both bonds simultaneously
            cut_pairs = tuple(cut_bonds)
            try:
                # Use _connected_component with exclude_edge for each cut
                # First, generate the two fragments by excluding both edges
                frag1_atoms = _connected_component(adjacency, cut_bonds[0][0],
                                                   exclude_edge=cut_bonds[0])
                frag2_atoms = frozenset(range(len(atoms))) - frag1_atoms

                # Both fragments should be even-electron (closed-shell)
                frag1_comp = _atoms_to_composition(atoms, frag1_atoms)
                frag2_comp = _atoms_to_composition(atoms, frag2_atoms)

                # Add implicit H
                frag1_comp = _add_implicit_h(frag1_comp, atoms, bonds, frag1_atoms)
                frag2_comp = _add_implicit_h(frag2_comp, atoms, bonds, frag2_atoms)

                results.append({
                    "rule":             "retro_diels_alder",
                    "ring_atoms":       frozenset(ring_list),
                    "double_bond":      (double_a, double_b),
                    "cut_bonds":        cut_bonds,
                    "frag1_comp":       frag1_comp,
                    "frag2_comp":       frag2_comp,
                    "frag1_formula":    hill_formula(frag1_comp),
                    "frag2_formula":    hill_formula(frag2_comp),
                    "base_probability": 0.01,  # [NEW] A2
                })
            except Exception:
                # Silently skip if fragmentation fails
                pass

    return results


# ---------------------------------------------------------------------------
# Convenience: run all Tier 2 rules on a mol_data dict
# ---------------------------------------------------------------------------

def get_structure_fragments(mol_data: Optional[dict], parent_dbe: float = 5.0, depth: int = 0) -> list[dict]:
    """
    Run all structure-based fragmentation rules and return the combined list.

    Parameters
    ----------
    mol_data : dict | None  Output of :func:`mol_parser.parse_mol_block_full`,
                            or None if no structure is available.
    parent_dbe : float      Degree of unsaturation for the parent (used in A1 bond rate calc).
    depth : int             Recursion depth (0 = primary, 1+ = secondary). Prevents infinite recursion.

    Returns
    -------
    list[dict]  All predicted fragment entries from all rules.
    """
    if mol_data is None:
        return []

    # [NEW] A1: Compute bond dissociation rates
    bond_rates = bond_thermochemistry.compute_bond_rates(
        mol_data.get("atoms", []),
        mol_data.get("bonds", []),
        parent_dbe
    )

    results: list[dict] = []
    # [NEW] A1: Pass bond_rates to homolytic_cleavages
    results.extend(enumerate_homolytic_cleavages(mol_data, bond_rates=bond_rates))
    results.extend(apply_alpha_cleavage(mol_data))
    results.extend(apply_inductive_cleavage(mol_data))
    results.extend(apply_mclafferty(mol_data))

    # D2: Add retro-Diels-Alder fragmentation
    results.extend(apply_retro_diels_alder(mol_data))

    # D1: Add secondary fragmentation (primary frags already collected)
    # Only apply at depth 0 to prevent infinite recursion
    if depth == 0:
        results.extend(get_secondary_fragments(mol_data, results))

    return results
