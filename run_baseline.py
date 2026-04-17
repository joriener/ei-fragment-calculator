"""
Phase 1 baseline measurement script.
Run with: C:\Python\Python311\python.exe run_baseline.py > baseline_metrics.txt 2>&1
"""
import sys
import re
sys.path.insert(0, r'D:\tmp\ei-fragment-calculator')

from ei_fragment_calculator.input_reader import read_records
from ei_fragment_calculator.formula import parse_formula, hill_formula
from ei_fragment_calculator.calculator import find_fragment_candidates, exact_mass
from ei_fragment_calculator.filters import FilterConfig, run_all_filters, rank_candidates
from ei_fragment_calculator.fragmentation_rules import (
    annotate_neutral_losses, get_structure_fragments, annotate_candidate,
    enumerate_homolytic_cleavages, apply_alpha_cleavage,
    apply_inductive_cleavage, apply_mclafferty,
)
from ei_fragment_calculator.mol_parser import parse_mol_block_full

# ─────────────────────────────────────────────────────────────────
# Section 1: Test fragmentation rules against known compounds
# ─────────────────────────────────────────────────────────────────
print("=" * 70)
print("SECTION 1: FRAGMENTATION RULE COVERAGE (example MSP, no MOL blocks)")
print("=" * 70)

msp_records = read_records(r'D:\tmp\ei-fragment-calculator\examples\three_compounds.msp')
print(f"Loaded {len(msp_records)} records from three_compounds.msp\n")

cfg = FilterConfig(nitrogen_rule=True, hd_check=True, lewis_senior=True,
                   max_ring_ratio=1.0, isotope_score=False, smiles_constraints=False)

for rec in msp_records:
    name = rec['name']
    formula_str = rec['fields'].get('MOLECULAR FORMULA') or rec['fields'].get('Formula', '')
    peak_text = rec['fields'].get('MASS SPECTRAL PEAKS', '')
    mol_block = rec.get('mol_block', '')

    if not formula_str:
        print(f"  [{name}] SKIP — no formula")
        continue

    parent = parse_formula(formula_str)
    parent_mass = exact_mass(parent)
    parent_nominal = round(parent_mass)

    raw_peaks = re.findall(r'(\d+)\s+(\d+)', peak_text)
    peak_list = [(int(m), int(i)) for m, i in raw_peaks]
    if not peak_list:
        print(f"  [{name}] SKIP — no peaks")
        continue

    peak_list.sort(key=lambda x: -x[1])
    max_int = max(i for _, i in peak_list)

    # Parse MOL block if present
    mol_data = parse_mol_block_full(mol_block) if mol_block else None

    # Get structure fragments from MOL block
    struct_frags = get_structure_fragments(mol_data) if mol_data else []

    print(f"--- {name}  ({formula_str}, M={parent_nominal}, peaks={len(peak_list)}, "
          f"mol_block={'yes' if mol_data else 'no'}, "
          f"struct_frags={len(struct_frags)}) ---")

    nl_matches_total = 0
    struct_matches_total = 0
    total_annotated = 0
    zero_candidate_peaks = 0

    for nom_mz, intensity in peak_list:
        rel_int = 100.0 * intensity / max_int

        # Neutral loss matches
        nl_matches = annotate_neutral_losses(nom_mz, parent_mass, parent, 'remove', 0.5)

        cands = find_fragment_candidates(nom_mz, parent, electron_mode='remove', tolerance=0.5)
        if not cands:
            zero_candidate_peaks += 1
            continue

        annotated = [run_all_filters(c, nom_mz, cfg, parent_composition=parent) for c in cands]
        passed = [c for c in annotated if c.get('filter_passed', True)]
        ranked = rank_candidates(passed) if passed else rank_candidates(annotated)

        # Annotate best candidate
        best = ranked[0]
        annotate_candidate(best, nl_matches, struct_frags)

        total_annotated += 1
        rule = best.get('fragmentation_rule', '')
        if rule and '[M-' in rule:
            nl_matches_total += 1
        elif rule:
            struct_matches_total += 1

        print(f"  m/z {nom_mz:>4} ({rel_int:>5.1f}%): best={best.get('formula','?'):>12}  "
              f"rule={rule if rule else '(none)':>25}  "
              f"conf={best.get('_confidence',0.0):.3f}")

    print(f"  Summary: {total_annotated} peaks assigned, NL hits={nl_matches_total}, "
          f"struct hits={struct_matches_total}, zero-cand={zero_candidate_peaks}\n")


# ─────────────────────────────────────────────────────────────────
# Section 2: Test structure-based rules with SDF (has MOL blocks)
# ─────────────────────────────────────────────────────────────────
print("=" * 70)
print("SECTION 2: STRUCTURE-BASED RULES (three_compounds.sdf, has MOL blocks)")
print("=" * 70)

sdf_records = read_records(r'D:\tmp\ei-fragment-calculator\examples\three_compounds.sdf')
print(f"Loaded {len(sdf_records)} records from three_compounds.sdf\n")

for rec in sdf_records:
    name = rec['name']
    mol_block = rec.get('mol_block', '')
    mol_data = parse_mol_block_full(mol_block) if mol_block else None

    print(f"--- {name} ---")
    print(f"  mol_block present: {'yes' if mol_block else 'no'}")
    if mol_data:
        print(f"  atoms: {len(mol_data['atoms'])}, bonds: {len(mol_data['bonds'])}, rings: {mol_data['ring_count']}")
        hom = enumerate_homolytic_cleavages(mol_data)
        alp = apply_alpha_cleavage(mol_data)
        ind = apply_inductive_cleavage(mol_data)
        mcl = apply_mclafferty(mol_data)
        struct_frags = get_structure_fragments(mol_data)
        print(f"  Homolytic cleavages: {len(hom)}")
        print(f"  Alpha cleavages: {len(alp)}")
        print(f"  Inductive cleavages: {len(ind)}")
        print(f"  McLafferty: {len(mcl)}")
        print(f"  Total struct frags: {len(struct_frags)}")
        if struct_frags:
            print("  First 5 fragment formulas:")
            for f in struct_frags[:5]:
                for key in ('frag1_formula', 'frag2_formula',
                            'charged_frag_formula', 'neutral_frag_formula', 'enol_formula'):
                    if key in f:
                        print(f"    {f['rule']:22s} {key}: {f[key]}")
    else:
        print("  mol_data: None (empty or No Structure block)")
    print()


# ─────────────────────────────────────────────────────────────────
# Section 3: McLafferty H-detection test
# ─────────────────────────────────────────────────────────────────
print("=" * 70)
print("SECTION 3: McLAFFERTY H-DETECTION BUG CHECK")
print("=" * 70)

# Acetophenone C8H8O: classic McLafferty compound
# Build a minimal MOL block with explicit H to test if McLafferty fires
# when H atoms ARE in the graph vs when they are NOT
print("Testing McLafferty with PubChem-style mol (no explicit H):")
print("If McLafferty=0 here, the H-detection bug is confirmed.\n")

for rec in sdf_records:
    if 'Acetophenone' in rec['name'] or 'acetophenone' in rec['name'].lower():
        mol_block = rec.get('mol_block', '')
        mol_data = parse_mol_block_full(mol_block) if mol_block else None
        if mol_data:
            mcl = apply_mclafferty(mol_data)
            print(f"  Acetophenone McLafferty hits: {len(mcl)}")
            if len(mcl) == 0:
                print("  *** BUG CONFIRMED: McLafferty=0 because H not in PubChem 2D adjacency ***")
            for m in mcl:
                print(f"    enol_formula={m['enol_formula']}, neutral_formula={m['neutral_formula']}")
        break

print()
print("=" * 70)
print("BASELINE MEASUREMENT COMPLETE")
print("=" * 70)
