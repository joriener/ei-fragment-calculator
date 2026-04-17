#!/usr/bin/env python3
"""Test Edit Metadata dialog content"""

import sys
import os
sys.path.insert(0, r"D:\tmp\ei-fragment-calculator")

from ei_fragment_calculator.gui import _SDFViewerTab
import tkinter as tk

def test_edit_dialog():
    """Test that Edit Metadata dialog shows values."""
    print("=" * 60)
    print("TEST: Edit Metadata Dialog Content")
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

        # Get current record ID
        record_id = viewer._current_idx + 1
        print(f"\n[INFO] Current record ID: {record_id}")
        print(f"[INFO] Current index: {viewer._current_idx}")

        # Check database directly
        print("\n[TEST] Querying database for metadata...")
        try:
            metadata_rows = viewer._db_cursor.execute(
                "SELECT field_name, field_value FROM metadata WHERE compound_id = ? ORDER BY field_name",
                (record_id,)
            ).fetchall()
            print(f"[PASS] Retrieved {len(metadata_rows)} metadata rows")
            
            if metadata_rows:
                print("Sample metadata rows:")
                for row in metadata_rows[:3]:
                    print(f"  - {row[0]}: {row[1][:50] if row[1] else 'NULL'}")
            else:
                print("[WARN] No metadata rows found in database")
            
            # Also check compound
            compound_row = viewer._db_cursor.execute(
                "SELECT name, formula, molecular_weight FROM compounds WHERE id = ?",
                (record_id,)
            ).fetchone()
            
            if compound_row:
                print(f"\n[PASS] Compound data: Name={compound_row[0]}, Formula={compound_row[1]}")
            else:
                print("[FAIL] No compound found")
                
        except Exception as e:
            print(f"[FAIL] Database query error: {e}")
            return False

        # Now simulate what the dialog does
        print("\n[TEST] Simulating dialog data loading...")
        try:
            metadata_dict = {}
            
            # Query again (simulating dialog)
            metadata_rows = viewer._db_cursor.execute(
                "SELECT field_name, field_value FROM metadata WHERE compound_id = ? ORDER BY field_name",
                (record_id,)
            ).fetchall()
            
            metadata_dict = {row[0]: row[1] for row in metadata_rows}
            print(f"[INFO] metadata_dict has {len(metadata_dict)} entries")
            
            # Also add compound fields (simulating dialog)
            compound_row = viewer._db_cursor.execute(
                "SELECT name, formula, molecular_weight, cas_number, iupac_name, smiles, inchi FROM compounds WHERE id = ?",
                (record_id,)
            ).fetchone()
            
            if compound_row:
                metadata_dict.update({
                    "NAME": compound_row[0],
                    "FORMULA": compound_row[1],
                    "MW": compound_row[2],
                    "CASNO": compound_row[3],
                    "IUPAC_NAME": compound_row[4],
                    "SMILES": compound_row[5],
                    "InChI": compound_row[6],
                })
                print(f"[PASS] Added compound fields, total now: {len(metadata_dict)}")
            
            # Print what would be in the tree
            print("\n[INFO] Items that would be in Treeview:")
            for field_name, field_value in sorted(metadata_dict.items()):
                val_str = str(field_value)[:40] if field_value else "(empty)"
                print(f"  - {field_name}: {val_str}")
            
            if len(metadata_dict) == 0:
                print("[WARN] metadata_dict is EMPTY - this is the problem!")
            
        except Exception as e:
            print(f"[FAIL] Dialog simulation error: {e}")
            import traceback
            traceback.print_exc()
            return False

        print("\n" + "=" * 60)
        if len(metadata_dict) > 0:
            print("DIALOG CONTENT TEST PASSED")
        else:
            print("DIALOG CONTENT TEST FAILED - metadata_dict is empty")
        print("=" * 60)
        return len(metadata_dict) > 0

    except Exception as e:
        print(f"\n[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        root.destroy()

if __name__ == "__main__":
    success = test_edit_dialog()
    sys.exit(0 if success else 1)
