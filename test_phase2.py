#!/usr/bin/env python3
"""Test Phase 2: Navigation Bar Enhancements"""

import sys
import os
sys.path.insert(0, r"D:\tmp\ei-fragment-calculator")

from ei_fragment_calculator.gui import _SDFViewerTab
import tkinter as tk


def test_phase2():
    """Test navigation enhancements."""
    print("=" * 60)
    print("PHASE 2 TEST: Navigation Bar Enhancements")
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
        print(f"\n[TEST] Loading SDF file: {test_file}")
        viewer._load_sdf(test_file)

        # Check navigation buttons exist
        if not viewer._nav_label:
            print("[FAIL] Navigation label not initialized!")
            return False
        print("[PASS] Navigation controls initialized")

        # Check filter controls exist
        if not viewer._filter_label:
            print("[FAIL] Filter label not initialized!")
            return False
        print("[PASS] Filter controls initialized")

        if not viewer._clear_filter_btn:
            print("[FAIL] Clear filter button not initialized!")
            return False
        print("[PASS] Clear filter button initialized")

        # Test database query capability for search
        print("\n[TEST] Testing search functionality...")
        try:
            # Simulate search
            search_results = viewer._db_cursor.execute(
                "SELECT id, name FROM compounds WHERE LOWER(name) LIKE LOWER('%' || ? || '%') ORDER BY id",
                ("",)
            ).fetchall()
            if search_results:
                print(f"[PASS] Database search works: found {len(search_results)} compounds")
            else:
                print("[WARN] No compounds in database (empty SDF?)")
        except Exception as e:
            print(f"[FAIL] Database search failed: {e}")
            return False

        # Test compound count
        compound_count = viewer._db_cursor.execute("SELECT COUNT(*) FROM compounds").fetchone()[0]
        print(f"\n[TEST] Compound count: {compound_count}")

        # Test tree population
        tree_children = viewer._compound_tree.get_children()
        if len(tree_children) == compound_count:
            print(f"[PASS] Tree populated with {len(tree_children)} items")
        else:
            print(f"[FAIL] Tree count mismatch: tree={len(tree_children)}, db={compound_count}")
            return False

        print("\n" + "=" * 60)
        print("PHASE 2 TEST PASSED")
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
    success = test_phase2()
    sys.exit(0 if success else 1)
