# ei-fragment-calculator vs UnitMass v1.2 vs UnitMass v3.0 — Feature Comparison

Three-way comparison of the same algorithm family across three codebases.

| | v1.2 | v3.0 | ei-fragment-calculator |
|---|---|---|---|
| **Author** | Luca Godina | Joerg Riener | Joerg Riener |
| **File / package** | `UnitMass_to_ExactMass_v1.2.txt` | `UnitMass_to_ExactMass_v3.py` | `joriener/ei-fragment-calculator` |
| **Version examined** | 1.2 | 3.0 | 1.9.2 (head `2a36fb9`, 2026-04-18) |
| **Platform** | IronPython 2.7.5 / .NET | IronPython 2.7.5 / .NET | CPython ≥ 3.10, pure stdlib |
| **Host** | MassHunter Library Editor | MassHunter Library Editor | Standalone — CLI + tkinter GUI |
| **UI toolkit** | WinForms | WinForms | tkinter / ttk |
| **Size** | 540 lines, 29 KB | 2,625 lines, 120 KB | 22,247 lines across 30 modules |
| **Structure** | Everything inside `_Run()` | Everything inside `_Run()`, 14 named sections | Installable package, 30 modules, 10 test modules |
| **Third-party deps** | None | None (RDKit .NET optional) | None required; matplotlib / rdkit-pypi optional extras |

---

## Core mass and formula machinery

| # | Feature | v1.2 | v3.0 | ei-fragment-calculator | Verdict |
|---|---|---|---|---|---|
| 1 | **Elements supported** | 12 (C H D N O F Si P S Cl Br I) | 30 (adds Na Mg Al K Ca Cr Mn Fe Co Ni Cu Zn As Se Sn Ti V Pb B) | 30 — same set, minus D, plus full isotope table | v3.0 added metals; ei-fragment-calculator keeps the same coverage but makes it data-driven |
| 2 | **Element data source** | Hardcoded `ELEM` dict | Hardcoded `ELEM` dict | `data/elements.csv` — 89 isotope rows, loaded at import | ei-fragment-calculator wins: add an element or update an abundance without touching Python |
| 3 | **Isotope data** | None | M+1/M+2 per-atom contributions, hardcoded | Full `(exact_mass, abundance)` list per element, all isotopes | ei-fragment-calculator enables real pattern simulation, not a two-peak approximation |
| 4 | **Electron mass** | 0.00054857990924 Da | 0.00054857990907 Da (CODATA 2018) | 0.00054857990907 Da (CODATA 2018) | v3.0 and ei-fragment-calculator agree; the v1.2 difference is 0.17 µDa, negligible |
| 5 | **Electron-mode control** | Single checkbox (subtract yes/no) | ComboBox: remove (EI+) / add (EI−) / none | `--electron` / GUI, same three modes | v3.0 introduced EI− support; ei-fragment-calculator retains it |
| 6 | **DBE formula** | Hardcoded `(2C+2+N+P−H−D−F−Cl−Br−I)/2` | General `1 + Σ(valence−2)×count / 2` via `VALENCE` | Same general formula, valences from CSV | v1.2 would give wrong DBE for metals; the later two are correct for all 30 elements |
| 7 | **Deuterium (D)** | Supported as a distinct element | Supported as a distinct element | **Not** a separate element in `elements.csv` | Regression if you work with labelled standards — v1.2/v3.0 handle D, ei-fragment-calculator does not |

---

## Candidate enumeration

| # | Feature | v1.2 | v3.0 | ei-fragment-calculator | Verdict |
|---|---|---|---|---|---|
| 8 | **Algorithm** | Branch-and-bound DFS, sorted by −nominal mass | Identical to v1.2 | Branch-and-bound DFS with **suffix-mass bound**, heaviest-first ordering | ei-fragment-calculator is the only one that prunes *upward* as well as downward — see §"Optimization options" below |
| 9 | **Count storage** | Dict keyed by element symbol | Dict keyed by element symbol | **Flat list** indexed by position | ei-fragment-calculator removes the per-node dict read/write that dominated the hot path |
| 10 | **Element ordering** | By descending nominal mass | Same | By descending **exact** mass, computed per call | Marginal, but makes the mass constraint tight at the earliest recursion levels |
| 11 | **Tolerance model** | Integer nominal mass | Integer nominal mass | `--tolerance` Da **or** `--ppm`, plus a high-resolution mode (`--hr`, `--auto-hr`, `--hr-ppm`) | ei-fragment-calculator is the only one usable on accurate-mass data |
| 12 | **Mass-defect ranking** | Not present | Not present | `_mdd_deviation` — per-Da mass-defect deviation from the parent | New signal in ei-fragment-calculator; favours candidates whose defect tracks the parent |
| 13 | **Second enumerator** | — | — | `formula_calculator.find_formulas_at_mass()` — a weaker depth-3 atom-removal search | **Defect.** Two different algorithms now coexist; see the warning below |
| 14 | **Parallelism** | None | None | `--workers` (process pool over compounds) | ei-fragment-calculator scales across cores; the IronPython hosts cannot |

> ### Warning — the two enumerators disagree
>
> `calculator.find_fragment_candidates()` is the real branch-and-bound
> enumerator and is what the CLI (and therefore the GUI, which shells out to
> `cli.main`) uses. But `formula_calculator.find_formulas_at_mass()` is a
> *different* algorithm: `_generate_fragment_compositions(max_counts,
> max_depth=3)` only removes up to three atoms from the parent composition, so
> it cannot reach most sub-formulas of a given nominal mass. `spectrum_analyzer.py`
> calls that one.
>
> This is exactly the failure mode Option 6 of the optimization paper warned
> about ("two call sites, one algorithm"), except worse — here the two paths do
> not merely risk drifting, they already implement different searches. The
> Spectrum Analyzer tab will therefore under-report candidates relative to the
> CLI on the same input.

---

## Scoring

| # | Feature | v1.2 | v3.0 | ei-fragment-calculator | Verdict |
|---|---|---|---|---|---|
| 15 | **Model** | Single additive score | Same additive score, plus new bonuses | **Weighted, normalised confidence model** (`confidence.score_compound`) with selectable weight sets | ei-fragment-calculator is a different class of scorer — comparable across compounds, not just within one peak |
| 16 | **EE/OE preference** | EE +200, OE +50 | Identical | `_score_even_odd()`, weighted term | Same chemistry, now a weighted component rather than a raw constant |
| 17 | **Neutral-loss recognition** | 36 losses, +15…+30 | Identical table | `neutral_losses.py` + `_formula_difference_matches()` / `_formula_sum_matches()` | ei-fragment-calculator checks losses *between observed peaks*, not only against the parent |
| 18 | **Heteroatom retention** | +8 per shared N/O/S/Si | Identical | Folded into the weighted model | Equivalent intent |
| 19 | **Carbon skeleton bonus** | +10 per C | Identical | Folded into the weighted model | Equivalent intent |
| 20 | **H-saturation bonus** | H/C ≥1.5 +20 / ≥1.0 +12 / ≥0.5 +5 | Identical | Folded into the weighted model | Equivalent intent |
| 21 | **Zero-H penalty** | C>2 and H=0: −150 | Identical | `apply_impossible_homoatomic()` rejects outright | ei-fragment-calculator promotes it from a penalty to a hard filter |
| 22 | **Low H/C penalty** | C>3 and H/C<0.3: −50 | Identical | Covered by the Golden Rules filter | ei-fragment-calculator uses the published heuristic instead of a local one |
| 23 | **Structural rule match** | Not present | +200 when a formula matches any of 4 rules | `fragmentation_rules.annotate_candidate()`, weighted | v3.0 introduced it; ei-fragment-calculator integrates it into the confidence model |
| 24 | **Stable-ion bonus** | Not present | +100 for 40+ known EI cations | `stable_ions.py`, 14 KB | Carried forward and expanded |
| 25 | **Isotope scoring** | Not present | M+1/M+2 deviation, used as a tiebreak | `_score_isotope()` + `_predict_m2_fraction()`, weighted term | ei-fragment-calculator predicts M+2 explicitly — matters for Cl/Br |
| 26 | **Peak-intensity weighting** | Not present | Not present | `_intensity_weight()` — strong peaks count more | New; stops a trace peak's assignment from carrying the same weight as the base peak |
| 27 | **Flat-spectrum guard** | Not present | Not present | `intensity_map_is_flat()` | New; detects a spectrum with no usable intensity contrast before trusting intensity-weighted terms |
| 28 | **Parent-DBE consistency** | Not present | Not present | `_dbe_penalty(candidate, parent_dbe)` | New |
| 29 | **Selection tiers** | 1 tier — highest score | 3 tiers — filter-pass → score → isotope deviation | `rank_candidates()` with a composite sort key | Equivalent in spirit; ei-fragment-calculator's is explicit and testable |
| 30 | **Confidence threshold** | Not present | Not present | `--confidence`, `--confidence-threshold` | ei-fragment-calculator can decline to assign rather than always naming a winner |

---

## Filters

| # | Filter | v1.2 | v3.0 | ei-fragment-calculator | Verdict |
|---|---|---|---|---|---|
| 31 | **Nitrogen rule** | ✗ | ✓ | ✓ `apply_nitrogen_rule` | Carried forward |
| 32 | **HD-check (DBE/C)** | ✗ | ✓ | ✓ `apply_hd_check`, configurable `--max-ring-ratio` | Carried forward, now tunable |
| 33 | **Lewis-Senior** | ✗ | ✓ | ✓ `apply_lewis_senior` | Carried forward |
| 34 | **Isotope M+1/M+2** | ✗ | ✓ | ✓ `score_isotope_match`, `--isotope-tolerance` | Carried forward, now tunable |
| 35 | **SMILES ring count** | ✗ | ✓ | ✓ `apply_smiles_constraints` | Carried forward |
| 36 | **RDKit bond-break** | ✗ | ✓ (optional, .NET DLL) | ✓ `apply_rdkit_validation`, `--rdkit` (optional `rdkit-pypi`) | Same check, far easier to install — `pip install` vs. dropping a DLL into `System32` |
| 37 | **Neutral-loss validation** | ✗ | ✗ | ✓ `apply_neutral_validation` | New |
| 38 | **Cl/Br M+2 check** | ✗ | ✗ | ✓ `apply_clbr_m2_check` | New — the single most diagnostic isotope test for halogens |
| 39 | **Impossible homoatomic** | ✗ | ✗ | ✓ `apply_impossible_homoatomic` | New |
| 40 | **Seven Golden Rules** | ✗ | ✗ | ✓ `apply_golden_rules` (Kind & Fiehn) | New — published heuristic set |
| 41 | **Filter count** | 0 | 6 | 10 | Steady accumulation |
| 42 | **Filter configuration** | — | 6 checkboxes, persisted | `FilterConfig` dataclass + 7 `--no-*` CLI switches | ei-fragment-calculator is scriptable; v3.0 is GUI-only |

---

## Structural fragmentation

| # | Rule | v1.2 | v3.0 | ei-fragment-calculator | Verdict |
|---|---|---|---|---|---|
| 43 | **V2000 MOL parser** | Field read but ignored | Full parser: atoms, bonds, adjacency, ring count | `mol_parser.py` + `mol_merger.py` | Carried forward and split out |
| 44 | **Homolytic cleavage** | ✗ | ✓ | ✓ `enumerate_homolytic_cleavages` | Carried forward |
| 45 | **Alpha cleavage** | ✗ | ✓ | ✓ `apply_alpha_cleavage` | Carried forward |
| 46 | **McLafferty** | ✗ | ✓ | ✓ `apply_mclafferty` | Carried forward |
| 47 | **Retro-Diels-Alder** | ✗ | ✓ | ✓ `apply_retro_diels_alder` | Carried forward |
| 48 | **Inductive cleavage** | ✗ | ✗ | ✓ `apply_inductive_cleavage` | New pathway |
| 49 | **Secondary fragments** | ✗ | ✗ | ✓ `get_secondary_fragments`, depth-limited | New — v3.0 only ever modelled one bond-breaking generation |
| 50 | **Bond thermochemistry** | ✗ | ✗ | ✓ `bond_thermochemistry.py`, `bond_rates` weighting | New — cleavages ranked by bond dissociation energy rather than treated as equally likely |
| 51 | **Implicit hydrogens** | ✗ | ✗ | ✓ `_add_implicit_h` | New — corrects compositions from MOL blocks that omit H |

---

## Input / output

| # | Feature | v1.2 | v3.0 | ei-fragment-calculator | Verdict |
|---|---|---|---|---|---|
| 52 | **Input** | MassHunter library XML | MassHunter library XML | SDF, MSP, CEF, NIST, plus `input_reader.py` field-name candidates | ei-fragment-calculator is not tied to one vendor format |
| 53 | **Output: MassHunter XML** | ✓ only format | ✓ default on | ✗ | **Regression for the MassHunter workflow** — the whole point of v1.2/v3.0 was writing back into an open library |
| 54 | **Output: NIST MSP** | ✗ | ✓ (checkbox, off) | ✓ `--output-msp` | Carried forward |
| 55 | **Output: MDL SDF** | ✗ | ✓ (checkbox, off) | ✓ `--output-sdf`, `sdf_writer.py` | Carried forward and expanded |
| 56 | **Base64 double arrays** | ✓ | ✓ | Not applicable | ei-fragment-calculator has no `.NET` binary spectrum encoding, so the whole class of codec bug disappears |
| 57 | **Structure fetching** | ✗ | ✗ | ✓ `--fetch-structures`, `structure_fetcher.py` | New |
| 58 | **NIST / SDBS lookup** | ✗ | ✗ | ✓ `--nist-lookup`, `nist_lookup.py`, `sdbs_lookup.py` | New |
| 59 | **CEF pipeline** | ✗ | ✗ | ✓ parser, matcher, DB, visualizer, viewer tab | New — a whole Agilent CEF workflow absent from both scripts |
| 60 | **Reference SDF merge** | ✗ | ✗ | ✓ `--reference-sdf`, `--merge-structures` | New |

---

## Engineering

| # | Aspect | v1.2 | v3.0 | ei-fragment-calculator | Verdict |
|---|---|---|---|---|---|
| 61 | **Code organisation** | One `_Run()` | One `_Run()`, 14 section banners | 30 modules, importable package | ei-fragment-calculator removes the IronPython closure-limit risk entirely (see Option 4) |
| 62 | **Automated tests** | None | None | 10 `pytest` modules under `tests/` | Only ei-fragment-calculator can be regression-tested |
| 63 | **CLI** | None | None | 30 options, three console entry points | ei-fragment-calculator is automatable |
| 64 | **Config persistence** | Last directory only | Last dir, min peaks, electron mode, 6 filter flags, 3 export flags | CLI flags + GUI state + SQLite DB | Comparable |
| 65 | **Packaging** | Copy a `.py` into the Actions folder | Same | `pyproject.toml`, `pip install`, PyInstaller spec, `install.bat` | ei-fragment-calculator ships as a real application |
| 66 | **Licence** | Internal | Internal | MIT | ei-fragment-calculator is publishable |
| 67 | **Documentation** | Header comment | Header comment + separate 27 KB doc | 25 markdown files, algorithm PDF/PPTX, 16 slides | ei-fragment-calculator is heavily documented, though much of it is release-note style |

---

## Status of the six optimization options

Checked against `UnitMass_to_ExactMass_v3_Optimization_Options.md`. Several are
already resolved in ei-fragment-calculator, and two no longer apply.

| Option | v3.0 | ei-fragment-calculator | Evidence |
|---|---|---|---|
| **1 — Rewrite the enumeration inner loop** | Not applied | **Applied** | `calculator._enumerate_pruned()` uses flat count/mass lists **and** a `max_tail` suffix-mass bound to compute `lo`, plus heaviest-first element ordering. This is the measured 7.2× change from the paper, implemented |
| **2 — Memoise across compounds sharing a parent formula** | Not applied | **Not applied** | No `functools.lru_cache`, `@cache` or hand-rolled cache anywhere in the package. Still the open item, and now cheaper to add: `find_fragment_candidates` is a clean module-level function |
| **3 — Pre-filter before full scoring** | Not applied | **Largely applied** | Cheap disqualifiers (mass window, `is_valid_dbe`) run inside the enumeration loop; `run_all_filters` and `confidence.score_compound` run after, in separate passes |
| **4 — Move functions out of `_Run()`** | Not applied | **Not applicable — resolved structurally** | The DLR `MutableTuple` closure limit is an IronPython artefact. A 30-module CPython package cannot hit it |
| **5 — Fix the base64 codecs** | Not applied | **Not applicable** | No `.NET`, no `Double.Parse`, no base64 double arrays. The only `base64` use is embedding a PNG in an HTML export. The locale dependency is gone by construction |
| **6 — Two call sites, one algorithm** | Not applied | **Regressed** | Two *different* enumerators now exist — `calculator.find_fragment_candidates` (CLI/GUI) and `formula_calculator.find_formulas_at_mass` (Spectrum Analyzer). See the warning above |

**Net:** of the four options that apply to a CPython port, one is done (1), one
is mostly done (3), one is outstanding (2), and one has become a live defect
rather than a latent risk (6). Options 4 and 5 were IronPython-specific and are
moot.

---

## Summary

- **v1.2 → v3.0** was a 5× expansion of the *chemistry*: 12 → 30 elements, 0 → 6
  filters, 0 → 4 structural rules, 1 → 3 output formats. The enumeration
  algorithm and the additive scoring model were untouched.
- **v3.0 → ei-fragment-calculator** is a change of *kind*: the same chemistry
  leaves the MassHunter host and becomes a standalone, tested, packaged
  application with a CLI, a weighted confidence model, 10 filters, 8 structural
  rules, accurate-mass support, multiprocessing, and a CEF workflow.
- **What was lost:** MassHunter XML output (#53) and deuterium as a distinct
  element (#7). If the goal is still writing exact masses back into a
  MassHunter library, the repo does not currently do that job —
  `ei_fragment_calculator_v3.1.py` (the MassHunter-hosted successor to v3.0,
  in the Scripts folder) is the tool that does.
- **What needs attention:** the duplicate enumerator (#13) is a correctness
  issue, not a style one.
