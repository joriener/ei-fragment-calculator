"""
launch_gui.py
=============
Thin entry-point used by PyInstaller to produce the frozen executable.

DO NOT rename or move this file — the spec file references it by name.
"""
import multiprocessing
from ei_fragment_calculator.gui import main

if __name__ == "__main__":
    # Required on Windows so that frozen-app worker processes don't
    # re-launch the full GUI instead of running the worker function.
    multiprocessing.freeze_support()
    main()
