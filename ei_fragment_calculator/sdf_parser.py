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
        # ---- Extract MOL block (everything before the first "> <…>" line) ----
        mol_block_lines: list[str] = []
        fields: dict[str, str] = {}
        field_name: str | None = None
        value_lines: list[str] = []
        in_mol_block = True

        for line in lines:
            header_match = re.match(r"^>\s*<([^>]+)>", line)
            if header_match:
                in_mol_block = False
                # Save previous field before starting a new one
                if field_name is not None:
                    fields[field_name] = "\n".join(value_lines).strip()
                field_name  = header_match.group(1).strip()
                value_lines = []
            elif in_mol_block:
                mol_block_lines.append(line)
            elif field_name is not None:
                value_lines.append(line)

        # Save the last field in this record
        if field_name is not None:
            fields[field_name] = "\n".join(value_lines).strip()

        mol_block = "\n".join(mol_block_lines).strip()
        records.append({"name": name, "mol_block": mol_block, "fields": fields})

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

    SDF mass spectral data is stored as space- or tab-separated
    ``mz intensity`` pairs, one pair per line or all on one line.
    Only the m/z values are returned; intensities are discarded.

    Handles both layouts:
        ``"41 999 43 850 55 620 77 412"``   (NIST style, one line)
        ``"41 999\\n43 850\\n55 620"``       (MassBank style, one per line)

    Also accepts exact-mass peak lists (e.g. from ChemVista / MassBank HR):
        ``"91.054227 100\\n92.062052 70"``   (exact m/z as floats)
    Decimal m/z values are rounded to the nearest integer so that the
    downstream nominal-mass matching still works correctly.

    Parameters
    ----------
    peak_text : str  Raw text content of the peak data field.

    Returns
    -------
    list[int]  Sorted, deduplicated list of nominal m/z values.
    """
    # Match both integer and decimal numbers (e.g. "91" or "91.054227")
    raw = re.findall(r"\d+(?:\.\d+)?", peak_text)
    tokens = [float(x) for x in raw]

    if len(tokens) < 2:
        return []

    # Even token count → interleaved mz/intensity pairs → take even indices.
    # Odd token count  → first token may be a peak count header → skip it,
    #                     then take even-indexed tokens from the remainder.
    if len(tokens) % 2 == 0:
        mz_values = [round(tokens[i]) for i in range(0, len(tokens), 2)]
    else:
        mz_values = [round(tokens[i]) for i in range(1, len(tokens), 2)]

    return sorted(set(mz_values))


def detect_hr_peaks(peak_text: str) -> bool:
    """
    Return True when *peak_text* looks like a high-resolution spectrum,
    i.e. the majority of m/z values above 10 Da have a fractional part
    greater than 0.010 (≥ 10 mDa from the nearest nominal integer).

    This is the heuristic used by ``--auto-hr``.

    Examples
    --------
    >>> detect_hr_peaks("91 100\\n92 70")
    False
    >>> detect_hr_peaks("91.054227 100\\n92.062052 70")
    True
    """
    raw = re.findall(r"\d+(?:\.\d+)?", peak_text)
    if len(raw) < 4:
        return False
    tokens = [float(x) for x in raw]
    if len(tokens) % 2 == 0:
        mz_vals = [tokens[i] for i in range(0, len(tokens), 2)]
    else:
        mz_vals = [tokens[i] for i in range(1, len(tokens), 2)]
    # Only consider peaks above 10 Da (ignore low-mass noise)
    sig = [v for v in mz_vals if v > 10.0]
    if not sig:
        return False
    fractional = [abs(v - round(v)) for v in sig]
    return sum(1 for f in fractional if f > 0.010) > len(fractional) * 0.5


def parse_peaks_float(peak_text: str) -> list[float]:
    """
    Extract m/z values as floats from a high-resolution peak list.

    Unlike :func:`parse_peaks`, this function preserves full decimal
    precision so that the caller can match candidates within a tight
    ppm window around each exact mass.

    Returns
    -------
    list[float]  Sorted, deduplicated list of m/z values (exact masses).
    """
    raw = re.findall(r"\d+(?:\.\d+)?", peak_text)
    tokens = [float(x) for x in raw]
    if len(tokens) < 2:
        return []
    if len(tokens) % 2 == 0:
        mz_vals = [tokens[i] for i in range(0, len(tokens), 2)]
    else:
        mz_vals = [tokens[i] for i in range(1, len(tokens), 2)]
    # Deduplicate by rounding to 3 decimal places (covers floating-point noise)
    seen: set[float] = set()
    unique: list[float] = []
    for v in sorted(mz_vals):
        key = round(v, 3)
        if key not in seen:
            seen.add(key)
            unique.append(v)
    return unique


def parse_peaks_with_intensity(peak_text: str) -> list[tuple[int, float]]:
    """
    Extract (nominal_mz, intensity) pairs from a raw SDF peak-field string.

    This is the shared tokeniser used by both ``sdf_writer`` and
    ``confidence`` so that the intensity parsing logic lives in one place.

    Parameters
    ----------
    peak_text : str  Raw text of the peak data field.

    Returns
    -------
    list[tuple[int, float]]  Sorted by m/z; duplicates averaged when the
        same nominal m/z appears more than once (rare but defensively handled).
    """
    raw = re.findall(r"\d+(?:\.\d+)?", peak_text)
    tokens = [float(x) for x in raw]

    if len(tokens) < 2:
        return []

    if len(tokens) % 2 == 0:
        pairs = [(int(round(tokens[i])), float(tokens[i + 1]))
                 for i in range(0, len(tokens), 2)]
    else:
        # Odd count: first token may be a peak-count header — skip it
        pairs = [(int(round(tokens[i])), float(tokens[i + 1]))
                 for i in range(1, len(tokens), 2) if i + 1 < len(tokens)]

    # Average duplicate nominal m/z values
    agg: dict[int, list[float]] = {}
    for mz, inten in pairs:
        agg.setdefault(mz, []).append(inten)
    return sorted((mz, sum(vs) / len(vs)) for mz, vs in agg.items())


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
