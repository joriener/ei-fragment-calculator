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
