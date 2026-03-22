"""Tests for calculator.py — exact mass, DBE, electron correction, enumeration."""

import pytest
from ei_fragment_calculator.calculator import (
    exact_mass, ion_mass, calculate_dbe, is_valid_dbe, find_fragment_candidates
)
from ei_fragment_calculator.constants import ELECTRON_MASS


class TestExactMass:
    def test_methane(self):
        # CH4: 12 + 4 * 1.007825032 = 16.031300128
        mass = exact_mass({"C": 1, "H": 4})
        assert abs(mass - 16.031300) < 1e-4

    def test_water(self):
        # H2O: 2 * 1.007825032 + 15.994914620 = 18.010564684
        mass = exact_mass({"H": 2, "O": 1})
        assert abs(mass - 18.010565) < 1e-5

    def test_empty_is_zero(self):
        assert exact_mass({}) == 0.0


class TestIonMass:
    def test_remove_subtracts_electron(self):
        neutral = 100.0
        result  = ion_mass(neutral, "remove")
        assert abs(result - (neutral - ELECTRON_MASS)) < 1e-12

    def test_add_adds_electron(self):
        neutral = 100.0
        result  = ion_mass(neutral, "add")
        assert abs(result - (neutral + ELECTRON_MASS)) < 1e-12

    def test_none_unchanged(self):
        neutral = 100.0
        result  = ion_mass(neutral, "none")
        assert result == neutral

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="Invalid electron_mode"):
            ion_mass(100.0, "positive")


class TestDBE:
    def test_benzene(self):
        # C6H6: DBE = 1 + 6 - 6/2 = 4
        assert calculate_dbe({"C": 6, "H": 6}) == 4.0

    def test_methane_zero_dbe(self):
        # CH4: DBE = 1 + 1 - 4/2 = 0
        assert calculate_dbe({"C": 1, "H": 4}) == 0.0

    def test_radical_cation_half_integer(self):
        # C7H7• (tropylium): DBE = 1 + 7 - 7/2 = 4.5
        assert calculate_dbe({"C": 7, "H": 7}) == 4.5

    def test_valid_dbe_zero(self):
        assert is_valid_dbe(0.0) is True

    def test_valid_dbe_half(self):
        assert is_valid_dbe(0.5) is True

    def test_invalid_dbe_negative(self):
        assert is_valid_dbe(-0.5) is False

    def test_invalid_dbe_non_half_integer(self):
        assert is_valid_dbe(0.3) is False


class TestFindFragmentCandidates:
    def test_tropylium_from_toluene(self):
        # Toluene C7H8, tropylium C7H7+ at m/z 91
        parent = {"C": 7, "H": 8}
        results = find_fragment_candidates(91, parent, electron_mode="remove")
        formulas = [c["formula"] for c in results]
        assert "C7H7" in formulas

    def test_electron_mode_none_vs_remove(self):
        # With "none" mode the ion mass equals neutral mass, so a formula
        # whose neutral mass is exactly at the nominal value should be found.
        parent = {"C": 6, "H": 6}
        cands_none   = find_fragment_candidates(78, parent, electron_mode="none")
        cands_remove = find_fragment_candidates(78, parent, electron_mode="remove")
        # Both should find benzene C6H6 at nominal 78 (within ±0.5 Da)
        formulas_none   = [c["formula"] for c in cands_none]
        formulas_remove = [c["formula"] for c in cands_remove]
        assert "C6H6" in formulas_none
        assert "C6H6" in formulas_remove

    def test_no_candidates_for_impossible_mz(self):
        parent = {"C": 1, "H": 4}   # methane
        results = find_fragment_candidates(200, parent)
        assert results == []

    def test_all_candidates_within_tolerance(self):
        parent = {"C": 10, "H": 12, "O": 2}
        for mz in [77, 91, 105, 120]:
            for cand in find_fragment_candidates(mz, parent):
                assert abs(cand["delta_mass"]) <= 0.5
