#!/usr/bin/env python3
"""Test Phase 1: Mass Spectrum Visualization"""

import sys
import os
sys.path.insert(0, r"D:\tmp\ei-fragment-calculator")

from ei_fragment_calculator.gui import _SDFViewerTab, _HAS_MATPLOTLIB
import tkinter as tk


def test_phase1():
    """Test mass spectrum visualization."""
    print("=" * 60)
    print("PHASE 1 TEST: Mass Spectrum Visualization")
    print("=" * 60)

    # Check matplotlib availability
    print(f"\n[INFO] Matplotlib available: {_HAS_MATPLOTLIB}")

    # Find test SDF file
    test_file = r"D:\tmp\ei-fragment-calculator\examples\example.sdf"
    if not os.path.exists(test_file):
        print("[FAIL] Test SDF file not found!")
        return False

    # Create Tk window
    root = tk.Tk()
    root.withdraw()

    try:
        viewer = _SDFViewerTab(root)
        print("\n[TEST] Loading SDF file...")
        viewer._load_sdf(test_file)

        # Check if spectrum frame is set up
        if not viewer._spec_canvas_frame:
            print("[FAIL] Spectrum canvas frame not initialized!")
            return False
        print("[PASS] Spectrum canvas frame initialized")

        # Check if plotting was called (it should have run in _show_record)
        spec_widgets = viewer._spec_canvas_frame.winfo_children()
        if _HAS_MATPLOTLIB:
            if spec_widgets:
                print(f"[PASS] Spectrum frame contains {len(spec_widgets)} widget(s)")
                # Check if it's a matplotlib canvas or a placeholder
                widget_types = [type(w).__name__ for w in spec_widgets]
                print(f"[INFO] Widget types: {widget_types}")
            else:
                print("[INFO] Spectrum frame empty (no peaks in test file)")
        else:
            if spec_widgets:
                print(f"[PASS] Placeholder shown: {spec_widgets[0].cget('text')}")
            else:
                print("[FAIL] No placeholder widget!")
                return False

        print("\n" + "=" * 60)
        print("PHASE 1 TEST PASSED")
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
    success = test_phase1()
    sys.exit(0 if success else 1)
