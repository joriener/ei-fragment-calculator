"""
sdf_writer.py
=============
Write fragment analysis results as an SDF file (``*-EXACT.sdf``).

One SDF record per (compound, peak, candidate) triple.  Each record
contains the original MOL block, all original data fields, and new
analysis fields added by the calculator.

Output file naming
------------------
    ``spectra.sdf``    ->  ``spectra-EXACT.sdf``
    ``data/test.sdf``  ->  ``data/test-EXACT.sdf``

Reference
---------
MDL SDF format: https://www.daylight.com/meetings/mug05/Ertl/mug05_ertl.pdf
"""

from pathlib import Path
from .isotope import pattern_summary


# ---------------------------------------------------------------------------
# Output path helper
# ---------------------------------------------------------------------------

def exact_sdf_path(input_path: str) -> str:
    """
    Derive the output ``-EXACT.sdf`` path from the input SDF path.

    Parameters
    ----------
    input_path : str  Path to the input ``.sdf`` file.

    Returns
    -------
    str  Output path with ``-EXACT`` inserted before the extension.

    Examples
    --------
    >>> exact_sdf_path("spectra.sdf")
    'spectra-EXACT.sdf'
    """
    p    = Path(input_path)
    stem = p.stem
    return str(p.parent / (stem + "-EXACT.sdf"))


# ---------------------------------------------------------------------------
# SDF record builder
# ---------------------------------------------------------------------------

REFERENCE_NOTES = (
    "Algorithms: "
    "(1) Nitrogen rule: McLafferty & Turecek 1993 "
    "https://doi.org/10.1002/jms.1190080509 | "
    "(2) H-deficiency: Pretsch et al. 2009 "
    "https://doi.org/10.1007/978-3-540-93810-1 | "
    "(3) Lewis/Senior: Senior 1951 https://doi.org/10.2307/2372318 | "
    "(4) Isotope pattern: Gross 2017 "
    "https://doi.org/10.1007/978-3-319-54398-7 | "
    "(5) SMILES/structure: Weininger 1988 "
    "https://doi.org/10.1021/ci00057a005"
)


def _format_field(name: str, value: str) -> str:
    """Format one SDF data field block."""
    return "> <{}>\n{}\n".format(name, value)


def _format_filter_details(details: dict) -> str:
    """Format filter details dict as a compact multi-line string."""
    lines = []
    for key, val in details.items():
        lines.append("{}: {}".format(key, val))
    return "\n".join(lines) if lines else "no filters applied"


def build_sdf_record(
    mol_block: str,
    original_fields: dict,
    compound_name: str,
    peak_mz: int,
    candidate: dict,
) -> str:
    """
    Build one SDF record string for a single (compound, peak, candidate).

    Parameters
    ----------
    mol_block       : str   MDL MOL block text (may be empty).
    original_fields : dict  Original SDF data fields to preserve.
    compound_name   : str   Name / identifier of the compound.
    peak_mz         : int   Nominal m/z of the spectral peak.
    candidate       : dict  Candidate dict enriched by run_all_filters().

    Returns
    -------
    str  Complete SDF record ending with ``$$$$\\n``.
    """
    parts = []

    if mol_block and mol_block.strip():
        parts.append(mol_block.strip())
    else:
        parts.append(
            "{}\n     EI_FRAG\n\n"
            "  0  0  0     0  0            999 V2000\n"
            "M  END".format(compound_name)
        )
    parts.append("")

    for fname, fval in original_fields.items():
        parts.append(_format_field(fname, fval))
        parts.append("")

    iso_pattern_str = ""
    if candidate.get("isotope_pattern"):
        iso_pattern_str = pattern_summary(candidate["isotope_pattern"])

    parts.append(_format_field("PEAK_MZ",          str(peak_mz)))
    parts.append("")
    parts.append(_format_field("CANDIDATE_FORMULA", candidate.get("formula", "")))
    parts.append("")
    parts.append(_format_field("NEUTRAL_MASS",
                               "{:.6f}".format(candidate.get("neutral_mass", 0.0))))
    parts.append("")
    parts.append(_format_field("ION_MASS",
                               "{:.6f}".format(candidate.get("ion_mass", 0.0))))
    parts.append("")
    parts.append(_format_field("DELTA_MASS",
                               "{:+.6f}".format(candidate.get("delta_mass", 0.0))))
    parts.append("")
    parts.append(_format_field("DBE",
                               "{:.1f}".format(candidate.get("dbe", 0.0))))
    parts.append("")
    parts.append(_format_field("ELECTRON_MODE",    candidate.get("electron_mode", "remove")))
    parts.append("")
    parts.append(_format_field("FILTER_PASSED",
                               "YES" if candidate.get("filter_passed", True) else "NO"))
    parts.append("")
    parts.append(_format_field("FILTER_DETAILS",
                               _format_filter_details(candidate.get("filter_details", {}))))
    parts.append("")
    parts.append(_format_field("ISOTOPE_SCORE",
                               "{:.2f}".format(candidate.get("isotope_score", 0.0))))
    parts.append("")

    if iso_pattern_str:
        parts.append(_format_field("ISOTOPE_PATTERN", iso_pattern_str))
        parts.append("")

    parts.append(_format_field("REFERENCE_NOTES", REFERENCE_NOTES))
    parts.append("")
    parts.append("$$$$")
    parts.append("")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Main writer function
# ---------------------------------------------------------------------------

def write_exact_sdf(results: list, output_path: str) -> int:
    """
    Write all candidate results to an ``-EXACT.sdf`` file.

    Parameters
    ----------
    results     : list  List of result dicts, each containing:
                        ``mol_block``, ``original_fields``,
                        ``compound_name``, ``peak_mz``, ``candidate``.
    output_path : str   Path for the output SDF file.

    Returns
    -------
    int  Number of SDF records written.
    """
    records_written = 0

    with open(output_path, "w", encoding="utf-8") as fh:
        for result in results:
            record = build_sdf_record(
                mol_block       = result.get("mol_block", ""),
                original_fields = result.get("original_fields", {}),
                compound_name   = result.get("compound_name", ""),
                peak_mz         = result.get("peak_mz", 0),
                candidate       = result.get("candidate", {}),
            )
            fh.write(record)
            records_written += 1

    return records_written
