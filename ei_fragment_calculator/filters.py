"""
filters.py
==========
Six optional post-enumeration filters, one scorer, and a ranking helper
that refine the candidate formula list for each EI mass spectrum peak.

All filters are enabled by default and can be individually deactivated
via FilterConfig or the corresponding CLI --no-* flags.

Filter summary
--------------
1. Nitrogen Rule         -- parity relationship between nominal mass and N count
2. H-Deficiency Check    -- DBE must not exceed half the carbon count
3. Lewis & Senior Rules  -- valence-sum constraints from graph theory
4. Isotope Pattern Score -- match theoretical M/M+1/M+2 ratios to spectrum
5. SMILES Constraints    -- ring count upper bound from parsed MOL block
6. RDKit Validation      -- element recognition via RDKit periodic table (optional)

Ranking
-------
rank_candidates()  -- sort a candidate list by quality (best first):
    (1) filter_passed=True before filter_passed=False
    (2) smallest |delta_mass| (closest to nominal m/z)
    (3) lowest isotope_score (best pattern match)

References
----------
Nitrogen rule:
  McLafferty & Turecek (1993) Interpretation of Mass Spectra, 4th ed.
  https://doi.org/10.1002/jms.1190080509
Lewis & Senior rules:
  Senior J.K. (1951) Am. J. Math. 73(3):663-689.
  https://doi.org/10.2307/2372318
H-deficiency / DBE:
  Pretsch et al. (2009) Structure Determination of Organic Compounds, 4th ed.
  https://doi.org/10.1007/978-3-540-93810-1
Isotope pattern scoring:
  Gross J.H. (2017) Mass Spectrometry: A Textbook, 3rd ed.
  https://doi.org/10.1007/978-3-319-54398-7
SMILES / structural constraints:
  Weininger D. (1988) J. Chem. Inf. Comput. Sci. 28(1):31-36.
  https://doi.org/10.1021/ci00057a005
RDKit chemical validation:
  RDKit: Open-source cheminformatics. https://www.rdkit.org
"""

from dataclasses import dataclass
from typing import Optional
from .constants import VALENCE


# ---------------------------------------------------------------------------
# Filter configuration dataclass
# ---------------------------------------------------------------------------

@dataclass
class FilterConfig:
    """
    Toggle each filter/scorer on or off independently.

    All filters are enabled (True) by default.
    Pass FilterConfig(nitrogen_rule=False) to disable individual checks.

    Attributes
    ----------
    nitrogen_rule       : bool   Apply nitrogen rule parity check (default True).
    hd_check            : bool   Apply DBE/C plausibility check (default True).
    lewis_senior        : bool   Apply Lewis & Senior valence-sum rules (default True).
    isotope_score       : bool   Score by isotope pattern match (default True).
    smiles_constraints  : bool   Apply ring-count upper bound from MOL block (default True).
    rdkit_validation    : bool   Validate elements via RDKit periodic table (default False).
    isotope_tolerance   : float  Max deviation in percentage points (default 30.0).
    max_ring_ratio      : float  Max DBE/C ratio for HD check (default 1.0).
                                 The previous default of 0.5 incorrectly
                                 rejected valid aromatic fragment ions such as
                                 phenyl (C6H5, DBE/C=0.75) and tropylium
                                 (C7H7, DBE/C=0.64).  1.0 retains these while
                                 still filtering degenerate H-poor formulas.
    """
    nitrogen_rule       : bool  = True
    hd_check            : bool  = True
    lewis_senior        : bool  = True
    isotope_score       : bool  = True
    smiles_constraints  : bool  = True
    rdkit_validation    : bool  = False
    isotope_tolerance   : float = 30.0
    max_ring_ratio      : float = 1.0


# ---------------------------------------------------------------------------
# 1.  Nitrogen rule
# ---------------------------------------------------------------------------

NITROGEN_RULE_REF = (
    "McLafferty & Turecek (1993) Interpretation of Mass Spectra, 4th ed. "
    "https://doi.org/10.1002/jms.1190080509"
)


def apply_nitrogen_rule(composition: dict, nominal_mz: int, dbe: float) -> tuple:
    """
    Apply the nitrogen rule to a candidate formula.

    For even-electron ions (integer DBE): odd m/z <=> odd N count.
    For odd-electron ions (half-integer DBE): rule is inverted.

    Returns (passed: bool, message: str).
    Ref: McLafferty & Turecek 1993.
    """
    n_count       = composition.get("N", 0) + composition.get("P", 0)
    mz_odd        = (nominal_mz % 2) == 1
    n_odd         = (n_count % 2) == 1
    even_electron = (round(dbe * 2) % 2) == 0

    if even_electron:
        passed = (mz_odd == n_odd)
    else:
        passed = (mz_odd != n_odd)

    if passed:
        return True, ""
    return False, (
        "Nitrogen rule violation: nominal m/z {} ({}) with N={} ({}). "
        "Ref: McLafferty & Turecek 1993".format(
            nominal_mz,
            "odd" if mz_odd else "even",
            n_count,
            "odd" if n_odd else "even",
        )
    )


# ---------------------------------------------------------------------------
# 2.  Hydrogen deficiency / DBE plausibility
# ---------------------------------------------------------------------------

HD_CHECK_REF = (
    "Pretsch et al. (2009) Structure Determination of Organic Compounds, 4th ed. "
    "https://doi.org/10.1007/978-3-540-93810-1"
)


def apply_hd_check(composition: dict, dbe: float, max_ring_ratio: float = 0.5) -> tuple:
    """
    Reject candidates whose DBE exceeds max_ring_ratio * C_count.

    Rationale: for typical organic molecules DBE rarely exceeds n/2
    where n = carbon count. A ratio above 0.5 implies an extraordinarily
    hydrogen-poor structure that is unlikely as an EI fragment.

    Returns (passed: bool, message: str).
    Ref: Pretsch et al. 2009.
    """
    c_count = composition.get("C", 0)
    if c_count == 0:
        return True, ""

    ratio = dbe / c_count
    if ratio <= max_ring_ratio:
        return True, ""

    return False, (
        "H-deficiency check failed: DBE/C = {:.3f} > {:.2f} "
        "(DBE={}, C={}). Ref: Pretsch et al. 2009".format(
            ratio, max_ring_ratio, dbe, c_count
        )
    )


# ---------------------------------------------------------------------------
# 3.  Lewis & Senior rules
# ---------------------------------------------------------------------------

LEWIS_SENIOR_REF = (
    "Senior J.K. (1951) Am. J. Math. 73(3):663-689. "
    "https://doi.org/10.2307/2372318"
)


def apply_lewis_senior(composition: dict, dbe: float = 0.0) -> tuple:
    """
    Apply Lewis octet rule and Senior valence-sum graph rules.

    Rule 1: sum of all valences must be even.
             **Relaxed for radical (odd-electron) species**: in EI mass
             spectrometry many fragment ions are radical cations (M•+,
             formed by alpha-cleavage or homolytic bond breaking).  These
             have a half-integer DBE, one unpaired electron, and
             legitimately possess an odd total valence.  Rule 1 is therefore
             only enforced for even-electron (closed-shell) ions where DBE
             is a whole number.
    Rule 2: sum of all valences >= 2 * (atom_count - 1).

    Parameters
    ----------
    composition : dict[str, int]  Elemental composition.
    dbe         : float           Degree of unsaturation (from calculate_dbe).
                                  Half-integer value flags odd-electron species.

    Returns (passed: bool, message: str).
    Ref: Senior 1951.
    """
    total_valence = 0
    atom_count    = 0

    for el, cnt in composition.items():
        if cnt <= 0:
            continue
        val = VALENCE.get(el, 2)
        total_valence += val * cnt
        atom_count    += cnt

    if atom_count == 0:
        return True, ""

    # Rule 1: even valence sum — skip for radical (odd-electron) ions.
    # A radical has a half-integer DBE: 2*DBE is odd.
    is_radical = (round(dbe * 2) % 2) != 0  # 2×DBE is odd ↔ half-integer DBE ↔ radical
    if not is_radical and total_valence % 2 != 0:
        return False, (
            "Lewis/Senior Rule 1 violation: sum of valences = {} (odd) "
            "for even-electron ion. Ref: Senior 1951".format(total_valence)
        )

    min_required = 2 * (atom_count - 1)
    if total_valence < min_required:
        return False, (
            "Lewis/Senior Rule 2 violation: sum of valences = {} < {} "
            "({} atoms). Ref: Senior 1951".format(
                total_valence, min_required, atom_count
            )
        )

    return True, ""


# ---------------------------------------------------------------------------
# 4.  Isotope pattern scorer
# ---------------------------------------------------------------------------

ISOTOPE_SCORE_REF = (
    "Gross J.H. (2017) Mass Spectrometry: A Textbook, 3rd ed. "
    "https://doi.org/10.1007/978-3-319-54398-7"
)


def score_isotope_match(
    theoretical_pattern: list,
    observed_spectrum: dict,
    nominal_mz: int,
    tolerance: float = 30.0,
) -> tuple:
    """
    Score how well a candidate's theoretical isotope pattern matches
    the observed mass spectrum.

    Score = sum of |theo% - obs%| for M+1 and M+2 (percentage points).
    Lower is better; 0 = perfect match.

    Returns (score: float, message: str).
    Ref: Gross 2017.
    """
    if not theoretical_pattern or not observed_spectrum:
        return 0.0, "no data for scoring"

    theo_map: dict = {}
    for peak in theoretical_pattern:
        offset = peak.get("nominal_offset", 0)
        if offset <= 4:
            theo_map[offset] = peak.get("relative_abundance", 0.0)

    if not theo_map:
        return 0.0, "empty theoretical pattern"

    mono_theo = theo_map.get(0, 100.0)
    if mono_theo <= 0:
        return 0.0, "zero monoisotopic theoretical abundance"

    total_score = 0.0
    details: list = []

    for offset in [1, 2]:
        if offset not in theo_map:
            continue
        theo_rel = (theo_map[offset] / mono_theo) * 100.0
        obs_abs  = observed_spectrum.get(nominal_mz + offset, 0.0)
        obs_mono = observed_spectrum.get(nominal_mz, 1.0)
        obs_rel  = (obs_abs / max(obs_mono, 1.0)) * 100.0 if obs_mono > 0 else 0.0
        diff = abs(theo_rel - obs_rel)
        total_score += diff
        details.append("M+{}: theo={:.1f}% obs={:.1f}% diff={:.1f}pp".format(
            offset, theo_rel, obs_rel, diff
        ))

    msg = "Isotope score={:.1f}pp (tol={:.0f}pp): {}. Ref: Gross 2017".format(
        total_score, tolerance,
        "; ".join(details) if details else "no M+1/M+2 peaks"
    )
    return total_score, msg


# ---------------------------------------------------------------------------
# 5.  SMILES / structural constraint (ring-count upper bound)
# ---------------------------------------------------------------------------

SMILES_CONSTRAINT_REF = (
    "Weininger D. (1988) J. Chem. Inf. Comput. Sci. 28(1):31-36. "
    "https://doi.org/10.1021/ci00057a005"
)


def apply_smiles_constraints(
    composition: dict,
    dbe: float,
    parent_ring_count: Optional[int],
) -> tuple:
    """
    Reject fragment candidates whose DBE greatly exceeds the parent ring count.

    A fragment cannot have more rings than the parent molecule. If no ring
    information is available (parent_ring_count is None), the filter is skipped.

    The threshold is: DBE > parent_ring_count * 2 + 1 triggers rejection.

    Returns (passed: bool, message: str).
    Ref: Weininger 1988.
    """
    if parent_ring_count is None:
        return True, "no MOL block ring data — constraint skipped"

    if dbe > parent_ring_count * 2 + 1:
        return False, (
            "SMILES constraint: DBE={} greatly exceeds parent ring count={} "
            "— fragment unlikely. Ref: Weininger 1988".format(dbe, parent_ring_count)
        )

    return True, ""


# ---------------------------------------------------------------------------
# 6.  RDKit chemical validation
# ---------------------------------------------------------------------------

RDKIT_VALIDATION_REF = (
    "RDKit: Open-source cheminformatics. https://www.rdkit.org"
)


def apply_rdkit_validation(composition: dict) -> tuple:
    """
    Validate a candidate formula using RDKit's periodic table.

    Checks that every element symbol is recognized by RDKit.  Unknown or
    misspelled element symbols (e.g. 'Xx', 'R') are rejected.

    If RDKit is not installed the filter is silently skipped (returns True).

    Returns (passed: bool, message: str).
    Ref: RDKit open-source cheminformatics.
    """
    try:
        from rdkit import Chem
    except ImportError:
        return True, "RDKit not installed — validation skipped"

    pt = Chem.GetPeriodicTable()
    for el, cnt in composition.items():
        if cnt <= 0:
            continue
        try:
            atomic_num = pt.GetAtomicNumber(el)
            if atomic_num == 0:
                return False, "RDKit: unknown element '{}'".format(el)
        except Exception:
            return False, "RDKit: unrecognized element '{}'".format(el)

    return True, ""


# ---------------------------------------------------------------------------
# 7.  Plausible neutral validation
# ---------------------------------------------------------------------------

NEUTRAL_VALIDATION_REF = (
    "Neutral loss must have non-negative element counts: parent - fragment >= 0 for all elements."
)


def apply_neutral_validation(
    fragment_comp: dict,
    parent_comp: dict,
) -> tuple:
    """
    Validate that the neutral loss (parent - fragment) is chemically plausible.

    Rejects candidates where parent_comp[el] < fragment_comp[el] for any element,
    or where the resulting neutral species would have negative H count.

    Returns (passed: bool, message: str).
    """
    # Compute neutral loss composition
    neutral = {}
    for el in parent_comp:
        parent_count = parent_comp.get(el, 0)
        fragment_count = fragment_comp.get(el, 0)
        neutral_count = parent_count - fragment_count
        if neutral_count < 0:
            return False, (
                "Invalid neutral loss: parent has fewer {} atoms ({}) than fragment ({}). "
                "Plausible neutral validation failed.".format(el, parent_count, fragment_count)
            )
        if neutral_count > 0:
            neutral[el] = neutral_count

    # Check H specifically
    if neutral.get("H", 0) < 0:
        return False, (
            "Invalid neutral loss: negative H count in neutral species. "
            "Plausible neutral validation failed."
        )

    return True, ""


# ---------------------------------------------------------------------------
# 8.  Cl/Br M+2 pattern hard constraint
# ---------------------------------------------------------------------------

CLBR_M2_REF = (
    "Isotope pattern constraints for Cl and Br: "
    "each Cl adds ~0.325 to M+2/M ratio, each Br adds ~0.970."
)


def apply_clbr_m2_check(
    composition: dict,
    intensity_map: Optional[dict],
    nominal_mz: int,
) -> tuple:
    """
    For Cl/Br-containing compositions, validate the M+2/M intensity ratio.

    Predicted ratios per atom:
    - 1 Cl → 0.325
    - 2 Cl → 0.650 (additive)
    - 1 Br → 0.970
    - Combinations are additive

    Rejects candidates where |predicted - observed| / predicted > 0.35.
    Skips if intensity_map is None or missing M and M+2 peaks.

    Returns (passed: bool, message: str).
    """
    if not intensity_map:
        return True, "no intensity map — M+2 check skipped"

    n_cl = composition.get("Cl", 0)
    n_br = composition.get("Br", 0)

    if n_cl == 0 and n_br == 0:
        return True, ""  # no Cl/Br, no check needed

    # Predicted M+2/M ratio
    predicted = n_cl * 0.325 + n_br * 0.970

    # Observed ratio
    mono_int = intensity_map.get(nominal_mz, 0.0)
    m2_int   = intensity_map.get(nominal_mz + 2, 0.0)

    if mono_int <= 0 or m2_int < 0:
        return True, "incomplete M/M+2 peaks — M+2 check skipped"

    observed = m2_int / mono_int

    # Tolerance: 35% relative error
    rel_error = abs(predicted - observed) / predicted if predicted > 0 else float('inf')
    tolerance = 0.35

    if rel_error <= tolerance:
        return True, ""

    return False, (
        "Cl/Br M+2 ratio mismatch: predicted={:.3f}, observed={:.3f}, "
        "rel.err={:.1%} > {:.0%} tol (Cl={}, Br={}). Ref: Isotope patterns".format(
            predicted, observed, rel_error, tolerance, n_cl, n_br
        )
    )


# ---------------------------------------------------------------------------
# E3: 7 Golden Rules (Kind & Fiehn 2007)
# ---------------------------------------------------------------------------

def apply_impossible_homoatomic(composition: dict) -> tuple[bool, str]:
    """
    Reject homoatomic molecules (single-element formulas) that don't exist.

    Allows: single atoms (H, C, N, O, etc.) and diatomic molecules (N2, O2, etc.).
    Rejects: triatomic or larger homoatomic molecules that are unstable
    (N3, N4, O3+, etc.) except those known to be stable (ozone O3 is borderline).

    Parameters
    ----------
    composition : dict  Elemental composition.

    Returns
    -------
    tuple[bool, str]  (passed, message).
    """
    # Count how many different elements are present
    elements_present = [el for el, cnt in composition.items() if cnt > 0]
    if len(elements_present) != 1:
        return True, ""  # Not homoatomic, allow

    element = elements_present[0]
    total_atoms = composition[element]

    # Single atoms and diatomic molecules are allowed
    if total_atoms <= 2:
        return True, ""

    # Known stable triatomic: O3 (ozone) — allow with mild concern
    if element == "O" and total_atoms == 3:
        return True, ""  # O3 exists but is rare; not rejected

    # Reject all other homoatomic molecules with 3+ atoms
    # Examples: N3, N4, S3, P4, etc. are unstable
    return False, (
        "Impossible homoatomic molecule: {} ({}×{}). "
        "Homoatomic molecules with >2 atoms are unstable except O3.".format(
            element * total_atoms, total_atoms, element
        )
    )


def apply_golden_rules(composition: dict) -> tuple[bool, str]:
    """
    Apply Kind & Fiehn 2007 heuristic rules for molecular formula validation.

    Rules apply to fragments with ≥5 heavy atoms:
    - H/C ratio: 0.125–3.1
    - N/C ratio: 0–1.3
    - O/C ratio: 0–1.2
    - S/C ratio: 0–0.8
    - P/C ratio: 0–0.32
    - Halogens/C: ≤1.5

    Parameters
    ----------
    composition : dict  Elemental composition {element: count}.

    Returns
    -------
    tuple[bool, str]  (passed, reason) where reason is empty if passed.
    """
    c = composition.get("C", 0)
    h = composition.get("H", 0)
    n = composition.get("N", 0)
    o = composition.get("O", 0)
    s = composition.get("S", 0)
    p = composition.get("P", 0)
    cl = composition.get("Cl", 0)
    br = composition.get("Br", 0)
    f = composition.get("F", 0)
    i = composition.get("I", 0)

    # Count heavy atoms
    heavy_atoms = c + n + o + s + p + cl + br + f + i
    if heavy_atoms < 5:
        # Rules don't apply to small fragments
        return True, ""

    # H/C ratio: 0.125–3.1
    if c > 0:
        hc_ratio = h / c
        if not (0.125 <= hc_ratio <= 3.1):
            return False, "H/C ratio {:.3f} outside range 0.125–3.1".format(hc_ratio)

    # N/C ratio: 0–1.3
    if c > 0:
        nc_ratio = n / c
        if not (0 <= nc_ratio <= 1.3):
            return False, "N/C ratio {:.3f} outside range 0–1.3".format(nc_ratio)

    # O/C ratio: 0–1.2
    if c > 0:
        oc_ratio = o / c
        if not (0 <= oc_ratio <= 1.2):
            return False, "O/C ratio {:.3f} outside range 0–1.2".format(oc_ratio)

    # S/C ratio: 0–0.8
    if c > 0:
        sc_ratio = s / c
        if not (0 <= sc_ratio <= 0.8):
            return False, "S/C ratio {:.3f} outside range 0–0.8".format(sc_ratio)

    # P/C ratio: 0–0.32
    if c > 0:
        pc_ratio = p / c
        if not (0 <= pc_ratio <= 0.32):
            return False, "P/C ratio {:.3f} outside range 0–0.32".format(pc_ratio)

    # Halogens/C ≤ 1.5
    if c > 0:
        hal_count = cl + br + f + i
        hal_ratio = hal_count / c
        if hal_ratio > 1.5:
            return False, "Halogens/C ratio {:.3f} exceeds 1.5".format(hal_ratio)

    return True, ""


# ---------------------------------------------------------------------------
# Combined filter runner
# ---------------------------------------------------------------------------

def run_all_filters(
    candidate: dict,
    nominal_mz: int,
    config: FilterConfig,
    observed_spectrum: Optional[dict] = None,
    parent_ring_count: Optional[int] = None,
    intensity_map: Optional[dict] = None,
    parent_composition: Optional[dict] = None,
) -> dict:
    """
    Apply all enabled filters to a candidate formula and attach results.

    Returns the original candidate dict augmented with:
        filter_passed  : bool
        filter_details : dict  (per-filter result strings)
        isotope_score  : float (0.0 if isotope scoring disabled)
    """
    from .isotope import isotope_pattern

    composition = candidate.get("_composition", {})
    dbe         = candidate.get("dbe", 0.0)
    details: dict = {}
    all_passed = True

    if config.nitrogen_rule:
        passed, msg = apply_nitrogen_rule(composition, nominal_mz, dbe)
        details["nitrogen_rule"] = msg if msg else "OK"
        if not passed:
            all_passed = False

    if config.hd_check:
        passed, msg = apply_hd_check(composition, dbe, config.max_ring_ratio)
        details["hd_check"] = msg if msg else "OK"
        if not passed:
            all_passed = False

    if config.lewis_senior:
        passed, msg = apply_lewis_senior(composition, dbe)
        details["lewis_senior"] = msg if msg else "OK"
        if not passed:
            all_passed = False

    iso_score = 0.0
    if config.isotope_score:
        pattern = isotope_pattern(composition) if composition else []
        iso_score, msg = score_isotope_match(
            pattern, observed_spectrum or {}, nominal_mz, config.isotope_tolerance,
        )
        details["isotope_score"] = msg
        if iso_score > config.isotope_tolerance:
            all_passed = False

    if config.smiles_constraints:
        passed, msg = apply_smiles_constraints(composition, dbe, parent_ring_count)
        details["smiles_constraints"] = msg if msg else "OK"
        if not passed:
            all_passed = False

    if config.rdkit_validation:
        passed, msg = apply_rdkit_validation(composition)
        details["rdkit_validation"] = msg if msg else "OK"
        if not passed:
            all_passed = False

    # Plausible neutral validation (always enabled when parent_composition is provided)
    if parent_composition:
        passed, msg = apply_neutral_validation(composition, parent_composition)
        details["neutral_validation"] = msg if msg else "OK"
        if not passed:
            all_passed = False

    # Cl/Br M+2 hard constraint (always enabled when intensity_map is provided)
    if intensity_map:
        passed, msg = apply_clbr_m2_check(composition, intensity_map, nominal_mz)
        details["clbr_m2_check"] = msg if msg else "OK"
        if not passed:
            all_passed = False

    # Impossible homoatomic check (always enabled)
    passed, msg = apply_impossible_homoatomic(composition)
    details["impossible_homoatomic"] = msg if msg else "OK"
    if not passed:
        all_passed = False

    # E3: 7 Golden Rules (always enabled, Kind & Fiehn 2007)
    passed, msg = apply_golden_rules(composition)
    details["golden_rules"] = msg if msg else "OK"
    if not passed:
        all_passed = False

    result = dict(candidate)
    result["filter_passed"]  = all_passed
    result["filter_details"] = details
    result["isotope_score"]  = iso_score
    return result


# ---------------------------------------------------------------------------
# Candidate ranking helper
# ---------------------------------------------------------------------------

def rank_candidates(candidates: list) -> list:
    """
    Return the candidate list sorted by quality, best candidate first.

    Sorting key (in priority order):
        1. ``filter_passed=True`` before ``filter_passed=False``.
        2. Smallest ``_mdd_deviation`` — per-Da mass-defect similarity to the
           parent compound (mDa/Da units, set by
           :func:`~ei_fragment_calculator.calculator.find_fragment_candidates`).
           EI fragment ions share a similar mass-defect signature with their
           parent molecule, so this criterion correctly favours stable
           aromatic hydrocarbon ions (e.g. C6H5 at 77.039, C7H7 at 91.054)
           over spurious O-rich formulas that are numerically closer to the
           integer nominal m/z (e.g. C5HO at 77.002).
           If the key is absent (legacy callers), falls back to
           ``|delta_mass|``-only ranking.
        3. Smallest ``|delta_mass|`` — tiebreaker: closest to nominal m/z.
        4. Lowest ``isotope_score`` — best agreement with the observed
           isotope pattern (lower score = smaller deviation).

    If filters have not been applied (no ``filter_passed`` key), all
    candidates are treated as passing.

    Parameters
    ----------
    candidates : list[dict]   Candidate dicts as returned by
                              :func:`~ei_fragment_calculator.calculator.find_fragment_candidates`.

    Returns
    -------
    list[dict]  Same candidates, sorted best-first (original list unchanged).
    """
    def _sort_key(c: dict):
        passed    = 0 if c.get("filter_passed", True) else 1   # 0 = better
        mdd_dev   = c.get("_mdd_deviation")                    # None = no parent info
        delta_abs = abs(c.get("delta_mass", 0.0))
        iso_score = c.get("isotope_score", 0.0)
        # Use mass-defect similarity as primary quality criterion when available.
        # Fall back to |delta_mass| for candidates without parent context.
        primary = mdd_dev if mdd_dev is not None else float("inf")
        return (passed, primary, delta_abs, iso_score)

    return sorted(candidates, key=_sort_key)


# ---------------------------------------------------------------------------
# Simple boolean filter wrappers for formula_calculator.py
# ---------------------------------------------------------------------------

def nitrogen_rule(composition: dict, nominal_mz: int = 0, dbe: float = 0.0) -> bool:
    """
    Simple boolean version of apply_nitrogen_rule.
    Returns True if the nitrogen rule is satisfied.
    """
    if not composition:
        return True
    if nominal_mz == 0:
        # Estimate nominal m/z from composition if not provided
        from .calculator import exact_mass
        nominal_mz = int(round(exact_mass(composition)))
    from .calculator import calculate_dbe as calc_dbe
    if dbe == 0.0:
        dbe = calc_dbe(composition) or 0.0
    passed, _ = apply_nitrogen_rule(composition, nominal_mz, dbe)
    return passed


def hd_check(composition: dict, dbe: float, max_ring_ratio: float = 1.0) -> bool:
    """
    Simple boolean version of apply_hd_check.
    Returns True if H-deficiency check is satisfied.
    """
    if not composition or dbe is None:
        return True
    passed, _ = apply_hd_check(composition, dbe, max_ring_ratio=max_ring_ratio)
    return passed


def lewis_senior(composition: dict, dbe: float = 0.0) -> bool:
    """
    Simple boolean version of apply_lewis_senior.
    Returns True if Lewis & Senior rules are satisfied.
    """
    if not composition:
        return True
    passed, _ = apply_lewis_senior(composition, dbe)
    return passed


def ring_check(composition: dict, max_dbe: float = None) -> bool:
    """
    Simple ring check: DBE must be non-negative and reasonable.
    Returns True if ring check passes.
    """
    if not composition:
        return True
    from .calculator import calculate_dbe
    dbe = calculate_dbe(composition)
    if dbe is None or dbe < 0:
        return False
    return True
