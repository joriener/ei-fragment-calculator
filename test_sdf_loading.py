#!/usr/bin/env python3
"""Direct test of SDF file loading without GUI."""

import sys
sys.path.insert(0, 'D:\\tmp\\ei-fragment-calculator')

# Check if RDKit is available
try:
    from rdkit import Chem
    print("[TEST] RDKit is available")
except ImportError:
    print("[ERROR] RDKit not installed")
    sys.exit(1)

# Test loading the SDF file directly
sdf_path = r"D:\Test\STRUSAMP.SDF"
print(f"[TEST] Loading SDF file: {sdf_path}")

try:
    suppl = Chem.SDMolSupplier(sdf_path, removeHs=False, sanitize=False)
    print(f"[TEST] SDMolSupplier created")
    print(f"[TEST] Number of molecules: {len(suppl)}")
    
    records = []
    for idx, mol in enumerate(suppl):
        print(f"[TEST] Processing record {idx}")
        
        if mol is None:
            print(f"[TEST] Record {idx} has no molecule")
            records.append({"mol": None, "fields": {}})
            continue
            
        # Get all properties
        fields = {}
        for prop in mol.GetPropNames():
            try:
                fields[prop] = mol.GetProp(prop)
            except:
                pass
        
        records.append({"mol": mol, "fields": fields})
        print(f"[TEST] Record {idx}: {fields.get('NAME', 'Unknown')}")
    
    print(f"[TEST] Successfully loaded {len(records)} records")
    print(f"[TEST] Test completed successfully!")
    
except Exception as e:
    print(f"[TEST] Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
