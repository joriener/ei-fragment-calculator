"""
cli.py
======
Command-line interface for the EI fragment exact-mass calculator.

Usage examples
--------------
    # Default: positive-ion EI, electron mass removed, ±0.5 Da window
    ei-fragment-calc spectra.sdf

    # Electron correction modes
    ei-fragment-calc spectra.sdf --electron remove   # standard EI+ (default)
    ei-fragment-calc spectra.sdf --electron add      # EI−
    ei-fragment-calc spectra.sdf --electron none     # no correction

    # Show theoretical isotope patterns for each candidate
    ei-fragment-calc spectra.sdf --isotope

    # Tighter tolerance + file output
    ei-fragment-calc spectra.sdf --tolerance 0.3 --output results.txt

    # Suppress peaks with no candidates
    ei-fragment-calc spectra.sdf --hide-empty
"""

import sys
import argparse
from .formula     import parse_formula, hill_formula
from .calculator  import exact_mass, ion_mass, calculate_dbe, find_fragment_candidates
from .sdf_parser  import parse_sdf, get_formula_and_peaks
from .isotope     import isotope_pattern, pattern_summary
from .constants   import ELECTRON_MASS
from .preflight   import run_preflight_checks


def format_record(
    record: dict,
    tolerance: float,
    electron_mode: str,
    hide_empty: bool,
    show_isotope: bool,
) -> str:
    """
    Process one SDF record and return the formatted result string.

    Parameters
    ----------
    record        : dict   One record from parse_sdf()
    tolerance     : float  Mass window in Da
    electron_mode : str    'remove' / 'add' / 'none'
    hide_empty    : bool   If True, peaks with 0 candidates are omitted
    show_isotope  : bool   If True, show theoretical isotope pattern per candidate
    """
    name  = record["name"] or "(unnamed compound)"
    lines: list[str] = []

    formula_str, nominal_mzs = get_formula_and_peaks(record)

    if formula_str is None:
        return f"  [SKIP] No molecular formula field found for '{name}'.\n"
    if not nominal_mzs:
        return f"  [SKIP] No mass spectral peaks found for '{name}'.\n"

    try:
        parent = parse_formula(formula_str.strip())
    except ValueError as exc:
        return f"  [ERROR] {exc}\n"

    parent_formula  = hill_formula(parent)
    parent_neutral  = exact_mass(parent)
    parent_ion      = ion_mass(parent_neutral, electron_mode)
    parent_dbe      = calculate_dbe(parent)

    # Isotope pattern of the intact molecule
    if show_isotope:
        parent_pattern = isotope_pattern(parent)
        parent_iso_str = pattern_summary(parent_pattern)
    else:
        parent_iso_str = ""

    correction_desc = {
        "remove": f"− m_e = −{ELECTRON_MASS:.9f} Da  (positive-ion EI)",
        "add":    f"+ m_e = +{ELECTRON_MASS:.9f} Da  (negative-ion EI)",
        "none":   "no correction applied",
    }[electron_mode]

    lines.append("=" * 72)
    lines.append(f"Compound        : {name}")
    lines.append(
        f"Formula         : {parent_formula}   "
        f"[neutral = {parent_neutral:.6f} Da,  DBE = {parent_dbe:.1f}]"
    )
    lines.append(
        f"Ion mass (M+•)  : {parent_ion:.6f} Da  "
        f"[{correction_desc}]"
    )
    if show_isotope and parent_iso_str:
        lines.append(f"Isotope pattern : {parent_iso_str}")
    lines.append(f"Tolerance       : ±{tolerance} Da")
    lines.append(f"Peaks           : {len(nominal_mzs)}")
    lines.append("=" * 72)

    for mz in nominal_mzs:
        candidates = find_fragment_candidates(
            mz, parent, tolerance, electron_mode,
            include_isotope_pattern=show_isotope,
        )

        if not candidates and hide_empty:
            continue

        if candidates:
            lines.append(f"\n  m/z {mz:>5d}  —  {len(candidates)} candidate(s)")

            if show_isotope:
                # Wider table with isotope summary column
                lines.append(
                    f"    {'Formula':<14}  {'Neutral mass':>13}  "
                    f"{'Ion m/z':>13}  {'Δ mass':>9}  {'DBE':>5}  "
                    f"Isotope pattern"
                )
                lines.append(
                    f"    {'-'*14}  {'-'*13}  {'-'*13}  {'-'*9}  {'-'*5}  "
                    f"{'-'*30}"
                )
                for c in candidates:
                    lines.append(
                        f"    {c['formula']:<14}  "
                        f"{c['neutral_mass']:>13.6f}  "
                        f"{c['ion_mass']:>13.6f}  "
                        f"{c['delta_mass']:>+9.6f}  "
                        f"{c['dbe']:>5.1f}  "
                        f"{c.get('isotope_summary', '—')}"
                    )
            else:
                lines.append(
                    f"    {'Formula':<14}  {'Neutral mass':>13}  "
                    f"{'Ion m/z':>13}  {'Δ mass':>9}  {'DBE':>5}"
                )
                lines.append(
                    f"    {'-'*14}  {'-'*13}  {'-'*13}  {'-'*9}  {'-'*5}"
                )
                for c in candidates:
                    lines.append(
                        f"    {c['formula']:<14}  "
                        f"{c['neutral_mass']:>13.6f}  "
                        f"{c['ion_mass']:>13.6f}  "
                        f"{c['delta_mass']:>+9.6f}  "
                        f"{c['dbe']:>5.1f}"
                    )
        else:
            lines.append(
                f"\n  m/z {mz:>5d}  —  no candidates "
                f"(outside formula constraints or invalid DBE)"
            )

    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="ei-fragment-calc",
        description=(
            "Calculate possible exact masses for every peak in an EI mass "
            "spectrum, constrained by the molecular formula of the compound."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
electron correction modes:
  remove  Subtract electron mass from candidate ion m/z.
          Standard positive-ion EI mode. (default)
  add     Add electron mass to candidate ion m/z.
          Use for negative-ion EI experiments.
  none    No electron-mass correction.
          Ion mass equals the neutral monoisotopic formula mass.

examples:
  ei-fragment-calc spectra.sdf
  ei-fragment-calc spectra.sdf --electron none --tolerance 0.4
  ei-fragment-calc spectra.sdf --isotope
  ei-fragment-calc spectra.sdf --electron add --output results.txt
        """,
    )

    parser.add_argument(
        "sdf_file",
        help="Path to the SDF file containing EI spectral data.",
    )
    parser.add_argument(
        "--tolerance", "-t",
        type=float,
        default=0.5,
        metavar="DA",
        help="Mass window ±Da for candidate matching (default: 0.5).",
    )
    parser.add_argument(
        "--electron", "-e",
        choices=["remove", "add", "none"],
        default="remove",
        dest="electron_mode",
        metavar="MODE",
        help=(
            "Electron-mass correction: 'remove' (EI+, default), "
            "'add' (EI−), or 'none'."
        ),
    )
    parser.add_argument(
        "--isotope", "-i",
        action="store_true",
        default=False,
        help=(
            "Calculate and display the theoretical isotope pattern "
            "(M, M+1, M+2, …) for every candidate formula."
        ),
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        metavar="FILE",
        help="Write results to FILE instead of stdout.",
    )
    parser.add_argument(
        "--hide-empty",
        action="store_true",
        default=False,
        help="Do not print peaks for which no candidate formula was found.",
    )

    return parser


def main(argv: list[str] | None = None) -> None:
    """Entry point for the ``ei-fragment-calc`` command."""
    # Run environment checks before anything else so the user gets a clear
    # error message if Python is too old or the data CSV is missing.
    run_preflight_checks()

    parser = build_parser()
    args   = parser.parse_args(argv)

    original_stdout = sys.stdout
    if args.output:
        try:
            sys.stdout = open(args.output, "w", encoding="utf-8")
        except OSError as exc:
            print(f"[ERROR] Cannot open output file: {exc}", file=sys.stderr)
            sys.exit(1)

    try:
        records = parse_sdf(args.sdf_file)
    except FileNotFoundError:
        print(f"[ERROR] File not found: '{args.sdf_file}'", file=sys.stderr)
        sys.exit(1)

    if not records:
        print("[ERROR] No records found in the SDF file.", file=sys.stderr)
        sys.exit(1)

    electron_desc = {
        "remove": "positive-ion EI  (m/z = M_neutral − m_e)",
        "add":    "negative-ion EI  (m/z = M_neutral + m_e)",
        "none":   "no correction   (m/z = M_neutral)",
    }[args.electron_mode]

    print(
        f"EI Fragment Exact-Mass Calculator\n"
        f"  SDF file        : {args.sdf_file}\n"
        f"  Records found   : {len(records)}\n"
        f"  Tolerance       : ±{args.tolerance} Da\n"
        f"  Electron mode   : {args.electron_mode}  ({electron_desc})\n"
        f"  Isotope pattern : {'yes' if args.isotope else 'no'}\n"
    )

    for record in records:
        output = format_record(
            record,
            tolerance=args.tolerance,
            electron_mode=args.electron_mode,
            hide_empty=args.hide_empty,
            show_isotope=args.isotope,
        )
        print(output)

    if args.output:
        sys.stdout.close()
        sys.stdout = original_stdout
        print(f"Results written to '{args.output}'.")
