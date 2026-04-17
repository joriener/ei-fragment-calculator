#!/usr/bin/env python3
"""Test Phase 0: Database Infrastructure"""

import sys
import os

# Add project to path
sys.path.insert(0, r"D:\tmp\ei-fragment-calculator")

from ei_fragment_calculator.gui import _SDFViewerTab
import tkinter as tk


def test_phase0():
    """Test database initialization and data loading."""
    print("=" * 60)
    print("PHASE 0 TEST: Database Infrastructure")
    print("=" * 60)

    # Find a test SDF file
    test_sdf_files = [
        r"D:\tmp\ei-fragment-calculator\examples\example.sdf",
        r"D:\tmp\ei-fragment-calculator\examples\three_compounds.sdf",
    ]

    test_file = None
    for f in test_sdf_files:
        if os.path.exists(f):
            test_file = f
            break

    if not test_file:
        print("[ERROR] No test SDF file found!")
        return False

    print(f"\n[INFO] Testing with: {test_file}")

    # Create a minimal Tk window
    root = tk.Tk()
    root.withdraw()  # Hide the window

    try:
        # Create SDF Viewer tab
        viewer = _SDFViewerTab(root)

        # Load SDF file
        print("\n[TEST] Loading SDF file...")
        viewer._load_sdf(test_file)

        # Check database was created
        if viewer._db_conn is None:
            print("[FAIL] Database not initialized!")
            return False
        print("[PASS] Database initialized")

        # Check schema exists
        print("\n[TEST] Verifying database schema...")
        tables = viewer._db_cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {t[0] for t in tables}

        required_tables = {"compounds", "metadata", "mass_spectrum", "mol_data"}
        if required_tables.issubset(table_names):
            print(f"[PASS] All required tables exist: {table_names}")
        else:
            missing = required_tables - table_names
            print(f"[FAIL] Missing tables: {missing}")
            return False

        # Check data was inserted
        print("\n[TEST] Checking data insertion...")
        compound_count = viewer._db_cursor.execute(
            "SELECT COUNT(*) FROM compounds"
        ).fetchone()[0]

        record_count = len(viewer._records)
        if compound_count == record_count:
            print(f"[PASS] Inserted {compound_count} compounds into database")
        else:
            print(f"[FAIL] Compound count mismatch: DB={compound_count}, Records={record_count}")
            return False

        # Check metadata was inserted
        metadata_count = viewer._db_cursor.execute(
            "SELECT COUNT(*) FROM metadata"
        ).fetchone()[0]
        print(f"[INFO] Inserted {metadata_count} metadata fields")

        # Check mass spectrum was inserted
        spectrum_count = viewer._db_cursor.execute(
            "SELECT COUNT(*) FROM mass_spectrum"
        ).fetchone()[0]
        print(f"[INFO] Inserted {spectrum_count} mass spectrum peaks")

        # Sample query test
        print("\n[TEST] Testing sample database query...")
        first_compound = viewer._db_cursor.execute(
            "SELECT id, name, formula FROM compounds LIMIT 1"
        ).fetchone()
        if first_compound:
            print(f"[PASS] First compound: ID={first_compound[0]}, Name={first_compound[1]}, Formula={first_compound[2]}")
        else:
            print("[FAIL] No compounds found in database!")
            return False

        # Test Treeview population
        print("\n[TEST] Checking Treeview population...")
        tree_count = len(viewer._compound_tree.get_children())
        if tree_count == record_count:
            print(f"[PASS] Treeview populated with {tree_count} items")
        else:
            print(f"[FAIL] Treeview count mismatch: Tree={tree_count}, Records={record_count}")
            return False

        print("\n" + "=" * 60)
        print("✓ PHASE 0 TEST PASSED")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n[ERROR] Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        root.destroy()


if __name__ == "__main__":
    success = test_phase0()
    sys.exit(0 if success else 1)
