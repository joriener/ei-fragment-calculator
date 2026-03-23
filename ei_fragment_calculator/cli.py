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

    # Show only the best-ranked candidate per peak; skip peaks with no fit
    ei-fragment-calc spectra.sdf --best-only
"""

import os
import sys
import argparse
import multiprocessing as mp
from .formula     import parse_formula, hill_formula
from .calculator  import exact_mass, ion_mass, calculate_dbe, find_fragment_candidates
from .sdf_parser  import parse_sdf, get_formula_and_peaks
from .isotope     import isotope_pattern, pattern_summary
from .constants   import ELECTRON_MASS
from .preflight   import run_preflight_checks
from .filters     import FilterConfig, rank_candidates
from .mol_parser  import parse_mol_block, extract_mol_block
from .sdf_writer  import write_exact_masses_sdf, exact_sdf_path


def format_record(
    record: dict,
    tolerance: float,
    electron_mode: str,
    hide_empty: bool,
    show_isotope: bool,
    best_only: bool = False,
    filter_config=None,
    sdf_results: list = None,
    record_index: int = 0,
) -> str:
    """
    Process one SDF record and return the formatted result string.

    Parameters
    ----------
    record        : dict        One record from parse_sdf()
    tolerance     : float       Mass window in Da
    electron_mode : str         'remove' / 'add' / 'none'
    hide_empty    : bool        If True, peaks with 0 candidates are omitted
    show_isotope  : bool        If True, show theoretical isotope pattern per candidate
    best_only     : bool        If True, show only the highest-ranked candidate per
                                peak and skip peaks where that candidate fails filters
    filter_config : FilterConfig | None  If provided, run filter pipeline
    sdf_results   : list | None  If provided, append SDF result dicts here
    record_index  : int         Position of this record in the input file (0-based).
                                Used as a unique key in the SDF writer so that
                                records sharing a MOL-block name (e.g. "No Structure")
                                are never merged together.
    """
    # Prefer the <NAME> SDF data field over the MOL-block first line so that
    # records whose MOL block starts with "No Structure" still display the
    # correct compound name (e.g. "Aniline").
    from .sdf_parser import find_field as _find_field
    name = (
        _find_field(record.get("fields", {}), ["NAME", "COMPOUND NAME", "COMPOUND_NAME"])
        or record["name"]
        or "(unnamed compound)"
    )
    lines: list[str] = []

    formula_str, nominal_mzs = get_formula_and_peaks(record)

    if formula_str is None:
        return "  [SKIP] No molecular formula field found for '{}'.\n".format(name)
    if not nominal_mzs:
        return "  [SKIP] No mass spectral peaks found for '{}'.\n".format(name)

    try:
        parent = parse_formula(formula_str.strip())
    except ValueError as exc:
        return "  [ERROR] {}\n".format(exc)

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
        "remove": "- m_e = -{:.9f} Da  (positive-ion EI)".format(ELECTRON_MASS),
        "add":    "+ m_e = +{:.9f} Da  (negative-ion EI)".format(ELECTRON_MASS),
        "none":   "no correction applied",
    }[electron_mode]

    lines.append("=" * 72)
    lines.append("Compound        : {}".format(name))
    lines.append(
        "Formula         : {}   "
        "[neutral = {:.6f} Da,  DBE = {:.1f}]".format(
            parent_formula, parent_neutral, parent_dbe
        )
    )
    lines.append(
        "Ion mass (M+\u2022)  : {:.6f} Da  "
        "[{}]".format(parent_ion, correction_desc)
    )
    if show_isotope and parent_iso_str:
        lines.append("Isotope pattern : {}".format(parent_iso_str))
    lines.append("Tolerance       : \u00b1{} Da".format(tolerance))
    lines.append("Peaks           : {}".format(len(nominal_mzs)))
    if best_only:
        lines.append("Mode            : best-only (top-ranked candidate per peak)")
    lines.append("=" * 72)

    mol_block = record.get("mol_block", "")
    original_fields = record.get("fields", {})

    for mz in nominal_mzs:
        candidates = find_fragment_candidates(
            mz, parent, tolerance, electron_mode,
            include_isotope_pattern=show_isotope,
            filter_config=filter_config,
        )

        # --- best-only mode: keep only the top-ranked candidate ---
        if best_only:
            if candidates:
                ranked = rank_candidates(candidates)
                best   = ranked[0]
                # Drop peak if best candidate does not pass filters
                if not best.get("filter_passed", True):
                    continue
                candidates = [best]
            else:
                continue  # no candidates → peak deleted

        # Collect SDF output data if requested
        if sdf_results is not None:
            for c in candidates:
                sdf_results.append({
                    "mol_block":     mol_block,
                    "fields":        original_fields,
                    "compound_name": name,
                    "record_index":  record_index,
                    "peak_mz":       mz,
                    "candidate":     c,
                })

        if not candidates and hide_empty:
            continue

        if candidates:
            lines.append("\n  m/z {:>5d}  \u2014  {} candidate(s)".format(
                mz, len(candidates)))
            show_filter = filter_config is not None

            if show_isotope:
                filter_hdr = "  FILTER" if show_filter else ""
                lines.append(
                    "    {:<14}  {:>13}  "
                    "{:>13}  {:>10}  {:>5}  "
                    "Isotope pattern{}".format(
                        "Formula", "Neutral mass",
                        "Ion m/z", "Delta mass", "DBE",
                        filter_hdr
                    )
                )
                lines.append(
                    "    {}  {}  {}  {}  {}  {}".format(
                        "-" * 14, "-" * 13, "-" * 13,
                        "-" * 10, "-" * 5, "-" * 30
                    ) + ("  " + "-" * 6 if show_filter else "")
                )
                for c in candidates:
                    flt = ("  " + ("OK" if c.get("filter_passed", True) else "FAIL"))
                    lines.append(
                        "    {:<14}  "
                        "{:>13.6f}  "
                        "{:>13.6f}  "
                        "{:>+10.6f}  "
                        "{:>5.1f}  "
                        "{}".format(
                            c["formula"],
                            c["neutral_mass"],
                            c["ion_mass"],
                            c["delta_mass"],
                            c["dbe"],
                            c.get("isotope_summary", "\u2014"),
                        ) + (flt if show_filter else "")
                    )
            else:
                filter_hdr = "  FILTER" if show_filter else ""
                lines.append(
                    "    {:<14}  {:>13}  "
                    "{:>13}  {:>10}  {:>5}{}".format(
                        "Formula", "Neutral mass",
                        "Ion m/z", "Delta mass", "DBE",
                        filter_hdr
                    )
                )
                lines.append(
                    "    {}  {}  {}  {}  {}".format(
                        "-" * 14, "-" * 13, "-" * 13,
                        "-" * 10, "-" * 5
                    ) + ("  " + "-" * 6 if show_filter else "")
                )
                for c in candidates:
                    flt = ("  " + ("OK" if c.get("filter_passed", True) else "FAIL"))
                    lines.append(
                        "    {:<14}  "
                        "{:>13.6f}  "
                        "{:>13.6f}  "
                        "{:>+10.6f}  "
                        "{:>5.1f}".format(
                            c["formula"],
                            c["neutral_mass"],
                            c["ion_mass"],
                            c["delta_mass"],
                            c["dbe"],
                        ) + (flt if show_filter else "")
                    )
        else:
            lines.append(
                "\n  m/z {:>5d}  \u2014  no candidates "
                "(outside formula constraints or invalid DBE)".format(mz)
            )

    lines.append("")
    return "\n".join(lines)


def _process_record(args: tuple) -> tuple[str, list]:
    """
    Top-level picklable worker used by multiprocessing.Pool.

    Parameters mirror format_record() kwargs, packed as a tuple so
    pool.map() can call this with a single iterable argument.

    Returns
    -------
    (output_text, sdf_results_for_this_record)
    """
    record, tolerance, electron_mode, hide_empty, show_isotope, \
        best_only, filter_config, save_sdf, record_index = args
    local_sdf: list = [] if save_sdf else None
    text = format_record(
        record,
        tolerance=tolerance,
        electron_mode=electron_mode,
        hide_empty=hide_empty,
        show_isotope=show_isotope,
        best_only=best_only,
        filter_config=filter_config,
        sdf_results=local_sdf,
        record_index=record_index,
    )
    return text, local_sdf


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
  ei-fragment-calc spectra.sdf --best-only
  ei-fragment-calc spectra.sdf --no-save-sdf   # skip SDF output
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
            "'add' (EI-), or 'none'."
        ),
    )
    parser.add_argument(
        "--isotope", "-i",
        action="store_true",
        default=False,
        help=(
            "Calculate and display the theoretical isotope pattern "
            "(M, M+1, M+2, ...) for every candidate formula."
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
    parser.add_argument(
        "--best-only",
        action="store_true",
        default=False,
        help=(
            "Show only the highest-ranked candidate per peak (ranked by "
            "filter pass, then mass accuracy, then isotope score). "
            "Peaks where the best candidate still fails all filters are "
            "silently dropped from the output."
        ),
    )

    # Algorithm toggle flags
    filter_group = parser.add_argument_group(
        "algorithm filters",
        "All filters are ON by default. Use --no-* flags to deactivate individually.",
    )
    filter_group.add_argument(
        "--no-nitrogen-rule", action="store_true", default=False,
        help="Disable nitrogen rule filter. Ref: McLafferty & Turecek 1993.",
    )
    filter_group.add_argument(
        "--no-hd-check", action="store_true", default=False,
        help="Disable hydrogen deficiency (DBE/C) check. Ref: Pretsch et al. 2009.",
    )
    filter_group.add_argument(
        "--no-lewis-senior", action="store_true", default=False,
        help="Disable Lewis & Senior valence-sum rules. Ref: Senior 1951.",
    )
    filter_group.add_argument(
        "--no-isotope-score", action="store_true", default=False,
        help="Disable isotope pattern match scoring. Ref: Gross 2017.",
    )
    filter_group.add_argument(
        "--no-smiles-constraints", action="store_true", default=False,
        help="Disable structure-based ring-count constraints. Ref: Weininger 1988.",
    )
    filter_group.add_argument(
        "--isotope-tolerance", type=float, default=30.0, metavar="PP",
        help="Max isotope score deviation in percentage points (default: 30.0).",
    )
    filter_group.add_argument(
        "--max-ring-ratio", type=float, default=0.5, metavar="RATIO",
        help="Max DBE/C ratio for H-deficiency check (default: 0.5).",
    )
    parser.add_argument(
        "--no-save-sdf", action="store_true", default=False,
        help="Do not write the <input>-EXACT.sdf output file (SDF is saved by default).",
    )
    parser.add_argument(
        "--output-sdf", type=str, default=None, metavar="FILE",
        help=(
            "Write the EXACT.sdf output to FILE instead of the default "
            "'<input>-EXACT.sdf' path next to the input file."
        ),
    )
    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=os.cpu_count() or 1,
        metavar="N",
        help=(
            "Number of parallel worker processes (default: all CPU cores). "
            "Set to 1 to disable multiprocessing."
        ),
    )

    return parser


def main(argv: list[str] | None = None) -> None:
    """Entry point for the ``ei-fragment-calc`` command."""
    # On Windows, freeze_support() must be called before any Pool is created
    # so that frozen-app worker processes act as workers rather than
    # re-launching the full application (which would cause a cascade of new
    # windows). It is a no-op on non-Windows and in non-frozen environments.
    mp.freeze_support()

    # Run environment checks before anything else so the user gets a clear
    # error message if Python is too old or the data CSV is missing.
    run_preflight_checks()

    parser = build_parser()
    args   = parser.parse_args(argv)

    filter_cfg = FilterConfig(
        nitrogen_rule      = not args.no_nitrogen_rule,
        hd_check           = not args.no_hd_check,
        lewis_senior       = not args.no_lewis_senior,
        isotope_score      = not args.no_isotope_score,
        smiles_constraints = not args.no_smiles_constraints,
        isotope_tolerance  = args.isotope_tolerance,
        max_ring_ratio     = args.max_ring_ratio,
    )

    original_stdout = sys.stdout
    if args.output:
        try:
            sys.stdout = open(args.output, "w", encoding="utf-8")
        except OSError as exc:
            print("[ERROR] Cannot open output file: {}".format(exc), file=sys.stderr)
            sys.exit(1)

    try:
        records = parse_sdf(args.sdf_file)
    except FileNotFoundError:
        print("[ERROR] File not found: '{}'".format(args.sdf_file), file=sys.stderr)
        sys.exit(1)

    if not records:
        print("[ERROR] No records found in the SDF file.", file=sys.stderr)
        sys.exit(1)

    electron_desc = {
        "remove": "positive-ion EI  (m/z = M_neutral - m_e)",
        "add":    "negative-ion EI  (m/z = M_neutral + m_e)",
        "none":   "no correction   (m/z = M_neutral)",
    }[args.electron_mode]

    print(
        "EI Fragment Exact-Mass Calculator\n"
        "  SDF file        : {}\n"
        "  Records found   : {}\n"
        "  Tolerance       : +/-{} Da\n"
        "  Electron mode   : {}  ({})\n"
        "  Isotope pattern : {}\n"
        "  Best-only mode  : {}\n".format(
            args.sdf_file,
            len(records),
            args.tolerance,
            args.electron_mode,
            electron_desc,
            "yes" if args.isotope else "no",
            "yes (top-ranked candidate per peak; unmatched peaks dropped)"
            if args.best_only else "no",
        )
    )

    save_sdf = not args.no_save_sdf
    all_sdf_results: list = [] if save_sdf else None

    workers = max(1, args.workers)
    worker_args = [
        (
            record,
            args.tolerance,
            args.electron_mode,
            args.hide_empty,
            args.isotope,
            args.best_only,
            filter_cfg,
            save_sdf,
            idx,
        )
        for idx, record in enumerate(records)
    ]

    total = len(records)

    if workers == 1 or total == 1:
        # ── Sequential path ───────────────────────────────────────────────
        for i, wa in enumerate(worker_args, 1):
            text, sdf_part = _process_record(wa)
            print(text, flush=True)
            print("[{}/{}] done".format(i, total), flush=True)
            if save_sdf and sdf_part:
                all_sdf_results.extend(sdf_part)
    else:
        # ── Parallel path ─────────────────────────────────────────────────
        workers = min(workers, total)
        print("Processing {} record(s) on {} worker(s)...\n".format(
            total, workers), flush=True)
        with mp.Pool(processes=workers) as pool:
            # imap preserves order and yields results as each worker finishes
            for i, (text, sdf_part) in enumerate(
                    pool.imap(_process_record, worker_args), 1):
                print(text, flush=True)
                print("[{}/{}] done".format(i, total), flush=True)
                if save_sdf and sdf_part:
                    all_sdf_results.extend(sdf_part)

    if args.output:
        sys.stdout.close()
        sys.stdout = original_stdout
        print("Results written to '{}'.".format(args.output))

    if save_sdf and all_sdf_results is not None:
        out_path = args.output_sdf or exact_sdf_path(args.sdf_file)
        n = write_exact_masses_sdf(all_sdf_results, out_path)
        print("Saved {} compound(s) to '{}'.".format(n, out_path))
