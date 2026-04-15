"""
preflight.py
============
Environment and dependency checks run before the main CLI logic.

Checks performed
----------------
1. Python version   -- requires Python 3.10+
2. elements.csv     -- must exist and be readable
3. CSV completeness -- warns if key elements (C, H, N, O) are missing
4. Optional deps    -- matplotlib warning if absent (only needed for workflow diagram)

Hard failures call sys.exit(1) with a clear message.
"""

import sys
from pathlib import Path

MIN_PYTHON = (3, 10)
REQUIRED_ELEMENTS = {"C", "H", "N", "O"}


def check_python_version():
    """Abort with a clear message if Python is too old (requires 3.10+)."""
    if sys.version_info < MIN_PYTHON:
        major, minor = MIN_PYTHON
        current = "{}.{}.{}".format(
            sys.version_info.major,
            sys.version_info.minor,
            sys.version_info.micro,
        )
        print(
            "\n[PREFLIGHT ERROR] Python {}.{}+ is required.\n"
            "  You are running Python {}.\n"
            "  Please upgrade: https://www.python.org/downloads/\n".format(
                major, minor, current
            ),
            file=sys.stderr,
        )
        sys.exit(1)


def check_elements_csv():
    """
    Verify that data/elements.csv exists, is readable, and contains
    the minimum required elements (C, H, N, O).
    """
    pkg_dir  = Path(__file__).parent
    csv_path = pkg_dir.parent / "data" / "elements.csv"

    if not csv_path.exists():
        print(
            "\n[PREFLIGHT ERROR] Element data file not found:\n"
            "  Expected: {}\n\n"
            "  This file is required for all mass calculations.\n"
            "  Restore it from the repository or re-clone the project.\n".format(
                csv_path
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        import csv
        with open(csv_path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows   = list(reader)
    except PermissionError:
        print(
            "\n[PREFLIGHT ERROR] Cannot read element data file (permission denied):\n"
            "  {}\n".format(csv_path),
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as exc:
        print(
            "\n[PREFLIGHT ERROR] Failed to read element data file:\n"
            "  {}\n"
            "  Reason: {}\n".format(csv_path, exc),
            file=sys.stderr,
        )
        sys.exit(1)

    required_columns = {"Symbol", "ExactMass", "Abundance", "Valence", "MonoisotopicFlag"}
    if rows:
        actual_columns = set(rows[0].keys())
        missing = required_columns - actual_columns
        if missing:
            print(
                "\n[PREFLIGHT ERROR] elements.csv is missing required columns: {}\n"
                "  Found columns: {}\n"
                "  Please check the CSV header row.\n".format(
                    ", ".join(sorted(missing)),
                    ", ".join(sorted(actual_columns)),
                ),
                file=sys.stderr,
            )
            sys.exit(1)

    symbols_in_csv = {row.get("Symbol", "").strip() for row in rows}
    missing_elements = REQUIRED_ELEMENTS - symbols_in_csv
    if missing_elements:
        print(
            "\n[PREFLIGHT WARNING] Missing important elements in elements.csv: {}\n"
            "  Add them to data/elements.csv to restore full functionality.\n".format(
                ", ".join(sorted(missing_elements))
            ),
            file=sys.stderr,
        )


def check_optional_dependencies():
    """Warn (do not abort) if optional packages are not installed."""
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        print(
            "[PREFLIGHT NOTE] matplotlib is not installed.\n"
            "  The main tool works without it, but the workflow diagram\n"
            "  generator (scripts/generate_workflow_image.py) requires it.\n"
            "  Install with:  pip install matplotlib\n",
            file=sys.stderr,
        )

    try:
        from rdkit import Chem  # noqa: F401
    except Exception:
        # Catches ImportError (not installed), AttributeError (_ARRAY_API not found
        # when RDKit was compiled against NumPy 1.x and NumPy 2.x is active), and
        # any other failure during rdkit initialisation.
        print(
            "[PREFLIGHT NOTE] rdkit is not available (not installed or NumPy version mismatch).\n"
            "  Filter 6 (RDKit chemical validation) and structure-based\n"
            "  fragmentation rules (--fragmentation-rules) require it.\n"
            "  Install with:  pip install rdkit-pypi\n",
            file=sys.stderr,
        )


def run_preflight_checks():
    """
    Run all preflight checks. Called automatically by main() before
    any other logic. Hard failures exit; soft warnings continue.
    """
    check_python_version()
    check_elements_csv()
    check_optional_dependencies()
