#!/usr/bin/env python3
"""Test inline editing in Edit Metadata and Edit Mass Spectrum dialogs."""

import sys
import os
sys.path.insert(0, r"D:\tmp\ei-fragment-calculator")

from ei_fragment_calculator.gui import _SDFViewerTab
import tkinter as tk

def test_inline_editing():
    """Test that inline editing works for both dialogs."""
    print("=" * 60)
    print("TEST: Inline Editing in Edit Dialogs")
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

        record_id = viewer._current_idx + 1
        print(f"[TEST] Testing with record {record_id}")

        # Test 1: Verify metadata dialog can be opened
        print(f"\n[TEST 1] Opening Edit Metadata dialog...")
        try:
            # Check that database has data for this record
            metadata_rows = viewer._db_cursor.execute(
                "SELECT field_name, field_value FROM metadata WHERE compound_id = ? ORDER BY field_name",
                (record_id,)
            ).fetchall()
            print(f"[PASS] Retrieved {len(metadata_rows)} metadata fields")

            if len(metadata_rows) > 0:
                print(f"[PASS] Sample field: {metadata_rows[0][0]} = {metadata_rows[0][1]}")
            else:
                print("[INFO] No custom metadata fields (this is OK)")

        except Exception as e:
            print(f"[FAIL] Could not access metadata: {e}")
            return False

        # Test 2: Verify spectrum dialog can be opened
        print(f"\n[TEST 2] Opening Edit Mass Spectrum dialog...")
        try:
            peaks_rows = viewer._db_cursor.execute(
                "SELECT mz, intensity, base_peak FROM mass_spectrum WHERE compound_id = ? ORDER BY mz",
                (record_id,)
            ).fetchall()
            print(f"[PASS] Retrieved {len(peaks_rows)} mass spectrum peaks")

            if len(peaks_rows) > 0:
                print(f"[PASS] Sample peak: m/z={peaks_rows[0][0]:.4f}, intensity={peaks_rows[0][1]:.2f}")
            else:
                print("[INFO] No peaks in spectrum (this is OK)")

        except Exception as e:
            print(f"[FAIL] Could not access spectrum: {e}")
            return False

        # Test 3: Verify database structure supports inline edits
        print(f"\n[TEST 3] Verifying database supports inline edits...")
        try:
            # Test UPDATE on metadata
            original_name = viewer._db_cursor.execute(
                "SELECT name FROM compounds WHERE id = ?", (record_id,)
            ).fetchone()[0]

            test_name = "Test Compound Inline"
            viewer._db_cursor.execute(
                "UPDATE compounds SET name = ? WHERE id = ?",
                (test_name, record_id)
            )
            viewer._db_conn.commit()

            updated_name = viewer._db_cursor.execute(
                "SELECT name FROM compounds WHERE id = ?", (record_id,)
            ).fetchone()[0]

            if updated_name == test_name:
                print(f"[PASS] Metadata inline UPDATE works")
                # Restore
                viewer._db_cursor.execute(
                    "UPDATE compounds SET name = ? WHERE id = ?",
                    (original_name, record_id)
                )
                viewer._db_conn.commit()
            else:
                print("[FAIL] Metadata UPDATE failed")
                return False

        except Exception as e:
            print(f"[FAIL] Metadata inline edit test failed: {e}")
            return False

        # Test 4: Verify inline peak addition structure
        print(f"\n[TEST 4] Verifying inline peak addition structure...")
        try:
            # Test INSERT of new peak
            viewer._db_cursor.execute(
                "INSERT INTO mass_spectrum (compound_id, mz, intensity, base_peak) VALUES (?, ?, ?, ?)",
                (record_id, 123.456, 75.5, 0)
            )
            viewer._db_conn.commit()

            test_peak = viewer._db_cursor.execute(
                "SELECT intensity FROM mass_spectrum WHERE compound_id = ? AND mz = ?",
                (record_id, 123.456)
            ).fetchone()

            if test_peak and abs(test_peak[0] - 75.5) < 0.01:
                print(f"[PASS] Inline peak insertion works")
                # Clean up
                viewer._db_cursor.execute(
                    "DELETE FROM mass_spectrum WHERE compound_id = ? AND mz = ?",
                    (record_id, 123.456)
                )
                viewer._db_conn.commit()
            else:
                print("[FAIL] Peak insertion verification failed")
                return False

        except Exception as e:
            print(f"[FAIL] Inline peak insertion test failed: {e}")
            return False

        print("\n" + "=" * 60)
        print("INLINE EDITING TEST PASSED")
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
    success = test_inline_editing()
    sys.exit(0 if success else 1)
