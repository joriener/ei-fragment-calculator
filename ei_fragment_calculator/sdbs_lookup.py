"""
sdbs_lookup.py
==============
Query SDBS (AIST Japan) for EI spectral data as a fallback after NIST miss.

SDBS contains mass spectral data for ~35,000 organic compounds.
Provides free access to spectra with varying levels of annotation.

Public API
----------
lookup_sdbs(compound_name: str) -> dict[int, str] | None
    Query SDBS by compound name (or IUPAC name).  Returns {nominal_mz: formula_str}
    for peaks with formula annotations, or None if not found or on error.

Notes
-----
- Uses urllib for HTTP POST requests.
- Implements a 0.5 second delay per request to respect rate limits.
- Parses HTML response for peak lists and formula annotations.
- Returns empty dict if found but no formulas annotated.
"""

import re
import time
import urllib.request
import urllib.parse
import urllib.error
from typing import Optional

# Rate-limit delay (seconds) between SDBS requests
_SDBS_DELAY_SECONDS = 0.5

# Time of the last SDBS request (module-level to enforce global rate limit)
_last_sdbs_request_time: Optional[float] = None


def lookup_sdbs(compound_name: str) -> Optional[dict[int, str]]:
    """
    Query SDBS by compound name and return annotated fragment formulas.

    Parameters
    ----------
    compound_name : str
        Compound name or IUPAC name (e.g., "benzene", "toluene").

    Returns
    -------
    dict[int, str] | None
        {nominal_mz: formula_str} for peaks with formula annotations,
        or None if not found or on error.

    Notes
    -----
    - Enforces a global 0.5 second delay between calls.
    - Returns None on network error, invalid response, or if compound not found.
    """
    global _last_sdbs_request_time

    if not compound_name:
        return None

    # Enforce rate limiting
    now = time.time()
    if _last_sdbs_request_time is not None:
        elapsed = now - _last_sdbs_request_time
        if elapsed < _SDBS_DELAY_SECONDS:
            time.sleep(_SDBS_DELAY_SECONDS - elapsed)

    _last_sdbs_request_time = time.time()

    # SDBS query endpoint: POST request with compound name
    url = "https://sdbs.db.aist.go.jp/sdbs/cgi-bin/direct_frame_top.cgi"

    # Build POST data
    post_data = urllib.parse.urlencode({
        "sdbsno": "auto",
        "compound": compound_name,
        "el": "",
        "molwt": "",
        "mf": "",
        "stype": "MS",
    }).encode("utf-8")

    try:
        request = urllib.request.Request(url, data=post_data)
        with urllib.request.urlopen(request, timeout=10) as response:
            html = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, Exception):
        # Network error, timeout, or invalid response
        return None

    # Parse the HTML response for mass spectral data
    # SDBS displays spectra in a simple tabular format

    result = {}

    # Look for mass spectral table in the response
    # Pattern: SDBS typically shows m/z, intensity, and optionally formula
    # Format varies, but often appears in table or preformatted text

    # Strategy 1: Look for patterns in table rows
    td_lines = re.findall(r"<tr[^>]*>.*?</tr>", html, re.IGNORECASE | re.DOTALL)

    for line in td_lines:
        # Extract all TD values
        td_values = re.findall(r"<td[^>]*>([^<]*)</td>", line, re.IGNORECASE)

        if len(td_values) >= 2:
            # Try to parse m/z and formula
            try:
                mz_str = td_values[0].strip()
                # Try to extract integer m/z
                mz_match = re.match(r"^(\d+)", mz_str)
                if not mz_match:
                    continue

                mz = int(mz_match.group(1))

                # Look for formula in subsequent columns
                formula = None
                for val in td_values[1:]:
                    val = val.strip()
                    # Match chemical formula pattern
                    if val and re.match(r"^[A-Z][a-z]?(\d+)?([A-Z][a-z]?(\d+)?)*$", val):
                        formula = val
                        break

                if formula:
                    result[mz] = formula

            except (ValueError, IndexError):
                continue

    # Strategy 2: Look for peak data in preformatted or plaintext sections
    if not result:
        # Look for lines with m/z and formula separated by whitespace/pipes
        # Pattern: "77" or "77 " followed by "C6H5" or "77|C6H5"
        pattern = r"(\d{1,4})\s*\|?\s*([A-Z][a-z]?(?:\d+)?(?:[A-Z][a-z]?(?:\d+)?)*)"
        for match in re.finditer(pattern, html):
            try:
                mz = int(match.group(1))
                formula = match.group(2)
                # Sanity check: m/z should be reasonable
                if 1 <= mz <= 2000:
                    result[mz] = formula
            except (ValueError, IndexError):
                continue

    return result if result else None
