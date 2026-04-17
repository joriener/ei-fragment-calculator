# EI Fragment Calculator — Project Reference

*Last updated: 2026-04-17. Reflects actual confirmed code state — read the code, don't trust the old session summaries.*

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Repository Layout](#2-repository-layout)
3. [Current Capabilities — What Actually Works](#3-current-capabilities--what-actually-works)
4. [Confirmed Bugs Fixed](#4-confirmed-bugs-fixed)
5. [Remaining Gap — Only One Item Left](#5-remaining-gap--only-one-item-left)
6. [Complete Pipeline Schema](#6-complete-pipeline-schema)
7. [All Strategies — Master Table](#7-all-strategies--master-table)
8. [Next Session Brief (Copy-Paste Ready)](#8-next-session-brief-copy-paste-ready)
9. [Key Commands](#9-key-commands)
10. [Accuracy Metrics Log](#10-accuracy-metrics-log)

---

## 1. Project Overview

**Purpose:** Assign exact elemental formulas to unit-mass EI (electron ionisation) fragment peaks,
starting from a molecular formula and a unit-mass spectrum. Optionally uses a 2-D MOL block
from PubChem for structure-based fragmentation rules.

**Goal:** Only assigned fragments should be *certain*. It is acceptable — preferred — to leave
a peak unassigned rather than assign it incorrectly. Coverage is secondary to certainty.

**Inputs accepted:**
- `.sdf` / `.sd` — MDL Structure-Data File (with or without MOL block)
- `.msp` / `.mspec` — NIST Mass Spectral format
- `.jdx` / `.jcamp` / `.dx` — JCAMP-DX
- `.csv` / `.tsv` — tabular peak lists (two layout variants)

**Outputs produced:**
- `<input>-EXACT.sdf` — annotated SDF with exact ion masses per peak
- `<input>-EXACT.msp` — NIST MSP with exact masses replacing nominal m/z
- Console / text log

**Environment:**
- Python: `C:\Python\Python311\python.exe`
- Project root: `D:\tmp\ei-fragment-calculator\`
- Test data: `D:\Test\Test2.MSPEC` (unit-mass EI), ChemVista SDF at `C:\Users\joerg\Downloads\`
- Run tests: `run_tests.bat` in project root → **169 passed** as of 2026-04-17
- Package version: `1.8.0` (pyproject.toml)
- Last commit: `2f08e9e` — "fix: McLafferty H-detection for PubChem 2D SDF (no explicit H)"

---

## 2. Repository Layout

```
ei_fragment_calculator/
  calculator.py          Branch-and-bound formula enumeration; MDD ranking; exact_mass()
  filters.py             Chemical validity filters + rank_candidates() + apply_golden_rules()
                         apply_clbr_m2_check()  apply_neutral_validation()
  confidence.py          3-pass confidence scoring; _score_isotope() with M+1 guard
  fragmentation_rules.py Tier 1 NL table; Tier 2 structural cleavages; _add_implicit_h();
                         apply_retro_diels_alder(); get_secondary_fragments()
  neutral_losses.py      106-entry nominal-mass EI neutral loss table
  stable_ions.py         57 known stable EI fragment ions with m/z lookup
  nist_lookup.py         NIST WebBook query by InChIKey → {nominal_mz: formula_str}
  sdbs_lookup.py         SDBS (AIST) lookup as NIST fallback → same format
  input_reader.py        Multi-format parser (SDF/MSP/MSPEC/JDX/CSV)
  sdf_parser.py          Low-level SDF field extraction
  mol_parser.py          V2000 MOL block parser (heavy atoms only — no explicit H)
  structure_fetcher.py   PubChem 2D MOL + SMILES/InChIKey/CID/ExactMW fetch
  mol_merger.py          Copy MOL blocks from a second SDF by name matching
  isotope.py             Full polynomial-convolution isotope pattern engine
  formula.py             Formula parsing, Hill ordering
  calculator.py          exact_mass(), ion_mass(), find_fragment_candidates()
  constants.py           Element masses, ISOTOPE_DATA, VALENCE table
  cli.py                 Main CLI; CLASS_TEMPLATES; _classify_compound(); E6 mol-ion check
  gui.py                 Tkinter GUI (runs CLI as subprocess)
  sdf_writer.py          Write annotated SDF and MSP output files
  enrich.py / enrich_cli.py  SDF enrichment pipeline (separate tool)
  preflight.py           Python version + elements.csv sanity checks

tests/
  test_calculator.py     18 tests
  test_confidence.py     49 tests
  test_filters.py        19 tests
  test_formula.py        11 tests
  test_input_reader.py   27 tests (including MSPEC format)
  test_isotope.py        10 tests
  test_sdf_parser.py     10 tests
  test_nist_sdbs_lookup.py  20 tests (mock HTTP)
  *** NO test_fragmentation_rules.py *** ← MISSING, needs to be written

compare_accuracy.py      Compares unit-mass assignments vs ChemVista QTOF reference
run_tests.bat            C:\Python\Python311\python.exe -m pytest tests -x -q → 169 passed
run_baseline.py          Manual baseline script (sections 1-3, fragment rule coverage check)
baseline_metrics.txt     Fragment rule coverage on three_compounds.msp (written 2026-04-17)
accuracy_baseline.txt    compare_accuracy.py output (written 2026-04-17)
PROJECT_REFERENCE.md     This file
```

---

## 3. Current Capabilities — What Actually Works

> Confirmed by reading code and running tests 2026-04-17. Do NOT trust older session summaries.

| Feature | Module | Status |
|---------|--------|--------|
| Multi-format input (SDF/MSP/MSPEC/JDX/CSV) | `input_reader.py` | ✅ Working, 27 tests |
| Branch-and-bound formula enumeration | `calculator.py` | ✅ Working |
| MDD (mass-defect-per-Da) ranking | `calculator.py` | ✅ Working |
| Chemical validity filters F1–F6 | `filters.py` | ✅ Working |
| Cl/Br M+2 hard constraint | `filters.py apply_clbr_m2_check()` | ✅ Working |
| Plausible neutral validation | `filters.py apply_neutral_validation()` | ✅ Working |
| 7 Golden Rules element ratios | `filters.py apply_golden_rules()` | ✅ Working |
| 3-pass confidence scoring | `confidence.py` | ✅ Working |
| M+1 guard (disabled below 50% parent mass) | `confidence.py _score_isotope()` | ✅ Working |
| Even/odd electron preference by mass range | `confidence.py` | ✅ Working |
| Stable-ion library bonus | `stable_ions.py` + confidence Pass 1 | ✅ Working |
| Neutral-loss inter-peak cross-check | confidence Pass 2 | ✅ Working |
| Complementary-ion pair check | confidence Pass 3 | ✅ Working |
| Tier 1 neutral-loss annotation (36 losses) | `fragmentation_rules.py` | ✅ Working |
| Tier 2 homolytic cleavage (implicit H) | `fragmentation_rules.py` | ✅ Working |
| Tier 2 alpha cleavage (implicit H) | `fragmentation_rules.py` | ✅ Working |
| Tier 2 inductive cleavage (implicit H) | `fragmentation_rules.py` | ✅ Working |
| Tier 2 McLafferty (implicit H + double-bond correction) | `fragmentation_rules.py` | ✅ Fixed 2026-04-17 |
| Retro-Diels-Alder rule | `fragmentation_rules.py apply_retro_diels_alder()` | ✅ Working |
| Secondary (depth-1) fragmentation | `fragmentation_rules.py get_secondary_fragments()` | ✅ Working |
| Whitelist hard gate (`--strict-structure`) | `fragmentation_rules.py annotate_candidate()` | ✅ Working |
| PubChem fetch: MOL block + SMILES + InChIKey + CID + ExactMW | `structure_fetcher.py` | ✅ Working |
| Formula validation vs PubChem exact MW | `structure_fetcher.py` | ✅ Working |
| NIST WebBook lookup by InChIKey (`--nist-lookup`) | `nist_lookup.py` | ✅ Working, 20 tests |
| SDBS fallback lookup | `sdbs_lookup.py` | ✅ Working |
| Compound class detection + templates | `cli.py CLASS_TEMPLATES` | ✅ Working |
| Molecular ion confirmation + peaks-above warning | `cli.py` E6 | ✅ Working |
| Adduct ion detection ([M+H]+) | `cli.py` F5 | ✅ Working |
| Intensity pre-filter (< 2% base peak dropped) | `cli.py` E4 | ✅ Working |
| `--reference-sdf` internal library flag | `cli.py` C4 | ✅ Working |
| **Kendrick mass series detection** | `confidence.py` | ❌ **NOT YET IMPLEMENTED** |

**Key CLI flags (all working):**

```
--best-only                 Top candidate per peak; unmatched dropped
--confidence                3-pass confidence scoring
--confidence-threshold 0.7  Drop peaks below threshold (use with --best-only)
--fragmentation-rules       Annotate candidates with EI structural rules
--fetch-structures          Fetch PubChem 2D MOL + properties for structureless records
--merge-structures FILE     Copy MOL blocks from a second SDF by name
--strict-structure          Hard gate: drop candidates with no structural explanation
--nist-lookup               Query NIST WebBook + SDBS for annotated EI spectra
--reference-sdf FILE        User-supplied exact-mass SDF as internal library (conf=0.99)
--hr                        High-resolution input mode (exact masses, ppm matching)
--output FILE               Write text output to file
--output-sdf / --output-msp Write annotated SDF / MSP output
```

---

## 4. Confirmed Bugs Fixed

All bugs listed in the old §4 have been resolved. Summary of what was fixed and when:

| Old Bug # | Description | Fix | Date |
|-----------|-------------|-----|------|
| BUG 1 | Implicit H in fragment rules — all H-free | `_add_implicit_h()` added and called in all 4 rule functions | pre-2026-04-17 |
| BUG 1b | McLafferty: H-detection checked explicit H atoms in adjacency graph (always 0 for PubChem 2D) | Implicit valence fallback; double-bond H correction in enol/neutral | **2026-04-17** (commit 2f08e9e) |
| BUG 2 | Whitelist not enforced as hard gate | `strict_structure` parameter in `annotate_candidate()`; `--strict-structure` CLI flag | pre-2026-04-17 |
| BUG 3 | M+1 scoring at all masses | `_score_isotope()` returns `(0.5,0.5,[])` when `mz < parent*0.5` | pre-2026-04-17 |
| GAP 4 | PubChem fetches only MOL block | Second REST call for SMILES/InChIKey/CID/ExactMW in `structure_fetcher.py` | pre-2026-04-17 |
| GAP 5/11 | No NIST/SDBS library lookup | `nist_lookup.py` + `sdbs_lookup.py` + `--nist-lookup` flag | pre-2026-04-17 |
| GAP 6 | No Retro-Diels-Alder | `apply_retro_diels_alder()` in `fragmentation_rules.py` | pre-2026-04-17 |
| GAP 7 | No secondary fragmentation | `get_secondary_fragments()` in `fragmentation_rules.py` | pre-2026-04-17 |
| GAP 8 | No compound class detection | `CLASS_TEMPLATES` + `_classify_compound()` in `cli.py` | pre-2026-04-17 |
| GAP 9 | No intensity pre-filter | Pre-filter loop in `cli.py format_record()` | pre-2026-04-17 |
| GAP 10 | Cl/Br M+2 soft only | `apply_clbr_m2_check()` sets `filter_passed=False` | pre-2026-04-17 |
| GAP 12 | No formula validation | In `structure_fetcher.py` after PubChem fetch | pre-2026-04-17 |
| GAP 13 | No peaks-above-M+• detection | E6 in `cli.py format_record()` | pre-2026-04-17 |

---

## 5. Remaining Gap — Only One Item Left

### E1 — Kendrick Mass Series Detection

**Where:** `confidence.py` — add as Pass 4 after the existing complementary-ion Pass 3.

**What it does:** Finds groups of 3+ peaks that differ by a fixed nominal mass (CH₂=14, C₂H₂=26,
H₂O=18) and verifies their top-ranked formula assignments differ by exactly that composition.
If the series is internally consistent, boosts confidence for all members by +0.15.

**Impact:** Medium — helps correctly rank candidates in alkyl chains, aromatic condensation series,
and sugar/dehydration series. No false positives (only boosts, never rejects).

**Implementation:**

```python
# In confidence.py — add after Pass 3, before final sort

# Pass 4 — Kendrick homologous series
_SERIES = {14: {"C": 1, "H": 2},   # CH2
            26: {"C": 2, "H": 2},   # C2H2
            18: {"H": 2, "O": 1}}   # H2O

for delta, series_comp in _SERIES.items():
    peak_mzs_sorted = sorted(scored.keys())
    for start_mz in peak_mzs_sorted:
        chain = []
        mz = start_mz
        while mz in scored:
            chain.append(mz)
            mz += delta
        if len(chain) < 3:
            continue
        # Verify that formula diffs between consecutive peaks equal series_comp
        consistent = True
        for i in range(len(chain) - 1):
            lo = scored[chain[i]][0]   if scored[chain[i]]   else None
            hi = scored[chain[i + 1]][0] if scored[chain[i + 1]] else None
            if not lo or not hi:
                consistent = False
                break
            diff = {el: hi["_composition"].get(el, 0) - lo["_composition"].get(el, 0)
                    for el in set(hi["_composition"]) | set(lo["_composition"])}
            diff = {el: v for el, v in diff.items() if v != 0}
            if diff != series_comp:
                consistent = False
                break
        if consistent:
            series_name = "CH2" if delta == 14 else ("C2H2" if delta == 26 else "H2O")
            for mz_s in chain:
                for cand in scored[mz_s]:
                    cand["confidence"] = min(1.0, cand.get("confidence", 0.5) + 0.15)
                    tags = cand.get("evidence_tags", [])
                    if f"SERIES({series_name})" not in tags:
                        tags.append(f"SERIES({series_name})")
                    cand["evidence_tags"] = tags
```

**Also needed:** A `tests/test_fragmentation_rules.py` file — no tests currently exist for
`apply_mclafferty()`, `enumerate_homolytic_cleavages()`, `apply_alpha_cleavage()`,
`apply_retro_diels_alder()`, etc. This is a testing gap independent of E1.

---

## 6. Complete Pipeline Schema

```
INPUT  (.msp / .mspec / .sdf / .jdx / .csv)
  └─ input_reader.py  auto-detect format → standard record schema
                      ✅ 27 tests, all formats working

STAGE 0 — ENRICHMENT  (--fetch-structures / --merge-structures)
  ├─ structure_fetcher.py  query PubChem by CASNO → NAME → FORMULA
  │   fetches: 2D MOL block + SMILES + InChIKey + CID + ExactMW  ✅
  │   validates formula against PubChem MonoisotopicMass  ✅
  └─ mol_merger.py  copy MOL blocks from second SDF by name match  ✅

STAGE 1 — SPECTRAL LIBRARY LOOKUP  (--nist-lookup)
  └─ nist_lookup.py  query NIST WebBook by InChIKey  ✅
      if hit → assign formulas directly (confidence=0.99, evidence=NIST_REF)
             → skip Stages 2-6 for matched peaks
      sdbs_lookup.py fallback if NIST misses  ✅

STAGE 2 — PARENT SETUP  (per compound)
  ├─ parse_formula() → composition dict
  ├─ exact_mass() → neutral monoisotopic mass
  ├─ ion_mass() → M+• ion m/z
  ├─ calculate_dbe() → parent DBE
  ├─ parse_mol_block_full() → heavy-atom adjacency graph (no explicit H)
  ├─ _classify_compound() → compound class for template priors  ✅
  ├─ CLASS_TEMPLATES lookup  ✅
  └─ E6: molecular ion confirmation + peaks-above warning  ✅

STAGE 3 — STRUCTURAL FRAGMENT GENERATION  (if MOL block, --fragmentation-rules)
  ├─ enumerate_homolytic_cleavages()  ✅ with implicit H
  ├─ apply_alpha_cleavage()           ✅ with implicit H
  ├─ apply_inductive_cleavage()       ✅ with implicit H
  ├─ apply_mclafferty()               ✅ with implicit H + double-bond correction
  │                                      (fixed 2026-04-17, commit 2f08e9e)
  ├─ apply_retro_diels_alder()        ✅ 6-membered ring + C=C → two even-e− fragments
  ├─ get_secondary_fragments()        ✅ depth-1 recursive from primary fragments
  └─ → structural_whitelist {formula → mechanism}  ✅ formulas now include correct H

STAGE 4 — FORMULA ENUMERATION  (per peak, after intensity pre-filter)
  ├─ Intensity pre-filter: drop peaks < 2% base peak  ✅
  └─ find_fragment_candidates()
      ├─ branch-and-bound over element counts (atom conservation)
      ├─ mass window: nominal_mz ± tolerance + mₑ correction
      ├─ DBE validity: ≥ 0, multiple of 0.5
      └─ MDD deviation stored per candidate

STAGE 5A — CHEMICAL VALIDITY FILTERS  (per candidate)
  ├─ F1  Nitrogen rule (radical-cation aware)  ✅
  ├─ F2  H-deficiency check  DBE/C ≤ 1.0  ✅
  ├─ F3  Lewis & Senior rules (Rule 1 skipped for radicals)  ✅
  ├─ F4  Isotope pattern score ±30 pp tolerance  ✅
  ├─ F5  SMILES ring-count upper bound  ✅
  ├─ F6  RDKit element validation (optional --rdkit)  ✅
  ├─ Cl/Br M+2 hard constraint  ✅
  ├─ Plausible neutral validation  ✅
  └─ 7 Golden Rules element ratios (Kind & Fiehn 2007)  ✅

STAGE 5B — FRAGMENTATION RULE ANNOTATION  (--fragmentation-rules)
  ├─ Tier 1: neutral loss from M+• — 36 known losses  ✅
  ├─ Tier 2: match structural whitelist from Stage 3  ✅ (working since H fix)
  └─ → fragmentation_rule, rule_score per candidate
      --strict-structure: sets filter_passed=False if no rule matched  ✅

STAGE 6 — CONFIDENCE SCORING  (--confidence)
  ├─ Pass 1 per candidate:
  │   A  M+1 score  pred vs I(mz+1)/I(mz)  (disabled below 50% parent)  ✅
  │   A  M+2 score  (Cl/Br/S/Si compounds only)  ✅
  │   B  Fragmentation score  (0.0 if rule matched, 1.0 if not)  ✅
  │   D  DBE penalty  −0.25 if frag_DBE > parent_DBE + 1  ✅
  │   E  Stable-ion bonus  +0.35 if in stable_ions.py table  ✅
  │   F  Even/odd electron: mass-range-dependent weights  ✅
  │   Mass accuracy  1 − |Δm| / tol  ✅
  │   Filter pass  1.0 ok / 0.3 fail  ✅
  ├─ Pass 2: neutral-loss inter-peak cross-check  ✅
  ├─ Pass 3: complementary-ion pairs  ✅
  └─ Pass 4: Kendrick homologous series  ❌ NOT YET IMPLEMENTED

STAGE 7 — RANKING & SELECTION
  ├─ without --confidence: MDD ASC, |Δm| ASC
  ├─ with --confidence: confidence DESC
  ├─ --best-only: top candidate per peak
  └─ --confidence-threshold: drop peak if confidence < threshold

STAGE 8 — OUTPUT
  ├─ Console / text (--output)
  ├─ SDF  <input>-EXACT.sdf  (--output-sdf)
  └─ MSP  <input>-EXACT.msp  (--output-msp)
```

---

## 7. All Strategies — Master Table

| # | Strategy | Status | Impact | Phase |
|---|----------|--------|--------|-------|
| A1 | Implicit H fix in fragmentation_rules.py | ✅ Done | ★★★★★ | 2 |
| A1b | McLafferty implicit-H + double-bond correction | ✅ Done 2026-04-17 | ★★★★★ | 2 |
| A2 | Whitelist as hard gate (`--strict-structure`) | ✅ Done | ★★★★★ | 2 |
| A3 | M+1 guard: disable below 50% parent mass | ✅ Done | ★★★☆☆ | 2 |
| A4 | Cl/Br M+2 as hard `filter_passed=False` | ✅ Done | ★★★★☆ | 2 |
| E4 | Intensity pre-filter: drop <2% base peak | ✅ Done | ★★★☆☆ | 2 |
| E2 | Plausible neutral validation (element budget) | ✅ Done | ★★★☆☆ | 2 |
| B1 | Extended PubChem: SMILES, InChIKey, CID, MW | ✅ Done | ★★★★☆ | 3 |
| B2 | Formula validation vs PubChem exact MW | ✅ Done | ★★★☆☆ | 3 |
| C4 | `--reference-sdf` internal library flag | ✅ Done | ★★★★★ | 3 |
| C1 | NIST WebBook lookup by InChIKey | ✅ Done | ★★★★★ | 4 |
| C2 | SDBS lookup as NIST fallback | ✅ Done | ★★★☆☆ | 4 |
| D1 | Secondary fragmentation (depth-1 recursive) | ✅ Done | ★★★★☆ | 5 |
| D2 | Retro-Diels-Alder rule | ✅ Done | ★★★☆☆ | 5 |
| D3 | Compound class detection + template fragments | ✅ Done | ★★★★☆ | 5 |
| E3 | 7 Golden Rules element ratio filter | ✅ Done | ★★☆☆☆ | 5 |
| E5 | Even/odd preference by mass range | ✅ Done | ★★☆☆☆ | 5 |
| E6 | Molecular ion confirmation + peaks-above warning | ✅ Done | ★★★☆☆ | 5 |
| F5 | Adduct ion detection ([M+H]+) | ✅ Done | ★★☆☆☆ | 5 |
| **E1** | **Kendrick mass series detection** | ❌ **TODO** | ★★★☆☆ | 5 |
| — | `tests/test_fragmentation_rules.py` | ❌ **TODO** | ★★★★☆ | — |
| C3 | MoNA local database (matchms, ~500k spectra) | 🔵 Optional/future | ★★★★☆ | 5+ |

---

## 8. Next Session Brief (Copy-Paste Ready)

```
Project: D:\tmp\ei-fragment-calculator
Python:  C:\Python\Python311\python.exe
Tests:   run_tests.bat → must stay at 169 passed after every change
Last commit: 2f08e9e  "fix: McLafferty H-detection for PubChem 2D SDF (no explicit H)"
Version: 1.8.0

State summary:
  All Phase 2–5 items implemented and confirmed in code EXCEPT:
    (a) E1 — Kendrick mass series detection (confidence.py Pass 4)
    (b) tests/test_fragmentation_rules.py does not exist

Accuracy: compare_accuracy.py on Test2.MSPEC vs ChemVista SDF:
  26/27 matched peaks correct (96.3%), 1 wrong (CV artifact), 56/83 no CV ref

TASK 1 — Write tests/test_fragmentation_rules.py
  Test these functions (they have zero test coverage):
    apply_mclafferty()        — use pentan-2-one mol block WITHOUT explicit H
                                (PubChem style: only C/O heavy atoms in atom table)
                                expect: 1 hit, enol=C3H6O, neutral=C2H4
    enumerate_homolytic_cleavages() — use a simple C-C single bond mol block
                                      expect: correct fragment formulas with H
    apply_alpha_cleavage()    — use acetaldehyde (CH3-CHO), expect [CHO]+ fragment
    apply_retro_diels_alder() — use cyclohexene mol block, expect 1 RDA pathway
    get_structure_fragments() — integration test, count > 0 frags for a real mol block

  Example PubChem-style mol blocks for tests are in:
    D:\tmp\ei-fragment-calculator\test_mclafferty_fix.py  (pentan-2-one PENTAN2ONE_MOL)

TASK 2 — Implement E1 Kendrick mass series detection (confidence.py)
  See §5 of PROJECT_REFERENCE.md for the full implementation code block.
  Add as Pass 4 after the existing complementary-ion Pass 3.
  Deltas to check: 14 (CH2), 26 (C2H2), 18 (H2O).
  Minimum chain length: 3 consecutive peaks.
  Confidence boost: +0.15 per member, evidence tag SERIES(CH2) etc.
  After implementing: add 2-3 tests to test_confidence.py.

TASK 3 — Run full 169-test suite (must still pass)
  C:\Python\Python311\python.exe -m pytest D:\tmp\ei-fragment-calculator\tests -x -q

TASK 4 — Git commit + tag
  git add tests/test_fragmentation_rules.py
  git add ei_fragment_calculator/confidence.py
  Write commit msg to file, run: git commit -F commit_msg.txt
  Then: git tag v1.8.1

TASK 5 — Re-run compare_accuracy.py and record result in PROJECT_REFERENCE.md §10
  C:\Python\Python311\python.exe D:\tmp\ei-fragment-calculator\compare_accuracy.py

DO NOT re-implement anything already done. Read the code first.
All Phase 2 items (implicit H, strict-structure, M+1 guard, Cl/Br, neutral validation,
  intensity pre-filter) are CONFIRMED DONE in the codebase.
All Phase 3 items (PubChem enrichment, --reference-sdf) are CONFIRMED DONE.
All Phase 4 items (nist_lookup.py, sdbs_lookup.py, --nist-lookup) are CONFIRMED DONE.
All Phase 5 items EXCEPT E1 Kendrick are CONFIRMED DONE.
```

---

## 9. Key Commands

```powershell
# Run full test suite (must report 169 passed)
D:\tmp\ei-fragment-calculator\run_tests.bat

# Run compare_accuracy (needs D:\Test\Test2.MSPEC + ChemVista SDF)
C:\Python\Python311\python.exe D:\tmp\ei-fragment-calculator\compare_accuracy.py

# Run CLI on example MSP (no internet needed)
C:\Python\Python311\python.exe -m ei_fragment_calculator.cli ^
  D:\tmp\ei-fragment-calculator\examples\three_compounds.msp ^
  --best-only --confidence --fragmentation-rules

# Run CLI on real test data (requires PubChem internet for --fetch-structures)
C:\Python\Python311\python.exe -m ei_fragment_calculator.cli ^
  D:\Test\Test2.MSPEC ^
  --best-only --confidence --fragmentation-rules --strict-structure ^
  --output D:\Test\Test2_results.txt

# Run CLI with NIST lookup (requires internet + InChIKey in input)
C:\Python\Python311\python.exe -m ei_fragment_calculator.cli ^
  D:\Test\Test2.MSPEC --best-only --confidence --nist-lookup

# Git commit (write message to file first, then use -F)
cd /d D:\tmp\ei-fragment-calculator
git add <files>
git commit -F commit_msg.txt
git tag v1.8.1
```

---

## 10. Accuracy Metrics Log

| Date | Version | Test dataset | Correct | Total | Wrong | CV-ref missing | Notes |
|------|---------|-------------|---------|-------|-------|----------------|-------|
| 2026-04-17 | 1.8.0 | Test2.MSPEC vs ChemVista | 26 | 83 | 1 | 56 | 96.3% on matched peaks; 1 wrong is CV data artifact (49.51 Da for nominal 50) |

*The 31.3% overall figure is misleading — 67% of peaks simply have no ChemVista reference entry.
For peaks that DO have a reference: 26/27 = 96.3% correct.*

*Re-run after each change and append a row.*

---

*End of PROJECT_REFERENCE.md. Updated 2026-04-17 after confirming actual code state.*
