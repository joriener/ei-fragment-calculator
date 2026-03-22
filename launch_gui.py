"""
launch_gui.py
=============
Thin entry-point used by PyInstaller to produce the frozen executable.

DO NOT rename or move this file — the spec file references it by name.
"""
from ei_fragment_calculator.gui import main

if __name__ == "__main__":
    main()
