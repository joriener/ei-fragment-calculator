#!/usr/bin/env python3
"""Direct test of SDF loading without GUI."""

import sys
import os

# Redirect output to a file
log_file = r"D:\tmp\ei-fragment-calculator\test_output.log"
log = open(log_file, 'w')

def log_print(*args, **kwargs):
    """Print to both console and log file."""
    msg = ' '.join(str(arg) for arg in args)
    print(msg)
    log.write(msg + '\n')
    log.flush()

sys.stdout = log  # Redirect stdout to file
sys.stderr = log  # Redirect stderr to file

log_print("=" * 50)
log_print("SDF VIEWER TEST")
log_print("=" * 50)

try:
    log_print("[TEST] Importing RDKit...")
    from rdkit import Chem
    log_print("[TEST] RDKit imported successfully")
except ImportError as e:
    log_print(f"[ERROR] RDKit import failed: {e}")
    sys.exit(1)

# Test the actual loading
sdf_path = r"D:\Test\STRUSAMP.SDF"
log_print(f"[TEST] Testing file: {sdf_path}")
log_print(f"[TEST] File exists: {os.path.isfile(sdf_path)}")

try:
    log_print("[TEST] Creating SDMolSupplier...")
    suppl = Chem.SDMolSupplier(sdf_path, removeHs=False, sanitize=False)
    log_print(f"[TEST] SDMolSupplier created: {suppl}")
    log_print(f"[TEST] Number of molecules: {len(suppl)}")
    
    for idx, mol in enumerate(suppl):
        log_print(f"[TEST] Record {idx}: mol is {type(mol).__name__}")
        if mol:
            name = mol.GetProp("NAME") if mol.HasProp("NAME") else "Unknown"
            log_print(f"[TEST] Record {idx}: {name}")
    
    log_print("[TEST] Test completed successfully!")
    
except Exception as e:
    log_print(f"[ERROR] Exception: {e}")
    import traceback
    traceback.print_exc(file=log)

log_print("=" * 50)
log.close()

# Print the result to console
with open(log_file, 'r') as f:
    content = f.read()
    print(content, file=open(1, 'w'))  # This won't work, so just exit
