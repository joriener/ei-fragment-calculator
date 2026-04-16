"""
tests/test_input_reader.py
==========================
Tests for the multi-format input reader (input_reader.py).

Covers:
  - SDF delegation to existing parse_sdf logic
  - MSP parsing (NIST format)
  - JCAMP-DX parsing
  - CSV Layout A (per-compound key-value blocks)
  - CSV Layout B (flat table)
  - Format detection by extension
  - Content sniffing (unknown extension)
  - Formula derivation from MOL block
  - Encoding fallback (Latin-1 SDF)
  - FileNotFoundError on missing file
  - ValueError on unknown format
"""

import os
import tempfile
import pytest

from ei_fragment_calculator.input_reader import (
    read_records,
    _read_msp,
    _read_jdx,
    _read_csv,
    _derive_formula_from_mol,
    _maybe_derive_formula,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_tmp(content: str, suffix: str) -> str:
    """Write *content* to a temporary file with *suffix* and return its path."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(content)
    return path


# ---------------------------------------------------------------------------
# SDF — delegation + formula derivation
# ---------------------------------------------------------------------------

SDF_MINIMAL = """\
Acetophenone
  test

  0  0  0     0  0            999 V2000
M  END
> <MOLECULAR FORMULA>
C8H8O

> <MASS SPECTRAL PEAKS>
51 43 77 100 105 67 120 40

$$$$
Toluene
  test

  0  0  0     0  0            999 V2000
M  END
> <MOLECULAR FORMULA>
C7H8

> <MASS SPECTRAL PEAKS>
39 17 91 100 92 70

$$$$
"""


def test_read_sdf_two_compounds():
    path = _write_tmp(SDF_MINIMAL, ".sdf")
    try:
        records = read_records(path)
        assert len(records) == 2
        assert records[0]["name"] == "Acetophenone"
        assert records[1]["name"] == "Toluene"
        assert "MOLECULAR FORMULA" in records[0]["fields"]
        assert records[0]["fields"]["MOLECULAR FORMULA"] == "C8H8O"
        assert "MASS SPECTRAL PEAKS" in records[0]["fields"]
    finally:
        os.unlink(path)


def test_read_sdf_returns_mol_block():
    path = _write_tmp(SDF_MINIMAL, ".sd")
    try:
        records = read_records(path)
        assert "mol_block" in records[0]
        # Minimal MOL block should contain "M  END"
        assert "M  END" in records[0]["mol_block"]
    finally:
        os.unlink(path)


# SDF with Latin-1 encoding (e.g. Ü character in name)
SDF_LATIN1 = (
    "Caf\xe9ine\n  test\n\n  0  0  0     0  0            999 V2000\nM  END\n"
    "> <MOLECULAR FORMULA>\nC8H10N4O2\n\n> <MASS SPECTRAL PEAKS>\n194 100\n\n$$$$\n"
)


def test_sdf_encoding_fallback_latin1():
    fd, path = tempfile.mkstemp(suffix=".sdf")
    with os.fdopen(fd, "wb") as fh:
        fh.write(SDF_LATIN1.encode("latin-1"))
    try:
        records = read_records(path)
        assert len(records) == 1
        # Name should contain the accented character (decoded correctly)
        assert "Caf" in records[0]["name"]
        assert records[0]["fields"]["MOLECULAR FORMULA"] == "C8H10N4O2"
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Formula derivation from MOL block
# ---------------------------------------------------------------------------

MOL_BLOCK_C7H8 = """\
Toluene
  test

  8  8  0     0  0            999 V2000
  0.0000   0.0000   0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
  0.0000   0.0000   0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
  0.0000   0.0000   0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
  0.0000   0.0000   0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
  0.0000   0.0000   0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
  0.0000   0.0000   0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
  0.0000   0.0000   0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
  0.0000   0.0000   0.0000 H   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  2  0  0  0  0
  2  3  1  0  0  0  0
  3  4  2  0  0  0  0
  4  5  1  0  0  0  0
  5  6  2  0  0  0  0
  6  1  1  0  0  0  0
  6  7  1  0  0  0  0
  7  8  1  0  0  0  0
M  END"""


def test_derive_formula_from_mol():
    formula = _derive_formula_from_mol(MOL_BLOCK_C7H8)
    assert formula is not None
    # Should contain C and H
    assert "C" in formula
    assert "H" in formula


def test_derive_formula_from_mol_empty_block():
    # MOL block with 0 atoms should return None
    mol_zero = "Empty\n  test\n\n  0  0  0     0  0            999 V2000\nM  END"
    formula = _derive_formula_from_mol(mol_zero)
    assert formula is None


def test_maybe_derive_formula_sets_flag():
    record = {
        "name": "TestCompound",
        "mol_block": MOL_BLOCK_C7H8,
        "fields": {"MASS SPECTRAL PEAKS": "91 100\n92 70"},
    }
    _maybe_derive_formula(record)
    assert "MOLECULAR FORMULA" in record["fields"]
    assert record["fields"].get("_derived_formula") == "1"


def test_maybe_derive_formula_does_not_overwrite_existing():
    record = {
        "name": "TestCompound",
        "mol_block": MOL_BLOCK_C7H8,
        "fields": {"MOLECULAR FORMULA": "C7H8", "MASS SPECTRAL PEAKS": "91 100"},
    }
    _maybe_derive_formula(record)
    # Should not set _derived_formula flag when formula already present
    assert record["fields"].get("_derived_formula") is None
    assert record["fields"]["MOLECULAR FORMULA"] == "C7H8"


# ---------------------------------------------------------------------------
# MSP
# ---------------------------------------------------------------------------

MSP_TWO = """\
Name: Caffeine
Formula: C8H10N4O2
MW: 194
Comments: EI test
Num Peaks: 3
55 28
138 100
194 75

Name: Toluene
Formula: C7H8
MW: 92
Num Peaks: 2
91 100
92 70

"""


def test_read_msp_two_compounds():
    path = _write_tmp(MSP_TWO, ".msp")
    try:
        records = read_records(path)
        assert len(records) == 2
        assert records[0]["name"] == "Caffeine"
        assert records[1]["name"] == "Toluene"
        assert records[0]["fields"]["MOLECULAR FORMULA"] == "C8H10N4O2"
        assert records[1]["fields"]["MOLECULAR FORMULA"] == "C7H8"
    finally:
        os.unlink(path)


def test_read_msp_peaks_parsed():
    path = _write_tmp(MSP_TWO, ".msp")
    try:
        records = read_records(path)
        peaks_text = records[0]["fields"]["MASS SPECTRAL PEAKS"]
        # Should contain the three peaks as "mz intensity" lines
        assert "55 28" in peaks_text
        assert "138 100" in peaks_text
        assert "194 75" in peaks_text
    finally:
        os.unlink(path)


def test_read_msp_mol_block_empty():
    path = _write_tmp(MSP_TWO, ".msp")
    try:
        records = read_records(path)
        assert records[0]["mol_block"] == ""
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# JCAMP-DX
# ---------------------------------------------------------------------------

JDX_TWO = """\
##TITLE=Caffeine
##JCAMP-DX=4.24
##DATA TYPE=MASS SPECTRUM
##FORMULA=C8H10N4O2
##MW=194
##XYDATA=(XY..XY)
55 28
138 100
194 75
##END=

##TITLE=Acetophenone
##JCAMP-DX=4.24
##DATA TYPE=MASS SPECTRUM
##FORMULA=C8H8O
##MW=120
##XYDATA=(XY..XY)
77 100
120 40
##END=
"""


def test_read_jdx_two_compounds():
    path = _write_tmp(JDX_TWO, ".jdx")
    try:
        records = read_records(path)
        assert len(records) == 2
        assert records[0]["name"] == "Caffeine"
        assert records[1]["name"] == "Acetophenone"
    finally:
        os.unlink(path)


def test_read_jdx_formula_and_peaks():
    path = _write_tmp(JDX_TWO, ".jdx")
    try:
        records = read_records(path)
        assert records[0]["fields"]["MOLECULAR FORMULA"] == "C8H10N4O2"
        peaks = records[0]["fields"]["MASS SPECTRAL PEAKS"]
        assert "55 28" in peaks
        assert "194 75" in peaks
    finally:
        os.unlink(path)


def test_read_jdx_jcamp_extension():
    path = _write_tmp(JDX_TWO, ".jcamp")
    try:
        records = read_records(path)
        assert len(records) == 2
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# CSV Layout A (per-compound blocks)
# ---------------------------------------------------------------------------

CSV_BLOCK = """\
Name,Acetophenone
Formula,C8H8O
MW,120
mz,intensity
51,43
77,100
120,40

Name,Toluene
Formula,C7H8
MW,92
mz,intensity
91,100
92,70
"""


def test_read_csv_layout_a():
    path = _write_tmp(CSV_BLOCK, ".csv")
    try:
        records = read_records(path)
        assert len(records) == 2
        assert records[0]["name"] == "Acetophenone"
        assert records[0]["fields"]["MOLECULAR FORMULA"] == "C8H8O"
        peaks = records[0]["fields"]["MASS SPECTRAL PEAKS"]
        assert "77 100" in peaks
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# CSV Layout B (flat table)
# ---------------------------------------------------------------------------

CSV_FLAT = """\
compound,formula,mz,intensity
Acetophenone,C8H8O,51,43
Acetophenone,C8H8O,77,100
Acetophenone,C8H8O,120,40
Toluene,C7H8,91,100
Toluene,C7H8,92,70
"""


def test_read_csv_layout_b():
    path = _write_tmp(CSV_FLAT, ".csv")
    try:
        records = read_records(path)
        assert len(records) == 2
        assert records[0]["name"] == "Acetophenone"
        assert records[1]["name"] == "Toluene"
        assert records[0]["fields"]["MOLECULAR FORMULA"] == "C8H8O"
    finally:
        os.unlink(path)


def test_read_csv_flat_peaks():
    path = _write_tmp(CSV_FLAT, ".csv")
    try:
        records = read_records(path)
        peaks = records[1]["fields"]["MASS SPECTRAL PEAKS"]
        assert "91 100" in peaks
        assert "92 70" in peaks
    finally:
        os.unlink(path)


# TSV variant
CSV_FLAT_TSV = CSV_FLAT.replace(",", "\t")


def test_read_csv_tsv_extension():
    path = _write_tmp(CSV_FLAT_TSV, ".tsv")
    try:
        records = read_records(path)
        assert len(records) == 2
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Format detection by extension
# ---------------------------------------------------------------------------

def test_format_detection_msp_extension():
    path = _write_tmp(MSP_TWO, ".msp")
    try:
        records = read_records(path)
        assert len(records) == 2
    finally:
        os.unlink(path)


def test_format_detection_sdf_extension():
    path = _write_tmp(SDF_MINIMAL, ".sdf")
    try:
        records = read_records(path)
        assert len(records) == 2
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Content sniffing (unknown extension)
# ---------------------------------------------------------------------------

def test_sniff_detects_msp():
    path = _write_tmp(MSP_TWO, ".dat")
    try:
        records = read_records(path)
        assert len(records) == 2
        assert records[0]["name"] == "Caffeine"
    finally:
        os.unlink(path)


def test_sniff_detects_jdx():
    path = _write_tmp(JDX_TWO, ".dat")
    try:
        records = read_records(path)
        assert len(records) == 2
    finally:
        os.unlink(path)


def test_sniff_detects_sdf():
    path = _write_tmp(SDF_MINIMAL, ".dat")
    try:
        records = read_records(path)
        assert len(records) == 2
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_file_not_found_raises():
    with pytest.raises(FileNotFoundError):
        read_records("/nonexistent/path/to/file.sdf")


def test_unknown_format_raises():
    path = _write_tmp("just some random text\nno recognizable format\n", ".xyz")
    try:
        with pytest.raises(ValueError, match="format"):
            read_records(path)
    finally:
        os.unlink(path)


def test_example_sdf_file():
    """Smoke-test the bundled example SDF file."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sdf_path = os.path.join(here, "examples", "three_compounds.sdf")
    if not os.path.exists(sdf_path):
        pytest.skip("examples/three_compounds.sdf not found")
    records = read_records(sdf_path)
    assert len(records) == 3
    names = [r["name"] for r in records]
    assert "Caffeine" in names


def test_example_msp_file():
    """Smoke-test the bundled example MSP file."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    msp_path = os.path.join(here, "examples", "three_compounds.msp")
    if not os.path.exists(msp_path):
        pytest.skip("examples/three_compounds.msp not found")
    records = read_records(msp_path)
    assert len(records) == 3


def test_example_jdx_file():
    """Smoke-test the bundled example JCAMP-DX file."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    jdx_path = os.path.join(here, "examples", "two_compounds.jdx")
    if not os.path.exists(jdx_path):
        pytest.skip("examples/two_compounds.jdx not found")
    records = read_records(jdx_path)
    assert len(records) == 2


# ---------------------------------------------------------------------------
# Phase 3: Extended PubChem enrichment tests (B1/B2)
# ---------------------------------------------------------------------------

def test_fetch_cid_from_name_mock():
    """Test B1: _fetch_cid_from_name with mock urllib (uses mocked response)."""
    from ei_fragment_calculator.structure_fetcher import _fetch_cid_from_name
    from unittest.mock import patch, MagicMock
    import json

    mock_response_data = {
        "IdentifierList": {
            "CID": [7311]  # Caffeine CID
        }
    }

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_file = MagicMock()
        mock_file.read.return_value = json.dumps(mock_response_data).encode("utf-8")
        mock_file.__enter__.return_value = mock_file
        mock_urlopen.return_value = mock_file

        cid = _fetch_cid_from_name("Caffeine")
        assert cid == 7311


def test_fetch_properties_from_pubchem_mock():
    """Test B1: _fetch_properties_from_pubchem with mock urllib."""
    from ei_fragment_calculator.structure_fetcher import _fetch_properties_from_pubchem
    from unittest.mock import patch, MagicMock
    import json

    mock_response_data = {
        "PropertyTable": {
            "Properties": [
                {
                    "CID": 7311,
                    "CanonicalSMILES": "CN1C=NC2=C1C(=O)N(C(=O)N2C)C",
                    "InChIKey": "RYYVLZVUVIJVGH-UHFFFAOYSA-N",
                    "MonoisotopicMass": 194.08044,
                    "MolecularFormula": "C8H10N4O2",
                    "IUPACName": "1,3,7-trimethylpurine-2,6-dione",
                }
            ]
        }
    }

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_file = MagicMock()
        mock_file.read.return_value = json.dumps(mock_response_data).encode("utf-8")
        mock_file.__enter__.return_value = mock_file
        mock_urlopen.return_value = mock_file

        props = _fetch_properties_from_pubchem(7311)
        assert props is not None
        assert props["SMILES"] == "CN1C=NC2=C1C(=O)N(C(=O)N2C)C"
        assert props["INCHIKEY"] == "RYYVLZVUVIJVGH-UHFFFAOYSA-N"
        assert props["PUBCHEM_EXACT_MW"] == 194.08044
        assert props["MOLECULAR_FORMULA"] == "C8H10N4O2"


def test_validate_formula_match():
    """Test B2: validate_formula with matching masses (no warning)."""
    from ei_fragment_calculator.structure_fetcher import validate_formula
    from io import StringIO
    import sys

    fields = {
        "MOLECULAR FORMULA": "C8H10N4O2",
        "PUBCHEM_EXACT_MW": 194.0804,
    }

    # Capture stdout to verify no warning is emitted
    old_stdout = sys.stdout
    sys.stdout = StringIO()
    result = validate_formula(fields, "Caffeine")
    output = sys.stdout.getvalue()
    sys.stdout = old_stdout

    assert result is True
    assert "[WARN]" not in output


def test_validate_formula_mismatch():
    """Test B2: validate_formula with mismatched masses (emits warning)."""
    from ei_fragment_calculator.structure_fetcher import validate_formula
    from io import StringIO
    import sys

    fields = {
        "MOLECULAR FORMULA": "C8H10N4O2",
        "PUBCHEM_EXACT_MW": 200.0,  # Significantly different from 194.08
    }

    # Capture stdout to verify warning is emitted
    old_stdout = sys.stdout
    sys.stdout = StringIO()
    result = validate_formula(fields, "TestCompound")
    output = sys.stdout.getvalue()
    sys.stdout = old_stdout

    assert result is True  # Never aborts
    assert "[WARN]" in output
    assert "mismatch" in output.lower()


def test_validate_formula_missing_data():
    """Test B2: validate_formula with missing data (skips validation)."""
    from ei_fragment_calculator.structure_fetcher import validate_formula
    from io import StringIO
    import sys

    fields = {
        "MOLECULAR FORMULA": "C8H10N4O2",
        # Missing PUBCHEM_EXACT_MW
    }

    # Capture stdout to verify no warning is emitted
    old_stdout = sys.stdout
    sys.stdout = StringIO()
    result = validate_formula(fields, "TestCompound")
    output = sys.stdout.getvalue()
    sys.stdout = old_stdout

    assert result is True
    assert "[WARN]" not in output


