#!/usr/bin/env python3
"""Test Phase 5: Edit Mass Spectrum Table"""

import sys
import os
sys.path.insert(0, r"D:\tmp\ei-fragment-calculator")

from ei_fragment_calculator.gui import _SDFViewerTab
import tkinter as tk


def test_phase5():
    """Test mass spectrum editor functionality."""
    print("=" * 60)
    print("PHASE 5 TEST: Edit Mass Spectrum Table")
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

        # Check that we can access mass spectrum for current record
        record_id = viewer._current_idx + 1
        print(f"\n[TEST] Checking mass spectrum for record {record_id}...")

        try:
            # Query mass spectrum peaks
            peaks_rows = viewer._db_cursor.execute(
                "SELECT mz, intensity, base_peak FROM mass_spectrum WHERE compound_id = ? ORDER BY mz",
                (record_id,)
            ).fetchall()
            print(f"[PASS] Retrieved {len(peaks_rows)} mass spectrum peaks")

            if peaks_rows:
                print(f"[INFO] First peak: m/z={peaks_rows[0][0]}, intensity={peaks_rows[0][1]}")
            else:
                print("[WARN] No peaks in this record")

        except Exception as e:
            print(f"[FAIL] Could not query mass spectrum: {e}")
            return False

        # Test database UPDATE operations (simulate peak edits)
        print(f"\n[TEST] Testing mass spectrum UPDATE operations...")
        try:
            if peaks_rows:
                original_mz, original_int, original_base = peaks_rows[0]

                # Test updating a peak
                viewer._db_cursor.execute(
                    "UPDATE mass_spectrum SET intensity = ? WHERE compound_id = ? AND mz = ?",
                    (original_int * 0.5, record_id, original_mz)
                )
                viewer._db_conn.commit()

                # Verify update
                updated = viewer._db_cursor.execute(
                    "SELECT intensity FROM mass_spectrum WHERE compound_id = ? AND mz = ?",
                    (record_id, original_mz)
                ).fetchone()

                if updated and abs(updated[0] - original_int * 0.5) < 0.01:
                    print(f"[PASS] Peak intensity updated successfully")
                    # Restore original
                    viewer._db_cursor.execute(
                        "UPDATE mass_spectrum SET intensity = ? WHERE compound_id = ? AND mz = ?",
                        (original_int, record_id, original_mz)
                    )
                    viewer._db_conn.commit()
                else:
                    print("[FAIL] Intensity update verification failed")
                    return False
            else:
                print("[INFO] Skipping UPDATE test (no peaks in record)")

        except Exception as e:
            print(f"[FAIL] Mass spectrum update test failed: {e}")
            return False

        # Test inserting new peak
        print(f"\n[TEST] Testing INSERT peak operations...")
        try:
            viewer._db_cursor.execute(
                "INSERT INTO mass_spectrum (compound_id, mz, intensity, base_peak) VALUES (?, ?, ?, ?)",
                (record_id, 999.99, 50.0, 0)
            )
            viewer._db_conn.commit()

            # Verify insert
            test_peak = viewer._db_cursor.execute(
                "SELECT intensity FROM mass_spectrum WHERE compound_id = ? AND mz = ?",
                (record_id, 999.99)
            ).fetchone()

            if test_peak and abs(test_peak[0] - 50.0) < 0.01:
                print("[PASS] New peak inserted successfully")
                # Clean up
                viewer._db_cursor.execute(
                    "DELETE FROM mass_spectrum WHERE compound_id = ? AND mz = ?",
                    (record_id, 999.99)
                )
                viewer._db_conn.commit()
            else:
                print("[FAIL] Peak insertion verification failed")
                return False

        except Exception as e:
            print(f"[FAIL] Mass spectrum insert test failed: {e}")
            return False

        # Test sorting capability
        print(f"\n[TEST] Testing peak sorting...")
        try:
            sorted_peaks = viewer._db_cursor.execute(
                "SELECT mz, intensity FROM mass_spectrum WHERE compound_id = ? ORDER BY mz DESC LIMIT 5",
                (record_id,)
            ).fetchall()

            if len(sorted_peaks) > 1:
                # Verify descending order
                is_sorted = all(sorted_peaks[i][0] >= sorted_peaks[i+1][0] for i in range(len(sorted_peaks)-1))
                if is_sorted:
                    print(f"[PASS] Peaks correctly sorted by m/z (descending)")
                else:
                    print("[FAIL] Peak sorting verification failed")
                    return False

        except Exception as e:
            print(f"[FAIL] Peak sorting test failed: {e}")
            return False

        print("\n" + "=" * 60)
        print("PHASE 5 TEST PASSED")
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
    success = test_phase5()
    sys.exit(0 if success else 1)
