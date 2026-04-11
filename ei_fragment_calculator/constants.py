"""
constants.py
============
Physical constants and CSV-based element data loader.

All element masses, isotope abundances, and valences are read from
``data/elements.csv`` at the package root, so new elements can be added
or abundances updated without touching Python source code.
"""

import csv
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Electron mass  (CODATA 2018)
# ---------------------------------------------------------------------------
ELECTRON_MASS = 0.00054857990907  # Da

# ---------------------------------------------------------------------------
# Locate data directory — works in both normal and PyInstaller-frozen builds.
#
# Normal (pip install / editable):
#   ei_fragment_calculator/constants.py  →  ../data/elements.csv
#
# Frozen (PyInstaller --onedir):
#   sys._MEIPASS is the temp directory where PyInstaller unpacks everything.
#   The spec file places elements.csv into a 'data/' sub-folder there.
# ---------------------------------------------------------------------------

def _find_csv() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # Running inside a PyInstaller bundle
        return Path(sys._MEIPASS) / "data" / "elements.csv"
    # Normal development / installed-package path
    return Path(__file__).parent.parent / "data" / "elements.csv"


_CSV_PATH = _find_csv()


def load_element_data(csv_path: Path = _CSV_PATH) -> tuple[dict, dict, dict]:
    """
    Parse the elements CSV and return three lookup tables.

    CSV columns (see data/elements.csv):
        Symbol, Name, Isotope, ExactMass, Abundance, Valence, MonoisotopicFlag

    Returns
    -------
    monoisotopic_masses : dict[str, float]
        symbol -> exact mass of the most abundant (monoisotopic) isotope.
        Used for the fast Cartesian-product enumeration.
    valences : dict[str, int]
        symbol -> integer valence for DBE calculation.
    isotope_data : dict[str, list[tuple[float, float]]]
        symbol -> [(exact_mass, abundance), ...] for ALL isotopes.
        Used for isotope-pattern simulation.

    Raises
    ------
    FileNotFoundError  if csv_path does not exist.
    ValueError         if a required column is missing or a row is malformed.
    """
    if not csv_path.exists():
        raise FileNotFoundError(
            "Element data CSV not found: " + str(csv_path) + "\n"
            "Expected location: data/elements.csv in the project root."
        )

    monoisotopic_masses: dict[str, float] = {}
    valences:            dict[str, int]   = {}
    isotope_data:        dict[str, list]  = {}

    required_columns = {"Symbol", "Isotope", "ExactMass", "Abundance", "Valence", "MonoisotopicFlag"}

    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)

        if not required_columns.issubset(set(reader.fieldnames or [])):
            missing = required_columns - set(reader.fieldnames or [])
            raise ValueError(
                "elements.csv is missing required columns: " + str(missing) + "\n"
                "Found columns: " + str(reader.fieldnames)
            )

        for row in reader:
            symbol    = row["Symbol"].strip()
            mass      = float(row["ExactMass"])
            abundance = float(row["Abundance"])
            valence   = int(row["Valence"])
            is_mono   = row["MonoisotopicFlag"].strip() == "1"

            # Build isotope list for this element
            if symbol not in isotope_data:
                isotope_data[symbol] = []
            isotope_data[symbol].append((mass, abundance))

            # Record valence (same for all isotopes of an element)
            valences[symbol] = valence

            # Record monoisotopic mass (flagged row)
            if is_mono:
                monoisotopic_masses[symbol] = mass

    return monoisotopic_masses, valences, isotope_data


# Load on import — cached as module-level constants
MONOISOTOPIC_MASSES, VALENCE, ISOTOPE_DATA = load_element_data()

# ---------------------------------------------------------------------------
# Common SDF field names (case-insensitive search)
# ---------------------------------------------------------------------------
PEAK_FIELD_CANDIDATES: list[str] = [
    "MASS SPECTRAL PEAKS",
    "MASS_SPECTRAL_PEAKS",
    "MS_PEAKS",
    "MSPEAKS",
    "PEAK LIST",
    "PEAKLIST",
    "SPECTRUM",
    "PEAKS",
    "EI MASS SPECTRUM",
    "EI_MASS_SPECTRUM",
]

FORMULA_FIELD_CANDIDATES: list[str] = [
    "MOLECULAR FORMULA",
    "MOLECULAR_FORMULA",
    "MOL FORMULA",
    "MOL_FORMULA",
    "FORMULA",
    "MF",
    "SUMFORMULA",
    "SUMM FORMULA",
    "SUMMENFORMEL",
]
