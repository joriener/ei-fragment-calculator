#!/usr/bin/env python3
"""
check_requirements.py
=====================
Verify that the system is correctly set up to run ei-fragment-calculator
and ei-enrich-sdf on this machine.

Run this script BEFORE first use or after moving to a new PC.

Usage
-----
    python scripts/check_requirements.py
"""

import importlib
import shutil
import subprocess
import sys
import urllib.request

# ---------------------------------------------------------------------------
REQUIRED_PYTHON = (3, 10)
# ---------------------------------------------------------------------------

_OK   = "[  OK  ]"
_FAIL = "[ FAIL ]"
_WARN = "[ WARN ]"
_INFO = "[ INFO ]"

errors   = []
warnings = []


def check(label: str, ok: bool, detail: str = "", warn_only: bool = False) -> bool:
    tag = _OK if ok else (_WARN if warn_only else _FAIL)
    msg = "{} {}".format(tag, label)
    if detail:
        msg += "  -  " + detail
    print(msg)
    if not ok:
        if warn_only:
            warnings.append(label)
        else:
            errors.append(label)
    return ok


def section(title: str) -> None:
    print()
    print("=" * 60)
    print("  " + title)
    print("=" * 60)


# ---------------------------------------------------------------------------
# 1. Python version
# ---------------------------------------------------------------------------
section("Python version")

v = sys.version_info
check(
    "Python >= {}.{}".format(*REQUIRED_PYTHON),
    v >= REQUIRED_PYTHON,
    "found Python {}.{}.{}  at  {}".format(v.major, v.minor, v.micro, sys.executable),
)
check(
    "Python < 4.0 (future-proof)",
    v.major < 4,
    warn_only=True,
)

# ---------------------------------------------------------------------------
# 2. Package installed
# ---------------------------------------------------------------------------
section("Package installation")

try:
    import ei_fragment_calculator as pkg
    check("ei-fragment-calculator installed", True,
          "version {}".format(pkg.__version__))
except ImportError as e:
    check("ei-fragment-calculator installed", False,
          "ImportError: {}  -  run: pip install -e .".format(e))

# Core modules
for mod in [
    "ei_fragment_calculator.cli",
    "ei_fragment_calculator.calculator",
    "ei_fragment_calculator.sdf_parser",
    "ei_fragment_calculator.sdf_writer",
    "ei_fragment_calculator.filters",
    "ei_fragment_calculator.isotope",
    "ei_fragment_calculator.enrich",
    "ei_fragment_calculator.enrich_cli",
]:
    try:
        importlib.import_module(mod)
        check(mod, True)
    except Exception as e:
        check(mod, False, str(e))

# ---------------------------------------------------------------------------
# 3. CLI entry points
# ---------------------------------------------------------------------------
section("CLI entry points")

for cmd in ["ei-fragment-calc", "ei-enrich-sdf"]:
    path = shutil.which(cmd)
    check(
        cmd,
        path is not None,
        "found at {}".format(path) if path else "not found - run: pip install -e .",
    )


# ---------------------------------------------------------------------------
# 4. data/elements.csv
# ---------------------------------------------------------------------------
section("Data files")

import pathlib
repo_root   = pathlib.Path(__file__).parent.parent
csv_path    = repo_root / "data" / "elements.csv"

check(
    "data/elements.csv exists",
    csv_path.exists(),
    str(csv_path),
)
if csv_path.exists():
    lines = csv_path.read_text(encoding="utf-8").splitlines()
    check(
        "data/elements.csv has data",
        len(lines) > 5,
        "{} rows".format(len(lines)),
    )

# ---------------------------------------------------------------------------
# 5. Standard library modules (should always pass)
# ---------------------------------------------------------------------------
section("Standard library")

for mod in ["argparse", "csv", "itertools", "json",
            "pathlib", "re", "urllib.request", "zipfile"]:
    try:
        importlib.import_module(mod)
        check(mod, True)
    except ImportError as e:
        check(mod, False, str(e))

# ---------------------------------------------------------------------------
# 6. Optional third-party packages
# ---------------------------------------------------------------------------
section("Optional packages  (warn only - not required)")

for mod, install, purpose in [
    ("matplotlib", "pip install matplotlib",
     "workflow diagram generation (scripts/generate_workflow_image.py)"),
    ("splashpy",   "pip install splashpy",
     "SPLASH spectral hash calculation in ei-enrich-sdf"),
]:
    try:
        importlib.import_module(mod)
        check(mod, True, purpose, warn_only=False)
    except ImportError:
        check(mod, False,
              "not installed - {}  (purpose: {})".format(install, purpose),
              warn_only=True)


# ---------------------------------------------------------------------------
# 7. Internet connectivity (needed for ei-enrich-sdf)
# ---------------------------------------------------------------------------
section("Internet connectivity  (needed for ei-enrich-sdf)")

for label, url in [
    ("PubChem API",  "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/caffeine/cids/JSON"),
    ("ChEBI API",    "https://www.ebi.ac.uk/webservices/chebi/2.0/test/getCompleteEntityByList"),
    ("KEGG API",     "https://rest.kegg.jp/find/compound/caffeine"),
    ("HMDB website", "https://hmdb.ca"),
]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ei-fragment-calculator/check"})
        with urllib.request.urlopen(req, timeout=8) as r:
            check(label, True, "HTTP {}".format(r.status))
    except Exception as e:
        check(label, False, str(e)[:80], warn_only=True)

# ---------------------------------------------------------------------------
# 8. Quick smoke test
# ---------------------------------------------------------------------------
section("Quick smoke test")

try:
    from ei_fragment_calculator import parse_formula, find_fragment_candidates
    comp = parse_formula("C8H10N4O2")
    cands = find_fragment_candidates(194, comp, electron_mode="remove")
    check("find_fragment_candidates(194, C8H10N4O2)",
          len(cands) >= 1,
          "{} candidate(s) found".format(len(cands)))
except Exception as e:
    check("smoke test", False, str(e))

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
section("Summary")

if errors:
    print("ERRORS ({}) - the tool will NOT work correctly:".format(len(errors)))
    for e in errors:
        print("    {}  {}".format(_FAIL, e))
else:
    print("No errors found.")

if warnings:
    print("Warnings ({}) - optional features unavailable:".format(len(warnings)))
    for w in warnings:
        print("    {}  {}".format(_WARN, w))

print()
if errors:
    print("Fix the errors above, then run this script again.")
    sys.exit(1)
else:
    print("All required checks passed.  You can run:")
    print()
    print("    ei-fragment-calc  your_spectrum.sdf  --best-only --isotope")
    print("    ei-enrich-sdf     your_spectrum.sdf")
    print()
