# EI Fragment Calculator family — four-way comparison

All four members of the family, in chronological order of authorship.

| | v1.2 | ei-fragment-calculator | v3.0 | v3.1.1 |
|---|---|---|---|---|
| **Author** | Luca Godina | Joerg Riener | Joerg Riener | Joerg Riener |
| **Written** | before April 2026 | **March–April 2026** — 64 commits, 50 of them in April; v1.9.2 released 18 April 2026 | April 2026 (file dated 24 April) | September 2026 |
| **File / package** | `UnitMass_to_ExactMass_v1.2.txt` | `joriener/ei-fragment-calculator` | `UnitMass_to_ExactMass_v3.py` | `ei_fragment_calculator_v3.1.py` |
| **Version examined** | 1.2 | 1.9.2 (head `2a36fb9`) | 3.0 | 3.1.1 |
| **Runtime** | IronPython 2.7.5 / .NET | CPython ≥ 3.10 | IronPython 2.7.5 / .NET | IronPython 2.7.5 / .NET |
| **Host** | MassHunter Library Editor | Standalone | MassHunter Library Editor | MassHunter Library Editor |
| **UI toolkit** | WinForms | tkinter / ttk | WinForms | WinForms |
| **Size** | 540 lines / 29 KB | 22,247 lines / 30 modules | 2,625 lines / 120 KB | 3,445 lines / 143 KB |
| **Status** | superseded | **active, parallel line** | superseded | **current MassHunter tool** |
| **Location** | an internal archive folder | this repository | an internal archive folder | `masshunter/` |

> **Two parallel lines, not one chain.** ei-fragment-calculator and v3.0 were
> written in the *same month*, April 2026 — the package's last release (18
> April) actually predates v3.0's file date (24 April). They are siblings that
> share chemistry, not successive versions. v3.1.1 renames the MassHunter line
> to match the package, but the two remain separate tools with different
> hosts.

---

## 1. Core mass and formula machinery

| # | Feature | v1.2 | ei-fragment-calculator | v3.0 | v3.1.1 |
|---|---|---|---|---|---|
| 1 | Elements supported | 12 | 30 (no D) | 30 | 30 |
| 2 | Element data source | hardcoded dict | **`data/elements.csv`** | hardcoded dict | hardcoded dict |
| 3 | Isotope data | none | **all isotopes, 89 rows** | M+1/M+2 per atom | M+1/M+2 per atom |
| 4 | Electron mass | 0.00054857990924 | 0.00054857990907 | 0.00054857990907 | 0.00054857990907 |
| 5 | Electron-mode control | checkbox | `--electron` | ComboBox, 3 modes | ComboBox, 3 modes |
| 6 | DBE formula | hardcoded, 12 elements | general, from CSV valences | general, `VALENCE` dict | general, `VALENCE` dict |
| 7 | Deuterium as an element | **yes** | no | **yes** | **yes** |

## 2. Candidate enumeration

| # | Feature | v1.2 | ei-fragment-calculator | v3.0 | v3.1.1 |
|---|---|---|---|---|---|
| 8 | Algorithm | B&B DFS, downward prune only | B&B DFS + **suffix-mass bound** | same as v1.2 | B&B DFS + **suffix-mass bound** |
| 9 | Count storage | dict by symbol | **flat list** | dict by symbol | **flat list** |
| 10 | Element ordering | desc. nominal mass | desc. exact mass | desc. nominal mass | desc. nominal mass |
| 11 | Per-compound prep | rebuilt per call | per call | rebuilt per call | **built once, reused** |
| 12 | Memoisation | none | none | none | **cache on (formula, mass)** |
| 13 | Tolerance model | integer nominal | **Da or ppm, plus `--hr`** | integer nominal | integer nominal |
| 14 | Mass-defect ranking | no | **yes** (`_mdd_deviation`) | no | no |
| 15 | Parallelism | none | **`--workers`** | none | none |
| 16 | Duplicate enumerator | no | **yes — a defect, see §7** | no | no |

## 3. Scoring

| # | Feature | v1.2 | ei-fragment-calculator | v3.0 | v3.1.1 |
|---|---|---|---|---|---|
| 17 | Model | additive score | **weighted, normalised confidence** | additive score | additive score |
| 18 | EE/OE preference | +200 / +50 | weighted term | +200 / +50 | +200 / +50 |
| 19 | Neutral-loss recognition | 36 losses | **between observed peaks** | 36 losses | 36 losses |
| 20 | Structural rule match | no | weighted term | **+200** | +200 |
| 21 | Stable-ion bonus | no | `stable_ions.py` | **+100, 40+ ions** | +100, 40+ ions |
| 22 | Isotope scoring | no | **predicts M+2 explicitly** | M+1/M+2 tiebreak | M+1/M+2 tiebreak |
| 23 | Peak-intensity weighting | no | **yes** | no | no |
| 24 | Parent-DBE consistency | no | **yes** | no | no |
| 25 | Selection tiers | 1 | composite sort key | 3 | 3 |
| 26 | Confidence threshold | no | **`--confidence-threshold`** | no | no |
| 27 | DBE recomputed per scorer | n/a | n/a | twice | **once, shared** |

## 4. Filters

| # | Filter | v1.2 | ei-fragment-calculator | v3.0 | v3.1.1 |
|---|---|---|---|---|---|
| 28 | Nitrogen rule | ✗ | ✓ | ✓ | ✓ |
| 29 | HD-check | ✗ | ✓ (tunable) | ✓ | ✓ |
| 30 | Lewis-Senior | ✗ | ✓ | ✓ | ✓ |
| 31 | Isotope M+1/M+2 | ✗ | ✓ (tunable) | ✓ | ✓ |
| 32 | SMILES ring count | ✗ | ✓ | ✓ | ✓ |
| 33 | RDKit bond-break | ✗ | ✓ (`pip install`) | ✓ (.NET DLL) | ✓ (.NET DLL) |
| 34 | Neutral-loss validation | ✗ | **✓** | ✗ | ✗ |
| 35 | Cl/Br M+2 check | ✗ | **✓** | ✗ | ✗ |
| 36 | Impossible homoatomic | ✗ | **✓** | ✗ | ✗ |
| 37 | Seven Golden Rules | ✗ | **✓** | ✗ | ✗ |
| 38 | **Filter count** | **0** | **10** | **6** | **6** |
| 39 | Configurable from a script | ✗ | **✓ (7 CLI switches)** | ✗ (GUI only) | ✗ (GUI only) |

## 5. Structural fragmentation

| # | Rule | v1.2 | ei-fragment-calculator | v3.0 | v3.1.1 |
|---|---|---|---|---|---|
| 40 | V2000 MOL parser | field ignored | ✓ | ✓ | ✓ |
| 41 | Homolytic cleavage | ✗ | ✓ | ✓ | ✓ |
| 42 | Alpha cleavage | ✗ | ✓ | ✓ | ✓ |
| 43 | McLafferty | ✗ | ✓ | ✓ | ✓ |
| 44 | Retro-Diels-Alder | ✗ | ✓ | ✓ | ✓ |
| 45 | Inductive cleavage | ✗ | **✓** | ✗ | ✗ |
| 46 | Secondary fragments | ✗ | **✓ (depth-limited)** | ✗ | ✗ |
| 47 | Bond thermochemistry | ✗ | **✓ (BDE-weighted)** | ✗ | ✗ |
| 48 | Implicit hydrogens | ✗ | **✓** | ✗ | ✗ |
| 49 | **Rule count** | **0** | **8** | **4** | **4** |

## 6. Input / output

| # | Feature | v1.2 | ei-fragment-calculator | v3.0 | v3.1.1 |
|---|---|---|---|---|---|
| 50 | Input formats | MassHunter XML | **SDF, MSP, CEF, NIST** | MassHunter XML | MassHunter XML |
| 51 | **MassHunter XML output** | **✓** | **✗** | **✓** | **✓** |
| 52 | NIST MSP output | ✗ | ✓ | ✓ | ✓ |
| 53 | MDL SDF output | ✗ | ✓ | ✓ | ✓ |
| 54 | Locale-safe number encoding | **✗** | n/a (no .NET) | **✗** | **✓** |
| 55 | Structure fetching | ✗ | **✓** | ✗ | ✗ |
| 56 | NIST / SDBS lookup | ✗ | **✓** | ✗ | ✗ |
| 57 | CEF pipeline | ✗ | **✓** | ✗ | ✗ |

## 7. Engineering

| # | Aspect | v1.2 | ei-fragment-calculator | v3.0 | v3.1.1 |
|---|---|---|---|---|---|
| 58 | Code organisation | one `_Run()` | 30 modules | one `_Run()`, 2,538 lines | **58 module-level functions, `_Run()` 553 lines** |
| 59 | MutableTuple closure risk | present | n/a | **present** | **removed** |
| 60 | Automated tests | none | **10 pytest modules** | none | extract-and-run harness |
| 61 | CLI | ✗ | **✓ 30 options** | ✗ | ✗ |
| 62 | Packaging | copy a file | **pyproject + PyInstaller** | copy a file | copy a file |
| 63 | Licence | internal | **MIT** | internal | MIT (in repo) |
| 64 | Pipeline call sites | 2 (unshared) | **2, different algorithms** | 2 (unshared) | **1 (shared)** |
| 65 | Dialog ownership | **broken** | n/a | **broken** | **fixed** |
| 66 | Style guide conformance | partial | tkinter guide | partial | **full WinForms guide** |

---

## Which to use

| If you need to… | Use |
|---|---|
| Write exact masses back into a MassHunter library | **v3.1.1** — the only one of the four that both does this *and* is current |
| Work on accurate-mass data, or script/automate the assignment | **ei-fragment-calculator** — CLI, ppm tolerance, `--hr` mode, multiprocessing |
| Get the strictest filtering and richest fragmentation model | **ei-fragment-calculator** — 10 filters and 8 rules vs. 6 and 4 |
| Handle deuterated standards | **v3.1.1** — the package has no D as a distinct element |
| Reproduce a historical result | the matching version in an internal archive folder |

## Known defects, by version

| Version | Defect |
|---|---|
| **v1.2** | Wrong DBE for metals (12-element hardcoded formula); locale-dependent number encoding; no filters at all, so ambiguous peaks are effectively unranked |
| **v3.0** | Locale-dependent number encoding — **libraries written on a non-English-locale machine carry corrupted m/z and abundance values and must be regenerated**; Browse and four MessageBoxes unreachable (dialog ownership); preview and conversion are separate code paths that can drift; MutableTuple closure ceiling |
| **ei-fragment-calculator** | Two different enumerators coexist: `calculator.find_fragment_candidates` (branch-and-bound, used by CLI and GUI) and `formula_calculator.find_formulas_at_mass`, which only removes up to three atoms from the parent and cannot reach most sub-formulas. `spectrum_analyzer.py` calls the weak one, so the Spectrum Analyzer under-reports candidates relative to the CLI on the same input. No MassHunter XML output; no deuterium |
| **v3.1.1** | Not yet executed inside a MassHunter Library Editor session; WinForms layout visually unchecked. Nominal mass only. Option 3's aggressive pre-filter deliberately not applied (finite penalties, not floors — filtering on them would change results) |

## Performance, v3.0 → v3.1.1

CPython, sweeping every nominal mass from 0 to the parent nominal mass over 12
parent formulas and 36,506 candidate formulas:

| | v3.0 | v3.1.1 |
|---|---|---|
| Total enumeration time | 929.0 ms | **53.5 ms** |
| Speedup | — | **17.4×** |
| Worst case (Chlorpyrifos `C9H11Cl3NO3PS`, 7 elements) | 415.0 ms | 23.1 ms (17.9×) |
| Isomer cache (30 isomers × 150 peaks) | 86.3 ms | **4.6 ms (18.8×)** |
| Output difference | — | **none** |

Cost is driven by element diversity, not molecule size — every distinct element
adds a level to the search. Halogenated and heteroatom-rich compounds are the
expensive case. IronPython is 2–5× slower than CPython in absolute terms, but
the ratios hold.

## Optimization options, by version

Status of the six options from `UnitMass_to_ExactMass_v3_Optimization_Options.md`:

| Option | v3.0 | ei-fragment-calculator | v3.1.1 |
|---|---|---|---|
| 1 — enumeration inner loop | ✗ | **✓** (independently) | **✓** |
| 2 — memoise across isomers | ✗ | ✗ | **✓** |
| 3 — pre-filter before scoring | ✗ | largely ✓ | ✓ conservative only |
| 4 — de-nest `_Run()` | ✗ | n/a (proper package) | **✓** |
| 5 — base64 codecs / locale | ✗ | n/a (no .NET) | **✓** |
| 6 — one algorithm, one call site | ✗ | **regressed** | **✓** |
