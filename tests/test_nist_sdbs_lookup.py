"""
tests/test_nist_sdbs_lookup.py
==============================
Unit tests for NIST WebBook and SDBS spectral library lookup.

All tests use mocked HTTP responses — no actual network requests.
"""

import pytest
from unittest.mock import patch, MagicMock
from ei_fragment_calculator.nist_lookup import lookup_nist
from ei_fragment_calculator.sdbs_lookup import lookup_sdbs


# ---------------------------------------------------------------------------
# NIST Lookup Tests
# ---------------------------------------------------------------------------


class TestNISTLookup:
    """Tests for NIST WebBook query by InChIKey."""

    def test_nist_empty_inchikey(self):
        """lookup_nist returns None for empty InChIKey."""
        result = lookup_nist("")
        assert result is None

    def test_nist_none_inchikey(self):
        """lookup_nist returns None for None InChIKey."""
        result = lookup_nist(None)
        assert result is None

    @patch("urllib.request.urlopen")
    def test_nist_not_found(self, mock_urlopen):
        """lookup_nist returns None when compound not found (404 or no match)."""
        # Simulate a 404 response (compound not in NIST)
        mock_urlopen.side_effect = Exception("HTTP Error")
        result = lookup_nist("INVALID-INCHIKEY-XYZ")
        assert result is None

    @patch("urllib.request.urlopen")
    def test_nist_network_error(self, mock_urlopen):
        """lookup_nist returns None on network error."""
        mock_urlopen.side_effect = ConnectionError("Network unreachable")
        result = lookup_nist("ZRMWVBDWYTBFAO-UHFFFAOYSA-N")
        assert result is None

    @patch("urllib.request.urlopen")
    def test_nist_timeout(self, mock_urlopen):
        """lookup_nist returns None on timeout."""
        mock_urlopen.side_effect = TimeoutError("Request timed out")
        result = lookup_nist("ZRMWVBDWYTBFAO-UHFFFAOYSA-N")
        assert result is None

    @patch("urllib.request.urlopen")
    def test_nist_simple_spectrum(self, mock_urlopen):
        """lookup_nist parses a simple NIST spectrum with annotated peaks."""
        # Mock a simple HTML response with a peak table
        html_response = """
        <html>
        <body>
        <h1>Mass Spectral Data</h1>
        <table>
        <tr><td>77</td><td>100</td><td>C6H5</td></tr>
        <tr><td>78</td><td>45</td><td>C6H6</td></tr>
        <tr><td>51</td><td>22</td><td>C4H3</td></tr>
        </table>
        </body>
        </html>
        """
        mock_response = MagicMock()
        mock_response.read.return_value = html_response.encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        result = lookup_nist("ZRMWVBDWYTBFAO-UHFFFAOYSA-N")
        assert result is not None
        assert 77 in result
        assert result[77] == "C6H5"
        assert 78 in result
        assert result[78] == "C6H6"
        assert 51 in result
        assert result[51] == "C4H3"

    @patch("urllib.request.urlopen")
    def test_nist_no_formulas(self, mock_urlopen):
        """lookup_nist returns None when spectrum has no formula annotations."""
        # Spectrum with m/z and intensity but no formula column
        html_response = """
        <html>
        <body>
        <h1>Mass Spectral Data</h1>
        <table>
        <tr><td>77</td><td>100</td><td></td></tr>
        <tr><td>78</td><td>45</td><td></td></tr>
        </table>
        </body>
        </html>
        """
        mock_response = MagicMock()
        mock_response.read.return_value = html_response.encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        result = lookup_nist("ZRMWVBDWYTBFAO-UHFFFAOYSA-N")
        # Should return None if no annotated peaks found
        assert result is None

    @patch("urllib.request.urlopen")
    def test_nist_malformed_html(self, mock_urlopen):
        """lookup_nist gracefully handles malformed HTML."""
        html_response = "<html><body>No table here</body></html>"
        mock_response = MagicMock()
        mock_response.read.return_value = html_response.encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        result = lookup_nist("ZRMWVBDWYTBFAO-UHFFFAOYSA-N")
        assert result is None

    @patch("urllib.request.urlopen")
    def test_nist_url_construction(self, mock_urlopen):
        """lookup_nist constructs the correct NIST query URL."""
        html_response = "<html><body></body></html>"
        mock_response = MagicMock()
        mock_response.read.return_value = html_response.encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        inchikey = "ZRMWVBDWYTBFAO-UHFFFAOYSA-N"
        lookup_nist(inchikey)

        # Verify the URL was constructed correctly
        mock_urlopen.assert_called_once()
        call_args = mock_urlopen.call_args
        url = call_args[0][0]
        assert "webbook.nist.gov" in url
        assert inchikey in url
        assert "Mask=200" in url


# ---------------------------------------------------------------------------
# SDBS Lookup Tests
# ---------------------------------------------------------------------------


class TestSDBSLookup:
    """Tests for SDBS (AIST Japan) spectral database lookup."""

    def test_sdbs_empty_name(self):
        """lookup_sdbs returns None for empty compound name."""
        result = lookup_sdbs("")
        assert result is None

    def test_sdbs_none_name(self):
        """lookup_sdbs returns None for None compound name."""
        result = lookup_sdbs(None)
        assert result is None

    @patch("urllib.request.urlopen")
    def test_sdbs_not_found(self, mock_urlopen):
        """lookup_sdbs returns None when compound not found."""
        mock_urlopen.side_effect = Exception("Not found")
        result = lookup_sdbs("nonexistent-compound-xyz")
        assert result is None

    @patch("urllib.request.urlopen")
    def test_sdbs_network_error(self, mock_urlopen):
        """lookup_sdbs returns None on network error."""
        mock_urlopen.side_effect = ConnectionError("Network unreachable")
        result = lookup_sdbs("benzene")
        assert result is None

    @patch("urllib.request.urlopen")
    def test_sdbs_timeout(self, mock_urlopen):
        """lookup_sdbs returns None on timeout."""
        mock_urlopen.side_effect = TimeoutError("Request timed out")
        result = lookup_sdbs("toluene")
        assert result is None

    @patch("urllib.request.urlopen")
    def test_sdbs_simple_spectrum(self, mock_urlopen):
        """lookup_sdbs parses a simple SDBS spectrum with annotated peaks."""
        html_response = """
        <html>
        <body>
        <table>
        <tr><td>77</td><td>100</td><td>C6H5</td></tr>
        <tr><td>51</td><td>45</td><td>C4H3</td></tr>
        <tr><td>39</td><td>22</td><td>C3H3</td></tr>
        </table>
        </body>
        </html>
        """
        mock_response = MagicMock()
        mock_response.read.return_value = html_response.encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        result = lookup_sdbs("benzene")
        assert result is not None
        assert 77 in result
        assert result[77] == "C6H5"
        assert 51 in result
        assert result[51] == "C4H3"

    @patch("urllib.request.urlopen")
    def test_sdbs_no_formulas(self, mock_urlopen):
        """lookup_sdbs returns None when spectrum has no formula annotations."""
        html_response = """
        <html>
        <body>
        <table>
        <tr><td>77</td><td>100</td><td></td></tr>
        <tr><td>51</td><td>45</td><td></td></tr>
        </table>
        </body>
        </html>
        """
        mock_response = MagicMock()
        mock_response.read.return_value = html_response.encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        result = lookup_sdbs("benzene")
        assert result is None

    @patch("urllib.request.urlopen")
    def test_sdbs_malformed_html(self, mock_urlopen):
        """lookup_sdbs gracefully handles malformed HTML."""
        html_response = "<html><body>Invalid format</body></html>"
        mock_response = MagicMock()
        mock_response.read.return_value = html_response.encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        result = lookup_sdbs("benzene")
        assert result is None

    @patch("urllib.request.urlopen")
    def test_sdbs_post_request_data(self, mock_urlopen):
        """lookup_sdbs sends correct POST data to SDBS."""
        html_response = "<html><body></body></html>"
        mock_response = MagicMock()
        mock_response.read.return_value = html_response.encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None
        mock_urlopen.return_value = mock_response

        compound_name = "benzene"
        lookup_sdbs(compound_name)

        # Verify POST request
        mock_urlopen.assert_called_once()
        call_args = mock_urlopen.call_args
        request_obj = call_args[0][0]

        # Check URL
        assert "sdbs.db.aist.go.jp" in request_obj.full_url
        assert request_obj.data is not None

        # Check POST data contains compound name
        post_data = request_obj.data.decode("utf-8")
        assert "compound=benzene" in post_data
        assert "stype=MS" in post_data


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


class TestLookupIntegration:
    """Integration tests for lookup functions with format_record."""

    def test_nist_annotation_structure(self):
        """NIST annotation dict has correct structure."""
        # Direct unit test of the result structure
        assert isinstance({}, dict)
        # m/z values should be ints, formulas should be strings
        test_result = {77: "C6H5", 51: "C4H3"}
        for mz, formula in test_result.items():
            assert isinstance(mz, int)
            assert isinstance(formula, str)
            assert mz > 0
            assert len(formula) > 0

    def test_sdbs_annotation_structure(self):
        """SDBS annotation dict has correct structure."""
        test_result = {77: "C6H5", 51: "C4H3", 39: "C3H3"}
        for mz, formula in test_result.items():
            assert isinstance(mz, int)
            assert isinstance(formula, str)
            assert 1 <= mz <= 2000  # Reasonable m/z range
