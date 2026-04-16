"""
nist_lookup.py
==============
Query NIST WebBook by InChIKey to retrieve annotated EI spectra.

NIST WebBook provides mass spectral data for ~350,000 compounds at no cost.
When a compound is found, fragment formula annotations (if present) are
considered ground truth — they bypass enumeration and scoring.

Public API
----------
lookup_nist(inchikey: str) -> dict[int, str] | None
    Query NIST by InChIKey.  Returns {nominal_mz: formula_str} for all
    annotated peaks, or None if the compound is not found or on error.
    Respects a 0.5 second delay between requests.

Notes
-----
- Uses urllib only (no external dependencies).
- Implements a 0.5 second delay per request to respect NIST rate limits.
- Parses HTML using regex; the NIST table structure is simple enough.
- Returns only rows with non-blank formula columns.
"""

import re
import time
import urllib.request
import urllib.error
from typing import Optional

# Rate-limit delay (seconds) between NIST requests
_NIST_DELAY_SECONDS = 0.5

# Time of the last NIST request (module-level to enforce global rate limit)
_last_nist_request_time: Optional[float] = None


def lookup_nist(inchikey: str) -> Optional[dict[int, str]]:
    """
    Query NIST WebBook by InChIKey and return annotated fragment formulas.

    Parameters
    ----------
    inchikey : str
        InChIKey identifier (e.g., "ZRMWVBDWYTBFAO-UHFFFAOYSA-N").

    Returns
    -------
    dict[int, str] | None
        {nominal_mz: formula_str} for all peaks with formula annotations,
        or None if the compound is not found or on error.

    Notes
    -----
    - Enforces a global 0.5 second delay between calls.
    - Returns None on network error, invalid response, or if compound not found.
    """
    global _last_nist_request_time

    if not inchikey:
        return None

    # Enforce rate limiting
    now = time.time()
    if _last_nist_request_time is not None:
        elapsed = now - _last_nist_request_time
        if elapsed < _NIST_DELAY_SECONDS:
            time.sleep(_NIST_DELAY_SECONDS - elapsed)

    _last_nist_request_time = time.time()

    # Construct NIST query URL: search by InChIKey, request MS data, mask=200
    # (mask=200 appears to be the bitmask for "show MS data")
    url = f"https://webbook.nist.gov/cgi/cbook.cgi?InChI={inchikey}&Mask=200&Type=MS"

    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            html = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, Exception):
        # Network error, timeout, or invalid response
        return None

    # Parse the HTML response for the MS table
    # NIST tables follow a pattern: table rows with m/z, rel. intensity, formula
    # Look for lines with numerical m/z values and extract formula annotations

    result = {}

    # Pattern 1: Look for table rows containing m/z values (integers) and formulas
    # NIST format typically shows: <td>m/z</td> <td>intensity</td> <td>formula</td>
    # Example: <tr><td>77</td><td>100</td><td>C6H5</td></tr>
    # More complex patterns may have additional spacing/formatting.

    # A more robust approach: find all lines that look like peak data.
    # Look for patterns like:  number (m/z), number (intensity), formula string.
    # The formula is typically C/H/N/O/S/P/etc. combinations.

    lines = html.split("\n")
    in_ms_table = False

    for line in lines:
        # Detect start of MS table
        if "Mass Spectral Data" in line or "m/z" in line and "Relative" in line:
            in_ms_table = True
            continue

        if not in_ms_table:
            continue

        # Exit table when we hit a new section or end marker
        if "</table>" in line.lower():
            break

        # Look for table data (TD) tags containing numeric m/z and formula
        # Pattern: <td>mz</td>...<td>formula</td>
        # Simplified: extract all td content
        td_values = re.findall(r"<td[^>]*>([^<]+)</td>", line, re.IGNORECASE)

        if len(td_values) >= 3:
            # Attempt to parse: m/z (first), intensity (second), formula (third or later)
            try:
                mz_str = td_values[0].strip()
                # Try to parse as integer m/z
                if not mz_str:
                    continue

                # Extract integer m/z (handle possible float input)
                mz_match = re.match(r"^(\d+)", mz_str)
                if not mz_match:
                    continue
                mz = int(mz_match.group(1))

                # Find a formula in the remaining values
                # Formula is typically a string like C6H5, CH3O, etc.
                formula = None
                for val in td_values[2:]:
                    val = val.strip()
                    # Check if this looks like a chemical formula
                    # Chemical formulas contain letters (elements) and numbers
                    if val and re.match(r"^[A-Z][a-z]?(\d+)?([A-Z][a-z]?(\d+)?)*$", val):
                        formula = val
                        break

                if formula:
                    result[mz] = formula

            except (ValueError, IndexError):
                # Skip lines that don't parse
                continue

    # Also try a fallback pattern: look for plain text patterns like "77 | C6H5"
    # in case the HTML structure is different
    if not result:
        # Fallback: find patterns like "m/z=77" or just "77" followed by formula
        pattern = r"(\d+)\s+\|?\s+([A-Z][a-z]?(?:\d+)?(?:[A-Z][a-z]?(?:\d+)?)*)"
        for match in re.finditer(pattern, html):
            mz = int(match.group(1))
            formula = match.group(2)
            result[mz] = formula

    return result if result else None
