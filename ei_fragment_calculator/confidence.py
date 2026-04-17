"""
confidence.py
=============
Multi-evidence confidence scoring for unit-mass EI fragment assignments.

All scoring is applied as a **post-processing pass** after
``find_fragment_candidates()`` has already generated and filtered
candidates. The existing filter pipeline (nitrogen rule, DBE, HD-check,
Lewis–Senior, etc.) is not repeated here — it is assumed to have run.

Public API
----------
score_compound(all_candidates, intensity_map, parent_composition,
               parent_dbe, ...) -> dict[int, list[dict]]

    Takes the full {mz: [candidate, ...]} dict for one compound, runs
    multi-pass confidence scoring, and returns the same structure with
    each candidate dict augmented with confidence scores and evidence tags.
    Candidates within each peak list are re-sorted by confidence descending.

parse_intensity_map(peak_text) -> dict[int, float]

    Parse raw SDF/MSP peak text into {nominal_mz: intensity}.

Evidence components
-------------------
A  M+1 / M+2 isotope pattern matching
B  Fragmentation-rule annotation integration
C  Neutral-loss cross-check  (inter-peak, iterative)
D  DBE upper-bound penalty
E  Stable-ion library bonus
F  Even/odd-electron preference

Multi-peak consistency
----------------------
Three iterative passes:
  Pass 1 — per-candidate individual scoring (A, B, D, E, F)
  Pass 2 — neutral-loss pair cross-check (C), re-rank
  Pass 3 — complementary-ion pair check, re-rank

Notes
-----
* Confidence is a dimensionless float in [0.0, 1.0].
* When called with all enable_* flags False the module returns candidates
  unchanged (no-op), preserving backward compatibility.
* HR input mode (exact-mass peaks) does not benefit from this module;
  callers should guard with ``if not hr_input``.
"""

from __future__ import annotations

import math
import re
from typing import Any

from .neutral_losses import losses_for_delta
from .stable_ions import STABLE_ION_BONUS, lookup_stable_ion

# Isotope contributions to M+1 (fraction of monoisotopic peak per atom)
_M1_CONTRIB: dict[str, float] = {
    "C":  0.01110,   # 13C
    "H":  0.000150,  # 2H  (deuterium)
    "N":  0.003700,  # 15N
    "S":  0.007500,  # 33S  (M+1 contributor; 34S → M+2)
    "Si": 0.050000,  # 29Si
    "P":  0.007500,  # 33P (trace; 31P has no stable +1 isotope — keep small)
}

# Isotope contributions to M+2 (fraction of monoisotopic peak per atom)
_M2_CONTRIB_LINEAR: dict[str, float] = {
    "S":  0.04250,   # 34S per S atom (dominant source for organosulphur)
    "Cl": 0.32500,   # 37Cl per Cl atom (binomial handled below for multi-Cl)
    "Br": 0.97000,   # 81Br per Br atom
    "Si": 0.033900,  # 30Si
    "O":  0.000400,  # 18O (very small)
}

# Minimum M+2 predicted fraction to bother scoring (avoids noise for C/H/N/O)
_M2_THRESHOLD: float = 0.030

# Confidence weight vector when all components are active
# Weights sum to 1.0 for base score (additive corrections applied separately)
_WEIGHTS_FULL: dict[str, float] = {
    "mass_accuracy": 0.30,
    "m1":            0.25,
    "m2":            0.15,
    "frag":          0.10,
    "filter":        0.20,
}

# Weights when M+2 is not informative (no S/Cl/Br) — redistribute M+2 weight
_WEIGHTS_NO_M2: dict[str, float] = {
    "mass_accuracy": 0.35,
    "m1":            0.35,
    "m2":            0.00,
    "frag":          0.10,
    "filter":        0.20,
}

# Weights when fragmentation rules are disabled
_WEIGHTS_NO_FRAG: dict[str, float] = {
    "mass_accuracy": 0.35,
    "m1":            0.30,
    "m2":            0.15,
    "frag":          0.00,
    "filter":        0.20,
}

_WEIGHTS_NO_M2_NO_FRAG: dict[str, float] = {
    "mass_accuracy": 0.40,
    "m1":            0.40,
    "m2":            0.00,
    "frag":          0.00,
    "filter":        0.20,
}


# ---------------------------------------------------------------------------
# Public: parse peak text into intensity map
# ---------------------------------------------------------------------------

def parse_intensity_map(peak_text: str) -> dict[int, float]:
    """
    Parse a raw SDF/MSP peak field string into ``{nominal_mz: intensity}``.

    Uses the shared tokeniser from ``sdf_parser.parse_peaks_with_intensity``.
    Returns an empty dict on failure.  The intensities are stored as-is
    (not normalised here; callers that need relative fractions divide by the
    maximum value themselves).

    If all intensities are identical (flat spectrum, e.g. CSV with intensity
    all 999), returns the dict unchanged but the caller should disable M+1
    scoring because no isotope information is present.
    """
    if not peak_text:
        return {}
    try:
        from .sdf_parser import parse_peaks_with_intensity
        pairs = parse_peaks_with_intensity(peak_text)
        return {mz: inten for mz, inten in pairs}
    except Exception:
        return {}


def intensity_map_is_flat(intensity_map: dict[int, float]) -> bool:
    """Return True when all intensities are the same (no isotope information)."""
    if len(intensity_map) < 2:
        return True
    vals = list(intensity_map.values())
    return max(vals) == min(vals)


# ---------------------------------------------------------------------------
# Public: main scoring entry point
# ---------------------------------------------------------------------------

def score_compound(
    all_candidates: dict[int, list[dict]],
    intensity_map: dict[int, float],
    parent_composition: dict[str, int],
    parent_dbe: float,
    *,
    mol_block: str | None = None,
    enable_isotope: bool = True,
    enable_neutral_loss: bool = True,
    enable_complementary: bool = True,
    enable_dbe_penalty: bool = True,
    enable_fragmentation: bool = True,
    enable_stable_ions: bool = True,
    enable_even_odd: bool = True,
    fragmentation_rules_enabled: bool = False,
    tolerance: float = 0.5,
    electron_mode: str = "remove",
    n_passes: int = 3,
) -> dict[int, list[dict]]:
    """
    Multi-evidence confidence scoring for all peaks of one compound.

    Parameters
    ----------
    all_candidates          : {mz: [candidate_dict, ...]}
    intensity_map           : {nominal_mz: intensity}, whole spectrum
    parent_composition      : elemental composition of intact molecule
    parent_dbe              : DBE of parent molecule
    mol_block               : raw MDL MOL block string (for fragmentation check)
    enable_isotope          : compute M+1/M+2 isotope score  (A)
    enable_neutral_loss     : neutral-loss cross-check        (C)
    enable_complementary    : complementary-ion pair check    (multi-peak)
    enable_dbe_penalty      : DBE upper-bound penalty         (D)
    enable_fragmentation    : integrate fragmentation score   (B)
    enable_stable_ions      : stable-ion library bonus        (E)
    enable_even_odd         : even/odd-electron preference    (F)
    fragmentation_rules_enabled : whether fragmentation_rule annotation ran
    tolerance               : peak-matching tolerance in Da (default 0.5)
    electron_mode           : "remove" | "add" | "none"
    n_passes                : number of iterative scoring passes (default 3)

    Returns
    -------
    dict[int, list[dict]]
        Same structure as *all_candidates*, with each candidate dict augmented:
        ``confidence``      float 0–1
        ``confidence_pct``  int 0–100
        ``evidence_tags``   list[str]
        ``m1_score``        float
        ``m2_score``        float
        ``nl_score``        float
        ``comp_score``      float
        ``dbe_penalty``     float
        ``frag_score``      float
        ``stable_bonus``    float
        ``even_odd_score``  float
        Sorted by confidence descending within each peak.
    """
    if not all_candidates:
        return all_candidates

    # Determine if isotope information is available
    flat_spectrum = intensity_map_is_flat(intensity_map) if intensity_map else True
    has_mol = bool(mol_block and mol_block.strip())
    base_intensity = max(intensity_map.values(), default=1.0) if intensity_map else 1.0

    # Parent nominal ion m/z for complementary-ion check
    parent_nominal_mz = _parent_nominal_mz(parent_composition, electron_mode)

    # Deep-copy candidates so we don't mutate the caller's dicts
    scored: dict[int, list[dict]] = {
        mz: [_copy_candidate(c) for c in cands]
        for mz, cands in all_candidates.items()
    }

    # ── Pass 1: individual per-candidate scoring ──────────────────────────
    for mz, cands in scored.items():
        for cand in cands:
            comp = cand.get("_composition", {})

            # A — isotope M+1 / M+2
            if enable_isotope and not flat_spectrum and intensity_map:
                m1, m2, iso_tags = _score_isotope(comp, intensity_map, mz, parent_nominal_mz)
            else:
                m1, m2, iso_tags = 0.5, 0.5, []

            # B — fragmentation rule
            frag = _score_fragmentation(cand, fragmentation_rules_enabled, has_mol)

            # D — DBE upper-bound penalty
            dbe_pen = _dbe_penalty(cand, parent_dbe) if enable_dbe_penalty else 0.0

            # E — stable ion library
            stable_bonus = 0.0
            stable_tag = ""
            if enable_stable_ions:
                si = lookup_stable_ion(comp, mz)
                if si:
                    stable_bonus = STABLE_ION_BONUS
                    stable_tag = "STABLE({})".format(si[0])

            # F — even/odd electron preference (E5: with mass-range adjustment)
            even_odd_sc, eo_tag = _score_even_odd(cand, electron_mode, parent_nominal_mz) if enable_even_odd else (0.5, "")

            # Mass accuracy
            delta = abs(cand.get("delta_mass", 0.0))
            mass_acc = max(0.0, 1.0 - delta / max(tolerance, 1e-9))

            # Filter pass
            filter_ok = cand.get("filter_passed", True)
            filter_sc = 1.0 if filter_ok else 0.3

            # Determine weight vector
            use_m2 = (m2 != 0.5)  # 0.5 is the "neutral/uninformative" default
            use_frag = enable_fragmentation and fragmentation_rules_enabled
            weights = _pick_weights(use_m2, use_frag)

            # Base confidence
            base = (
                weights["mass_accuracy"] * mass_acc
                + weights["m1"]          * m1
                + weights["m2"]          * m2
                + weights["frag"]        * frag
                + weights["filter"]      * filter_sc
            )

            # Additive corrections (Pass 1 only; NL and COMP added in later passes)
            conf = max(0.0, min(1.0, base + dbe_pen + stable_bonus))

            # Build evidence tags
            tags: list[str] = list(iso_tags)
            if stable_tag:
                tags.append(stable_tag)
            if eo_tag:
                tags.append(eo_tag)
            if dbe_pen < 0:
                tags.append("DBE↑")

            cand.update({
                "confidence":     conf,
                "confidence_pct": int(round(conf * 100)),
                "evidence_tags":  tags,
                "m1_score":       m1,
                "m2_score":       m2,
                "nl_score":       0.0,
                "comp_score":     0.0,
                "dbe_penalty":    dbe_pen,
                "frag_score":     frag,
                "stable_bonus":   stable_bonus,
                "even_odd_score": even_odd_sc,
                "_mass_acc":      mass_acc,
                "_filter_sc":     filter_sc,
                "_weights":       weights,
            })

        # Sort by confidence descending after Pass 1
        cands.sort(key=lambda c: c["confidence"], reverse=True)

    if n_passes < 2:
        _finalise(scored)
        return scored

    # ── Pass 2: neutral-loss cross-check ─────────────────────────────────
    if enable_neutral_loss:
        nl_boosts: dict[int, float] = {mz: 0.0 for mz in scored}
        nl_new_tags: dict[int, list[str]] = {mz: [] for mz in scored}

        peak_mzs = sorted(scored.keys())
        for i, mz_a in enumerate(peak_mzs):
            for mz_b in peak_mzs[:i]:
                delta_nom = mz_a - mz_b
                if delta_nom <= 0:
                    continue
                matches = losses_for_delta(delta_nom)
                if not matches:
                    continue
                # Use top-ranked candidate from Pass 1
                top_a = scored[mz_a][0] if scored[mz_a] else None
                top_b = scored[mz_b][0] if scored[mz_b] else None
                if top_a is None or top_b is None:
                    continue
                comp_a = top_a.get("_composition", {})
                comp_b = top_b.get("_composition", {})
                for nl_name, nl_formula in matches:
                    if _formula_difference_matches(comp_a, comp_b, nl_formula):
                        w_a = _intensity_weight(mz_a, intensity_map, base_intensity)
                        w_b = _intensity_weight(mz_b, intensity_map, base_intensity)
                        weight = math.sqrt(w_a * w_b)
                        boost = min(0.35, 0.15 * weight)
                        if boost > nl_boosts[mz_a]:
                            nl_boosts[mz_a] = boost
                            nl_new_tags[mz_a] = ["NL({},{})".format(nl_name, delta_nom)]
                        if boost > nl_boosts[mz_b]:
                            nl_boosts[mz_b] = boost
                            nl_new_tags[mz_b] = ["NL({},{})".format(nl_name, delta_nom)]
                        break  # first matching neutral loss per pair is sufficient

        # Apply NL boosts and re-rank
        for mz, cands in scored.items():
            boost = nl_boosts[mz]
            tags = nl_new_tags[mz]
            for cand in cands:
                # Boost applies to the TOP candidate at this peak (index 0 after Pass 1)
                # Other candidates at this peak also share the boost (conservative)
                cand["nl_score"] = boost
                cand["evidence_tags"] = cand["evidence_tags"] + tags
                conf_updated = max(0.0, min(1.0, cand["confidence"] + boost))
                cand["confidence"] = conf_updated
                cand["confidence_pct"] = int(round(conf_updated * 100))
            cands.sort(key=lambda c: c["confidence"], reverse=True)

    if n_passes < 3:
        _finalise(scored)
        return scored

    # ── Pass 3: complementary-ion pair check ─────────────────────────────
    if enable_complementary:
        comp_boosts: dict[int, float] = {mz: 0.0 for mz in scored}

        peak_mzs = sorted(scored.keys())
        for i, mz_a in enumerate(peak_mzs):
            for mz_b in peak_mzs[:i]:
                pair_sum = mz_a + mz_b
                if pair_sum not in (parent_nominal_mz - 1, parent_nominal_mz, parent_nominal_mz + 1):
                    continue
                top_a = scored[mz_a][0] if scored[mz_a] else None
                top_b = scored[mz_b][0] if scored[mz_b] else None
                if top_a is None or top_b is None:
                    continue
                comp_a = top_a.get("_composition", {})
                comp_b = top_b.get("_composition", {})
                if _formula_sum_matches(comp_a, comp_b, parent_composition):
                    boost = 0.20
                    if boost > comp_boosts[mz_a]:
                        comp_boosts[mz_a] = boost
                    if boost > comp_boosts[mz_b]:
                        comp_boosts[mz_b] = boost

        # Apply COMP boosts and re-rank
        for mz, cands in scored.items():
            boost = comp_boosts[mz]
            if boost <= 0:
                continue
            for cand in cands:
                cand["comp_score"] = boost
                cand["evidence_tags"] = cand["evidence_tags"] + ["COMP"]
                conf_updated = max(0.0, min(1.0, cand["confidence"] + boost))
                cand["confidence"] = conf_updated
                cand["confidence_pct"] = int(round(conf_updated * 100))
            cands.sort(key=lambda c: c["confidence"], reverse=True)

    # ── Pass 4: Kendrick series detection (E1) ─────────────────────────────
    if enable_complementary:  # Use same enable flag since it's a multi-peak analysis
        kendrick_deltas = {14: "CH2", 26: "C2H2", 18: "H2O"}
        kendrick_boosts: dict[int, float] = {mz: 0.0 for mz in scored}

        peak_mzs = sorted(scored.keys())
        for delta, formula_name in kendrick_deltas.items():
            # For each peak, check if peaks exist at mz±delta, mz±2×delta
            for i, mz_center in enumerate(peak_mzs):
                series_peaks = [mz_center]
                # Check forward and backward
                for mult in [1, 2]:
                    if mz_center + mult * delta in peak_mzs:
                        series_peaks.append(mz_center + mult * delta)
                    if mz_center - mult * delta in peak_mzs:
                        series_peaks.append(mz_center - mult * delta)

                # If ≥3 peaks form a series, check formula consistency
                if len(series_peaks) >= 3:
                    series_peaks_sorted = sorted(series_peaks)
                    consistent = True
                    # Check that consecutive peaks differ by the expected delta
                    for j in range(len(series_peaks_sorted) - 1):
                        diff = series_peaks_sorted[j + 1] - series_peaks_sorted[j]
                        if abs(diff - delta) > 1:  # Within ±1 mass tolerance
                            consistent = False
                            break

                    if consistent:
                        # Boost all members of the series
                        boost = 0.15
                        for peak_mz in series_peaks_sorted:
                            if boost > kendrick_boosts[peak_mz]:
                                kendrick_boosts[peak_mz] = boost

        # Apply Kendrick boosts and re-rank
        for mz, cands in scored.items():
            boost = kendrick_boosts[mz]
            if boost <= 0:
                continue
            for cand in cands:
                cand["kendrick_score"] = boost
                cand["evidence_tags"] = cand["evidence_tags"] + ["SERIES(CH2)"]
                conf_updated = max(0.0, min(1.0, cand["confidence"] + boost))
                cand["confidence"] = conf_updated
                cand["confidence_pct"] = int(round(conf_updated * 100))
            cands.sort(key=lambda c: c["confidence"], reverse=True)

    _finalise(scored)
    return scored


# ---------------------------------------------------------------------------
# Component A: Isotope M+1 / M+2 scoring
# ---------------------------------------------------------------------------

def _score_isotope(
    composition: dict[str, int],
    intensity_map: dict[int, float],
    mz: int,
    parent_nominal_mz: int = None,
) -> tuple[float, float, list[str]]:
    """
    Return (m1_score, m2_score, evidence_tags) for *composition* at *mz*.

    m1_score and m2_score are both in [0.0, 1.0].
    If M+2 is not informative (predicted < 3%), m2_score is returned as 0.5
    (neutral / does not count against the candidate).

    If parent_nominal_mz is provided and mz < parent_nominal_mz * 0.5,
    returns neutral scores (fragment too small for isotope analysis).
    """
    mono_int = intensity_map.get(mz, 0.0)
    if mono_int <= 0:
        return 0.5, 0.5, []

    # M+1 mass-range guard: skip isotope analysis for very small fragments
    if parent_nominal_mz is not None and mz < parent_nominal_mz * 0.5:
        return 0.5, 0.5, []

    # ── M+1 ────────────────────────────────────────────────────────────────
    pred_m1 = sum(
        composition.get(el, 0) * frac
        for el, frac in _M1_CONTRIB.items()
    )
    obs_m1_int = intensity_map.get(mz + 1, 0.0)
    obs_m1 = obs_m1_int / mono_int

    tol_m1 = max(0.030, pred_m1 * 0.30)
    dev_m1 = abs(pred_m1 - obs_m1)
    m1_score = 1.0 / (1.0 + (dev_m1 / max(tol_m1, 1e-9)) ** 2)

    if dev_m1 < tol_m1 * 0.5:
        m1_tag = "M+1+"
    elif dev_m1 < tol_m1:
        m1_tag = "M+1~"
    else:
        m1_tag = "M+1-"

    # ── M+2 ────────────────────────────────────────────────────────────────
    pred_m2 = _predict_m2_fraction(composition)
    m2_score = 0.5  # default: neutral
    m2_tag = ""

    if pred_m2 >= _M2_THRESHOLD:
        obs_m2_int = intensity_map.get(mz + 2, 0.0)
        obs_m2 = obs_m2_int / mono_int
        tol_m2 = max(0.050, pred_m2 * 0.40)
        dev_m2 = abs(pred_m2 - obs_m2)
        m2_score = 1.0 / (1.0 + (dev_m2 / max(tol_m2, 1e-9)) ** 2)
        if dev_m2 < tol_m2 * 0.5:
            m2_tag = "M+2+"
        elif dev_m2 < tol_m2:
            m2_tag = "M+2~"
        else:
            m2_tag = "M+2-"

    tags = [t for t in [m1_tag, m2_tag] if t]
    return m1_score, m2_score, tags


def _predict_m2_fraction(composition: dict[str, int]) -> float:
    """
    Predict the M+2 intensity as a fraction of the monoisotopic peak.

    For multi-Cl and multi-Br compounds uses the full binomial expansion
    (via exact isotope pattern when available), otherwise a linear
    approximation per atom.
    """
    n_cl = composition.get("Cl", 0)
    n_br = composition.get("Br", 0)
    n_s  = composition.get("S",  0)
    n_si = composition.get("Si", 0)

    if n_cl == 0 and n_br == 0 and n_s == 0 and n_si == 0:
        return 0.0  # below threshold for pure C/H/N/O

    try:
        from .isotope import isotope_pattern
        pattern = isotope_pattern(composition)
        if not pattern:
            raise ValueError("empty pattern")
        mono   = next((p for p in pattern if p.get("nominal_offset", -1) == 0), None)
        m2_pks = [p for p in pattern if p.get("nominal_offset", -1) == 2]
        if mono and m2_pks and mono.get("relative_abundance", 0) > 0:
            m2_total = sum(p.get("relative_abundance", 0) for p in m2_pks)
            return m2_total / mono["relative_abundance"]
    except Exception:
        pass

    # Fallback: linear approximation
    pred = (
        n_s  * _M2_CONTRIB_LINEAR["S"]
        + n_si * _M2_CONTRIB_LINEAR["Si"]
    )
    # Cl binomial: P(exactly one 37Cl) term dominates for small n_cl
    if n_cl == 1:
        pred += 0.325
    elif n_cl == 2:
        pred += 2 * 0.325 * 0.675  # dominant M+2 term from 2-Cl binomial
    elif n_cl > 2:
        pred += n_cl * 0.325  # rough upper bound; full binomial would be lower
    # Br: each Br contributes ~97% to M+2
    pred += n_br * 0.970
    return pred


# ---------------------------------------------------------------------------
# Component B: Fragmentation rule score
# ---------------------------------------------------------------------------

def _score_fragmentation(
    candidate: dict,
    fragmentation_rules_enabled: bool,
    has_mol_block: bool,
) -> float:
    """
    Return a 0–1 score based on the fragmentation-rule annotation.

    0.5  neutral (rules not enabled or no mol_block)
    1.0  a known EI pathway matched
    0.2  mol_block present + rules enabled + no pathway matched (unlikely)
    """
    if not fragmentation_rules_enabled:
        return 0.5
    rule = candidate.get("fragmentation_rule", None)
    if rule is None:
        return 0.5  # annotation did not run
    if rule:
        return 1.0  # matched a pathway
    # No pathway matched
    return 0.2 if has_mol_block else 0.5


# ---------------------------------------------------------------------------
# Component D: DBE upper-bound penalty
# ---------------------------------------------------------------------------

def _dbe_penalty(candidate: dict, parent_dbe: float) -> float:
    """
    Return -0.25 if fragment DBE > parent_dbe + 1, else 0.0.

    Radical cation fragments can have DBE = parent_DBE + 0.5 (half-integer
    from odd-electron counting).  The +1 buffer handles this and minor
    rearrangements.
    """
    frag_dbe = candidate.get("dbe", 0.0)
    return -0.25 if frag_dbe > parent_dbe + 1.0 else 0.0


# ---------------------------------------------------------------------------
# Component E: Stable-ion bonus — see stable_ions.py (applied inline above)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Component F: Even/odd electron preference
# ---------------------------------------------------------------------------

def _score_even_odd(
    candidate: dict,
    electron_mode: str,
    parent_nominal_mz: int = None,
) -> tuple[float, str]:
    """
    Score based on the even-electron / odd-electron nature of the fragment.

    In EI:
    - The molecular ion (M+•) is always odd-electron (radical cation)
    - Simple bond cleavage fragments: odd-electron (same parity as M)
    - Rearrangement fragments: even-electron (closed-shell cation)

    A closed-shell cation (even-electron) has an integer DBE when computed
    with the standard formula: DBE = C - H/2 + N/2 + 1.
    A radical cation (odd-electron) has a half-integer DBE
    (e.g. 0.5, 1.5, ...).

    EI produces predominantly even-electron fragment ions, with odd-electron
    fragments appearing mainly at high m/z (close to the molecular ion).

    E5: Mass-range dependent scoring:
    - mz > 0.8 × parent_mz: even=0.6, odd=1.0 (high-mass: radical cations dominate)
    - mz < 0.3 × parent_mz: even=0.8, odd=0.8 (low-mass: no preference)
    - middle: even=1.0, odd=0.7 (current, default)

    Score:
    - even-electron (integer DBE): 1.0 (or range-adjusted)
    - odd-electron (half-integer DBE): 0.7 (plausible, or range-adjusted)
    - DBE not calculable: 0.5 (neutral)
    """
    dbe = candidate.get("dbe", None)
    if dbe is None:
        return 0.5, ""
    # Check if DBE is (approximately) integer or half-integer
    frac = abs(dbe - round(dbe))  # should be ~0 (integer) or ~0.5 (half-integer)

    # Default scores
    even_score = 1.0
    odd_score = 0.7

    # E5: Adjust scores based on mass range
    if parent_nominal_mz is not None:
        mz = candidate.get("ion_mass", 0)
        if mz > 0 and parent_nominal_mz > 0:
            if mz > 0.8 * parent_nominal_mz:
                # High-mass: radical cations dominate
                even_score = 0.6
                odd_score = 1.0
            elif mz < 0.3 * parent_nominal_mz:
                # Low-mass: no preference
                even_score = 0.8
                odd_score = 0.8
            # else: middle range uses default scores

    if frac < 0.1:
        return even_score, "ee"   # even-electron: more stable, preferred
    if abs(frac - 0.5) < 0.1:
        return odd_score, "oe"   # odd-electron: possible but less common
    return 0.5, ""


# ---------------------------------------------------------------------------
# Neutral-loss helpers (used in Pass 2)
# ---------------------------------------------------------------------------

def _formula_difference_matches(
    comp_a: dict[str, int],
    comp_b: dict[str, int],
    nl_formula: dict[str, int],
) -> bool:
    """
    Return True if comp_a - comp_b == nl_formula (within ±1 H for
    hydrogen-rearrangement tolerance).

    comp_a must correspond to the higher-m/z peak (mz_a > mz_b) so that
    the difference comp_a - comp_b is positive for normal neutral loss.
    """
    all_els = set(comp_a) | set(comp_b) | set(nl_formula)
    diff = {el: comp_a.get(el, 0) - comp_b.get(el, 0) for el in all_els}
    diff = {el: v for el, v in diff.items() if v != 0}

    # Guard: negative elements mean comp_b > comp_a for that element
    if any(v < 0 for v in diff.values()):
        return False

    # Exact match
    nl_clean = {el: v for el, v in nl_formula.items() if v != 0}
    if diff == nl_clean:
        return True

    # ±1 H rearrangement
    for h_delta in (-1, 1):
        adjusted = dict(nl_clean)
        adjusted["H"] = adjusted.get("H", 0) + h_delta
        adjusted = {el: v for el, v in adjusted.items() if v != 0}
        if diff == adjusted:
            return True

    return False


def _formula_sum_matches(
    comp_a: dict[str, int],
    comp_b: dict[str, int],
    parent_comp: dict[str, int],
) -> bool:
    """
    Return True if comp_a + comp_b == parent_comp within ±2 H (rearrangements).
    """
    all_els = set(comp_a) | set(comp_b) | set(parent_comp)
    combined = {el: comp_a.get(el, 0) + comp_b.get(el, 0) for el in all_els}
    combined = {el: v for el, v in combined.items() if v != 0}
    parent_clean = {el: v for el, v in parent_comp.items() if v != 0}

    if combined == parent_clean:
        return True

    for h_delta in (-2, -1, 1, 2):
        adjusted = dict(parent_clean)
        adjusted["H"] = adjusted.get("H", 0) + h_delta
        adjusted = {el: v for el, v in adjusted.items() if v != 0}
        if combined == adjusted:
            return True

    return False


# ---------------------------------------------------------------------------
# Complementary-ion helpers (used in Pass 3)
# ---------------------------------------------------------------------------

def _parent_nominal_mz(
    parent_composition: dict[str, int],
    electron_mode: str,
) -> int:
    """Compute the nominal molecular-ion m/z for the EI parent ion."""
    from .calculator import exact_mass
    from .constants import ELECTRON_MASS
    neutral_mass = exact_mass(parent_composition)
    if electron_mode == "remove":
        ion_mass = neutral_mass - ELECTRON_MASS
    elif electron_mode == "add":
        ion_mass = neutral_mass + ELECTRON_MASS
    else:
        ion_mass = neutral_mass
    return int(round(ion_mass))


# ---------------------------------------------------------------------------
# Intensity weighting (for neutral-loss boost magnitude)
# ---------------------------------------------------------------------------

def _intensity_weight(
    mz: int,
    intensity_map: dict[int, float],
    base_intensity: float,
) -> float:
    """
    Return an intensity weight multiplier for *mz*.

    base peak (= 100 % intensity) → 2.0
    > 20 % of base              → 1.5
    otherwise                   → 1.0
    """
    if base_intensity <= 0:
        return 1.0
    rel = intensity_map.get(mz, 0.0) / base_intensity
    if rel >= 0.99:
        return 2.0
    if rel >= 0.20:
        return 1.5
    return 1.0


# ---------------------------------------------------------------------------
# Weight selection
# ---------------------------------------------------------------------------

def _pick_weights(use_m2: bool, use_frag: bool) -> dict[str, float]:
    if use_m2 and use_frag:
        return _WEIGHTS_FULL
    if use_m2 and not use_frag:
        return {**_WEIGHTS_FULL, "frag": 0.0,
                "mass_accuracy": _WEIGHTS_FULL["mass_accuracy"] + 0.05,
                "m1": _WEIGHTS_FULL["m1"] + 0.05}
    if not use_m2 and use_frag:
        return _WEIGHTS_NO_M2
    return _WEIGHTS_NO_M2_NO_FRAG


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _copy_candidate(c: dict) -> dict:
    """Shallow copy with a new evidence_tags list."""
    copy = dict(c)
    copy["evidence_tags"] = list(c.get("evidence_tags", []))
    return copy


def _finalise(scored: dict[int, list[dict]]) -> None:
    """Ensure all candidates have the expected keys (fill defaults)."""
    for cands in scored.values():
        for cand in cands:
            cand.setdefault("confidence",     0.5)
            cand.setdefault("confidence_pct", 50)
            cand.setdefault("evidence_tags",  [])
            cand.setdefault("nl_score",       0.0)
            cand.setdefault("comp_score",     0.0)
            cand.setdefault("dbe_penalty",    0.0)
