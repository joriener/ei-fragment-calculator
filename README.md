# EI Fragment Exact-Mass Calculator

A pure-Python command-line tool that calculates all chemically plausible **exact monoisotopic masses** for every peak in an **EI (electron ionisation) unit-mass spectrum**, constrained by the molecular formula of the intact compound.

No third-party dependencies — only the Python standard library is required.

---

## Background

In EI mass spectrometry the molecular ion M+• is formed by removing one electron from the neutral analyte:

```
M  +  e⁻(fast)  →  M+•  +  2 e⁻
```

The instrument measures the mass-to-charge ratio of the **ion**, not the neutral molecule. For a singly charged positive ion:

```
m/z_measured  =  M_neutral  −  m_electron        (m_e = 0.000548579909 Da)
```

This tool supports three **electron-mass correction modes**:

| Mode | Formula | Use case |
|------|---------|----------|
| `remove` *(default)* | `ion_mass = neutral_mass − m_e` | Standard EI positive-ion |
| `add` | `ion_mass = neutral_mass + m_e` | Negative-ion EI |
| `none` | `ion_mass = neutral_mass` | No correction / comparison |

---

## Algorithm

For each unit-mass peak at nominal m/z **n** the script:

1. **Defines the search space** — the parent molecular formula sets the *upper bound* for every element. A fragment can never contain more atoms of element X than the intact molecule (atom conservation).

2. **Enumerates all combinations** via Cartesian product over element counts 0 … max:
   ```
   C10H12O2  →  range(11) × range(13) × range(3)  =  429 candidates
   ```

3. **Applies a mass window filter** — only candidates whose ion m/z (after electron correction) is within ±tolerance of **n** are kept.

4. **Applies a DBE filter** — candidates with DBE < 0 or non-integer/half-integer DBE are discarded:
   ```
   DBE = 1 + C + Si  −  (H + halogens)/2  +  (N + P)/2
   ```
   - Integer DBE → even-electron ion (closed-shell fragment)
   - Half-integer DBE → radical cation (odd-electron, e.g. M+•)
   - DBE < 0 → impossible → discarded

5. **Runs five optional filter algorithms** (all on by default, each individually disableable via `--no-*` flags — see below).

6. **Ranks candidates** by quality (filter pass → mass accuracy → isotope score).

---

## Five Filter Algorithms

All filters are **enabled by default**. Each can be switched off independently with a `--no-*` flag.

### 1. Nitrogen Rule  `--no-nitrogen-rule`
Odd nominal m/z ↔ odd nitrogen count for even-electron ions (closed-shell fragments); the rule is inverted for radical cations (half-integer DBE).
**Ref:** McLafferty & Turecek (1993) *Interpretation of Mass Spectra*, 4th ed. https://doi.org/10.1002/jms.1190080509

### 2. H-Deficiency Check  `--no-hd-check`
Rejects candidates where DBE / C > 0.5 (configurable via `--max-ring-ratio`). Extraordinarily hydrogen-poor formulas are chemically implausible as EI fragments.
**Ref:** Pretsch et al. (2009) *Structure Determination of Organic Compounds*, 4th ed. https://doi.org/10.1007/978-3-540-93810-1

### 3. Lewis & Senior Rules  `--no-lewis-senior`
Two graph-theory valence-sum constraints:
- **Rule 1:** sum of all valences must be even.
- **Rule 2:** sum of all valences ≥ 2 × (atom count − 1).

**Ref:** Senior J.K. (1951) *Am. J. Math.* 73(3):663–689. https://doi.org/10.2307/2372318

### 4. Isotope Pattern Score  `--no-isotope-score`
Scores each candidate by comparing its theoretical M+1 and M+2 isotope peaks against the observed spectrum. Score = Σ |theo% − obs%| in percentage points. Candidates exceeding `--isotope-tolerance` (default 30 pp) are rejected.
**Ref:** Gross J.H. (2017) *Mass Spectrometry: A Textbook*, 3rd ed. https://doi.org/10.1007/978-3-319-54398-7

### 5. SMILES Constraints  `--no-smiles-constraints`
Uses the ring count from the parent MOL block (Euler formula: rings = bonds − atoms + 1) as an upper bound on fragment DBE. A fragment cannot have more rings than the parent molecule.
**Ref:** Weininger D. (1988) *J. Chem. Inf. Comput. Sci.* 28(1):31–36. https://doi.org/10.1021/ci00057a005

---

## Candidate Ranking

After filtering, candidates are ranked by quality (best first):

| Priority | Criterion | Direction |
|----------|-----------|-----------|
| 1 | `filter_passed` | True before False |
| 2 | `\|delta_mass\|` | smaller is better |
| 3 | `isotope_score` | lower is better |

Use `--best-only` to keep only the **top-ranked candidate per peak** and automatically drop peaks where even the best candidate fails all filters.

---

## Installation

```bash
git clone https://github.com/joriener/ei-fragment-calculator.git
cd ei-fragment-calculator
pip install -e .
```

For development (includes pytest):

```bash
pip install -e ".[dev]"
```

---

## Usage

```bash
# Standard EI positive-ion mode (electron mass removed — default)
ei-fragment-calc spectra.sdf

# Negative-ion EI (electron mass added)
ei-fragment-calc spectra.sdf --electron add

# No electron-mass correction
ei-fragment-calc spectra.sdf --electron none

# Tighter tolerance
ei-fragment-calc spectra.sdf --tolerance 0.3

# Show theoretical isotope patterns
ei-fragment-calc spectra.sdf --isotope

# Save results to a text file
ei-fragment-calc spectra.sdf --output results.txt

# Suppress peaks with no candidates
ei-fragment-calc spectra.sdf --hide-empty

# Keep only the single best-ranked candidate per peak;
# peaks with no passing candidate are dropped entirely
ei-fragment-calc spectra.sdf --best-only

# Best-only with isotope patterns
ei-fragment-calc spectra.sdf --best-only --isotope

# Skip writing the SDF output
ei-fragment-calc spectra.sdf --no-save-sdf
```

### All options

| Option | Default | Description |
|--------|---------|-------------|
| `sdf_file` | — | Path to the input SDF file |
| `--electron`, `-e` | `remove` | Electron-mass correction: `remove`, `add`, or `none` |
| `--tolerance`, `-t` | `0.5` | Mass window in ±Da |
| `--isotope`, `-i` | off | Show theoretical isotope pattern per candidate |
| `--output`, `-o` | stdout | Write text results to this file |
| `--hide-empty` | off | Omit peaks with zero candidates |
| `--best-only` | off | Show only the highest-ranked candidate per peak; drop peaks with no passing fit |
| `--no-save-sdf` | — | Skip writing `<input>-EXACT.sdf` (the SDF output is written **by default**) |

### Algorithm filter options

| Option | Default | Description |
|--------|---------|-------------|
| `--no-nitrogen-rule` | on | Disable nitrogen rule parity check |
| `--no-hd-check` | on | Disable DBE/C hydrogen-deficiency check |
| `--no-lewis-senior` | on | Disable Lewis & Senior valence-sum rules |
| `--no-isotope-score` | on | Disable isotope pattern match scoring |
| `--no-smiles-constraints` | on | Disable ring-count upper-bound constraint |
| `--isotope-tolerance PP` | `30.0` | Max isotope score deviation in percentage points |
| `--max-ring-ratio RATIO` | `0.5` | Max DBE/C ratio for H-deficiency check |

---

## SDF File Format — Input

The tool looks for these **data field names** (case-insensitive):

**Molecular formula fields:**
`MOLECULAR FORMULA`, `MOL FORMULA`, `FORMULA`, `MF`, `SUMFORMULA`, `SUMMENFORMEL`, …

**Mass spectral peak fields:**
`MASS SPECTRAL PEAKS`, `MS_PEAKS`, `PEAK LIST`, `SPECTRUM`, `EI MASS SPECTRUM`, …

Peak data may be on one line or one pair per line:
```
> <MASS SPECTRAL PEAKS>
51 100 77 999 105 850 120 500
```
or:
```
> <MASS SPECTRAL PEAKS>
51 100
77 999
105 850
120 500
```

---

## Output SDF (written automatically as `*-EXACT.sdf`)

The output SDF **preserves the original file structure exactly** — one record per compound, the same MOL block, and all original data fields unchanged. Only two fields are modified:

### `MASS SPECTRAL PEAKS` — exact masses replace nominal m/z values

Each nominal integer m/z is replaced by the **best-matching exact monoisotopic ion mass** (6 decimal places). Peaks for which no valid candidate formula was found are **removed entirely**.

```
Input (unit-mass):          Output (exact mass):
> <MASS SPECTRAL PEAKS>     > <MASS SPECTRAL PEAKS>
41 999                      41.038577 999
43 850          →           43.018389 850
44 12                       ← removed (no valid candidate)
77 412                      77.038577 412
```

### `NUM PEAKS` — updated automatically

Updated to reflect the number of peaks that received an exact mass assignment.

### Caffeine example

| | Before | After |
|---|---|---|
| `NUM PEAKS` | 90 | 42 |
| `MASS SPECTRAL PEAKS` | integer m/z | exact masses (6 d.p.) |
| All other fields | unchanged | unchanged |
| MOL block | unchanged | unchanged |

Use `--no-save-sdf` to suppress the output file entirely.

---

## Example Output

```
EI Fragment Exact-Mass Calculator
  SDF file        : Caffeine.sdf
  Records found   : 1
  Tolerance       : +/-0.5 Da
  Electron mode   : remove  (positive-ion EI  (m/z = M_neutral - m_e))
  Isotope pattern : yes
  Best-only mode  : yes (top-ranked candidate per peak; unmatched peaks dropped)

========================================================================
Compound        : Caffeine
Formula         : C8H10N4O2   [neutral = 194.080376 Da,  DBE = 6.0]
Ion mass (M+•)  : 194.079827 Da  [- m_e = -0.000548580 Da  (positive-ion EI)]
Isotope pattern : M(100.0%)  M+1(1.5%)  M+1(8.7%)  M+2(0.4%)
Tolerance       : ±0.5 Da
Peaks           : 90
Mode            : best-only (top-ranked candidate per peak)
========================================================================

  m/z   109  —  1 candidate(s)
    Formula          Neutral mass        Ion m/z  Delta mass    DBE  Isotope pattern  FILTER
    --------------  -------------  -------------  ----------  -----  --------------  ------
    C5H5N3O          109.038947     109.038399   +0.038399    4.0  M(100.0%)  M+1(5.4%)  M+2(0.2%)  OK

  m/z   194  —  1 candidate(s)
    Formula          Neutral mass        Ion m/z  Delta mass    DBE  Isotope pattern  FILTER
    --------------  -------------  -------------  ----------  -----  --------------  ------
    C8H10N4O2        194.080376     194.079827   +0.079827    6.0  M(100.0%)  M+1(1.5%)  M+1(8.7%)  M+2(0.4%)  OK
```

Of 90 peaks in the Caffeine spectrum, **42 peaks** received a best-ranked passing candidate; the remaining 48 were dropped (`--best-only` mode). The output `Caffeine-EXACT.sdf` contains the same MOL block and all original fields, with 42 exact masses in the peak section.

---

## Supported Elements

| Element | Monoisotopic mass (Da) |
|---------|----------------------|
| C | 12.000000000 |
| H | 1.007825032 |
| N | 14.003074004 |
| O | 15.994914620 |
| S | 31.972070690 |
| F | 18.998403163 |
| Cl | 34.968852682 |
| Br | 78.918337100 |
| I | 126.904468000 |
| P | 30.973761998 |
| Si | 27.976926535 |

Element data is loaded from `data/elements.csv` at runtime. To add new elements or update abundances, edit that CSV file — no Python source changes needed.

---

## Running Tests

```bash
pytest
```

68 tests, 0 failures.

---

## Project Structure

```
ei-fragment-calculator/
├── README.md
├── LICENSE
├── pyproject.toml
├── .gitignore
├── data/
│   └── elements.csv             # All element masses, abundances, valences
├── ei_fragment_calculator/
│   ├── __init__.py              # Public API exports (v1.5.0)
│   ├── constants.py             # Physical constants, element data loader
│   ├── formula.py               # Formula parsing & Hill-notation formatting
│   ├── calculator.py            # Exact mass, DBE, electron correction, enumerator
│   ├── isotope.py               # Isotope pattern simulation (polynomial convolution)
│   ├── filters.py               # Five filter algorithms + rank_candidates()
│   ├── mol_parser.py            # MDL MOL block parser (ring count)
│   ├── sdf_parser.py            # SDF file parsing, mol block + peak extraction
│   ├── sdf_writer.py            # *-EXACT.sdf output writer
│   ├── preflight.py             # Environment / dependency checks
│   └── cli.py                   # Command-line interface
├── tests/
│   ├── test_formula.py
│   ├── test_calculator.py
│   ├── test_isotope.py
│   ├── test_sdf_parser.py
│   └── test_filters.py
└── docs/
    ├── workflow.png             # Algorithm flowchart
    └── ei_fragment_workflow.pptx
```

---

## Changelog

### v1.5.0
- **Changed — output SDF format:** `*-EXACT.sdf` now preserves the **exact structure of the input SDF** — one record per compound, same MOL block, all original fields intact.
- **Changed — `MASS SPECTRAL PEAKS`:** nominal integer m/z values are replaced by the best-matching exact monoisotopic ion masses (6 decimal places). Peaks with no valid candidate are removed.
- **Changed — `NUM PEAKS`:** updated automatically to the new peak count.
- **Fixed — `sdf_parser.py`:** now correctly extracts the MDL MOL block from each SDF record (previously mol_block was empty).
- **Fixed — `cli.py`:** `sdf_results` now stores the flat `fields` dict and the `mol_block` correctly.

### v1.4.1
- **Changed:** `*-EXACT.sdf` is now written **by default** after every run. Use `--no-save-sdf` to suppress it.

### v1.4.0
- **New:** `--best-only` flag — show only the highest-ranked candidate per peak (ranked by filter pass → |Δm| → isotope score); peaks with no passing candidate are silently dropped.
- **New:** `rank_candidates()` public API function for programmatic ranking.
- All five filter algorithms now contribute to ranking via `filter_passed` and `isotope_score`.

### v1.3.0
- Five new filter algorithms (nitrogen rule, H-deficiency, Lewis/Senior, isotope score, SMILES constraints).
- `--save-sdf` flag writes `*-EXACT.sdf` output (made default in v1.4.1).
- `FilterConfig` dataclass with per-filter `--no-*` CLI toggles.

### v1.2.0
- Isotope pattern simulation via polynomial convolution.
- `--isotope` flag.
- CSV-driven element database (`data/elements.csv`).

### v1.1.0
- Electron-mass correction modes (`remove` / `add` / `none`).
- SDF file input.

### v1.0.0
- Initial release: constrained Cartesian-product enumerator + DBE filter.
