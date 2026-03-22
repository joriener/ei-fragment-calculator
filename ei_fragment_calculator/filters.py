"""
filters.py
==========
Five optional post-enumeration filters, one scorer, and a ranking helper
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
    isotope_tolerance   : float  Max deviation in percentage points (default 30.0).
    max_ring_ratio      : float  Max DBE/C ratio for HD check (default 0.5).
    """
    nitrogen_rule       : bool  = True
    hd_check            : bool  = True
    lewis_senior        : bool  = True
    isotope_score       : bool  = True
    smiles_constraints  : bool  = True
    isotope_tolerance   : float = 30.0
    max_ring_ratio      : float = 0.5


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


def apply_lewis_senior(composition: dict) -> tuple:
    """
    Apply Lewis octet rule and Senior valence-sum graph rules.

    Rule 1: sum of all valences must be even.
    Rule 2: sum of all valences >= 2 * (atom_count - 1).

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

    if total_valence % 2 != 0:
        return False, (
            "Lewis/Senior Rule 1 violation: sum of valences = {} (odd). "
            "Ref: Senior 1951".format(total_valence)
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
# Combined filter runner
# ---------------------------------------------------------------------------

def run_all_filters(
    candidate: dict,
    nominal_mz: int,
    config: FilterConfig,
    observed_spectrum: Optional[dict] = None,
    parent_ring_count: Optional[int] = None,
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
        passed, msg = apply_lewis_senior(composition)
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
        2. Smallest ``|delta_mass|`` — closest match to the nominal m/z.
        3. Lowest ``isotope_score`` — best agreement with the observed
           isotope pattern (lower score = smaller deviation).

    If filters have not been applied (no ``filter_passed`` key), all
    candidates are treated as passing and ranked by mass accuracy alone.

    Parameters
    ----------
    candidates : list[dict]   Candidate dicts as returned by
                              :func:`find_fragment_candidates`.

    Returns
    -------
    list[dict]  Same candidates, sorted best-first (original list unchanged).
    """
    def _sort_key(c: dict):
        passed       = 0 if c.get("filter_passed", True) else 1  # 0 = better
        delta_abs    = abs(c.get("delta_mass", 0.0))
        iso_score    = c.get("isotope_score", 0.0)
        return (passed, delta_abs, iso_score)

    return sorted(candidates, key=_sort_key)
