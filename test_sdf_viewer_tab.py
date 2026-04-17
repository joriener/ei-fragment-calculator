#!/usr/bin/env python3
"""Direct test of the _SDFViewerTab loading functionality."""

import sys
import tkinter as tk
sys.path.insert(0, 'D:\\tmp\\ei-fragment-calculator')

# Import the GUI module
from ei_fragment_calculator.gui import _SDFViewerTab

# Create a minimal root window
root = tk.Tk()
root.title("Test SDF Viewer Tab")
root.geometry("800x600")

print("[TEST] Creating _SDFViewerTab instance...")
try:
    tab = _SDFViewerTab(root)
    tab.pack(fill=tk.BOTH, expand=True)
    print("[TEST] _SDFViewerTab created successfully")
except Exception as e:
    print(f"[ERROR] Failed to create _SDFViewerTab: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Try to load an SDF file
sdf_path = r"D:\Test\STRUSAMP.SDF"
print(f"[TEST] Attempting to load SDF file: {sdf_path}")

try:
    print("[TEST] Calling _load_sdf()...")
    tab._load_sdf(sdf_path)
    print("[TEST] _load_sdf() completed")
    print(f"[TEST] Number of records loaded: {len(tab._records)}")
    print(f"[TEST] Test completed successfully!")
except Exception as e:
    print(f"[TEST] Error during _load_sdf: {e}")
    import traceback
    traceback.print_exc()

print("[TEST] Showing window...")
root.mainloop()
