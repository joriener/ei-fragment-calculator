@echo off
setlocal
cd /d D:\tmp\ei-fragment-calculator

echo === BASELINE MEASUREMENT ===========================================
echo.

echo --- Test 1: Fragmentation rules on Toluene (MSP, no MOL block) ---
C:\Python\Python311\python.exe -c "
import sys
sys.path.insert(0, r'D:\tmp\ei-fragment-calculator')
from ei_fragment_calculator.input_reader import read_records
from ei_fragment_calculator.fragmentation_rules import annotate_neutral_losses, get_structure_fragments
from ei_fragment_calculator.formula import parse_formula, exact_mass
from ei_fragment_calculator.mol_parser import parse_mol_block_full

records = read_records(r'D:\tmp\ei-fragment-calculator\examples\three_compounds.msp')
print('Records loaded:', len(records))
for r in records:
    print('  Name:', r['name'], '| Formula:', r['fields'].get('MOLECULAR FORMULA','?'), '| mol_block len:', len(r.get('mol_block','')))

# Test Tier 1 neutral losses for Toluene C7H8, m/z 91
parent = parse_formula('C7H8')
parent_mass = exact_mass(parent)
matches = annotate_neutral_losses(91, parent_mass, parent, 'remove', 0.5)
print('Tier 1 NL matches for Toluene at m/z 91:', len(matches))
for m in matches:
    print(' ', m['rule_name'], m['description'])
print()

# Test Tier 1 for m/z 92 (M+.)
matches2 = annotate_neutral_losses(92, parent_mass, parent, 'remove', 0.5)
print('Tier 1 NL matches for Toluene at m/z 92:', len(matches2))
"

echo.
echo --- Test 2: CLI run with fragmentation rules on three_compounds.msp ---
C:\Python\Python311\python.exe -m ei_fragment_calculator.cli --fragmentation-rules --confidence --best-only examples\three_compounds.msp 2>&1 | head -60

echo.
echo --- Test 3: CLI with SDF (has MOL block) ---
C:\Python\Python311\python.exe -m ei_fragment_calculator.cli --fragmentation-rules --confidence --best-only examples\three_compounds.sdf 2>&1 | head -80

echo.
echo === END BASELINE ===================================================
