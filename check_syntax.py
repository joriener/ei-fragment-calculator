#!/usr/bin/env python3
"""Check syntax of refactored gui.py"""

import sys
import py_compile

try:
    py_compile.compile(r"D:\tmp\ei-fragment-calculator\ei_fragment_calculator\gui.py", doraise=True)
    print("[PASS] gui.py syntax is valid")
    sys.exit(0)
except py_compile.PyCompileError as e:
    print(f"[FAIL] Syntax error in gui.py:")
    print(e)
    sys.exit(1)
