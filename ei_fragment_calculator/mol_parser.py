"""
mol_parser.py
=============
Minimal MDL MOL block parser to extract structural information
(atom count, bond count, ring count) from SDF records without
requiring RDKit or any third-party chemistry library.

Only the V2000 COUNTS line and bond table are read.

Reference
---------
MDL MOL file format specification:
  Accelrys (2011) CTfile Formats.
  https://www.daylight.com/meetings/mug05/Ertl/mug05_ertl.pdf

Euler's formula for planar graphs (ring count derivation):
  https://mathworld.wolfram.com/EulerFormula.html
"""

import re
from dataclasses import dataclass
from typing import Optional


# Standard valences for common elements in organic chemistry
ELEMENT_VALENCES = {
    "H": [1],
    "C": [4],
    "N": [3, 5],
    "O": [2],
    "S": [2, 4, 6],
    "P": [3, 5],
    "F": [1],
    "Cl": [1],
    "Br": [1],
    "I": [1],
    "B": [3],
    "Si": [4],
}


def get_valence(element: str) -> int:
    """
    Get the primary (most common) valence for an element.
    For nitrogen and sulfur, returns the neutral valence (3 and 2, respectively).
    """
    valences = ELEMENT_VALENCES.get(element, [])
    return valences[0] if valences else 4  # Default to 4 if unknown


def calculate_implicit_hydrogens(atom: dict, degree: int) -> int:
    """
    Calculate the number of implicit hydrogens for an atom.

    Parameters
    ----------
    atom : dict       Atom dict with "element" and optional "charge"
    degree : int      Sum of bond orders from explicit bonds

    Returns
    -------
    int  Number of implicit hydrogens
    """
    element = atom.get("element", "C")
    charge = atom.get("charge", 0)

    valence = get_valence(element)

    # Adjust valence for charged species
    # Positive charge reduces hydrogen count, negative charge increases it
    adjusted_valence = valence - charge

    # Implicit hydrogens = remaining valence after accounting for bonds
    # degree = sum of bond orders (single=1, double=2, triple=3)
    implicit_h = max(0, adjusted_valence - degree)

    return implicit_h


@dataclass
class MolInfo:
    """
    Structural summary extracted from an MDL MOL block.

    Attributes
    ----------
    atom_count          : int   Number of heavy atoms.
    bond_count          : int   Number of bonds.
    ring_count          : int   Minimum rings via Euler formula: bonds-atoms+1.
    aromatic_bond_count : int   Number of bonds with bond type 4 (aromatic).
    has_aromatic        : bool  True if any aromatic bonds are present.
    parse_ok            : bool  True if parsed without errors.
    error               : str   Error message if parse_ok is False.
    """
    atom_count          : int  = 0
    bond_count          : int  = 0
    ring_count          : int  = 0
    aromatic_bond_count : int  = 0
    has_aromatic        : bool = False
    parse_ok            : bool = False
    error               : str  = ""


def parse_mol_block(mol_text: str) -> MolInfo:
    """
    Parse the MDL MOL (V2000) block of an SDF record.

    Ring count is estimated using Euler's formula for connected graphs:
        rings = bond_count - atom_count + 1

    Parameters
    ----------
    mol_text : str  Raw text of the MOL block.

    Returns
    -------
    MolInfo  Parsed structural summary.
    """
    info  = MolInfo()
    lines = mol_text.strip().splitlines()

    if len(lines) < 4:
        info.error = "MOL block too short ({} lines)".format(len(lines))
        return info

    counts_line  = lines[3]
    counts_match = re.match(r"^\s*(\d+)\s+(\d+)", counts_line)
    if not counts_match:
        info.error = "Cannot parse COUNTS line: {!r}".format(counts_line[:40])
        return info

    atom_count = int(counts_match.group(1))
    bond_count = int(counts_match.group(2))

    bond_start     = 4 + atom_count
    bond_end       = bond_start + bond_count
    aromatic_bonds = 0

    for i in range(bond_start, min(bond_end, len(lines))):
        bond_line  = lines[i]
        bond_match = re.match(r"^\s*(\d+)\s+(\d+)\s+(\d+)", bond_line)
        if bond_match:
            bond_type = int(bond_match.group(3))
            if bond_type == 4:
                aromatic_bonds += 1

    ring_count = max(0, bond_count - atom_count + 1)

    info.atom_count          = atom_count
    info.bond_count          = bond_count
    info.ring_count          = ring_count
    info.aromatic_bond_count = aromatic_bonds
    info.has_aromatic        = aromatic_bonds > 0
    info.parse_ok            = True
    return info


def parse_mol_block_full(mol_block: str) -> Optional[dict]:
    """
    Parse a V2000 MDL MOL block into a full atom + bond connectivity graph.

    Returns ``None`` for 'No Structure' blocks (atom_count == 0) or on parse
    failure.  When successful, returns::

        {
          "atoms":     [{"element": "C", "charge": 0}, ...],   # 0-indexed
          "bonds":     [{"a1": 0, "a2": 1, "type": 1}, ...],   # 0-indexed
          "adjacency": {0: [1, 2], 1: [0, 3], ...},
          "ring_count": int,
        }

    Bond types follow the V2000 convention:
        1 = single, 2 = double, 3 = triple, 4 = aromatic.

    Parameters
    ----------
    mol_block : str  Raw MDL MOL block text.

    Returns
    -------
    dict | None
    """
    lines = mol_block.strip().splitlines()
    if len(lines) < 4:
        return None

    counts_match = re.match(r"^\s*(\d+)\s+(\d+)", lines[3])
    if not counts_match:
        return None

    atom_count = int(counts_match.group(1))
    bond_count = int(counts_match.group(2))

    if atom_count == 0:
        return None   # 'No Structure' block

    # ── Atom table ────────────────────────────────────────────────────────
    atom_pattern = re.compile(
        r"^\s*-?\d+\.\d+\s+-?\d+\.\d+\s+-?\d+\.\d+\s+"
        r"([A-Za-z][a-z]?[a-z]?)"     # element symbol (1-3 chars)
        r"(?:\s+(-?\d+))?",            # optional mass-difference (ignored)
    )
    charge_map = {
        1: +3, 2: +2, 3: +1, 4: 0, 5: -1, 6: -2, 7: -3,
    }

    atoms: list[dict] = []
    for i in range(4, 4 + atom_count):
        if i >= len(lines):
            break
        m = atom_pattern.match(lines[i])
        if m:
            # charge is the 6th token on the atom line (0-based index 5 after 3 coords)
            parts = lines[i].split()
            charge = 0
            if len(parts) >= 6:
                try:
                    raw_charge = int(parts[5])
                    charge = charge_map.get(raw_charge, 0)
                except ValueError:
                    pass
            atoms.append({"element": m.group(1), "charge": charge})

    # ── Bond table ────────────────────────────────────────────────────────
    bond_pattern = re.compile(r"^\s*(\d+)\s+(\d+)\s+(\d+)")
    bonds: list[dict] = []
    adjacency: dict[int, list] = {i: [] for i in range(len(atoms))}

    bond_start = 4 + atom_count
    for i in range(bond_start, bond_start + bond_count):
        if i >= len(lines):
            break
        m = bond_pattern.match(lines[i])
        if m:
            a1 = int(m.group(1)) - 1   # V2000 is 1-indexed → 0-indexed
            a2 = int(m.group(2)) - 1
            btype = int(m.group(3))
            if 0 <= a1 < len(atoms) and 0 <= a2 < len(atoms):
                bonds.append({"a1": a1, "a2": a2, "type": btype})
                adjacency[a1].append(a2)
                adjacency[a2].append(a1)

    ring_count = max(0, len(bonds) - len(atoms) + 1)

    # ── Calculate implicit hydrogens and molecular composition ──────────────
    # Build degree (bond count) for each atom
    degree = [0] * len(atoms)
    for bond in bonds:
        a1 = bond["a1"]
        a2 = bond["a2"]
        bond_type = bond["type"]
        # Each bond contributes its type to the degree (single=1, double=2, etc.)
        degree[a1] += bond_type
        degree[a2] += bond_type

    # Add implicit hydrogens to atoms and build composition
    composition = {}
    for i, atom in enumerate(atoms):
        element = atom["element"]
        implicit_h = calculate_implicit_hydrogens(atom, degree[i])
        atom["implicit_h"] = implicit_h

        # Add to composition
        composition[element] = composition.get(element, 0) + 1
        if implicit_h > 0:
            composition["H"] = composition.get("H", 0) + implicit_h

    return {
        "atoms":        atoms,
        "bonds":        bonds,
        "adjacency":    adjacency,
        "ring_count":   ring_count,
        "composition":  composition,  # Molecular formula as dict
    }


def extract_mol_block(raw_record_text: str) -> Optional[str]:
    """
    Extract the MOL block from a raw SDF record string.

    Reads everything from the start up to the first ``> <FIELDNAME>``
    data field header or the ``M  END`` terminator line.

    Parameters
    ----------
    raw_record_text : str  One complete SDF record (without ``$$$$``).

    Returns
    -------
    str | None  The MOL block text, or None if not found.
    """
    lines     = raw_record_text.splitlines()
    mol_lines = []
    found_end = False

    for line in lines:
        if re.match(r"^>\s*<", line):
            break
        mol_lines.append(line)
        if line.strip().upper() == "M  END":
            found_end = True
            break

    if not mol_lines or not found_end:
        return None

    return "\n".join(mol_lines)
