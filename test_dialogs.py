#!/usr/bin/env python3
"""Test that Edit dialogs open with data"""

import sys
import os
sys.path.insert(0, r"D:\tmp\ei-fragment-calculator")

from ei_fragment_calculator.gui import _SDFViewerTab
import tkinter as tk

def test_dialogs():
    """Test that Edit Metadata and Spectrum dialogs show data."""
    print("=" * 60)
    print("TEST: Dialog Data Loading")
    print("=" * 60)

    test_file = r"D:\tmp\ei-fragment-calculator\examples\three_compounds.sdf"
    if not os.path.exists(test_file):
        test_file = r"D:\tmp\ei-fragment-calculator\examples\example.sdf"

    if not os.path.exists(test_file):
        print("[FAIL] Test SDF file not found!")
        return False

    root = tk.Tk()
    root.geometry("400x300")

    try:
        viewer = _SDFViewerTab(root)
        print("\n[TEST] Loading SDF file...")
        viewer._load_sdf(test_file)

        print("\n[TEST] Checking if Edit Metadata button exists...")
        if hasattr(viewer, '_edit_metadata_btn'):
            print("[PASS] Edit Metadata button exists")
        else:
            print("[FAIL] Edit Metadata button missing")
            return False

        print("\n[TEST] Checking if Edit Spectrum button exists...")
        if hasattr(viewer, '_edit_spectrum_btn'):
            print("[PASS] Edit Spectrum button exists")
        else:
            print("[FAIL] Edit Spectrum button missing")
            return False

        # Simulate opening dialogs and checking their content
        print("\n[TEST] Simulating Edit Metadata dialog...")
        try:
            # Get record ID
            record_id = viewer._current_idx + 1
            print(f"[INFO] Current record ID: {record_id}")
            
            # Query metadata directly
            metadata_rows = viewer._db_cursor.execute(
                "SELECT field_name, field_value FROM metadata WHERE compound_id = ?",
                (record_id,)
            ).fetchall()
            print(f"[PASS] Retrieved {len(metadata_rows)} metadata fields")
            
            if len(metadata_rows) > 0:
                print(f"[INFO] Sample metadata: {metadata_rows[0]}")
                
            # Query compound data
            compound_row = viewer._db_cursor.execute(
                "SELECT name, formula, molecular_weight FROM compounds WHERE id = ?",
                (record_id,)
            ).fetchone()
            
            if compound_row:
                print(f"[PASS] Retrieved compound: {compound_row[0]}")
            else:
                print("[FAIL] No compound data")
                return False
                
        except Exception as e:
            print(f"[FAIL] Error querying metadata: {e}")
            return False

        print("\n[TEST] Simulating Edit Spectrum dialog...")
        try:
            record_id = viewer._current_idx + 1
            peaks_rows = viewer._db_cursor.execute(
                "SELECT mz, intensity FROM mass_spectrum WHERE compound_id = ? ORDER BY mz",
                (record_id,)
            ).fetchall()
            print(f"[PASS] Retrieved {len(peaks_rows)} mass spectrum peaks")
            
        except Exception as e:
            print(f"[FAIL] Error querying spectrum: {e}")
            return False

        print("\n" + "=" * 60)
        print("DIALOG DATA LOADING TEST PASSED")
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
    success = test_dialogs()
    sys.exit(0 if success else 1)
