"""Tests for isotope.py — isotope pattern simulation."""

import pytest
from ei_fragment_calculator.isotope import isotope_pattern, pattern_summary


class TestIsotopePattern:
    def test_monoisotopic_element_single_peak(self):
        # Fluorine has only one isotope (19F, abundance 1.0)
        # A single F atom should give exactly one peak at mass 18.998...
        pattern = isotope_pattern({"F": 1})
        assert len(pattern) == 1
        assert pattern[0]["relative_abundance"] == 100.0
        assert pattern[0]["nominal_offset"] == 0

    def test_carbon_two_isotopes(self):
        # One C atom: 12C (98.93%) and 13C (1.07%)
        pattern = isotope_pattern({"C": 1})
        assert len(pattern) == 2
        # Monoisotopic peak must be 100%
        mono = next(p for p in pattern if p["nominal_offset"] == 0)
        assert mono["relative_abundance"] == 100.0
        # M+1 peak ≈ 1.07/98.93 * 100 ≈ 1.08%
        m1 = next(p for p in pattern if p["nominal_offset"] == 1)
        assert 1.0 < m1["relative_abundance"] < 1.5

    def test_chlorine_isotope_ratio(self):
        # One Cl atom: 35Cl (75.76%) and 37Cl (24.24%)
        # M+2 / M ratio ≈ 0.24/0.76 * 100 ≈ 31.9%
        pattern = isotope_pattern({"Cl": 1})
        mono = next(p for p in pattern if p["nominal_offset"] == 0)
        m2   = next(p for p in pattern if p["nominal_offset"] == 2)
        ratio = m2["relative_abundance"] / mono["relative_abundance"]
        assert 0.28 < ratio < 0.36   # roughly 1/3

    def test_benzene_m_plus_1(self):
        # C6H6: M+1 ≈ 6 * 1.1% = 6.6%
        pattern = isotope_pattern({"C": 6, "H": 6})
        m1 = next((p for p in pattern if p["nominal_offset"] == 1), None)
        assert m1 is not None
        assert 5.5 < m1["relative_abundance"] < 8.0

    def test_monoisotopic_peak_always_100(self):
        # For any composition, the most abundant peak = 100 after normalisation
        pattern = isotope_pattern({"C": 10, "H": 12, "O": 2})
        assert max(p["relative_abundance"] for p in pattern) == 100.0

    def test_empty_composition(self):
        assert isotope_pattern({}) == []

    def test_returns_sorted_by_mass(self):
        pattern = isotope_pattern({"C": 5, "H": 10, "O": 2})
        masses = [p["mass"] for p in pattern]
        assert masses == sorted(masses)


class TestPatternSummary:
    def test_basic_summary(self):
        pattern = isotope_pattern({"C": 6, "H": 6})
        summary = pattern_summary(pattern)
        assert "M(" in summary
        assert "M+1(" in summary

    def test_max_peaks_respected(self):
        pattern = isotope_pattern({"C": 20, "H": 20})
        summary = pattern_summary(pattern, max_peaks=2)
        # Should contain at most 2 entries
        assert summary.count("M") <= 2

    def test_empty_pattern(self):
        assert pattern_summary([]) == "—"
