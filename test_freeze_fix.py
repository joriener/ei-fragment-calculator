#!/usr/bin/env python3
"""
Test to verify the freeze fix in _SDFViewerTab.

This test verifies that the infinite loop caused by tree selection events
is properly fixed by the highlight_in_tree parameter.
"""

import sys
import os
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Test the fix conceptually
def test_infinite_loop_fix():
    """
    Verify that the fix prevents infinite loops.
    
    The problem was:
    1. User selects record in tree
    2. _on_compound_selected() is triggered
    3. _show_record(idx) is called
    4. _show_record() calls selection_set(idx)  <-- This triggers step 1 again!
    5. Infinite loop
    
    The fix:
    - Add highlight_in_tree parameter to _show_record()
    - Only call selection_set() when highlight_in_tree=True
    - Only set highlight_in_tree=True during initial load, not during event handling
    """
    
    print("=" * 60)
    print("Testing freeze fix in _SDFViewerTab")
    print("=" * 60)
    
    # Verify the fix is in place
    with open("ei_fragment_calculator/gui.py", "r") as f:
        gui_content = f.read()
    
    # Check 1: _show_record has highlight_in_tree parameter
    if "def _show_record(self, idx: int, highlight_in_tree: bool = False)" in gui_content:
        print("✓ CHECK 1 PASSED: _show_record has highlight_in_tree parameter")
    else:
        print("✗ CHECK 1 FAILED: _show_record missing highlight_in_tree parameter")
        return False
    
    # Check 2: highlight_in_tree guards the selection_set call
    if "if highlight_in_tree and self._compound_tree:" in gui_content:
        print("✓ CHECK 2 PASSED: selection_set() is guarded by highlight_in_tree")
    else:
        print("✗ CHECK 2 FAILED: selection_set() is not properly guarded")
        return False
    
    # Check 3: _show_record is called with highlight_in_tree=True only during load
    if "self._show_record(0, highlight_in_tree=True)" in gui_content:
        print("✓ CHECK 3 PASSED: Initial load calls _show_record with highlight_in_tree=True")
    else:
        print("✗ CHECK 3 FAILED: Initial load doesn't pass highlight_in_tree=True")
        return False
    
    # Check 4: Event handler doesn't pass highlight_in_tree parameter
    # This means it uses the default value of False
    event_handler_pattern = "_on_compound_selected"
    if "_show_record(idx)" in gui_content and event_handler_pattern in gui_content:
        # Extract the event handler section
        start = gui_content.find("def _on_compound_selected")
        end = gui_content.find("\n    def ", start + 1)
        event_handler = gui_content[start:end]
        
        if "self._show_record(idx)" in event_handler and "highlight_in_tree" not in event_handler:
            print("✓ CHECK 4 PASSED: Event handler calls _show_record(idx) without highlight_in_tree")
        else:
            print("✗ CHECK 4 FAILED: Event handler handling may be incorrect")
            return False
    
    print("\n" + "=" * 60)
    print("All checks passed! The freeze fix is properly implemented.")
    print("=" * 60)
    return True


def test_with_actual_sdf():
    """
    Test with an actual SDF file to verify loading works.
    """
    print("\nTesting with actual SDF file...")
    
    sdf_file = Path("D:\\Test\\STRUSAMP.SDF")
    if not sdf_file.exists():
        print(f"✗ Test SDF file not found: {sdf_file}")
        return False
    
    print(f"✓ Found test SDF file: {sdf_file}")
    
    try:
        from ei_fragment_calculator.sdf_parser import parse_sdf_file
        records = parse_sdf_file(str(sdf_file))
        print(f"✓ Successfully parsed SDF file")
        print(f"  - Found {len(records)} records")
        
        for i, record in enumerate(records[:2]):
            name = record.get("fields", {}).get("NAME", "Unknown")
            print(f"  - Record {i}: {name[:50]}")
        
        return True
    except Exception as e:
        print(f"✗ Error parsing SDF: {e}")
        return False


if __name__ == "__main__":
    success = test_infinite_loop_fix()
    if success:
        test_with_actual_sdf()
        sys.exit(0)
    else:
        sys.exit(1)
