"""
sdf_parser.py
=============
Minimal SDF (Structure-Data File) parser.

SDF format summary
------------------
An SDF file contains one or more *records*.  Each record consists of:
  - An MDL MOL block (atom coordinates, bond table, …)
  - One or more named data fields:
        > <FIELDNAME>
        field value (one or more lines)
        (blank line terminates the field value)
  - A record terminator:  $$$$

This parser does *not* interpret the MOL coordinate block — it only extracts
the compound name (line 0 of the MOL block) and the named data fields.
"""

import re
from .constants import PEAK_FIELD_CANDIDATES, FORMULA_FIELD_CANDIDATES


def parse_sdf(filepath: str) -> list[dict]:
    """
    Parse an SDF file and return one dict per compound record.

    Parameters
    ----------
    filepath : str  Path to the .sdf file.

    Returns
    -------
    list[dict]  Each dict has:
        ``name``   : str   Compound name / identifier (first line of MOL block).
        ``fields`` : dict  All > <FIELDNAME> entries as str → str.

    Raises
    ------
    FileNotFoundError  if the file does not exist.
    """
    with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
        raw_text = fh.read()

    # Each record is terminated by "$$$$" on its own line.
    raw_records = raw_text.split("$$$$")

    records: list[dict] = []

    for raw in raw_records:
        raw = raw.strip()
        if not raw:
            continue   # skip empty trailing block after last "$$$$"

        lines = raw.splitlines()

        # Line 0 of every MDL MOL block is the compound name (may be blank)
        name = lines[0].strip() if lines else ""

        # ------------------------------------------------------------------
        # Parse data fields.
        # A field starts with a header line matching:  > <FIELDNAME>
        # optionally followed by a data-tag suffix:    > <FIELDNAME> (dtag)
        # The field value spans all following non-header lines until a blank
        # line or the next header.
        # ------------------------------------------------------------------
        fields: dict[str, str] = {}
        field_name: str | None = None
        value_lines: list[str] = []

        for line in lines:
            header_match = re.match(r"^>\s*<([^>]+)>", line)
            if header_match:
                # Save previous field before starting a new one
                if field_name is not None:
                    fields[field_name] = "\n".join(value_lines).strip()
                field_name  = header_match.group(1).strip()
                value_lines = []
            elif field_name is not None:
                value_lines.append(line)

        # Save the last field in this record
        if field_name is not None:
            fields[field_name] = "\n".join(value_lines).strip()

        records.append({"name": name, "fields": fields})

    return records


def find_field(fields: dict[str, str], candidates: list[str]) -> str | None:
    """
    Case-insensitive lookup of the first matching key in an SDF fields dict.

    Parameters
    ----------
    fields     : dict  SDF data fields (key → value).
    candidates : list  Ordered list of field names to try.

    Returns
    -------
    str | None  Field value of the first match, or None if no match found.
    """
    upper_map = {k.upper(): v for k, v in fields.items()}
    for candidate in candidates:
        value = upper_map.get(candidate.upper())
        if value is not None:
            return value
    return None


def parse_peaks(peak_text: str) -> list[int]:
    """
    Extract nominal m/z values from a raw SDF peak-field string.

    SDF mass spectral data is almost always stored as space- or
    tab-separated  ``mz intensity``  pairs, either on a single long
    line or one pair per line.  Only the m/z values are returned;
    intensities are discarded.

    Handles both layouts:
        ``"41 999 43 850 55 620 77 412"``   (NIST style, one line)
        ``"41 999\\n43 850\\n55 620"``       (MassBank style, one per line)

    Parameters
    ----------
    peak_text : str  Raw text content of the peak data field.

    Returns
    -------
    list[int]  Sorted, deduplicated list of nominal m/z values.
    """
    tokens = list(map(int, re.findall(r"\d+", peak_text)))

    if len(tokens) < 2:
        return []

    # Even token count → interleaved mz/intensity pairs → take even indices.
    # Odd token count  → first token may be a peak count header → skip it,
    #                     then take even-indexed tokens from the remainder.
    if len(tokens) % 2 == 0:
        mz_values = tokens[0::2]
    else:
        mz_values = tokens[1::2]

    return sorted(set(mz_values))


def get_formula_and_peaks(
    record: dict,
) -> tuple[str | None, list[int]]:
    """
    Convenience wrapper: extract molecular formula and peak list from one
    SDF record using the standard field-name candidates.

    Parameters
    ----------
    record : dict  One record as returned by :func:`parse_sdf`.

    Returns
    -------
    tuple (formula_str | None, list[int])
        ``formula_str`` – raw formula string, or None if not found.
        peak list       – sorted nominal m/z values (may be empty).
    """
    fields    = record["fields"]
    formula   = find_field(fields, FORMULA_FIELD_CANDIDATES)
    peak_text = find_field(fields, PEAK_FIELD_CANDIDATES)
    peaks     = parse_peaks(peak_text) if peak_text else []
    return formula, peaks
