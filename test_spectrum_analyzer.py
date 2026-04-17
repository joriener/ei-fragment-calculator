#!/usr/bin/env python
"""
test_spectrum_analyzer.py
==========================
Standalone test of the Spectrum Analyzer tab with sample data.

Run: python test_spectrum_analyzer.py
"""

import tkinter as tk
from ei_fragment_calculator.spectrum_analyzer import SpectrumAnalyzerTab

# Sample test data with various compounds
TEST_RECORDS = [
    {
        "COMPOUNDNAME": "Caffeine",
        "NAME": "Caffeine",
        "FORMULA": "C8H10N4O2",
        "MASS SPECTRAL PEAKS": "50 287; 51 144; 52 9; 77 120; 109 115; 110 999; 111 80; 123 48; 194 150"
    },
    {
        "COMPOUNDNAME": "Benzene",
        "NAME": "Benzene",
        "FORMULA": "C6H6",
        "MASS SPECTRAL PEAKS": "50 28; 51 44; 52 999; 53 52; 77 999; 78 999"
    },
    {
        "COMPOUNDNAME": "Toluene (methylbenzene)",
        "NAME": "Toluene",
        "FORMULA": "C7H8",
        "MASS SPECTRUM": "50 32\n51 52\n52 999\n65 120\n77 450\n91 999"  # newline format
    },
    {
        "COMPOUNDNAME": "Naphthalene",
        "NAME": "Naphthalene",
        "FORMULA": "C10H8",
        "MASS SPECTRUM": "50 15 51 22 52 32 63 18 76 95 77 150 78 320 127 999 128 80 128 45 129 22"  # space format
    },
    {
        "COMPOUNDNAME": "n-Hexane",
        "NAME": "n-Hexane",
        "FORMULA": "C6H14",
        "MASS SPECTRAL PEAKS": "29 450; 41 350; 42 520; 43 999; 57 250; 71 180; 86 350"
    }
]

def main():
    root = tk.Tk()
    root.title("EI Fragment Calculator - Spectrum Analyzer Test")
    root.geometry("1200x700")

    # Create spectrum analyzer with test data
    analyzer = SpectrumAnalyzerTab(root, records=TEST_RECORDS)
    analyzer.pack(fill=tk.BOTH, expand=True)

    print("Spectrum Analyzer Test Window")
    print("=" * 50)
    print(f"Loaded {len(TEST_RECORDS)} test compounds")
    print("\nFeatures:")
    print("- Browse compounds in the left panel")
    print("- Search by name in the search field")
    print("- View mass spectrum with annotated formulas")
    print("- Formula assignments use formula_calculator module")
    print("\nTest Compounds:")
    for i, record in enumerate(TEST_RECORDS, 1):
        name = record.get("COMPOUNDNAME", "Unknown")
        formula = record.get("FORMULA", "?")
        print(f"  {i}. {name} ({formula})")

    root.mainloop()

if __name__ == "__main__":
    main()
