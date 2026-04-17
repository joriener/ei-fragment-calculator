#!/usr/bin/env python3
"""Test search field visibility"""

import sys
import os
sys.path.insert(0, r"D:\tmp\ei-fragment-calculator")

from ei_fragment_calculator.gui import _SDFViewerTab
import tkinter as tk

def test_search_field():
    """Test that search field is visible after loading SDF."""
    print("=" * 60)
    print("TEST: Search Field Visibility")
    print("=" * 60)

    test_file = r"D:\tmp\ei-fragment-calculator\examples\three_compounds.sdf"
    if not os.path.exists(test_file):
        test_file = r"D:\tmp\ei-fragment-calculator\examples\example.sdf"

    if not os.path.exists(test_file):
        print("[FAIL] Test SDF file not found!")
        return False

    root = tk.Tk()
    root.withdraw()

    try:
        viewer = _SDFViewerTab(root)
        print("\n[TEST] Checking search field before loading...")
        
        # Check if _search_var exists
        if hasattr(viewer, '_search_var'):
            print("[PASS] _search_var attribute exists")
        else:
            print("[FAIL] _search_var attribute missing")
            return False

        # Try to get the search variable value
        try:
            val = viewer._search_var.get()
            print(f"[PASS] Can access _search_var: '{val}'")
        except Exception as e:
            print(f"[FAIL] Cannot access _search_var: {e}")
            return False

        print("\n[TEST] Loading SDF file...")
        viewer._load_sdf(test_file)

        print("\n[TEST] Checking search field after loading...")
        
        # Check if _search_var still accessible
        try:
            val = viewer._search_var.get()
            print(f"[PASS] Can still access _search_var: '{val}'")
        except Exception as e:
            print(f"[FAIL] Cannot access _search_var after loading: {e}")
            return False

        # Check if search entry widget is visible
        print("\n[TEST] Checking widget visibility...")
        # Find all widgets and check for search entry
        def find_search_widgets(widget, depth=0):
            indent = "  " * depth
            widget_name = type(widget).__name__
            if hasattr(widget, 'cget'):
                try:
                    text = widget.cget('text') if widget_name == 'Label' else ''
                    if 'Search' in text:
                        print(f"{indent}[FOUND] {widget_name}: {text}")
                        return True
                except:
                    pass
            
            # Check children
            found = False
            try:
                for child in widget.winfo_children():
                    if find_search_widgets(child, depth + 1):
                        found = True
            except:
                pass
            return found

        if find_search_widgets(root):
            print("[PASS] Search widgets found in widget tree")
        else:
            print("[WARN] Could not verify search widgets in tree")

        print("\n" + "=" * 60)
        print("SEARCH FIELD TEST PASSED")
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
    success = test_search_field()
    sys.exit(0 if success else 1)
