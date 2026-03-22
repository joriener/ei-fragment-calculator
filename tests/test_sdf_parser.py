"""Tests for sdf_parser.py — SDF parsing and peak extraction."""

import os
import tempfile
import pytest
from ei_fragment_calculator.sdf_parser import parse_sdf, parse_peaks, find_field


MINIMAL_SDF = """\
Acetophenone
  test

  0  0  0     0  0            999 V2000
M  END
> <MOLECULAR FORMULA>
C8H8O

> <MASS SPECTRAL PEAKS>
51 100 77 999 105 850 120 500

$$$$
"""


class TestParseSdf:
    def test_reads_compound_name(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".sdf", delete=False, encoding="utf-8"
        ) as f:
            f.write(MINIMAL_SDF)
            fname = f.name
        try:
            records = parse_sdf(fname)
            assert len(records) == 1
            assert records[0]["name"] == "Acetophenone"
        finally:
            os.unlink(fname)

    def test_reads_data_fields(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".sdf", delete=False, encoding="utf-8"
        ) as f:
            f.write(MINIMAL_SDF)
            fname = f.name
        try:
            record = parse_sdf(fname)[0]
            assert "MOLECULAR FORMULA" in record["fields"]
            assert record["fields"]["MOLECULAR FORMULA"].strip() == "C8H8O"
        finally:
            os.unlink(fname)


class TestParsePeaks:
    def test_space_separated_pairs(self):
        text = "41 999 43 850 55 620 77 412"
        result = parse_peaks(text)
        assert result == [41, 43, 55, 77]

    def test_newline_separated_pairs(self):
        text = "41 999\n43 850\n55 620"
        result = parse_peaks(text)
        assert result == [41, 43, 55]

    def test_deduplication(self):
        text = "41 999 41 500"
        result = parse_peaks(text)
        assert result == [41]

    def test_empty_string(self):
        assert parse_peaks("") == []


class TestFindField:
    def test_exact_match(self):
        fields = {"MOLECULAR FORMULA": "C8H8O"}
        assert find_field(fields, ["MOLECULAR FORMULA"]) == "C8H8O"

    def test_case_insensitive(self):
        fields = {"molecular formula": "C8H8O"}
        assert find_field(fields, ["MOLECULAR FORMULA"]) == "C8H8O"

    def test_first_match_wins(self):
        fields = {"FORMULA": "C8H8O", "MF": "C8H8O_other"}
        result = find_field(fields, ["FORMULA", "MF"])
        assert result == "C8H8O"

    def test_no_match_returns_none(self):
        fields = {"SMILES": "c1ccccc1"}
        assert find_field(fields, ["MOLECULAR FORMULA", "MF"]) is None
