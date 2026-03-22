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
    Parse a peak-list string into a list of (nominal_mz: int, intensity: int) pairs.

    Handles both layouts:
        ``"41 999 43 850 55 620"``     (space-separated pairs on one line)
        ``"41 999\\n43 850\\n55 620"``  (one pair per line)
        ``"3\\n41 999\\n43 850"``       (optional leading peak count, odd tokens)

    Returns
    -------
    list[tuple[int, int]]  In original order (not sorted).
    """
    tokens = list(map(int, re.findall(r"\d+", peak_text)))
    if len(tokens) < 2:
        return []
    # Even token count → interleaved mz/intensity pairs.
    # Odd  token count → first token is a peak count header; skip it.
    if len(tokens) % 2 != 0:
        tokens = tokens[1:]
    return [(tokens[i], tokens[i + 1]) for i in range(0, len(tokens) - 1, 2)]


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
    # ---- Group results by compound (preserve input order) ----------------
    compound_order: list[str] = []
    compounds: dict[str, dict] = {}

    for result in results:
        name = result["compound_name"]
        if name not in compounds:
            compound_order.append(name)
            compounds[name] = {
                "mol_block": result.get("mol_block", ""),
                "fields":    dict(result["fields"]),
                "peaks":     defaultdict(list),   # nominal_mz -> [candidates]
            }
        compounds[name]["peaks"][result["peak_mz"]].append(result["candidate"])

    # ---- Write one record per compound -----------------------------------
    records_written = 0

    with open(output_path, "w", encoding="utf-8") as fh:
        for name in compound_order:
            data     = compounds[name]
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

            # Build modified fields dict (preserve original key order)
            modified: dict[str, str] = OrderedDict()
            for k, v in fields.items():
                if num_key and k == num_key:
                    modified[k] = str(len(new_peaks))
                elif peak_key and k == peak_key:
                    modified[k] = "\n".join(
                        "{} {}".format(m, i) for m, i in new_peaks
                    )
                else:
                    modified[k] = v

            # ---- Assemble the SDF record ---------------------------------
            parts: list[str] = []

            # MOL block (or minimal placeholder if absent)
            if mol_blk:
                parts.append(mol_blk)
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
