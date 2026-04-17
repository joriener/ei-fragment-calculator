#!/usr/bin/env python3
"""Quick verification that the freeze fix is in place."""

import sys
from pathlib import Path

gui_file = Path("ei_fragment_calculator/gui.py")
if not gui_file.exists():
    print("ERROR: gui.py not found")
    sys.exit(1)

with open(gui_file, "r") as f:
    content = f.read()

# Check 1: _show_record has highlight_in_tree parameter
check1 = "def _show_record(self, idx: int, highlight_in_tree: bool = False)" in content
print(f"✓ _show_record has highlight_in_tree parameter: {check1}")

# Check 2: selection_set() is guarded by highlight_in_tree
check2 = "if highlight_in_tree and self._compound_tree:" in content
print(f"✓ selection_set() is guarded: {check2}")

# Check 3: Initial load uses highlight_in_tree=True
check3 = "self._show_record(0, highlight_in_tree=True)" in content
print(f"✓ Initial load uses highlight_in_tree=True: {check3}")

if check1 and check2 and check3:
    print("\n✅ All fixes are in place!")
    sys.exit(0)
else:
    print("\n❌ Some fixes are missing!")
    sys.exit(1)
