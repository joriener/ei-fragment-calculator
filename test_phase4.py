#!/usr/bin/env python3
"""Test Phase 4: Edit Metadata Dialog"""

import sys
import os
sys.path.insert(0, r"D:\tmp\ei-fragment-calculator")

from ei_fragment_calculator.gui import _SDFViewerTab
import tkinter as tk


def test_phase4():
    """Test metadata editing functionality."""
    print("=" * 60)
    print("PHASE 4 TEST: Edit Metadata Dialog")
    print("=" * 60)

    # Find test SDF file
    test_file = r"D:\tmp\ei-fragment-calculator\examples\three_compounds.sdf"
    if not os.path.exists(test_file):
        test_file = r"D:\tmp\ei-fragment-calculator\examples\example.sdf"

    if not os.path.exists(test_file):
        print("[FAIL] Test SDF file not found!")
        return False

    # Create Tk window
    root = tk.Tk()
    root.withdraw()

    try:
        viewer = _SDFViewerTab(root)
        print(f"\n[TEST] Loading SDF file...")
        viewer._load_sdf(test_file)

        # Check that we can access metadata for current record
        record_id = viewer._current_idx + 1
        print(f"\n[TEST] Checking metadata for record {record_id}...")

        try:
            # Query metadata
            metadata_rows = viewer._db_cursor.execute(
                "SELECT field_name, field_value FROM metadata WHERE compound_id = ?",
                (record_id,)
            ).fetchall()
            print(f"[PASS] Retrieved {len(metadata_rows)} metadata fields")

            # Query compound data
            compound_row = viewer._db_cursor.execute(
                "SELECT name, formula, molecular_weight FROM compounds WHERE id = ?",
                (record_id,)
            ).fetchone()

            if compound_row:
                print(f"[PASS] Retrieved compound data: {compound_row[0]}")
            else:
                print("[FAIL] Could not retrieve compound data")
                return False

        except Exception as e:
            print(f"[FAIL] Could not query metadata: {e}")
            return False

        # Test database UPDATE operations (simulate metadata changes)
        print(f"\n[TEST] Testing database UPDATE operations...")
        try:
            # Test updating compound field
            viewer._db_cursor.execute(
                "UPDATE compounds SET name = ? WHERE id = ?",
                ("Test Compound", record_id)
            )
            viewer._db_conn.commit()

            # Verify update
            updated_name = viewer._db_cursor.execute(
                "SELECT name FROM compounds WHERE id = ?",
                (record_id,)
            ).fetchone()[0]

            if updated_name == "Test Compound":
                print(f"[PASS] Compound name updated successfully")
                # Restore original
                original_name = viewer._records[viewer._current_idx]["fields"].get("NAME", f"Compound {record_id}")
                viewer._db_cursor.execute(
                    "UPDATE compounds SET name = ? WHERE id = ?",
                    (original_name, record_id)
                )
                viewer._db_conn.commit()
            else:
                print("[FAIL] Name update verification failed")
                return False

        except Exception as e:
            print(f"[FAIL] Database update test failed: {e}")
            return False

        # Test inserting new metadata field
        print(f"\n[TEST] Testing INSERT metadata operations...")
        try:
            viewer._db_cursor.execute(
                "INSERT INTO metadata (compound_id, field_name, field_value) VALUES (?, ?, ?)",
                (record_id, "TEST_FIELD", "test_value")
            )
            viewer._db_conn.commit()

            # Verify insert
            test_field = viewer._db_cursor.execute(
                "SELECT field_value FROM metadata WHERE compound_id = ? AND field_name = ?",
                (record_id, "TEST_FIELD")
            ).fetchone()

            if test_field and test_field[0] == "test_value":
                print("[PASS] New metadata field inserted successfully")
                # Clean up
                viewer._db_cursor.execute(
                    "DELETE FROM metadata WHERE compound_id = ? AND field_name = ?",
                    (record_id, "TEST_FIELD")
                )
                viewer._db_conn.commit()
            else:
                print("[FAIL] Metadata insertion verification failed")
                return False

        except Exception as e:
            print(f"[FAIL] Database insert test failed: {e}")
            return False

        print("\n" + "=" * 60)
        print("PHASE 4 TEST PASSED")
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
    success = test_phase4()
    sys.exit(0 if success else 1)
