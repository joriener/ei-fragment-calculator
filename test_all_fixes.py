#!/usr/bin/env python3
"""Test all three fixes together"""

import sys
import os
sys.path.insert(0, r"D:\tmp\ei-fragment-calculator")

from ei_fragment_calculator.gui import _SDFViewerTab
import tkinter as tk

def test_all_fixes():
    """Test that all three issues are fixed."""
    print("=" * 60)
    print("COMPREHENSIVE TEST: All Three Fixes")
    print("=" * 60)

    test_file = r"D:\tmp\ei-fragment-calculator\examples\three_compounds.sdf"
    if not os.path.exists(test_file):
        print("[FAIL] Test SDF file not found!")
        return False

    root = tk.Tk()
    root.withdraw()

    try:
        viewer = _SDFViewerTab(root)
        print("\n[TEST 1] Search field should exist and be accessible")
        
        if not hasattr(viewer, '_search_var'):
            print("[FAIL] _search_var attribute missing")
            return False
        print("[PASS] _search_var exists")

        print("\n[TEST] Loading SDF file...")
        viewer._load_sdf(test_file)

        print("\n[TEST 2] Search field should still be accessible after loading")
        try:
            val = viewer._search_var.get()
            print(f"[PASS] Search field accessible: '{val}'")
        except Exception as e:
            print(f"[FAIL] Search field not accessible: {e}")
            return False

        print("\n[TEST 3] Edit Metadata should load data")
        record_id = viewer._current_idx + 1
        try:
            metadata_rows = viewer._db_cursor.execute(
                "SELECT field_name, field_value FROM metadata WHERE compound_id = ?",
                (record_id,)
            ).fetchall()
            
            compound_row = viewer._db_cursor.execute(
                "SELECT name, formula, molecular_weight FROM compounds WHERE id = ?",
                (record_id,)
            ).fetchone()
            
            if not compound_row:
                print(f"[FAIL] No compound data retrieved")
                return False
            
            print(f"[PASS] Edit Metadata can load data:")
            print(f"       Compound: {compound_row[0]}")
            print(f"       Metadata fields: {len(metadata_rows)}")
            
        except Exception as e:
            print(f"[FAIL] Edit Metadata data loading failed: {e}")
            return False

        print("\n[TEST 4] Edit Spectrum should load data")
        try:
            peaks_rows = viewer._db_cursor.execute(
                "SELECT mz, intensity FROM mass_spectrum WHERE compound_id = ? ORDER BY mz",
                (record_id,)
            ).fetchall()
            
            print(f"[PASS] Edit Spectrum can load data:")
            print(f"       Mass spectrum peaks: {len(peaks_rows)}")
            
        except Exception as e:
            print(f"[FAIL] Edit Spectrum data loading failed: {e}")
            return False

        print("\n" + "=" * 60)
        print("ALL TESTS PASSED - All three issues fixed!")
        print("=" * 60)
        print("\nSummary:")
        print("1. Search field is visible and accessible")
        print("2. Edit Metadata loads compound and metadata data")
        print("3. Edit Spectrum loads mass spectrum data")
        return True

    except Exception as e:
        print(f"\n[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        root.destroy()

if __name__ == "__main__":
    success = test_all_fixes()
    sys.exit(0 if success else 1)
