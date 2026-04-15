"""
tests/test_confidence.py
========================
Unit tests for the multi-evidence confidence scoring module.

All tests use synthetic in-memory data — no file I/O required.
"""

import pytest

from ei_fragment_calculator.confidence import (
    score_compound,
    parse_intensity_map,
    intensity_map_is_flat,
    _score_isotope,
    _dbe_penalty,
    _formula_difference_matches,
    _formula_sum_matches,
    _parent_nominal_mz,
)
from ei_fragment_calculator.neutral_losses import NEUTRAL_LOSSES, losses_for_delta
from ei_fragment_calculator.stable_ions import STABLE_IONS, lookup_stable_ion


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candidate(
    formula_str: str,
    composition: dict,
    neutral_mass: float,
    dbe: float,
    delta_mass: float = 0.001,
    filter_passed: bool = True,
    rule: str = "",
    rule_score: float = 1.0,
) -> dict:
    """Construct a minimal candidate dict as produced by find_fragment_candidates."""
    return {
        "formula":            formula_str,
        "_composition":       composition,
        "neutral_mass":       neutral_mass,
        "ion_mass":           neutral_mass - 0.000549,
        "delta_mass":         delta_mass,
        "dbe":                dbe,
        "filter_passed":      filter_passed,
        "fragmentation_rule": rule,
        "rule_score":         rule_score,
        "isotope_score":      0.0,
    }


CAFFEINE_PARENT = {"C": 8, "H": 10, "N": 4, "O": 2}
CAFFEINE_DBE    = 6.0


# ---------------------------------------------------------------------------
# parse_intensity_map
# ---------------------------------------------------------------------------

class TestParseIntensityMap:

    def test_standard_sdf_format(self):
        peak_text = "82 331\n83 37\n84 5\n109 710"
        result = parse_intensity_map(peak_text)
        assert result[82] == 331
        assert result[83] == 37
        assert result[84] == 5
        assert result[109] == 710

    def test_single_line_interleaved(self):
        peak_text = "41 999 43 850 55 620 77 412"
        result = parse_intensity_map(peak_text)
        assert result[41] == 999.0
        assert result[77] == 412.0

    def test_empty_string(self):
        assert parse_intensity_map("") == {}

    def test_float_mz_rounded(self):
        # Exact-mass formatted peaks should be rounded to nearest integer key
        peak_text = "82.077702 331\n83.081250 37"
        result = parse_intensity_map(peak_text)
        assert 82 in result
        assert result[82] == 331.0


class TestIntensityMapIsFlat:

    def test_flat_all_same(self):
        assert intensity_map_is_flat({82: 999, 83: 999, 84: 999}) is True

    def test_not_flat(self):
        assert intensity_map_is_flat({82: 331, 83: 37, 84: 5}) is False

    def test_single_entry(self):
        assert intensity_map_is_flat({82: 100}) is True

    def test_empty(self):
        assert intensity_map_is_flat({}) is True


# ---------------------------------------------------------------------------
# Component A: Isotope M+1 scoring
# ---------------------------------------------------------------------------

class TestIsotopeM1Scoring:

    def test_c6h10_beats_c2n3o_at_caffeine_m82(self):
        """C6H10 should score higher than C2N3O at m/z 82 for Caffeine.

        Observed M+1 ratio for Caffeine at m/z 82: 37/331 = 11.2%
        C6H10 predicts: 6 × 1.11% = 6.66%  →  closer to 11.2% than
        C2N3O which predicts: 2 × 1.11% + 3 × 0.37% = 3.33%
        """
        intensity_map = {82: 331, 83: 37, 84: 5}
        c6h10 = {"C": 6, "H": 10}
        c2n3o = {"C": 2, "N": 3, "O": 1}
        m1_c6h10, _, _ = _score_isotope(c6h10, intensity_map, 82)
        m1_c2n3o, _, _ = _score_isotope(c2n3o, intensity_map, 82)
        assert m1_c6h10 > m1_c2n3o, (
            "C6H10 M+1 score ({:.3f}) should beat C2N3O ({:.3f}) at m/z 82".format(
                m1_c6h10, m1_c2n3o))

    def test_score_is_normalized(self):
        """All M+1 scores must lie within [0, 1]."""
        intensity_map = {50: 1000, 51: 60}
        for comp in [{"C": 4}, {"C": 6, "H": 10}, {"N": 3}]:
            m1, m2, _ = _score_isotope(comp, intensity_map, 50)
            assert 0.0 <= m1 <= 1.0
            assert 0.0 <= m2 <= 1.0

    def test_zero_mono_intensity_returns_neutral(self):
        """When monoisotopic peak is absent, return neutral 0.5."""
        intensity_map = {83: 37}   # 82 missing
        m1, m2, tags = _score_isotope({"C": 6, "H": 10}, intensity_map, 82)
        assert m1 == 0.5
        assert m2 == 0.5

    def test_m1_tag_good_match(self):
        """Expect M+1+ tag when prediction closely matches observation."""
        # C4H8 → pred M+1 = 4×1.11% = 4.44%
        # obs = 40/900 = 4.44% → perfect match
        intensity_map = {56: 900, 57: 40}
        _, _, tags = _score_isotope({"C": 4, "H": 8}, intensity_map, 56)
        assert "M+1+" in tags


class TestIsotopeM2Scoring:

    def test_chlorine_compound_gets_high_m2_score(self):
        """A compound with 2 Cl should score well when M+2 ≈ 66% of M."""
        # For 2 Cl: dominant M+2 term ≈ 2×0.325×0.675 ≈ 44% (binomial)
        # Use approximate: just verify M+2 score > 0.5 when M+2 is present
        intensity_map = {82: 1000, 83: 25, 84: 440}  # large M+2 for Cl2
        comp = {"C": 2, "Cl": 2}
        _, m2, _ = _score_isotope(comp, intensity_map, 82)
        assert m2 > 0.5, "C2Cl2 should get M+2 score > 0.5 with realistic isotope pattern"

    def test_pure_cho_no_m2_score(self):
        """Pure C/H/O formula gets neutral (0.5) M+2 score — not enough S/Cl/Br."""
        intensity_map = {82: 1000, 84: 2}
        _, m2, _ = _score_isotope({"C": 6, "H": 10}, intensity_map, 82)
        assert m2 == 0.5, "C/H only formula should return neutral M+2 score"

    def test_sulfur_compound_m2_tag(self):
        """S-containing fragment gets M+2 scoring tag when M+2 present."""
        # S contributes 4.25% to M+2; with 2 S → 8.5%
        intensity_map = {94: 1000, 96: 85}
        _, m2, tags = _score_isotope({"C": 2, "S": 2}, intensity_map, 94)
        assert any("M+2" in t for t in tags), "Expected M+2 tag for S2 compound"


# ---------------------------------------------------------------------------
# Component D: DBE upper bound
# ---------------------------------------------------------------------------

class TestDbePenalty:

    def test_no_penalty_within_bound(self):
        c = _make_candidate("C5H8", {"C": 5, "H": 8}, 68.0, dbe=2.0)
        assert _dbe_penalty(c, parent_dbe=3.0) == 0.0

    def test_no_penalty_at_boundary(self):
        # DBE = parent + 1 → exactly at boundary → no penalty
        c = _make_candidate("C6H6", {"C": 6, "H": 6}, 78.0, dbe=4.0)
        assert _dbe_penalty(c, parent_dbe=3.0) == 0.0

    def test_penalty_above_bound(self):
        c = _make_candidate("C7H4", {"C": 7, "H": 4}, 88.0, dbe=5.5)
        assert _dbe_penalty(c, parent_dbe=3.0) == -0.25

    def test_penalty_magnitude(self):
        c = _make_candidate("X", {}, 0.0, dbe=100.0)
        assert _dbe_penalty(c, parent_dbe=3.0) == -0.25


# ---------------------------------------------------------------------------
# Component C: Neutral-loss cross-check helpers
# ---------------------------------------------------------------------------

class TestFormulaDifference:

    def test_exact_co_loss(self):
        comp_a = {"C": 7, "H": 10, "O": 1}
        comp_b = {"C": 6, "H": 10}
        nl_co  = {"C": 1, "O": 1}
        assert _formula_difference_matches(comp_a, comp_b, nl_co)

    def test_h2o_loss(self):
        comp_a = {"C": 4, "H": 8, "O": 1}
        comp_b = {"C": 4, "H": 6}
        nl_h2o = {"H": 2, "O": 1}
        assert _formula_difference_matches(comp_a, comp_b, nl_h2o)

    def test_rearrangement_h_tolerance(self):
        # ±1 H rearrangement: comp_a - comp_b = CO + 1H (McLafferty-type)
        comp_a = {"C": 7, "H": 11, "O": 1}
        comp_b = {"C": 6, "H": 10}
        nl_co  = {"C": 1, "O": 1}
        assert _formula_difference_matches(comp_a, comp_b, nl_co)

    def test_no_match(self):
        comp_a = {"C": 7, "H": 10, "N": 1}
        comp_b = {"C": 6, "H": 10}
        nl_co  = {"C": 1, "O": 1}
        assert not _formula_difference_matches(comp_a, comp_b, nl_co)

    def test_negative_diff_returns_false(self):
        # comp_b > comp_a for some element → invalid
        comp_a = {"C": 4, "H": 5}
        comp_b = {"C": 6, "H": 10}
        nl_co  = {"C": 1, "O": 1}
        assert not _formula_difference_matches(comp_a, comp_b, nl_co)


class TestFormulaSumMatches:

    def test_exact_match(self):
        comp_a  = {"C": 4, "H": 3}
        comp_b  = {"C": 2, "H": 3}
        parent  = {"C": 6, "H": 6}
        assert _formula_sum_matches(comp_a, comp_b, parent)

    def test_rearrangement_h2_tolerance(self):
        comp_a  = {"C": 4, "H": 4}    # +1 H rearrangement
        comp_b  = {"C": 2, "H": 3}
        parent  = {"C": 6, "H": 6}    # sum = C6H7 → off by 1H → within ±2H
        assert _formula_sum_matches(comp_a, comp_b, parent)

    def test_no_match(self):
        comp_a = {"C": 4, "H": 3}
        comp_b = {"C": 3, "H": 3}   # sum = C7H6 ≠ C6H6
        parent = {"C": 6, "H": 6}
        assert not _formula_sum_matches(comp_a, comp_b, parent)


# ---------------------------------------------------------------------------
# Neutral loss table integrity
# ---------------------------------------------------------------------------

class TestNeutralLossTable:

    def test_all_entries_have_int_delta(self):
        for name, (delta, formula_dict) in NEUTRAL_LOSSES.items():
            assert isinstance(delta, int), \
                "delta for '{}' must be int, got {}".format(name, type(delta))

    def test_all_entries_have_dict_formula(self):
        for name, (delta, formula_dict) in NEUTRAL_LOSSES.items():
            assert isinstance(formula_dict, dict), \
                "formula for '{}' must be dict".format(name)

    def test_all_formula_values_are_int(self):
        for name, (delta, formula_dict) in NEUTRAL_LOSSES.items():
            for el, count in formula_dict.items():
                assert isinstance(count, int), \
                    "count for element '{}' in '{}' must be int".format(el, name)

    def test_losses_for_delta_returns_correct_entries(self):
        entries = losses_for_delta(28)
        names = [n for n, _ in entries]
        # Both CO and C2H4 have delta=28
        assert "CO" in names
        assert "C2H4" in names

    def test_losses_for_delta_empty_for_unknown(self):
        assert losses_for_delta(9999) == []


# ---------------------------------------------------------------------------
# Stable ion library
# ---------------------------------------------------------------------------

class TestStableIons:

    def test_tropylium_found(self):
        result = lookup_stable_ion({"C": 7, "H": 7}, 91)
        assert result is not None
        name, ion_type = result
        assert "C7H7" in name or "tropylium" in name.lower()

    def test_phenyl_found(self):
        result = lookup_stable_ion({"C": 6, "H": 5}, 77)
        assert result is not None

    def test_wrong_mz_returns_none(self):
        # Tropylium at wrong m/z
        result = lookup_stable_ion({"C": 7, "H": 7}, 92)
        assert result is None

    def test_unknown_composition_returns_none(self):
        result = lookup_stable_ion({"C": 99, "H": 99}, 91)
        assert result is None


# ---------------------------------------------------------------------------
# Parent nominal m/z
# ---------------------------------------------------------------------------

class TestParentNominalMz:

    def test_caffeine(self):
        # Caffeine C8H10N4O2, exact mass 194.0804, EI+ → m/z ≈ 194
        mz = _parent_nominal_mz(CAFFEINE_PARENT, "remove")
        assert mz == 194

    def test_toluene(self):
        mz = _parent_nominal_mz({"C": 7, "H": 8}, "remove")
        assert mz == 92


# ---------------------------------------------------------------------------
# Integration: score_compound
# ---------------------------------------------------------------------------

class TestScoreCompound:

    def test_returns_same_peaks(self):
        """score_compound must return the same m/z keys as input."""
        cands = {
            82: [_make_candidate("C6H10", {"C": 6, "H": 10}, 82.078, 2.0)],
            109: [_make_candidate("C7H9N", {"C": 7, "H": 9, "N": 1}, 109.073, 3.0)],
        }
        imap = {82: 331, 83: 37, 109: 710, 110: 92}
        result = score_compound(cands, imap, CAFFEINE_PARENT, CAFFEINE_DBE)
        assert set(result.keys()) == {82, 109}

    def test_confidence_added_to_candidates(self):
        """Every returned candidate must have a confidence key."""
        cands = {
            82: [
                _make_candidate("C6H10",  {"C": 6, "H": 10},  82.078, 2.0),
                _make_candidate("C2N3O",  {"C": 2, "N": 3, "O": 1}, 82.017, 2.5),
            ],
        }
        imap = {82: 331, 83: 37}
        result = score_compound(cands, imap, CAFFEINE_PARENT, CAFFEINE_DBE)
        for cand in result[82]:
            assert "confidence" in cand
            assert 0.0 <= cand["confidence"] <= 1.0
            assert "evidence_tags" in cand

    def test_c6h10_ranked_above_c2n3o_at_caffeine_m82(self):
        """After scoring, C6H10 should be ranked above C2N3O at m/z 82.

        Real Caffeine data: m/z 82 = 331, m/z 83 = 37 (M+1 ratio 11.2%)
        C6H10 predicts M+1 ≈ 6.66%, C2N3O predicts ≈ 3.33%.
        C6H10 is closer to 11.2% so should outscore C2N3O.
        """
        cands = {
            82: [
                _make_candidate("C6H10", {"C": 6, "H": 10},  82.078, 2.0, delta_mass=0.001),
                _make_candidate("C2N3O", {"C": 2, "N": 3, "O": 1}, 82.017, 2.5, delta_mass=0.003),
            ],
        }
        imap = {82: 331, 83: 37, 84: 5}
        result = score_compound(cands, imap, CAFFEINE_PARENT, CAFFEINE_DBE, n_passes=1)
        top = result[82][0]
        assert top["formula"] == "C6H10", (
            "C6H10 should rank first at m/z 82, got {}".format(top["formula"]))

    def test_neutral_loss_co_boosts_both_peaks(self):
        """Peaks at 82 and 110 with Δ=28 and ΔFormula=CO should both get NL boost."""
        cands = {
            82:  [_make_candidate("C6H10",   {"C": 6, "H": 10},       82.078, 2.0)],
            110: [_make_candidate("C7H10O",  {"C": 7, "H": 10, "O": 1}, 110.073, 2.0)],
        }
        imap = {82: 331, 83: 37, 110: 92, 111: 12}
        result = score_compound(cands, imap, CAFFEINE_PARENT, CAFFEINE_DBE, n_passes=2)
        nl_82  = result[82][0].get("nl_score", 0.0)
        nl_110 = result[110][0].get("nl_score", 0.0)
        assert nl_82  > 0.0, "m/z 82 should receive a neutral-loss boost"
        assert nl_110 > 0.0, "m/z 110 should receive a neutral-loss boost"

    def test_complementary_ion_pair_boost(self):
        """Peaks summing to parent_mz with consistent formulas get COMP boost."""
        # Benzene C6H6, parent_mz = 78; peaks 51 + 27 = 78
        parent_comp = {"C": 6, "H": 6}
        cands = {
            51: [_make_candidate("C4H3", {"C": 4, "H": 3}, 51.023, 3.5)],
            27: [_make_candidate("C2H3", {"C": 2, "H": 3}, 27.023, 0.5)],
        }
        imap = {27: 120, 51: 100, 78: 999}
        result = score_compound(cands, imap, parent_comp, parent_dbe=4.0, n_passes=3)
        boost_51 = result[51][0].get("comp_score", 0.0)
        boost_27 = result[27][0].get("comp_score", 0.0)
        assert boost_51 > 0.0, "m/z 51 should get complementary-ion boost"
        assert boost_27 > 0.0, "m/z 27 should get complementary-ion boost"

    def test_empty_candidates_handled(self):
        result = score_compound({}, {}, CAFFEINE_PARENT, CAFFEINE_DBE)
        assert result == {}

    def test_no_op_when_all_disabled(self):
        """With all components disabled, candidates still get confidence field."""
        cands = {82: [_make_candidate("C6H10", {"C": 6, "H": 10}, 82.078, 2.0)]}
        result = score_compound(
            cands, {}, CAFFEINE_PARENT, CAFFEINE_DBE,
            enable_isotope=False,
            enable_neutral_loss=False,
            enable_complementary=False,
            enable_dbe_penalty=False,
            enable_stable_ions=False,
            enable_even_odd=False,
            n_passes=1,
        )
        assert "confidence" in result[82][0]

    def test_dbe_penalty_applied_to_high_dbe_candidate(self):
        """Candidate with DBE > parent_DBE + 1 should have lower confidence."""
        parent_dbe = 2.0
        low_dbe  = _make_candidate("C4H8",  {"C": 4, "H": 8},  56.062, dbe=1.0)
        high_dbe = _make_candidate("C6H2",  {"C": 6, "H": 2},  74.015, dbe=5.5)
        cands = {56:  [low_dbe], 74: [high_dbe]}
        result = score_compound(
            cands, {}, CAFFEINE_PARENT, parent_dbe,
            enable_isotope=False,
            enable_neutral_loss=False,
            enable_complementary=False,
            enable_dbe_penalty=True,
            enable_stable_ions=False,
            enable_even_odd=False,
            n_passes=1,
        )
        pen_low  = result[56][0].get("dbe_penalty", 0.0)
        pen_high = result[74][0].get("dbe_penalty", 0.0)
        assert pen_low  == 0.0,   "Low-DBE candidate should not be penalised"
        assert pen_high == -0.25, "High-DBE candidate should receive -0.25 penalty"

    def test_stable_ion_tropylium_gets_bonus(self):
        """Tropylium (C7H7+, m/z 91) should receive the stable-ion bonus."""
        tropylium = _make_candidate("C7H7", {"C": 7, "H": 7}, 91.054, dbe=4.5)
        other     = _make_candidate("C5H3N", {"C": 5, "H": 3, "N": 1}, 77.027, dbe=4.5)
        cands = {91: [tropylium, other]}
        result = score_compound(
            cands, {91: 999}, {"C": 8, "H": 8}, 5.0,
            enable_isotope=False,
            enable_neutral_loss=False,
            enable_complementary=False,
            enable_stable_ions=True,
            n_passes=1,
        )
        bonus_trop  = result[91][0].get("stable_bonus", 0.0)
        # Tropylium should be first after scoring (highest bonus)
        assert result[91][0]["formula"] == "C7H7"
        assert bonus_trop > 0.0

    def test_three_pass_refinement_improves_ranking(self):
        """Three passes should not degrade ranking vs. one pass for a clear case."""
        cands = {
            82: [
                _make_candidate("C6H10", {"C": 6, "H": 10}, 82.078, 2.0, 0.001),
                _make_candidate("C2N3O", {"C": 2, "N": 3, "O": 1}, 82.017, 2.5, 0.003),
            ],
            110: [
                _make_candidate("C7H10O", {"C": 7, "H": 10, "O": 1}, 110.073, 2.0),
            ],
        }
        imap = {82: 331, 83: 37, 84: 5, 110: 92, 111: 12}
        result_3 = score_compound(cands, imap, CAFFEINE_PARENT, CAFFEINE_DBE, n_passes=3)
        # C6H10 should still be top after 3 passes
        assert result_3[82][0]["formula"] == "C6H10"

    def test_candidates_sorted_by_confidence_descending(self):
        """Within each peak, candidates must be sorted best-first."""
        cands = {
            82: [
                _make_candidate("LowScore",  {"C": 1}, 82.0, dbe=0.0, filter_passed=False),
                _make_candidate("HighScore", {"C": 6, "H": 10}, 82.078, dbe=2.0),
            ]
        }
        result = score_compound(cands, {82: 331, 83: 37}, CAFFEINE_PARENT, CAFFEINE_DBE,
                                n_passes=1)
        # Higher-scoring candidate must come first
        confs = [c["confidence"] for c in result[82]]
        assert confs == sorted(confs, reverse=True)
