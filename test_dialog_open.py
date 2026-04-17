#!/usr/bin/env python3
"""Test opening Edit Metadata dialog"""

import sys
import os
import io
from contextlib import redirect_stdout
sys.path.insert(0, r"D:\tmp\ei-fragment-calculator")

from ei_fragment_calculator.gui import _SDFViewerTab
import tkinter as tk

def test_dialog_open():
    """Test opening Edit Metadata dialog and capture debug output."""
    print("=" * 60)
    print("TEST: Opening Edit Metadata Dialog")
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
        
        print("\n[INFO] Current record state after loading:")
        print(f"       current_idx: {viewer._current_idx}")
        print(f"       num records: {len(viewer._records)}")

        # Capture stdout to see debug output
        print("\n[TEST] Opening Edit Metadata dialog...")
        captured_output = io.StringIO()
        
        # Call the dialog method - it will print debug output
        viewer._edit_metadata()
        
        # Let tkinter process the dialog creation
        root.update()
        
        # Get any print output that was made
        print("\n[TEST] Dialog opened. Check for Record 1 window in background.")
        
        # Close any opened dialogs
        for widget in root.winfo_children():
            if isinstance(widget, tk.Toplevel):
                print(f"[INFO] Found Toplevel widget: {widget}")
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
    success = test_dialog_open()
    sys.exit(0 if success else 1)
