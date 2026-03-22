"""
enrich_cli.py
=============
Command-line interface for the SDF enrichment tool.

Usage
-----
    ei-enrich-sdf  input.sdf  [options]

Output
------
    input-ENRICHED.sdf   (written next to the input file by default)
"""

import argparse
import sys
from pathlib import Path

from .sdf_parser import parse_sdf
from .sdf_writer import write_exact_masses_sdf   # reuse SDF writer
from .enrich     import EnrichConfig, enrich_records


def _enriched_path(input_path: str) -> str:
    p = Path(input_path)
    return str(p.parent / (p.stem + "-ENRICHED.sdf"))


def _write_enriched_sdf(records: list[dict], output_path: str) -> int:
    """
    Write enriched SDF records preserving mol_block and all fields.
    Returns number of records written.
    """
    import os
    with open(output_path, "w", encoding="utf-8") as fh:
        for rec in records:
            mol_block = rec.get("mol_block", "")
            fields    = rec.get("fields", {})
            name      = rec.get("name", "")

            # MOL block
            if mol_block:
                fh.write(mol_block + "\n")
            else:
                fh.write("{}\n     EI_ENRICH\n\n"
                         "  0  0  0     0  0            999 V2000\n"
                         "M  END\n".format(name))

            fh.write("\n")

            # Data fields
            for fname, fval in fields.items():
                fh.write("> <{}>\n{}\n\n".format(fname, fval))

            fh.write("$$$$\n")

    return len(records)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ei-enrich-sdf",
        description=(
            "Add missing compound metadata to SDF files by querying free\n"
            "external databases (PubChem, ChEBI, KEGG, HMDB).\n\n"
            "Only absent fields are filled; existing values are not overwritten\n"
            "unless --overwrite is specified."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  ei-enrich-sdf spectra.sdf\n"
            "  ei-enrich-sdf spectra.sdf --output enriched.sdf\n"
            "  ei-enrich-sdf spectra.sdf --no-hmdb --no-kegg\n"
            "  ei-enrich-sdf spectra.sdf --overwrite\n"
            "  ei-enrich-sdf spectra.sdf --delay 1.0\n"
        ),
    )

    p.add_argument("sdf_file", help="Input SDF file to enrich.")
    p.add_argument("--output", "-o", metavar="FILE",
                   help="Output SDF path (default: <input>-ENRICHED.sdf).")

    sources = p.add_argument_group("data sources",
                                   "All sources are ON by default.")
    sources.add_argument("--no-pubchem",  action="store_true",
                         help="Skip PubChem queries.")
    sources.add_argument("--no-chebi",    action="store_true",
                         help="Skip ChEBI queries.")
    sources.add_argument("--no-kegg",     action="store_true",
                         help="Skip KEGG queries.")
    sources.add_argument("--no-hmdb",     action="store_true",
                         help="Skip HMDB queries.")

    p.add_argument("--no-exact-mass", action="store_true",
                   help="Skip local exact-mass calculation.")
    p.add_argument("--no-splash",     action="store_true",
                   help="Skip SPLASH spectral hash (requires splashpy).")
    p.add_argument("--overwrite",     action="store_true",
                   help="Overwrite existing non-empty field values.")
    p.add_argument("--delay", type=float, default=0.5, metavar="SEC",
                   help="Seconds between API calls (default: 0.5).")
    p.add_argument("--quiet", "-q", action="store_true",
                   help="Suppress per-field log output.")
    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args   = parser.parse_args(argv)

    # -- Read input --------------------------------------------------------
    try:
        records = parse_sdf(args.sdf_file)
    except FileNotFoundError:
        print("ERROR: File not found: {}".format(args.sdf_file), file=sys.stderr)
        sys.exit(1)

    print("EI SDF Enrichment Tool")
    print("  Input   : {}".format(args.sdf_file))
    print("  Records : {}".format(len(records)))
    print("  Sources : {}".format(", ".join(
        s for s, on in [
            ("PubChem",    not args.no_pubchem),
            ("ChEBI",      not args.no_chebi),
            ("KEGG",       not args.no_kegg),
            ("HMDB",       not args.no_hmdb),
            ("ExactMass",  not args.no_exact_mass),
            ("SPLASH",     not args.no_splash),
        ] if on
    )))
    print()

    # -- Build config ------------------------------------------------------
    cfg = EnrichConfig(
        pubchem         = not args.no_pubchem,
        chebi           = not args.no_chebi,
        kegg            = not args.no_kegg,
        hmdb            = not args.no_hmdb,
        calc_exact_mass = not args.no_exact_mass,
        calc_splash     = not args.no_splash,
        delay           = args.delay,
        overwrite       = args.overwrite,
    )

    # -- Enrich ------------------------------------------------------------
    enrich_records(records, config=cfg, verbose=not args.quiet)

    # -- Write output ------------------------------------------------------
    out_path = args.output or _enriched_path(args.sdf_file)
    n = _write_enriched_sdf(records, out_path)
    print()
    print("Saved {} record(s) to '{}'.".format(n, out_path))


if __name__ == "__main__":
    main()
