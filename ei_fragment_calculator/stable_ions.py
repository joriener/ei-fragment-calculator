"""
stable_ions.py
==============
Library of well-known, highly-stable EI fragment ions.

When a candidate formula matches one of these entries AND the parent
molecular formula allows that composition (sub-formula check), the
candidate receives a high confidence bonus (STABLE_ION_BONUS = 0.35).

Sources
-------
McLafferty & Tureček, "Interpretation of Mass Spectra", 4th ed.
Gross, "Mass Spectrometry: A Textbook", 2nd ed.
NIST WebBook common fragment tables.

Format
------
Dict mapping nominal m/z → list of (formula_dict, ion_name, ion_type)
  ion_type : "stable_cation" | "common_radical_cation"
"""

# Each entry: (composition_dict, name, ion_type)
STABLE_IONS: dict[int, list[tuple[dict[str, int], str, str]]] = {

    # ── m/z 15 ─────────────────────────────────────────────────────────────
    15: [
        ({"C": 1, "H": 3}, "CH3+", "stable_cation"),
    ],

    # ── m/z 18 ─────────────────────────────────────────────────────────────
    18: [
        ({"H": 2, "O": 1}, "H2O+•", "common_radical_cation"),
    ],

    # ── m/z 26 ─────────────────────────────────────────────────────────────
    26: [
        ({"C": 2, "H": 2}, "C2H2+•", "common_radical_cation"),
    ],

    # ── m/z 27 ─────────────────────────────────────────────────────────────
    27: [
        ({"C": 2, "H": 3}, "C2H3+", "stable_cation"),            # vinyl
        ({"H": 1, "C": 1, "N": 1}, "HCN+•", "common_radical_cation"),
    ],

    # ── m/z 28 ─────────────────────────────────────────────────────────────
    28: [
        ({"C": 1, "O": 1}, "CO+•",  "common_radical_cation"),
        ({"N": 2},          "N2+•", "common_radical_cation"),
        ({"C": 2, "H": 4}, "C2H4+•", "common_radical_cation"),
    ],

    # ── m/z 29 ─────────────────────────────────────────────────────────────
    29: [
        ({"C": 2, "H": 5}, "C2H5+", "stable_cation"),            # ethyl
        ({"C": 1, "H": 1, "O": 1}, "CHO+", "stable_cation"),     # formyl
    ],

    # ── m/z 39 ─────────────────────────────────────────────────────────────
    39: [
        ({"C": 3, "H": 3}, "C3H3+", "stable_cation"),            # cyclopropenyl
    ],

    # ── m/z 41 ─────────────────────────────────────────────────────────────
    41: [
        ({"C": 3, "H": 5}, "C3H5+", "stable_cation"),            # allyl
    ],

    # ── m/z 43 ─────────────────────────────────────────────────────────────
    43: [
        ({"C": 2, "H": 3, "O": 1}, "C2H3O+",  "stable_cation"),  # acetyl
        ({"C": 3, "H": 7},          "C3H7+",   "stable_cation"),  # propyl
    ],

    # ── m/z 44 ─────────────────────────────────────────────────────────────
    44: [
        ({"C": 1, "O": 2}, "CO2+•", "common_radical_cation"),
        ({"N": 2, "O": 1}, "N2O+•", "common_radical_cation"),
    ],

    # ── m/z 45 ─────────────────────────────────────────────────────────────
    45: [
        ({"C": 2, "H": 5, "O": 1}, "C2H5O+", "stable_cation"),   # ethoxy
    ],

    # ── m/z 50 ─────────────────────────────────────────────────────────────
    50: [
        ({"C": 4, "H": 2}, "C4H2+•", "common_radical_cation"),
    ],

    # ── m/z 51 ─────────────────────────────────────────────────────────────
    51: [
        ({"C": 4, "H": 3}, "C4H3+", "stable_cation"),
    ],

    # ── m/z 55 ─────────────────────────────────────────────────────────────
    55: [
        ({"C": 4, "H": 7}, "C4H7+", "stable_cation"),            # butyl-like
        ({"C": 3, "H": 3, "O": 1}, "C3H3O+", "stable_cation"),
    ],

    # ── m/z 57 ─────────────────────────────────────────────────────────────
    57: [
        ({"C": 4, "H": 9}, "C4H9+", "stable_cation"),            # tert-butyl
        ({"C": 3, "H": 5, "O": 1}, "C3H5O+", "stable_cation"),   # acrolein
    ],

    # ── m/z 58 ─────────────────────────────────────────────────────────────
    58: [
        ({"C": 3, "H": 6, "N": 1}, "C3H6N+", "stable_cation"),   # common immonium
    ],

    # ── m/z 65 ─────────────────────────────────────────────────────────────
    65: [
        ({"C": 5, "H": 5}, "C5H5+", "stable_cation"),            # cyclopentadienyl
    ],

    # ── m/z 67 ─────────────────────────────────────────────────────────────
    67: [
        ({"C": 5, "H": 7}, "C5H7+", "stable_cation"),
    ],

    # ── m/z 69 ─────────────────────────────────────────────────────────────
    69: [
        ({"C": 5, "H": 9}, "C5H9+", "stable_cation"),
        ({"C": 4, "H": 5, "O": 1}, "C4H5O+", "stable_cation"),
        ({"C": 3, "H": 5, "N": 2}, "C3H5N2+", "stable_cation"),
    ],

    # ── m/z 71 ─────────────────────────────────────────────────────────────
    71: [
        ({"C": 5, "H": 11}, "C5H11+", "stable_cation"),
        ({"C": 4, "H": 7, "O": 1}, "C4H7O+", "stable_cation"),
    ],

    # ── m/z 77 ─────────────────────────────────────────────────────────────
    77: [
        ({"C": 6, "H": 5}, "C6H5+", "stable_cation"),            # phenyl — very common
    ],

    # ── m/z 78 ─────────────────────────────────────────────────────────────
    78: [
        ({"C": 6, "H": 6}, "C6H6+•", "common_radical_cation"),   # benzene radical cation
    ],

    # ── m/z 79 ─────────────────────────────────────────────────────────────
    79: [
        ({"C": 6, "H": 7}, "C6H7+", "stable_cation"),
        ({"P": 1, "O": 3}, "PO3-",  "stable_cation"),             # phosphonate fragment
    ],

    # ── m/z 80 ─────────────────────────────────────────────────────────────
    80: [
        ({"C": 5, "H": 6, "N": 1}, "C5H6N+", "stable_cation"),   # pyridinium-like
    ],

    # ── m/z 81 ─────────────────────────────────────────────────────────────
    81: [
        ({"C": 6, "H": 9}, "C6H9+", "stable_cation"),
        ({"C": 5, "H": 5, "O": 1}, "C5H5O+", "stable_cation"),
    ],

    # ── m/z 83 ─────────────────────────────────────────────────────────────
    83: [
        ({"C": 6, "H": 11}, "C6H11+", "stable_cation"),
    ],

    # ── m/z 85 ─────────────────────────────────────────────────────────────
    85: [
        ({"C": 5, "H": 9, "O": 1}, "C5H9O+", "stable_cation"),
        ({"C": 6, "H": 13}, "C6H13+", "stable_cation"),
    ],

    # ── m/z 91 ─────────────────────────────────────────────────────────────
    91: [
        ({"C": 7, "H": 7}, "C7H7+", "stable_cation"),            # tropylium — very common
    ],

    # ── m/z 92 ─────────────────────────────────────────────────────────────
    92: [
        ({"C": 7, "H": 8}, "C7H8+•", "common_radical_cation"),   # toluene radical cation
    ],

    # ── m/z 93 ─────────────────────────────────────────────────────────────
    93: [
        ({"C": 7, "H": 9}, "C7H9+", "stable_cation"),
        ({"C": 6, "H": 5, "O": 1}, "C6H5O+", "stable_cation"),   # phenoxy (approx)
    ],

    # ── m/z 94 ─────────────────────────────────────────────────────────────
    94: [
        ({"C": 6, "H": 6, "O": 1}, "C6H6O+•", "common_radical_cation"),  # phenol rc
    ],

    # ── m/z 95 ─────────────────────────────────────────────────────────────
    95: [
        ({"C": 7, "H": 11}, "C7H11+", "stable_cation"),
        ({"C": 6, "H": 7, "O": 1}, "C6H7O+", "stable_cation"),
    ],

    # ── m/z 97 ─────────────────────────────────────────────────────────────
    97: [
        ({"C": 7, "H": 13}, "C7H13+", "stable_cation"),
    ],

    # ── m/z 99 ─────────────────────────────────────────────────────────────
    99: [
        ({"C": 7, "H": 15}, "C7H15+", "stable_cation"),
        ({"C": 6, "H": 11, "O": 1}, "C6H11O+", "stable_cation"),
    ],

    # ── m/z 105 ────────────────────────────────────────────────────────────
    105: [
        ({"C": 8, "H": 9},            "C8H9+",    "stable_cation"),
        ({"C": 7, "H": 5, "O": 1},   "C7H5O+",   "stable_cation"),  # benzoyl
    ],

    # ── m/z 107 ────────────────────────────────────────────────────────────
    107: [
        ({"C": 7, "H": 7, "O": 1}, "C7H7O+", "stable_cation"),   # methylbenzoyl / hydroxytoluene
    ],

    # ── m/z 119 ────────────────────────────────────────────────────────────
    119: [
        ({"C": 9, "H": 11},           "C9H11+",   "stable_cation"),
        ({"C": 8, "H": 7, "O": 1},   "C8H7O+",   "stable_cation"),
    ],

    # ── m/z 121 ────────────────────────────────────────────────────────────
    121: [
        ({"C": 8, "H": 9, "O": 1}, "C8H9O+", "stable_cation"),
    ],

    # ── m/z 149 ────────────────────────────────────────────────────────────
    149: [
        ({"C": 8, "H": 5, "O": 3}, "C8H5O3+", "stable_cation"),  # phthalate
    ],
}


# Bonus added to candidate confidence when it matches a stable ion
STABLE_ION_BONUS: float = 0.35


def lookup_stable_ion(
    composition: dict[str, int],
    nominal_mz: int,
) -> tuple[str, str] | None:
    """
    Look up *composition* in the stable-ion library at *nominal_mz*.

    Returns
    -------
    (ion_name, ion_type) if found, else None.
    """
    entries = STABLE_IONS.get(nominal_mz, [])
    for (lib_comp, name, ion_type) in entries:
        if lib_comp == composition:
            return (name, ion_type)
    return None
