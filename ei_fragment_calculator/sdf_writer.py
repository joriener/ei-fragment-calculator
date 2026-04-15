"""
sdf_writer.py
=============
Write fragment analysis results as a modified SDF file (``*-EXACT.sdf``).

The output preserves the exact structure of the input SDF — one record per
compound, same MOL block, same data fields — with two modifications:

1. ``MASS SPECTRAL PEAKS``  — nominal unit-mass m/z values are replaced by
   the best-matching exact monoisotopic masses (6 decimal places).
   Peaks for which no valid candidate formula was found are removed.

2. ``NUM PEAKS`` (or equivalent)  — updated to reflect the new peak count.

No extra fields are added; no fields are removed.

Output file naming
------------------
    ``spectra.sdf``    ->  ``spectra-EXACT.sdf``
    ``data/test.sdf``  ->  ``data/test-EXACT.sdf``

Reference
---------
MDL SDF format: https://www.daylight.com/meetings/mug05/Ertl/mug05_ertl.pdf
"""

import re
from collections import defaultdict, OrderedDict
from pathlib import Path
from .constants import PEAK_FIELD_CANDIDATES


# ---------------------------------------------------------------------------
# Common field name variants for "number of peaks"
# ---------------------------------------------------------------------------

_NUM_PEAKS_CANDIDATES: list[str] = [
    "NUM PEAKS",
    "NUM_PEAKS",
    "NUMBER OF PEAKS",
    "NPEAKS",
    "NUMPEAKS",
    "NUM SPECTRAL PEAKS",
]


# ---------------------------------------------------------------------------
# Output path helper
# ---------------------------------------------------------------------------

def exact_sdf_path(input_path: str) -> str:
    """
    Derive the output ``-EXACT.sdf`` path from the input SDF path.

    Examples
    --------
    >>> exact_sdf_path("spectra.sdf")
    'spectra-EXACT.sdf'
    """
    p = Path(input_path)
    return str(p.parent / (p.stem + "-EXACT.sdf"))


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _find_field_key(fields: dict, candidates: list) -> str | None:
    """Return the actual dict key that case-insensitively matches a candidate."""
    upper_map = {k.strip().upper(): k for k in fields}
    for candidate in candidates:
        key = upper_map.get(candidate.strip().upper())
        if key is not None:
            return key
    return None


def _parse_peaks_with_intensity(peak_text: str) -> list:
    """
    Parse a peak-list string into a list of (nominal_mz: int, intensity) pairs.

    Handles both layouts:
        ``"41 999 43 850 55 620"``       (space-separated integer pairs)
        ``"41 999\\n43 850\\n55 620"``    (one pair per line, integers)
        ``"3\\n41 999\\n43 850"``         (optional leading peak count, odd tokens)
        ``"91.054 100\\n92.062 70"``      (exact-mass m/z as floats)

    Decimal m/z values are rounded to the nearest integer so that they can
    be looked up in the peaks_by_mz dict (which uses nominal integer keys).
    Intensities are kept as-is (may be float for fractional abundances).

    Returns
    -------
    list[tuple[int, float|int]]  In original order (not sorted).
    """
    # Accept both integer and decimal numbers
    raw = re.findall(r"\d+(?:\.\d+)?", peak_text)
    tokens = [float(x) for x in raw]
    if len(tokens) < 2:
        return []
    # Even token count → interleaved mz/intensity pairs.
    # Odd  token count → first token is a peak count header; skip it.
    if len(tokens) % 2 != 0:
        tokens = tokens[1:]
    return [(round(tokens[i]), tokens[i + 1]) for i in range(0, len(tokens) - 1, 2)]


def _best_passing_candidate(candidates: list) -> dict | None:
    """
    Return the best-quality candidate that passes all filters, or None.

    Ranking (lower = better):
        1. filter_passed (True before False)
        2. |delta_mass|  (smallest first)
        3. isotope_score (lowest first)

    If no filters were applied (filter_passed key absent), all candidates
    are treated as passing.
    """
    passing = [c for c in candidates if c.get("filter_passed", True)]
    if not passing:
        return None
    return min(
        passing,
        key=lambda c: (abs(c.get("delta_mass", 0.0)), c.get("isotope_score", 0.0)),
    )


# ---------------------------------------------------------------------------
# Main writer
# ---------------------------------------------------------------------------

def write_exact_masses_sdf(results: list, output_path: str) -> int:
    """
    Write one SDF record per compound with exact masses in the peak field.

    The output mirrors the original SDF structure exactly. Only
    ``MASS SPECTRAL PEAKS`` and ``NUM PEAKS`` are modified:

    - Each nominal m/z that has a passing candidate formula is replaced
      by the best-matching exact ion mass (6 decimal places).
    - Peaks with no valid candidate are removed entirely.
    - ``NUM PEAKS`` is updated to the new peak count.

    Parameters
    ----------
    results     : list  List of result dicts, each containing:
                        ``mol_block``       -- MDL MOL block string
                        ``fields``          -- flat dict of original SDF fields
                        ``compound_name``   -- compound name string
                        ``peak_mz``         -- nominal integer m/z
                        ``candidate``       -- candidate dict from the pipeline
    output_path : str   Path for the ``*-EXACT.sdf`` output file.

    Returns
    -------
    int  Number of SDF records written.
    """
    # ---- Group results by record_index (preserve input order) --------------
    # Grouping by compound name is unreliable — many SDF files contain
    # records whose MOL-block name is a placeholder like "No Structure",
    # which would cause all such records to be merged into one.
    # record_index (0-based position in the input file) is always unique.
    compound_order: list[int] = []
    compounds: dict[int, dict] = {}

    for result in results:
        key = result.get("record_index", id(result))   # fallback for old data
        if key not in compounds:
            compound_order.append(key)
            compounds[key] = {
                "mol_block":     result.get("mol_block", ""),
                "fields":        dict(result["fields"]),
                "compound_name": result["compound_name"],
                "peaks":         defaultdict(list),   # nominal_mz -> [candidates]
            }
        # Skip sentinel entries (candidate=None) added when a compound has no
        # passing candidates at all — the compound is already registered above.
        if result.get("candidate") is not None:
            compounds[key]["peaks"][result["peak_mz"]].append(result["candidate"])

    # ---- Write one record per compound -----------------------------------
    records_written = 0

    with open(output_path, "w", encoding="utf-8") as fh:
        for key in compound_order:
            data     = compounds[key]
            name     = data["compound_name"]
            fields   = data["fields"]
            mol_blk  = data["mol_block"]
            peaks_by_mz = data["peaks"]

            # Find the peak field key in this record's fields
            peak_key     = _find_field_key(fields, PEAK_FIELD_CANDIDATES)
            num_key      = _find_field_key(fields, _NUM_PEAKS_CANDIDATES)

            # Parse original (mz, intensity) pairs
            mz_intensity = []
            if peak_key and fields.get(peak_key):
                mz_intensity = _parse_peaks_with_intensity(fields[peak_key])

            # Build new peak list: replace nominal mz with best exact mass
            new_peaks: list[tuple[str, int]] = []
            for mz, intensity in mz_intensity:
                if mz in peaks_by_mz:
                    best = _best_passing_candidate(peaks_by_mz[mz])
                    if best is not None:
                        new_peaks.append(("{:.6f}".format(best["ion_mass"]), intensity))

            # Build modified fields dict (preserve original key order).
            # If no exact masses were assigned for this compound, copy all
            # fields unchanged so the original nominal peaks are preserved.
            modified: dict[str, str] = OrderedDict()
            if new_peaks:
                for k, v in fields.items():
                    if num_key and k == num_key:
                        modified[k] = str(len(new_peaks))
                    elif peak_key and k == peak_key:
                        modified[k] = "\n".join(
                            "{} {}".format(m, i) for m, i in new_peaks
                        )
                    else:
                        modified[k] = v
            else:
                # No candidates passed — keep original fields untouched
                modified.update(fields)

            # ---- ChemVista / standard SDF compatibility fixes ---------------

            # 1. Ensure <NAME> field exists as the very first data field.
            #    Many SDF importers (ChemVista, ChemDraw, …) require an explicit
            #    <NAME> field; they do NOT read the MOL-block header line 1.
            if not _find_field_key(modified, ["NAME", "COMPOUND NAME", "COMPOUND_NAME"]):
                name_first: dict[str, str] = OrderedDict()
                name_first["NAME"] = name
                name_first.update(modified)
                modified = name_first

            # 2. Add <FORMULA> alias when only <MOLECULAR FORMULA> is present.
            #    ChemVista uses FORMULA; keep MOLECULAR FORMULA too for NIST tools.
            if (_find_field_key(modified, ["MOLECULAR FORMULA"])
                    and not _find_field_key(modified, ["FORMULA"])):
                mol_form_key = _find_field_key(modified, ["MOLECULAR FORMULA"])
                with_formula: dict[str, str] = OrderedDict()
                for k, v in modified.items():
                    with_formula[k] = v
                    if k == mol_form_key:
                        with_formula["FORMULA"] = v   # duplicate as FORMULA
                modified = with_formula

            # 3. Ensure <NUM PEAKS> field exists immediately before the peak
            #    field.  ChemVista and MSP-aware tools expect it.
            actual_peak_key = _find_field_key(modified, PEAK_FIELD_CANDIDATES)
            if actual_peak_key and not _find_field_key(modified, _NUM_PEAKS_CANDIDATES):
                n_peaks = len(new_peaks) if new_peaks else len(
                    _parse_peaks_with_intensity(modified.get(actual_peak_key, ""))
                )
                with_num: dict[str, str] = OrderedDict()
                for k, v in modified.items():
                    if k == actual_peak_key:
                        with_num["NUM PEAKS"] = str(n_peaks)
                    with_num[k] = v
                modified = with_num

            # ---- Assemble the SDF record ---------------------------------
            parts: list[str] = []

            # MOL block (or minimal placeholder if absent).
            # Always terminate with M  END so downstream parsers are happy.
            if mol_blk:
                stripped_blk = mol_blk.rstrip()
                if not re.search(r"M\s+END\s*$", stripped_blk):
                    stripped_blk += "\nM  END"
                parts.append(stripped_blk)
            else:
                parts.append(
                    "{}\n     EI_FRAG\n\n"
                    "  0  0  0     0  0            999 V2000\n"
                    "M  END".format(name)
                )

            # Data fields
            for fname, fval in modified.items():
                parts.append("")
                parts.append("> <{}>".format(fname))
                parts.append(fval)

            parts.append("")
            parts.append("$$$$")
            parts.append("")

            fh.write("\n".join(parts))
            records_written += 1

    return records_written


# ---------------------------------------------------------------------------
# Legacy writer (kept for backward API compatibility)
# ---------------------------------------------------------------------------

def write_exact_sdf(results: list, output_path: str) -> int:
    """
    Alias for :func:`write_exact_masses_sdf` (retained for compatibility).
    """
    return write_exact_masses_sdf(results, output_path)


# ---------------------------------------------------------------------------
# MSP (NIST format) writer — unit-mass → high-resolution conversion output
# ---------------------------------------------------------------------------

def exact_msp_path(input_path: str) -> str:
    """
    Derive the ``-EXACT.msp`` output path from the input file path.

    Examples
    --------
    >>> exact_msp_path("spectra.sdf")
    'spectra-EXACT.msp'
    >>> exact_msp_path("data/nist.msp")
    'data/nist-EXACT.msp'
    """
    p = Path(input_path)
    return str(p.parent / (p.stem + "-EXACT.msp"))


def write_exact_masses_msp(results: list, output_path: str) -> int:
    """
    Write one NIST MSP record per compound with exact masses in the peak list.

    This is the unit-mass → high-resolution conversion output format.
    Each confirmed peak (one with a passing candidate formula) is written
    with the theoretical exact ion m/z (6 decimal places) and the original
    relative intensity.  Peaks with no confirmed assignment are omitted.

    Parameters
    ----------
    results     : list  Same list of result dicts as used by
                        :func:`write_exact_masses_sdf`.
    output_path : str   Path for the output ``.msp`` file.

    Returns
    -------
    int  Number of MSP records written.
    """
    from .sdf_parser import find_field
    from .constants import FORMULA_FIELD_CANDIDATES

    # ---- Group results by record_index (same logic as SDF writer) ----------
    compound_order: list[int] = []
    compounds: dict[int, dict] = {}

    for result in results:
        key = result.get("record_index", id(result))
        if key not in compounds:
            compound_order.append(key)
            compounds[key] = {
                "fields":        dict(result["fields"]),
                "compound_name": result["compound_name"],
                "peaks":         defaultdict(list),
            }
        if result.get("candidate") is not None:
            compounds[key]["peaks"][result["peak_mz"]].append(result["candidate"])

    # ---- Write one MSP record per compound ---------------------------------
    records_written = 0

    with open(output_path, "w", encoding="utf-8") as fh:
        for idx, key in enumerate(compound_order):
            data        = compounds[key]
            name        = data["compound_name"]
            fields      = data["fields"]
            peaks_by_mz = data["peaks"]

            # Retrieve metadata from original fields
            formula_str = find_field(fields, FORMULA_FIELD_CANDIDATES) or ""
            mw_str = (
                fields.get("MW")
                or fields.get("Mw")
                or fields.get("mw")
                or fields.get("EXACT MASS")
                or ""
            )

            # Build confirmed peak list (exact mass, intensity)
            # Use _parse_peaks_with_intensity to recover original order + intensities
            peak_key    = _find_field_key(fields, PEAK_FIELD_CANDIDATES)
            mz_intensity: list = []
            if peak_key and fields.get(peak_key):
                mz_intensity = _parse_peaks_with_intensity(fields[peak_key])

            new_peaks: list[tuple[str, float]] = []
            for mz, intensity in mz_intensity:
                if mz in peaks_by_mz:
                    best = _best_passing_candidate(peaks_by_mz[mz])
                    if best is not None:
                        new_peaks.append(("{:.6f}".format(best["ion_mass"]), intensity))

            # Separator between records
            if idx > 0:
                fh.write("\n")

            # Write MSP header fields
            fh.write("Name: {}\n".format(name))
            if formula_str:
                fh.write("Formula: {}\n".format(formula_str))
            if mw_str:
                # Write as integer nominal MW if it looks like a float with no
                # significant decimal (e.g. "194.08037" → "194"); keep as-is
                # if it is already an integer string like "194".
                try:
                    fh.write("MW: {}\n".format(int(float(mw_str))))
                except ValueError:
                    fh.write("MW: {}\n".format(mw_str))

            # Comments: copy any COMMENTS / ORIGIN field if present
            comments = (
                fields.get("COMMENTS")
                or fields.get("Comment")
                or fields.get("ORIGIN")
                or ""
            )
            if comments:
                fh.write("Comments: {}\n".format(comments.strip()))

            fh.write("Num Peaks: {}\n".format(len(new_peaks)))

            # Write peaks — no trailing space, one pair per line
            for exact_mz, intensity in new_peaks:
                fh.write("{} {}\n".format(exact_mz, int(round(intensity))))

            records_written += 1

    return records_written
