#!/usr/bin/env python3
"""Visual test of search field visibility"""

import sys
import os
sys.path.insert(0, r"D:\tmp\ei-fragment-calculator")

from ei_fragment_calculator.gui import SDFViewerApp
import tkinter as tk

def test_visual():
    """Visual test - load SDF and check search field."""
    print("=" * 60)
    print("VISUAL TEST: Search Field Visibility")
    print("=" * 60)
    print("\n[INFO] Starting GUI...")
    print("[INFO] The search field should be visible below the compounds list")
    print("[INFO] Try loading D:\tmp\ei-fragment-calculator\examples\three_compounds.sdf")
    print("[INFO] Close the window when done")
    
    root = tk.Tk()
    root.title("EI Fragment Calculator - Visual Test")
    root.geometry("1200x700")
    
    app = SDFViewerApp(root)
    
    print("\n[INFO] GUI window should now be visible")
    print("[INFO] Search field location: Should be below 'Compounds' panel")
    
    root.mainloop()
    
    print("\n[INFO] Test complete")
    return True

if __name__ == "__main__":
    try:
        test_visual()
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
