"""
neutral_losses.py
=================
Database of common EI (electron ionisation) neutral losses.

Each entry maps a human-readable name to a tuple of
  (nominal_delta_mass: int, formula_dict: dict[str, int])

The nominal_delta_mass is the integer-rounded mass difference used for
fast peak-pair lookup.  The formula_dict allows the exact elemental
composition check that disambiguates losses with the same nominal mass
(e.g. CO vs C2H4, both nominally 28 Da; HCN vs CHN, both nominally 27 Da).

Multiple entries sharing the same integer delta are intentional — formula
subtraction resolves which neutral is the true match at the cross-check stage.
"""

# --------------------------------------------------------------------------
# Type alias
# --------------------------------------------------------------------------
# Each value: (nominal_Δm: int, {element: count})
NEUTRAL_LOSSES: dict[str, tuple[int, dict[str, int]]] = {

    # ── Single-atom / radical losses ──────────────────────────────────────
    "H":        (1,  {"H": 1}),
    "H2":       (2,  {"H": 2}),
    "C":        (12, {"C": 1}),
    "CH":       (13, {"C": 1, "H": 1}),
    "N":        (14, {"N": 1}),
    "CH2":      (14, {"C": 1, "H": 2}),
    "CH3":      (15, {"C": 1, "H": 3}),
    "O":        (16, {"O": 1}),
    "NH3":      (17, {"N": 1, "H": 3}),
    "OH":       (17, {"O": 1, "H": 1}),
    "H2O":      (18, {"H": 2, "O": 1}),
    "F":        (19, {"F": 1}),
    "HF":       (20, {"H": 1, "F": 1}),
    "Ne":       (20, {}),           # placeholder, not chemically relevant
    "Na":       (23, {"Na": 1}),
    "C2H2":     (26, {"C": 2, "H": 2}),
    "CHN":      (27, {"C": 1, "H": 1, "N": 1}),
    "HCN":      (27, {"H": 1, "C": 1, "N": 1}),  # alias — same composition
    "CO":       (28, {"C": 1, "O": 1}),
    "C2H4":     (28, {"C": 2, "H": 4}),
    "N2":       (28, {"N": 2}),
    "CHO":      (29, {"C": 1, "H": 1, "O": 1}),
    "C2H5":     (29, {"C": 2, "H": 5}),
    "CH2O":     (30, {"C": 1, "H": 2, "O": 1}),
    "NO":       (30, {"N": 1, "O": 1}),
    "CF":       (31, {"C": 1, "F": 1}),
    "CH3O":     (31, {"C": 1, "H": 3, "O": 1}),
    "S":        (32, {"S": 1}),
    "CH4O":     (32, {"C": 1, "H": 4, "O": 1}),   # methanol
    "H2S":      (34, {"H": 2, "S": 1}),
    "Cl":       (35, {"Cl": 1}),
    "HCl":      (36, {"H": 1, "Cl": 1}),
    "C3H2":     (38, {"C": 3, "H": 2}),
    "C3H3":     (39, {"C": 3, "H": 3}),
    "C3H4":     (40, {"C": 3, "H": 4}),
    "C3H5":     (41, {"C": 3, "H": 5}),
    "C3H6":     (42, {"C": 3, "H": 6}),
    "CHNO":     (43, {"C": 1, "H": 1, "N": 1, "O": 1}),
    "C3H7":     (43, {"C": 3, "H": 7}),
    "C2H4O":    (44, {"C": 2, "H": 4, "O": 1}),
    "CO2":      (44, {"C": 1, "O": 2}),
    "CS":       (44, {"C": 1, "S": 1}),
    "C2H5N":    (43, {"C": 2, "H": 5, "N": 1}),
    "OCS":      (60, {"C": 1, "O": 1, "S": 1}),
    "COS":      (60, {"C": 1, "O": 1, "S": 1}),   # alias
    "C4H8":     (56, {"C": 4, "H": 8}),
    "C4H9":     (57, {"C": 4, "H": 9}),
    "SO2":      (64, {"S": 1, "O": 2}),
    "C5H5":     (65, {"C": 5, "H": 5}),
    "C5H8":     (68, {"C": 5, "H": 8}),
    "C5H10":    (70, {"C": 5, "H": 10}),
    "C5H11":    (71, {"C": 5, "H": 11}),
    "HBr":      (80, {"H": 1, "Br": 1}),
    "Br":       (79, {"Br": 1}),
    "C6H6":     (78, {"C": 6, "H": 6}),
    "C6H5":     (77, {"C": 6, "H": 5}),
    "C7H7":     (91, {"C": 7, "H": 7}),
    "C2H5S":    (61, {"C": 2, "H": 5, "S": 1}),
    "C3H7S":    (75, {"C": 3, "H": 7, "S": 1}),
    "C4H9S":    (89, {"C": 4, "H": 9, "S": 1}),

    # ── Common phosphorus-containing losses ────────────────────────────────
    "PO3":      (79, {"P": 1, "O": 3}),
    "HPO3":     (80, {"H": 1, "P": 1, "O": 3}),
    "H3PO4":    (98, {"H": 3, "P": 1, "O": 4}),
    "SPO":      (79, {"S": 1, "P": 1, "O": 1}),    # approximation

    # ── Diethylphosphate / organophosphate characteristic ─────────────────
    "C2H5O":    (45, {"C": 2, "H": 5, "O": 1}),    # ethoxy radical
    "C2H5O2":   (61, {"C": 2, "H": 5, "O": 2}),
    "C4H10O":   (74, {"C": 4, "H": 10, "O": 1}),

    # ── Larger fragments (ring losses, rearrangements) ─────────────────────
    "C6H5O":    (93,  {"C": 6, "H": 5, "O": 1}),    # phenoxy
    "C7H8":     (92,  {"C": 7, "H": 8}),             # toluene
    "C7H7O":    (107, {"C": 7, "H": 7, "O": 1}),
    "C8H10":    (106, {"C": 8, "H": 10}),
    "C6H5Cl":   (112, {"C": 6, "H": 5, "Cl": 1}),   # chlorobenzene loss
    "CCl2":     (82,  {"C": 1, "Cl": 2}),
    "CCl3":     (117, {"C": 1, "Cl": 3}),
    "C2Cl2":    (94,  {"C": 2, "Cl": 2}),
}

# --------------------------------------------------------------------------
# Reverse index: nominal delta → list of (name, formula_dict)
# Built once at import time for O(1) lookup by delta in the cross-check loop.
# --------------------------------------------------------------------------
_BY_DELTA: dict[int, list[tuple[str, dict[str, int]]]] = {}
for _name, (_delta, _formula) in NEUTRAL_LOSSES.items():
    _BY_DELTA.setdefault(_delta, []).append((_name, _formula))


def losses_for_delta(delta: int) -> list[tuple[str, dict[str, int]]]:
    """
    Return all (name, formula_dict) pairs whose nominal mass equals *delta*.

    Parameters
    ----------
    delta : int  Nominal mass difference (always positive).

    Returns
    -------
    list of (name: str, formula_dict: dict[str, int])
    Empty list if no entry matches.
    """
    return _BY_DELTA.get(delta, [])
