"""
Test that McLafferty fires correctly for PubChem 2D-style SDF
(no explicit H atoms in atom table — only implicit via valence).

Acetophenone C8H8O is the canonical McLafferty compound:
  O=C(Ph)–CH2–CH3  → enol C6H6O (m/z 94) + neutral C2H2

But for the minimal test: a simple ketone structure.
"""
import sys
sys.path.insert(0, r'D:\tmp\ei-fragment-calculator')

from ei_fragment_calculator.fragmentation_rules import apply_mclafferty
from ei_fragment_calculator.mol_parser import parse_mol_block_full

# -------------------------------------------------------------------
# Pentan-2-one CH3-CO-CH2-CH2-CH3 (MW=86)  —  textbook McLafferty
# V2000 MOL block with implicit H (PubChem style: no H atoms listed)
# Atom order: C1(methyl), C2(carbonyl-C), O3, C4(alpha), C5(beta), C6(gamma=CH2CH3?)
# More precisely: build 5-carbon chain with C=O at C2
#
# Structure:  C1-C2(=O3)-C4-C5-C6
#   C1 = CH3 (valence 4, 3 bonds: 1 to C2, 3 implicit H)
#   C2 = carbonyl C (valence 4, bonds: C1, O3(double), C4 → used=4, implicit H=0)
#   O3 = carbonyl O (valence 2, 1 double bond → used=2, implicit H=0)
#   C4 = alpha C (valence 4, bonds: C2, C5 → used=2, implicit H=2)  — needs 2H → methylenyl
#   C5 = beta C  (valence 4, bonds: C4, C6 → used=2, implicit H=2)
#   C6 = gamma C (valence 4, bonds: C5 → used=1, implicit H=3)  — this is the γ with H!
#
# McLafferty: H migrates from C6(gamma) to O3 via 6-membered TS; C4-C5 bond cleaves
# Enol fragment: C1-C2(=O3)(H) = CH2=C(OH)-CH3  (C3H6O, m/z 58)
# Neutral fragment: C5=C6  = CH2=CH2? No, actually neutral = CH2=CH2 (C2H4)...
# Wait. Pentan-2-one: CH3-CO-CH2-CH2-CH3 → McLafferty gives:
#   enol = CH2=C(OH)-CH3  (C3H6O, m/z 58) [charged]
#   neutral = CH2=CH2 (C2H4, m/z 28) [lost as neutral]
#
# We just need to see that apply_mclafferty() returns ≥1 result.

PENTAN2ONE_MOL = """\
Pentan-2-one
  PubChemTest

  6  5  0  0  0  0  0  0  0  0  0 V2000
    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.5000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    1.5000    1.5000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0
    3.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    4.5000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
    6.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  1  0
  2  3  2  0
  2  4  1  0
  4  5  1  0
  5  6  1  0
M  END
"""

mol_data = parse_mol_block_full(PENTAN2ONE_MOL)
assert mol_data is not None, "Mol block parse failed"
print(f"atoms: {len(mol_data['atoms'])}, bonds: {len(mol_data['bonds'])}")
for a in mol_data['atoms']:
    print(f"  {a['element']}")

results = apply_mclafferty(mol_data)
print(f"\nMcLafferty hits: {len(results)}")
for r in results:
    print(f"  enol_formula={r['enol_formula']}, neutral_formula={r['neutral_formula']}")
    print(f"  enol_comp={r['enol_comp']}, neutral_comp={r['neutral_comp']}")
    print(f"  H_count_at_gamma={r['H_count_at_gamma']}")

if len(results) > 0:
    print("\n*** PASS: McLafferty fires with implicit H (PubChem 2D style) ***")
    # Verify enol = C3H6O (CH2=C(OH)CH3), neutral = C2H4
    r = results[0]
    enol = r['enol_comp']
    neut = r['neutral_comp']
    assert enol.get('C', 0) == 3 and enol.get('O', 0) == 1, f"Expected C3xxO enol, got {r['enol_formula']}"
    print(f"  Enol  = {r['enol_formula']}  (expected C3H6O)")
    print(f"  Neutral = {r['neutral_formula']}  (expected C2H4)")
else:
    print("\n*** FAIL: McLafferty returned 0 results — fix did not work ***")
    sys.exit(1)
