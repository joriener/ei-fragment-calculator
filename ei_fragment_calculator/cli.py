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
from .sdf_parser  import get_formula_and_peaks
from .input_reader import read_records
from .isotope     import isotope_pattern, pattern_summary
from .constants   import ELECTRON_MASS
from .preflight   import run_preflight_checks
from .filters     import FilterConfig, rank_candidates
from .mol_parser  import parse_mol_block, extract_mol_block, parse_mol_block_full
from .sdf_writer  import (write_exact_masses_sdf, exact_sdf_path,
                           write_exact_masses_msp, exact_msp_path)


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
    ppm: float = None,
    fragmentation_rules: bool = False,
    hr_input: bool = False,
    hr_ppm: float = 20.0,
    confidence: bool = False,
    confidence_threshold: float = 0.0,
    intensity_map: dict = None,
    strict_structure: bool = False,
    reference_dict: dict = None,
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
    ppm           : float|None  If set, use ppm-based per-peak tolerance instead
                                of the fixed Da tolerance.
    fragmentation_rules : bool  If True, annotate candidates with EI fragmentation
                                rules (neutral losses and structure-based cleavages).
    hr_input      : bool        If True, treat peak m/z as exact masses and match
                                candidates within ±hr_ppm (high-resolution mode).
    hr_ppm        : float       ppm tolerance for HR input mode (default 20).
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

    # Emit [WARN] if formula was derived automatically from the MOL block
    if record.get("fields", {}).get("_derived_formula") == "1":
        lines.append("  [WARN] Formula '{}' derived from MOL block atom table for '{}'.".format(
            formula_str, name))

    if formula_str is None:
        return "  [SKIP] No molecular formula field found for '{}'.\n".format(name)

    # In HR mode, use exact float m/z values from parse_peaks_float(); otherwise
    # use the nominal integer list from get_formula_and_peaks().
    if hr_input:
        from .sdf_parser import parse_peaks_float as _ppf2, find_field as _ff2
        from .constants import PEAK_FIELD_CANDIDATES
        _peak_text = _ff2(record.get("fields", {}), PEAK_FIELD_CANDIDATES)
        iter_mzs = _ppf2(_peak_text) if _peak_text else []
    else:
        iter_mzs = nominal_mzs  # list[int]

    if not iter_mzs:
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
    if hr_input:
        lines.append("Tolerance       : \u00b1{} ppm (HR input, per-peak Da varies)".format(hr_ppm))
    elif ppm is not None:
        lines.append("Tolerance       : \u00b1{} ppm (per-peak Da varies)".format(ppm))
    else:
        lines.append("Tolerance       : \u00b1{} Da".format(tolerance))
    lines.append("Peaks           : {}".format(len(iter_mzs)))
    if hr_input:
        lines.append("HR input        : yes (exact-mass spectrum, ppm matching)")
    if best_only:
        lines.append("Mode            : best-only (top-ranked candidate per peak)")
    if confidence and not hr_input:
        lines.append("Confidence      : yes (M+1/M+2 isotope, neutral-loss, DBE, stable-ion)")
    lines.append("=" * 72)

    mol_block = record.get("mol_block", "")
    original_fields = record.get("fields", {})

    # Track how many SDF entries exist before the peak loop so we can detect
    # compounds where no peak produced a candidate and still include them.
    _sdf_count_before = len(sdf_results) if sdf_results is not None else 0

    # Tier-2 structure data (parsed once per record)
    mol_data = None
    if fragmentation_rules and mol_block:
        mol_data = parse_mol_block_full(mol_block)

    # ── Reference SDF lookup: check for exact compound match ──────────────────
    _reference_peaks = {}  # {nominal_mz: exact_mass} if matched
    if reference_dict:
        ref_entry = reference_dict.get(name.lower())
        if ref_entry:
            _reference_peaks = ref_entry
            lines.append("[INFO] Reference match found for '{}': {} peaks".format(
                name, len(ref_entry)))

    # ── Confidence mode: collect ALL candidates first, then score ──────────
    _use_confidence = confidence and not hr_input
    _all_candidates_by_mz: dict = {}   # {mz: [candidate, ...]}

    # Intensity pre-filter: compute base intensity and filter weak peaks
    base_intensity = max(intensity_map.values()) if intensity_map else 1.0
    filtered_mzs = []
    for mz in iter_mzs:
        if intensity_map and base_intensity > 0:
            rel_intensity = intensity_map.get(mz, 0) / base_intensity
            if rel_intensity < 0.02:
                continue  # skip peaks < 2% of base intensity
        filtered_mzs.append(mz)

    if _use_confidence:
        for mz in filtered_mzs:
            if hr_input:
                tol = mz * hr_ppm / 1_000_000
            elif ppm is not None:
                tol = mz * ppm / 1_000_000
            else:
                tol = tolerance
            cands = find_fragment_candidates(
                mz, parent, tol, electron_mode,
                include_isotope_pattern=show_isotope,
                filter_config=filter_config,
            )
            if fragmentation_rules and cands:
                from .fragmentation_rules import (
                    annotate_neutral_losses, get_structure_fragments, annotate_candidate,
                )
                nl_m = annotate_neutral_losses(mz, parent_neutral, parent, electron_mode, tol)
                sf   = get_structure_fragments(mol_data) if mol_data else []
                cands = [annotate_candidate(c, nl_m, sf, strict_structure=strict_structure) for c in cands]
            _all_candidates_by_mz[int(round(mz))] = cands

        # Scoring phase
        _imap = intensity_map or {}
        from .confidence import score_compound
        _all_candidates_by_mz = score_compound(
            all_candidates=_all_candidates_by_mz,
            intensity_map=_imap,
            parent_composition=parent,
            parent_dbe=parent_dbe,
            mol_block=mol_block if mol_block else None,
            enable_fragmentation=fragmentation_rules,
            fragmentation_rules_enabled=fragmentation_rules,
            tolerance=tolerance if ppm is None else tolerance,
            electron_mode=electron_mode,
            n_passes=3,
        )

    for mz in filtered_mzs:
        # Per-peak tolerance: HR ppm-based, global ppm-based, or fixed Da
        if hr_input:
            tol = mz * hr_ppm / 1_000_000
        elif ppm is not None:
            tol = mz * ppm / 1_000_000
        else:
            tol = tolerance

        # ── Check for reference match first ──────────────────────────────────
        candidates = []
        nominal_mz = int(round(mz))
        if nominal_mz in _reference_peaks:
            ref_exact_mass = _reference_peaks[nominal_mz]
            # Create a reference candidate (skip enumeration entirely)
            ref_candidate = {
                "formula": "REF",
                "neutral_mass": ref_exact_mass,  # Use exact mass as neutral
                "ion_mass": ref_exact_mass,
                "delta_mass": 0.0,
                "dbe": 0.0,
                "filter_passed": True,
                "confidence": 0.99,
                "confidence_pct": 99,
                "evidence_tags": ["REF_SDF"],
            }
            candidates = [ref_candidate]
        elif _use_confidence:
            # Use pre-scored candidates from the collection phase
            candidates = _all_candidates_by_mz.get(int(round(mz)), [])
        else:
            candidates = find_fragment_candidates(
                mz, parent, tol, electron_mode,
                include_isotope_pattern=show_isotope,
                filter_config=filter_config,
            )
            # Fragmentation rule annotation
            if fragmentation_rules and candidates:
                from .fragmentation_rules import (
                    annotate_neutral_losses, get_structure_fragments, annotate_candidate,
                )
                nl_matches   = annotate_neutral_losses(mz, parent_neutral, parent, electron_mode, tol)
                struct_frags = get_structure_fragments(mol_data) if mol_data else []
                candidates   = [annotate_candidate(c, nl_matches, struct_frags, strict_structure=strict_structure) for c in candidates]

        # --- best-only mode: keep only the top-ranked candidate ---
        if best_only:
            if candidates:
                ranked = rank_candidates(candidates) if not _use_confidence else candidates
                best   = ranked[0]
                # Drop peak if best candidate does not pass filters
                if not best.get("filter_passed", True):
                    continue
                # In confidence mode, skip peaks below the confidence threshold
                if _use_confidence and confidence_threshold > 0:
                    if best.get("confidence", 1.0) < confidence_threshold:
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
                    "peak_mz":       round(mz) if hr_input else mz,
                    "candidate":     c,
                })

        if not candidates and hide_empty:
            continue

        if candidates:
            _mz_str = "{:.6f}".format(mz) if hr_input else "{:d}".format(mz)
            lines.append("\n  m/z {:>12}  \u2014  {} candidate(s)".format(
                _mz_str, len(candidates)))
            show_filter = filter_config is not None

            if show_isotope:
                filter_hdr = "  FILTER" if show_filter else ""
                conf_hdr   = "  Conf  Evidence" if _use_confidence else ""
                _delta_hdr = "Delta ppm" if hr_input else "Delta mass"
                lines.append(
                    "    {:<14}  {:>13}  "
                    "{:>13}  {:>10}  {:>5}  "
                    "Isotope pattern{}{}".format(
                        "Formula", "Neutral mass",
                        "Ion m/z", _delta_hdr, "DBE",
                        filter_hdr, conf_hdr
                    )
                )
                lines.append(
                    "    {}  {}  {}  {}  {}  {}".format(
                        "-" * 14, "-" * 13, "-" * 13,
                        "-" * 10, "-" * 5, "-" * 30
                    ) + ("  " + "-" * 6 if show_filter else "")
                      + ("  " + "-" * 4 + "  " + "-" * 16 if _use_confidence else "")
                )
                for c in candidates:
                    flt  = ("  " + ("OK" if c.get("filter_passed", True) else "FAIL"))
                    rule = c.get("fragmentation_rule", "")
                    rule_tag = "  [{}]".format(rule) if rule else ""
                    _delta = (
                        "{:>+10.2f}".format(c["delta_mass"] / mz * 1e6)
                        if hr_input and mz != 0
                        else "{:>+10.6f}".format(c["delta_mass"])
                    )
                    conf_col = ""
                    if _use_confidence:
                        evid = " ".join(c.get("evidence_tags", []))[:16]
                        conf_col = "  {:>3}%  {:<16}".format(
                            c.get("confidence_pct", 50), evid)
                    lines.append(
                        "    {:<14}  "
                        "{:>13.6f}  "
                        "{:>13.6f}  "
                        "{}  "
                        "{:>5.1f}  "
                        "{}".format(
                            c["formula"],
                            c["neutral_mass"],
                            c["ion_mass"],
                            _delta,
                            c["dbe"],
                            c.get("isotope_summary", "\u2014"),
                        ) + (flt if show_filter else "") + rule_tag + conf_col
                    )
            else:
                filter_hdr = "  FILTER" if show_filter else ""
                conf_hdr   = "  Conf  Evidence" if _use_confidence else ""
                _delta_hdr2 = "Delta ppm" if hr_input else "Delta mass"
                lines.append(
                    "    {:<14}  {:>13}  "
                    "{:>13}  {:>10}  {:>5}{}{}".format(
                        "Formula", "Neutral mass",
                        "Ion m/z", _delta_hdr2, "DBE",
                        filter_hdr, conf_hdr
                    )
                )
                lines.append(
                    "    {}  {}  {}  {}  {}".format(
                        "-" * 14, "-" * 13, "-" * 13,
                        "-" * 10, "-" * 5
                    ) + ("  " + "-" * 6 if show_filter else "")
                      + ("  " + "-" * 4 + "  " + "-" * 16 if _use_confidence else "")
                )
                for c in candidates:
                    flt  = ("  " + ("OK" if c.get("filter_passed", True) else "FAIL"))
                    rule = c.get("fragmentation_rule", "")
                    rule_tag = "  [{}]".format(rule) if rule else ""
                    _delta2 = (
                        "{:>+10.2f}".format(c["delta_mass"] / mz * 1e6)
                        if hr_input and mz != 0
                        else "{:>+10.6f}".format(c["delta_mass"])
                    )
                    conf_col = ""
                    if _use_confidence:
                        evid = " ".join(c.get("evidence_tags", []))[:16]
                        conf_col = "  {:>3}%  {:<16}".format(
                            c.get("confidence_pct", 50), evid)
                    lines.append(
                        "    {:<14}  "
                        "{:>13.6f}  "
                        "{:>13.6f}  "
                        "{}  "
                        "{:>5.1f}".format(
                            c["formula"],
                            c["neutral_mass"],
                            c["ion_mass"],
                            _delta2,
                            c["dbe"],
                        ) + (flt if show_filter else "") + rule_tag + conf_col
                    )
        else:
            _mz_str2 = "{:.6f}".format(mz) if hr_input else "{:d}".format(mz)
            lines.append(
                "\n  m/z {:>12}  \u2014  no candidates "
                "(outside formula constraints or invalid DBE)".format(_mz_str2)
            )

    lines.append("")

    # Ensure this compound appears in the SDF output even when every peak had
    # no candidate (e.g. all were rejected by the HD-check or other filters).
    # A sentinel entry (peak_mz=None, candidate=None) is added so the writer
    # can still emit the compound block with its original, unmodified fields.
    if sdf_results is not None and len(sdf_results) == _sdf_count_before:
        sdf_results.append({
            "mol_block":     mol_block,
            "fields":        original_fields,
            "compound_name": name,
            "record_index":  record_index,
            "peak_mz":       None,   # sentinel: compound present, no peaks assigned
            "candidate":     None,
        })

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
        best_only, filter_config, save_sdf, record_index, ppm, \
        fragmentation_rules, hr_input, hr_ppm, \
        confidence, confidence_threshold, intensity_map, strict_structure, \
        reference_dict = args
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
        ppm=ppm,
        fragmentation_rules=fragmentation_rules,
        hr_input=hr_input,
        hr_ppm=hr_ppm,
        confidence=confidence,
        confidence_threshold=confidence_threshold,
        intensity_map=intensity_map,
        strict_structure=strict_structure,
        reference_dict=reference_dict,
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
    tol_group = parser.add_mutually_exclusive_group()
    tol_group.add_argument(
        "--tolerance", "-t",
        type=float,
        default=None,
        metavar="DA",
        help="Mass window ±Da for candidate matching (default: 0.5 Da).",
    )
    tol_group.add_argument(
        "--ppm",
        type=float,
        default=None,
        metavar="PPM",
        help=(
            "Mass window in ppm — per-peak Da tolerance is computed as "
            "mz × ppm / 1,000,000. Mutually exclusive with --tolerance."
        ),
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
        "--max-ring-ratio", type=float, default=1.0, metavar="RATIO",
        help="Max DBE/C ratio for H-deficiency check (default: 1.0). "
             "Value 1.0 correctly allows aromatic fragment ions such as "
             "phenyl (DBE/C=0.75) and tropylium (DBE/C=0.64); the previous "
             "default of 0.5 incorrectly rejected them.",
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
    parser.add_argument(
        "--fetch-structures",
        action="store_true",
        default=False,
        help=(
            "For records with no 2-D structure (atom count = 0), query PubChem "
            "by CAS number / compound name and insert the fetched MOL block into "
            "the output SDF.  Requires an internet connection.  Rate-limited to "
            "<=5 requests/second per PubChem guidelines."
        ),
    )
    parser.add_argument(
        "--fragmentation-rules",
        action="store_true",
        default=False,
        help=(
            "Annotate candidates with EI fragmentation rules: common neutral "
            "losses (H2O, CO, HCl, …) and structure-based cleavages (α-cleavage, "
            "McLafferty, i-cleavage) when a 2-D MOL block is present. "
            "Matching candidates are labelled with the rule name in the output."
        ),
    )
    parser.add_argument(
        "--strict-structure",
        action="store_true",
        default=False,
        help=(
            "When --fragmentation-rules is enabled and a 2-D MOL block is present, "
            "reject candidates that do not match any structure-derived fragment "
            "(hard gate). Default: off (candidates are annotated but not filtered)."
        ),
    )
    parser.add_argument(
        "--rdkit",
        action="store_true",
        default=False,
        dest="rdkit_validation",
        help=(
            "Enable Filter 6: RDKit chemical validation — rejects candidates "
            "whose element symbols are not recognized by the RDKit periodic table. "
            "Requires:  pip install rdkit-pypi"
        ),
    )

    # ── High-resolution (HR) input mode ─────────────────────────────────────
    hr_group = parser.add_argument_group(
        "high-resolution input",
        "Options for spectra stored as exact masses (e.g. QTOF, Orbitrap, ChemVista).",
    )
    hr_group.add_argument(
        "--hr",
        action="store_true",
        default=False,
        dest="hr",
        help=(
            "Treat peak m/z values as exact masses and match candidates within "
            "±hr-ppm (default 20 ppm).  Use this when the input spectrum is "
            "already high-resolution (e.g. ChemVista, MassBank HR, NIST QTOF)."
        ),
    )
    hr_group.add_argument(
        "--auto-hr",
        action="store_true",
        default=False,
        dest="auto_hr",
        help=(
            "Auto-detect whether the input spectrum is high-resolution: if the "
            "majority of m/z values above 10 Da have a fractional part > 0.010 Da, "
            "enable HR mode automatically.  Overridden by --hr."
        ),
    )
    hr_group.add_argument(
        "--hr-ppm",
        type=float,
        default=20.0,
        metavar="PPM",
        dest="hr_ppm",
        help="ppm tolerance used in HR input mode (default: 20 ppm).",
    )
    hr_group.add_argument(
        "--output-msp",
        type=str,
        default=None,
        metavar="FILE",
        dest="output_msp",
        help=(
            "Write a NIST MSP file with theoretical exact ion masses substituting "
            "the original peak m/z values.  Use '-auto' to write to "
            "'<input>-EXACT.msp' next to the input file."
        ),
    )

    # ── Confidence scoring ───────────────────────────────────────────────────
    conf_group = parser.add_argument_group(
        "confidence scoring",
        "Multi-evidence confidence scoring for unit-mass EI spectra.",
    )
    conf_group.add_argument(
        "--confidence",
        action="store_true",
        default=False,
        help=(
            "Enable multi-evidence confidence scoring: M+1/M+2 isotope pattern, "
            "neutral-loss cross-check, DBE upper bound, stable-ion library, "
            "and even/odd-electron preference.  Adds a Conf%% and Evidence "
            "column to the output table.  Not applicable in --hr mode."
        ),
    )
    conf_group.add_argument(
        "--confidence-threshold",
        type=float,
        default=0.0,
        metavar="THRESH",
        dest="confidence_threshold",
        help=(
            "In --best-only mode, skip peaks whose top candidate has confidence "
            "< THRESH (0.0–1.0).  Requires --confidence.  Default: 0.0 (all shown)."
        ),
    )
    conf_group.add_argument(
        "--merge-structures",
        type=str,
        default=None,
        metavar="FILE",
        dest="merge_structures",
        help=(
            "Load a second SDF file and copy 2-D mol_blocks into the primary "
            "records by name matching (exact -> normalised -> fuzzy Levenshtein). "
            "Useful when the primary file is an MSP/MSPEC without structures and "
            "a separate SDF contains the matching 2-D geometries."
        ),
    )
    conf_group.add_argument(
        "--reference-sdf",
        type=str,
        default=None,
        metavar="FILE",
        dest="reference_sdf",
        help=(
            "Load a reference SDF file containing known mass spectral peaks. "
            "For compounds matching by name, matched peaks bypass candidate "
            "enumeration and use the reference exact masses with confidence=0.99. "
            "Useful for validating against certified reference standards."
        ),
    )

    return parser


# ---------------------------------------------------------------------------
# HR auto-detection helper
# ---------------------------------------------------------------------------

def _any_record_hr(records: list) -> bool:
    """
    Return True if any record in *records* contains a high-resolution peak list
    (i.e. the majority of m/z values above 10 Da have a fractional part > 0.010).

    Used to implement ``--auto-hr`` detection.
    """
    from .sdf_parser import detect_hr_peaks, find_field
    from .constants import PEAK_FIELD_CANDIDATES
    for record in records:
        peak_text = find_field(record.get("fields", {}), PEAK_FIELD_CANDIDATES)
        if peak_text and detect_hr_peaks(peak_text):
            return True
    return False


def _load_reference_sdf(ref_sdf_path: str) -> dict:
    """
    Load a reference SDF and build a lookup dict for fast peak matching.

    Returns a dict: {name.lower(): {nominal_mz: exact_mass}}

    The exact_mass is extracted from each peak's nominal m/z value (integer part).

    Parameters
    ----------
    ref_sdf_path : str
        Path to the reference SDF file.

    Returns
    -------
    dict
        Lookup dict mapping lowercased compound names to peak dictionaries.
    """
    from .sdf_parser import find_field, parse_peaks_float
    from .constants import PEAK_FIELD_CANDIDATES

    ref_dict = {}
    try:
        ref_records = read_records(ref_sdf_path)
    except Exception as exc:
        print("[WARN] Could not load reference SDF '{}': {}".format(
            ref_sdf_path, exc), file=sys.stderr)
        return ref_dict

    for record in ref_records:
        name = (find_field(record.get("fields", {}), ["NAME", "COMPOUND NAME", "COMPOUND_NAME"])
                or record.get("name") or "").strip()
        if not name:
            continue

        peak_text = find_field(record.get("fields", {}), PEAK_FIELD_CANDIDATES)
        if not peak_text:
            continue

        # Parse peaks as floats (exact masses if available)
        peaks = parse_peaks_float(peak_text)
        if not peaks:
            continue

        # Build peak dict: {nominal_mz -> exact_mass}
        peak_dict = {}
        for exact_mz in peaks:
            nominal_mz = int(round(exact_mz))
            peak_dict[nominal_mz] = exact_mz

        ref_dict[name.lower()] = peak_dict

    return ref_dict


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

    # Resolve tolerance: ppm takes precedence; fall back to --tolerance or 0.5 Da
    use_ppm = args.ppm is not None
    tolerance = args.tolerance if args.tolerance is not None else 0.5

    filter_cfg = FilterConfig(
        nitrogen_rule      = not args.no_nitrogen_rule,
        hd_check           = not args.no_hd_check,
        lewis_senior       = not args.no_lewis_senior,
        isotope_score      = not args.no_isotope_score,
        smiles_constraints = not args.no_smiles_constraints,
        rdkit_validation   = args.rdkit_validation,
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
        records = read_records(args.sdf_file)
    except FileNotFoundError:
        print("[ERROR] File not found: '{}'".format(args.sdf_file), file=sys.stderr)
        sys.exit(1)
    except ValueError as exc:
        print("[ERROR] {}".format(exc), file=sys.stderr)
        sys.exit(1)

    if not records:
        print("[ERROR] No records found in the input file.", file=sys.stderr)
        sys.exit(1)

    # ── Optional: merge 2-D structures from a separate SDF ──────────────────
    if args.merge_structures:
        try:
            from .input_reader import read_records as _read_struct
            from .mol_merger import merge_mol_blocks, match_summary
            struct_recs = _read_struct(args.merge_structures)
            summary = match_summary(records, struct_recs)
            matched = sum(1 for _, _, s in summary if s != "no_match")
            print(
                "Merging 2-D structures from '{}': {}/{} records matched.\n".format(
                    args.merge_structures, matched, len(records)
                ),
                flush=True,
            )
            for prim_name, matched_name, strategy in summary:
                if strategy == "no_match":
                    print("  [WARN] No structure match for '{}'".format(prim_name),
                          file=sys.stderr)
                elif strategy not in ("existing",):
                    print("  [INFO] '{}' -> '{}' ({})".format(
                        prim_name, matched_name, strategy), flush=True)
            records = merge_mol_blocks(records, struct_recs)
        except FileNotFoundError:
            print("[ERROR] --merge-structures file not found: '{}'".format(
                args.merge_structures), file=sys.stderr)
            sys.exit(1)

    # ── Optional: fetch 2-D structures from PubChem ──────────────────────────
    if args.fetch_structures:
        from .structure_fetcher import enrich_mol_blocks, _mol_block_has_atoms
        missing = sum(
            1 for r in records if not _mol_block_has_atoms(r.get("mol_block", ""))
        )
        if missing:
            print(
                "Fetching 2-D structures from PubChem for {} / {} record(s) "
                "with no structure...\n".format(missing, len(records)),
                flush=True,
            )
            def _struct_progress(done, total, name):
                print(
                    "  [{}/{}] {}".format(done, total, name or "(unnamed)"),
                    flush=True,
                )
            enrich_mol_blocks(records, progress_callback=_struct_progress)
            print("Structure fetch complete.\n", flush=True)
        else:
            print("All records already have 2-D structures — skipping fetch.\n",
                  flush=True)

    # Resolve HR input mode: explicit --hr flag, or --auto-hr if any record has
    # exact-mass peaks (detect_hr_peaks heuristic).
    hr_input = args.hr or (args.auto_hr and _any_record_hr(records))
    hr_ppm   = args.hr_ppm

    electron_desc = {
        "remove": "positive-ion EI  (m/z = M_neutral - m_e)",
        "add":    "negative-ion EI  (m/z = M_neutral + m_e)",
        "none":   "no correction   (m/z = M_neutral)",
    }[args.electron_mode]

    if hr_input:
        tol_display = "+/-{} ppm (HR input, per-peak)".format(hr_ppm)
    elif use_ppm:
        tol_display = "+/-{} ppm (per-peak)".format(args.ppm)
    else:
        tol_display = "+/-{} Da".format(tolerance)

    hr_desc = (
        "yes (auto-detected)" if (args.auto_hr and not args.hr and hr_input)
        else "yes" if hr_input
        else "no"
    )
    print(
        "EI Fragment Exact-Mass Calculator\n"
        "  Input file          : {}\n"
        "  Records found       : {}\n"
        "  Tolerance           : {}\n"
        "  HR input mode       : {}\n"
        "  Electron mode       : {}  ({})\n"
        "  Isotope pattern     : {}\n"
        "  Best-only mode      : {}\n"
        "  Fragmentation rules : {}\n"
        "  RDKit validation    : {}\n".format(
            args.sdf_file,
            len(records),
            tol_display,
            hr_desc,
            args.electron_mode,
            electron_desc,
            "yes" if args.isotope else "no",
            "yes (top-ranked candidate per peak; unmatched peaks dropped)"
            if args.best_only else "no",
            "yes" if args.fragmentation_rules else "no",
            "yes (Filter 6)" if args.rdkit_validation else "no",
        )
    )
    if args.confidence and not hr_input:
        print(
            "  Confidence scoring  : yes (M+1/M+2 isotope, neutral-loss, "
            "DBE bound, stable-ion, even/odd-electron)\n"
            "  Conf threshold      : {}\n".format(
                "{:.0%}".format(args.confidence_threshold)
                if args.confidence_threshold > 0 else "none"
            )
        )

    # Collect results when writing SDF *or* MSP output.
    # --no-save-sdf only suppresses the SDF file; MSP still needs the data.
    save_sdf    = not args.no_save_sdf
    need_results = save_sdf or (args.output_msp is not None)
    all_sdf_results: list = [] if need_results else None

    # Pre-parse intensity maps for confidence scoring (picklable plain dicts)
    use_confidence = args.confidence and not hr_input
    if use_confidence:
        if args.confidence_threshold > 0 and not args.best_only:
            print("[WARN] --confidence-threshold has no effect without --best-only.",
                  file=sys.stderr)
        from .sdf_parser import find_field as _ff_conf
        from .confidence import parse_intensity_map as _pim
        from .constants import PEAK_FIELD_CANDIDATES
        _imaps = [
            _pim(_ff_conf(rec.get("fields", {}), PEAK_FIELD_CANDIDATES) or "")
            for rec in records
        ]
    else:
        _imaps = [{} for _ in records]

    # ── Optional: load reference SDF for peak matching ──────────────────────
    reference_dict = {}
    if args.reference_sdf:
        reference_dict = _load_reference_sdf(args.reference_sdf)
        if reference_dict:
            print("Loaded reference SDF with {} compound(s).\n".format(
                len(reference_dict)), flush=True)

    workers = max(1, args.workers)
    worker_args = [
        (
            record,
            tolerance,
            args.electron_mode,
            args.hide_empty,
            args.isotope,
            args.best_only,
            filter_cfg,
            need_results,
            idx,
            args.ppm,
            args.fragmentation_rules,
            hr_input,
            hr_ppm,
            use_confidence,
            args.confidence_threshold,
            _imaps[idx],
            args.strict_structure,
            reference_dict,
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
            if need_results:
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
                if need_results:
                    all_sdf_results.extend(sdf_part)

    if args.output:
        sys.stdout.close()
        sys.stdout = original_stdout
        print("Results written to '{}'.".format(args.output))

    if save_sdf and all_sdf_results is not None:
        out_path = args.output_sdf or exact_sdf_path(args.sdf_file)
        n = write_exact_masses_sdf(all_sdf_results, out_path)
        print("Saved {} compound(s) to '{}'.".format(n, out_path))

    # ── Optional MSP output ──────────────────────────────────────────────────
    if args.output_msp is not None and all_sdf_results is not None:
        msp_path = (
            exact_msp_path(args.sdf_file)
            if args.output_msp == "-auto"
            else args.output_msp
        )
        n_msp = write_exact_masses_msp(all_sdf_results, msp_path)
        print("Saved {} MSP record(s) to '{}'.".format(n_msp, msp_path))


if __name__ == "__main__":
    main()
