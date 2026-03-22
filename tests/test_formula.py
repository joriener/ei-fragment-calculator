"""Tests for formula.py — parsing and Hill-notation formatting."""

import pytest
from ei_fragment_calculator.formula import parse_formula, hill_formula


class TestParseFormula:
    def test_simple_formula(self):
        result = parse_formula("C10H12O2")
        assert result == {"C": 10, "H": 12, "O": 2}

    def test_single_atoms(self):
        result = parse_formula("CHN")
        assert result == {"C": 1, "H": 1, "N": 1}

    def test_two_letter_element(self):
        result = parse_formula("C6H5Br")
        assert result == {"C": 6, "H": 5, "Br": 1}

    def test_chlorine(self):
        result = parse_formula("C2H4Cl2")
        assert result == {"C": 2, "H": 4, "Cl": 2}

    def test_unknown_element_raises(self):
        with pytest.raises(ValueError, match="Unknown or unsupported element"):
            parse_formula("C10H12Xe2")

    def test_empty_formula_raises(self):
        with pytest.raises(ValueError):
            parse_formula("123")


class TestHillFormula:
    def test_carbon_first(self):
        assert hill_formula({"O": 1, "H": 7, "C": 3}) == "C3H7O"

    def test_hydrogen_second(self):
        result = hill_formula({"N": 1, "C": 6, "H": 5})
        assert result == "C6H5N"

    def test_no_subscript_for_one(self):
        assert hill_formula({"C": 1, "H": 1}) == "CH"

    def test_alphabetical_rest(self):
        result = hill_formula({"C": 2, "H": 5, "N": 1, "Br": 1})
        assert result == "C2H5BrN"

    def test_no_carbon(self):
        result = hill_formula({"H": 2, "O": 1})
        assert result == "H2O"
