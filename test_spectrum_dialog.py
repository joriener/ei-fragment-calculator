#!/usr/bin/env python3
"""Test opening Edit Spectrum dialog"""

import sys
import os
sys.path.insert(0, r"D:\tmp\ei-fragment-calculator")

from ei_fragment_calculator.gui import _SDFViewerTab
import tkinter as tk

def test_spectrum_dialog():
    """Test opening Edit Spectrum dialog."""
    print("=" * 60)
    print("TEST: Opening Edit Spectrum Dialog")
    print("=" * 60)

    test_file = r"D:\tmp\ei-fragment-calculator\examples\three_compounds.sdf"
    if not os.path.exists(test_file):
        print("[FAIL] Test SDF file not found!")
        return False

    root = tk.Tk()
    root.withdraw()

    try:
        viewer = _SDFViewerTab(root)
        print("\n[TEST] Loading SDF file...")
        viewer._load_sdf(test_file)
        
        print(f"\n[INFO] Current record: idx={viewer._current_idx}")

        print("\n[TEST] Opening Edit Spectrum dialog...")
        viewer._edit_mass_spectrum()
        root.update()
        
        print("\n[TEST] Dialog opened. Check for Record 1 window in background.")
        
        # Close any opened dialogs
        for widget in root.winfo_children():
            if isinstance(widget, tk.Toplevel):
                print(f"[INFO] Found Toplevel widget")
                widget.destroy()
        
        print("\n" + "=" * 60)
        print("TEST COMPLETE")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        root.destroy()

if __name__ == "__main__":
    success = test_spectrum_dialog()
    sys.exit(0 if success else 1)
