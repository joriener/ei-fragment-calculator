"""
Compare our exact-mass assignments vs ChemVista QTOF reference data.
Runs the algorithm on Test2.MSPEC (unit-mass) and checks correctness
of the highest-intensity peaks against the ChemVista SDF ground truth.
"""
import sys, re
from collections import defaultdict
sys.path.insert(0, r'D:\tmp\ei-fragment-calculator')

from ei_fragment_calculator.input_reader import read_records
from ei_fragment_calculator.formula import parse_formula
from ei_fragment_calculator.calculator import find_fragment_candidates, ion_mass
from ei_fragment_calculator.filters import FilterConfig, run_all_filters, rank_candidates
from ei_fragment_calculator.sdf_parser import parse_sdf

MSPEC_FILE   = r'D:\Test\Test2.MSPEC'
CHEMVISTA    = r'C:\Users\joerg\Downloads\chemvista_output_f315e368-2db3-4d7d-8e2b-e68c26fa8364 (1).sdf'
TOL_DA       = 0.5
PPM_MATCH    = 10.0   # ppm tolerance when matching our result vs ChemVista reference

# ── Load ChemVista reference: name -> {nominal_mz -> exact_mass} ─────────────
def parse_peak_list(text):
    pairs = re.findall(r'(\d+\.\d+)\s+([\d.]+)', text)
    return [(float(m), float(i)) for m, i in pairs]

cv_records = parse_sdf(CHEMVISTA)
cv_ref = {}   # name -> {nominal_mz: exact_mass}  (highest intensity wins per nominal)
for rec in cv_records:
    # ChemVista SDF has blank MOL-block line 1; real name is in the <NAME> data field
    name = (rec['fields'].get('NAME')
            or rec['fields'].get('COMPOUND NAME')
            or rec['name'])
    peak_text = rec['fields'].get('MASS SPECTRAL PEAKS', '')
    peaks = parse_peak_list(peak_text)
    nom_map = {}
    for exact_mz, intensity in peaks:
        nom = round(exact_mz)
        if nom not in nom_map or intensity > nom_map[nom][1]:
            nom_map[nom] = (exact_mz, intensity)
    cv_ref[name] = nom_map

# ── Load and process Test2.MSPEC ─────────────────────────────────────────────
records = read_records(MSPEC_FILE)

print("=" * 72)
print(f"{'Compound':<26} {'m/z':>5} {'Intens':>7}  {'Our exact':>12}  {'CV exact':>12}  {'dppm':>7}  OK?")
print("=" * 72)

total_peaks = 0
correct     = 0
wrong       = 0
missing_cv  = 0

for rec in records:
    name   = rec['name']
    fields = rec['fields']

    formula_str = fields.get('Formula') or fields.get('MOLECULAR FORMULA') or fields.get('FORMULA', '')
    peak_text   = fields.get('MASS SPECTRAL PEAKS', '')

    if not formula_str or not peak_text:
        print(f"  [{name}]  SKIP — no formula or peaks")
        continue

    try:
        parent = parse_formula(formula_str)
    except Exception as e:
        print(f"  [{name}]  SKIP — bad formula: {e}")
        continue

    # Parse peaks: "mz intensity;" format
    raw_peaks = re.findall(r'(\d+)\s+(\d+)', peak_text)
    peak_list = [(int(m), int(i)) for m, i in raw_peaks]
    if not peak_list:
        print(f"  [{name}]  SKIP — no peaks parsed")
        continue

    # Sort by intensity descending, take top 15 (most analytically important)
    peak_list.sort(key=lambda x: -x[1])
    top_peaks = peak_list[:15]
    max_int   = max(i for _, i in peak_list)

    ref = cv_ref.get(name, {})
    if not ref:
        # Try partial name match
        for k in cv_ref:
            if name.lower() in k.lower() or k.lower() in name.lower():
                ref = cv_ref[k]
                break

    cfg = FilterConfig(
        nitrogen_rule=True,
        hd_check=True,         # safe: max_ring_ratio=1.0 allows aromatics
        lewis_senior=True,
        max_ring_ratio=1.0,    # rejects only truly H-degenerate formulas (DBE/C > 1)
        isotope_score=False,
        smiles_constraints=False,
    )

    print(f"\n  {name}  (formula: {formula_str})")
    print(f"  {'m/z':>5} {'%base':>6}  {'Our exact':>12}  {'CV ref':>12}  {'dppm':>7}  match?")
    print(f"  {'-'*62}")

    for nom_mz, intensity in top_peaks:
        rel_int = 100.0 * intensity / max_int

        cands = find_fragment_candidates(nom_mz, parent,
                                         electron_mode="remove",
                                         tolerance=TOL_DA)
        if cands:
            # run_all_filters preserves _mdd_deviation and adds filter_passed
            annotated = [run_all_filters(c, nom_mz, cfg) for c in cands]
            passed    = [c for c in annotated if c.get('filter_passed', True)]
            ranked    = rank_candidates(passed) if passed else rank_candidates(annotated)
            best      = ranked[0]
            our_mass  = best['ion_mass']
        else:
            our_mass = None

        # ChemVista reference for this nominal m/z
        cv_entry = ref.get(nom_mz)
        cv_mass  = cv_entry[0] if cv_entry else None

        if our_mass is not None and cv_mass is not None:
            delta_ppm = abs(our_mass - cv_mass) / cv_mass * 1e6
            ok = delta_ppm < PPM_MATCH
            if ok:
                correct += 1
                tag = "OK"
            else:
                wrong += 1
                tag = f"WRONG ({best.get('formula','?')} vs CV)"
            total_peaks += 1
        elif our_mass is not None:
            delta_ppm = None
            cv_mass   = None
            tag = "(no CV ref)"
            missing_cv += 1
            total_peaks += 1
        else:
            delta_ppm = None
            tag = "NO CAND"

        our_str = f"{our_mass:.6f}" if our_mass is not None else "       —"
        cv_str  = f"{cv_mass:.6f}"  if cv_mass  is not None else "       —"
        ppm_str = f"{delta_ppm:+.1f}" if delta_ppm is not None else "      —"

        print(f"  {nom_mz:>5} {rel_int:>5.1f}%  {our_str:>12}  {cv_str:>12}  {ppm_str:>7}  {tag}")

print()
print("=" * 72)
if total_peaks > 0:
    print(f"Summary: {correct}/{total_peaks} correct within {PPM_MATCH:.0f} ppm  "
          f"({100*correct/total_peaks:.1f}%)   wrong={wrong}  no-CV-ref={missing_cv}")
print("=" * 72)
