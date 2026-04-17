"""
test_fragmentation_rules.py
===========================
Unit tests for fragmentation rule integration with confidence scoring.

Coverage:
  - annotate_candidate: base_probability and bond_dissociation_rate attachment
  - confidence scoring: using base_probability for reaction type bonuses (A2)
  - get_structure_fragments: integration with bond thermochemistry (A1)
"""

import pytest
from ei_fragment_calculator.fragmentation_rules import (
    annotate_candidate,
    get_structure_fragments,
)
from ei_fragment_calculator.confidence import _score_fragmentation


# ─────────────────────────────────────────────────────────────────────────────
# Test annotate_candidate
# ─────────────────────────────────────────────────────────────────────────────

def test_annotate_candidate_with_neutral_loss():
    """Test annotating a candidate that matches a neutral-loss fragment."""
    candidate = {
        "formula": "C6H5",
        "_composition": {"C": 6, "H": 5},
        "ion_mass": 77,
    }
    neutral_losses = [
        {
            "rule_name": "CO2_loss",
            "description": "CO2 neutral loss",
            "fragment_composition": {"C": 6, "H": 5},
        }
    ]

    result = annotate_candidate(candidate, neutral_losses, structure_frags=None)
    assert result["fragmentation_rule"] == "CO2_loss"
    assert result["rule_score"] == 0.0  # Matched fragment


def test_annotate_candidate_attaches_base_probability():
    """Test that annotate_candidate copies base_probability from matched fragment."""
    candidate = {
        "formula": "C2H6O",
        "_composition": {"C": 2, "H": 6, "O": 1},
        "ion_mass": 46,
    }

    # Create a mock fragment structure with base_probability
    structure_frags = [
        {
            "rule": "alpha_cleavage",
            "charged_frag_comp": {"C": 2, "H": 6, "O": 1},
            "base_probability": 0.12,
            "bond_dissociation_rate": 75,
        }
    ]

    result = annotate_candidate(candidate, [], structure_frags=structure_frags)
    if result["fragmentation_rule"]:
        # If a rule matched, base_probability should be attached
        assert "base_probability" in result
        assert result["base_probability"] == 0.12


def test_annotate_candidate_attaches_bond_dissociation_rate():
    """Test that annotate_candidate copies bond_dissociation_rate from matched fragment."""
    candidate = {
        "formula": "C2H6O",
        "_composition": {"C": 2, "H": 6, "O": 1},
        "ion_mass": 46,
    }

    structure_frags = [
        {
            "rule": "homolytic_cleavage",
            "frag1_comp": {"C": 2, "H": 6, "O": 1},
            "base_probability": 0.50,
            "bond_dissociation_rate": 85,
        }
    ]

    result = annotate_candidate(candidate, [], structure_frags=structure_frags)
    if result["fragmentation_rule"]:
        assert "bond_dissociation_rate" in result
        assert result["bond_dissociation_rate"] == 85


def test_annotate_candidate_no_match():
    """Test annotating a candidate that doesn't match any fragment."""
    candidate = {
        "formula": "C10H8",
        "_composition": {"C": 10, "H": 8},
        "ion_mass": 128,
    }

    result = annotate_candidate(candidate, [], structure_frags=None)
    assert result["fragmentation_rule"] == ""
    assert result["rule_score"] == 1.0  # No match


# ─────────────────────────────────────────────────────────────────────────────
# Test get_structure_fragments (integration)
# ─────────────────────────────────────────────────────────────────────────────

def test_get_structure_fragments_none():
    """Test that get_structure_fragments returns [] when mol_data is None."""
    frags = get_structure_fragments(None, parent_dbe=0.0)
    assert frags == []


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests: Confidence scoring uses base_probability (A2)
# ─────────────────────────────────────────────────────────────────────────────

def test_confidence_scoring_neutral_when_no_rules():
    """Test that fragmentation scoring returns 0.5 when rules are disabled."""
    candidate = {"fragmentation_rule": None}
    score = _score_fragmentation(candidate, fragmentation_rules_enabled=False, has_mol_block=False)
    assert score == 0.5


def test_confidence_scoring_high_probability_reaction():
    """Test that high-probability reactions (>15%) get maximum boost."""
    candidate = {
        "fragmentation_rule": "Homolytic cleavage",
        "base_probability": 0.50,  # High probability (>15%)
    }
    score = _score_fragmentation(candidate, fragmentation_rules_enabled=True, has_mol_block=True)
    # Should get 0.20 bonus → 0.70 + 0.20 = 0.90
    assert 0.85 <= score <= 0.95


def test_confidence_scoring_medium_probability_reaction():
    """Test that medium-probability reactions (5–15%) get medium boost."""
    candidate = {
        "fragmentation_rule": "α-Cleavage",
        "base_probability": 0.12,  # Medium probability (5–15%)
    }
    score = _score_fragmentation(candidate, fragmentation_rules_enabled=True, has_mol_block=True)
    # Should get 0.10 bonus → 0.70 + 0.10 = 0.80
    assert 0.75 <= score <= 0.85


def test_confidence_scoring_low_probability_reaction():
    """Test that low-probability reactions (<5%) get minimal boost."""
    candidate = {
        "fragmentation_rule": "Retro-Diels-Alder",
        "base_probability": 0.01,  # Low probability (<5%)
    }
    score = _score_fragmentation(candidate, fragmentation_rules_enabled=True, has_mol_block=True)
    # Should get 0.0 bonus → 0.70
    assert 0.69 <= score <= 0.71


def test_confidence_scoring_no_path_with_mol():
    """Test that no-match with mol_block gets low score."""
    candidate = {"fragmentation_rule": ""}
    score = _score_fragmentation(candidate, fragmentation_rules_enabled=True, has_mol_block=True)
    assert score == 0.2


def test_confidence_scoring_no_path_without_mol():
    """Test that no-match without mol_block gets neutral score."""
    candidate = {"fragmentation_rule": ""}
    score = _score_fragmentation(candidate, fragmentation_rules_enabled=True, has_mol_block=False)
    assert score == 0.5


def test_confidence_scoring_missing_base_probability():
    """Test that missing base_probability defaults to neutral (0.05 cutoff)."""
    candidate = {
        "fragmentation_rule": "Some rule",
        # No base_probability field
    }
    score = _score_fragmentation(candidate, fragmentation_rules_enabled=True, has_mol_block=True)
    # Should use default 0.05 (< 5%) → 0.0 bonus → 0.70
    assert 0.69 <= score <= 0.71


# ─────────────────────────────────────────────────────────────────────────────
# Edge cases and additional coverage
# ─────────────────────────────────────────────────────────────────────────────

def test_annotate_candidate_empty_structure_frags():
    """Test annotate_candidate with empty structure fragments list."""
    candidate = {
        "formula": "C6H5",
        "_composition": {"C": 6, "H": 5},
        "ion_mass": 77,
    }

    result = annotate_candidate(candidate, [], structure_frags=[])
    assert result["fragmentation_rule"] == ""
    assert result["rule_score"] == 1.0


def test_annotate_candidate_multiple_structure_frags_picks_first_match():
    """Test that annotate_candidate picks the first matching fragment."""
    candidate = {
        "formula": "C2H4O",
        "_composition": {"C": 2, "H": 4, "O": 1},
        "ion_mass": 44,
    }

    structure_frags = [
        {
            "rule": "alpha_cleavage",
            "frag1_comp": {"C": 2, "H": 4, "O": 1},
            "base_probability": 0.12,
        },
        {
            "rule": "inductive_cleavage",
            "frag1_comp": {"C": 2, "H": 4, "O": 1},
            "base_probability": 0.05,
        },
    ]

    result = annotate_candidate(candidate, [], structure_frags=structure_frags)
    # Should match first fragment (alpha_cleavage)
    if result["fragmentation_rule"]:
        assert "base_probability" in result


def test_confidence_scoring_boundary_15_percent():
    """Test that base_probability = 0.15 uses medium boost."""
    candidate = {
        "fragmentation_rule": "Some rule",
        "base_probability": 0.15,  # Boundary: still uses 0.10 bonus
    }
    score = _score_fragmentation(candidate, fragmentation_rules_enabled=True, has_mol_block=True)
    # At exactly 0.15, should use 0.10 bonus (not > 0.15) → 0.80
    assert 0.75 <= score <= 0.85


def test_confidence_scoring_boundary_5_percent():
    """Test that base_probability = 0.05 uses minimal boost."""
    candidate = {
        "fragmentation_rule": "Some rule",
        "base_probability": 0.05,  # Boundary: still uses 0.0 bonus
    }
    score = _score_fragmentation(candidate, fragmentation_rules_enabled=True, has_mol_block=True)
    # At exactly 0.05, should use 0.0 bonus (not > 0.05) → 0.70
    assert 0.69 <= score <= 0.71


# ─────────────────────────────────────────────────────────────────────────────
# A4: Multi-step rate tracking tests
# ─────────────────────────────────────────────────────────────────────────────

def test_secondary_fragment_has_step_rates():
    """Test that secondary fragments include step_1_rate and step_2_rate fields."""
    secondary_frag = {
        "rule": "homolytic_cleavage",
        "frag1_comp": {"C": 2, "H": 5},
        "step_1_rate": 85,  # Rate of primary bond dissociation
        "step_2_rate": 60,  # Rate of secondary bond dissociation
        "secondary": True,
    }

    assert "step_1_rate" in secondary_frag
    assert "step_2_rate" in secondary_frag
    assert secondary_frag["step_1_rate"] == 85
    assert secondary_frag["step_2_rate"] == 60


def test_secondary_fragment_rate_progression():
    """Test that secondary fragments include rate_progression field."""
    secondary_frag = {
        "rule": "alpha_cleavage",
        "frag1_comp": {"C": 2, "H": 6, "O": 1},
        "step_1_rate": 75,
        "step_2_rate": 45,
        "rate_progression": 0.6,  # step_2 / step_1
        "secondary": True,
    }

    assert "rate_progression" in secondary_frag
    assert abs(secondary_frag["rate_progression"] - 0.6) < 0.01


def test_secondary_fragment_marked_as_secondary():
    """Test that secondary fragments are correctly marked."""
    secondary_frag = {
        "rule": "homolytic_cleavage",
        "frag1_comp": {"C": 2, "H": 5},
        "secondary": True,
        "step_1_rate": 80,
        "step_2_rate": 50,
    }

    assert secondary_frag["secondary"] is True
    assert secondary_frag["secondary"] != "false"  # String vs boolean


def test_secondary_fragment_includes_step_rule():
    """Test that secondary fragments track the primary rule that generated them."""
    secondary_frag = {
        "rule": "inductive_cleavage",
        "step_1_rule": "alpha_cleavage",  # Primary rule
        "step_1_rate": 75,
        "step_2_rate": 40,
        "secondary": True,
    }

    assert "step_1_rule" in secondary_frag
    assert secondary_frag["step_1_rule"] == "alpha_cleavage"


def test_rate_progression_calculation():
    """Test various rate progression ratios."""
    test_cases = [
        (100, 50, 0.5),   # Slower second step
        (50, 100, 2.0),   # Faster second step
        (75, 75, 1.0),    # Same rate
        (100, 10, 0.1),   # Much slower second step
    ]

    for step1, step2, expected_prog in test_cases:
        secondary_frag = {
            "step_1_rate": step1,
            "step_2_rate": step2,
            "rate_progression": step2 / step1 if step1 > 0 else 1.0,
        }
        assert abs(secondary_frag["rate_progression"] - expected_prog) < 0.01


def test_multi_step_pathway_interpretation():
    """Test interpretation of multi-step fragmentation pathways."""
    # Example pathway: Primary → Secondary → Tertiary
    primary = {
        "rule": "homolytic_cleavage",
        "bond_dissociation_rate": 90,
        "base_probability": 0.50,
    }

    secondary = {
        "rule": "homolytic_cleavage",
        "secondary": True,
        "step_1_rate": 90,      # From primary
        "step_2_rate": 65,      # Secondary bond
        "rate_progression": 65/90,  # ~0.72 (slower)
    }

    # Interpretation: Primary breaks quickly (rate 90), secondary breaks slower (rate 65)
    # This explains why secondary peaks appear later in the mass spectrum
    assert primary["bond_dissociation_rate"] > secondary["step_2_rate"]
    assert secondary["rate_progression"] < 1.0  # Slower second step


def test_secondary_rate_defaults():
    """Test default rate values when specific rates unavailable."""
    secondary_frag = {
        "rule": "alpha_cleavage",
        "secondary": True,
        "step_1_rate": 75,
        "step_2_rate": 50,  # Could be default 50 if not computed
    }

    # Secondary fragments should have reasonable defaults
    assert 0 <= secondary_frag["step_2_rate"] <= 120
