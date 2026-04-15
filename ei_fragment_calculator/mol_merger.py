"""
mol_merger.py
=============
Copy mol_blocks from a structure-only record list (e.g. SDF) into a
spectral record list (e.g. MSP/MSPEC) by compound name matching.

Matching strategy (in priority order)
--------------------------------------
1. Exact string match
2. Case-insensitive match
3. Fuzzy Levenshtein match if normalised edit distance < 0.15

All matching is done on *normalised* names (lowercase, whitespace collapsed,
punctuation stripped) to maximise recall across typical NIST name variants.

No third-party dependencies — the Levenshtein distance is computed in
pure Python.
"""

from __future__ import annotations

import re


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def merge_mol_blocks(
    primary_records: list[dict],
    structure_records: list[dict],
) -> list[dict]:
    """
    Return a new list of records that mirrors *primary_records* but with
    ``mol_block`` filled where a name match is found in *structure_records*.

    Parameters
    ----------
    primary_records   : Records lacking (or having empty) mol_blocks, e.g. from MSP.
    structure_records : Records with mol_blocks, e.g. from SDF.

    Returns
    -------
    list[dict]  New record dicts (copies); *primary_records* is not mutated.
                Records without a match retain their original (possibly empty)
                mol_block unchanged.
    """
    # Build lookup tables from structure_records
    exact_map:   dict[str, str] = {}   # exact_name  → mol_block
    normal_map:  dict[str, str] = {}   # normalised  → mol_block
    struct_norms: list[tuple[str, str]] = []  # (normalised, mol_block)

    for rec in structure_records:
        name = rec.get("name", "")
        mol  = rec.get("mol_block", "")
        if not mol:
            continue
        exact_map[name] = mol
        norm = _normalise_name(name)
        normal_map[norm] = mol
        struct_norms.append((norm, mol))

    result: list[dict] = []
    for rec in primary_records:
        rec_copy = dict(rec)
        rec_copy["fields"] = dict(rec.get("fields", {}))

        name = rec.get("name", "")
        existing_mol = rec.get("mol_block", "")

        if existing_mol and existing_mol.strip():
            # Already has a structure — keep it
            result.append(rec_copy)
            continue

        # Strategy 1: exact match
        mol = exact_map.get(name)
        if mol:
            rec_copy["mol_block"] = mol
            result.append(rec_copy)
            continue

        # Strategy 2: case-insensitive (normalised) match
        norm = _normalise_name(name)
        mol = normal_map.get(norm)
        if mol:
            rec_copy["mol_block"] = mol
            result.append(rec_copy)
            continue

        # Strategy 3: fuzzy Levenshtein (threshold 0.15)
        best_mol, best_dist = None, 1.0
        for (struct_norm, struct_mol) in struct_norms:
            dist = _levenshtein_ratio(norm, struct_norm)
            if dist < best_dist:
                best_dist = dist
                best_mol = struct_mol
        if best_dist < 0.15 and best_mol is not None:
            rec_copy["mol_block"] = best_mol
        result.append(rec_copy)

    return result


def match_summary(
    primary_records: list[dict],
    structure_records: list[dict],
) -> list[tuple[str, str, str]]:
    """
    Return a list of (primary_name, matched_name_or_empty, strategy) tuples
    for reporting which records were matched and how.

    Useful for ``--merge-structures`` verbose output.
    """
    exact_map:   dict[str, str] = {}
    normal_map:  dict[str, tuple[str, str]] = {}   # norm → (orig_name, mol)
    struct_norms: list[tuple[str, str, str]] = []  # (norm, orig_name, mol)

    for rec in structure_records:
        name = rec.get("name", "")
        mol  = rec.get("mol_block", "")
        if not mol:
            continue
        exact_map[name] = name
        norm = _normalise_name(name)
        normal_map[norm] = (name, mol)
        struct_norms.append((norm, name, mol))

    summary: list[tuple[str, str, str]] = []
    for rec in primary_records:
        name = rec.get("name", "")
        existing_mol = rec.get("mol_block", "")
        if existing_mol and existing_mol.strip():
            summary.append((name, name, "existing"))
            continue
        if name in exact_map:
            summary.append((name, name, "exact"))
            continue
        norm = _normalise_name(name)
        if norm in normal_map:
            matched, _ = normal_map[norm]
            summary.append((name, matched, "normalised"))
            continue
        best_name, best_dist = "", 1.0
        for (snorm, sname, _mol) in struct_norms:
            d = _levenshtein_ratio(norm, snorm)
            if d < best_dist:
                best_dist = d
                best_name = sname
        if best_dist < 0.15:
            summary.append((name, best_name, "fuzzy({:.0%})".format(1 - best_dist)))
        else:
            summary.append((name, "", "no_match"))
    return summary


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalise_name(name: str) -> str:
    """
    Return a canonical lowercase version of *name* for comparison.

    Strips: brackets, ±/+/- signs, asterisks, extra whitespace.
    Collapses internal whitespace to single spaces.
    """
    n = name.lower().strip()
    n = re.sub(r"[()±\[\]\{\}\*]", "", n)
    n = re.sub(r"[\s\-_]+", " ", n)
    n = re.sub(r"[+/,;]", " ", n)
    return n.strip()


def _levenshtein_ratio(a: str, b: str) -> float:
    """
    Return the normalised Levenshtein edit distance in [0.0, 1.0].

    0.0  = identical strings
    1.0  = completely different (max edits)

    Uses an O(min(len_a, len_b)) space iterative DP algorithm.
    """
    if a == b:
        return 0.0
    la, lb = len(a), len(b)
    if la == 0 or lb == 0:
        return 1.0

    # Ensure a is the shorter string for space optimisation
    if la > lb:
        a, b = b, a
        la, lb = lb, la

    prev = list(range(la + 1))
    for j in range(1, lb + 1):
        curr = [j] + [0] * la
        for i in range(1, la + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[i] = min(
                curr[i - 1] + 1,      # insertion
                prev[i] + 1,          # deletion
                prev[i - 1] + cost,   # substitution
            )
        prev = curr

    return prev[la] / max(la, lb)
