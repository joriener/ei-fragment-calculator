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

---

## Installation

```bash
git clone https://github.com/your-username/ei-fragment-calculator.git
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

# Save results to a file
ei-fragment-calc spectra.sdf --output results.txt

# Suppress peaks with no candidates
ei-fragment-calc spectra.sdf --hide-empty
```

### All options

| Option | Default | Description |
|--------|---------|-------------|
| `sdf_file` | — | Path to the input SDF file |
| `--electron`, `-e` | `remove` | Electron-mass correction: `remove`, `add`, or `none` |
| `--tolerance`, `-t` | `0.5` | Mass window in ±Da |
| `--output`, `-o` | stdout | Write results to this file |
| `--hide-empty` | off | Omit peaks with zero candidates |

---

## SDF File Format

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

## Example Output

```
EI Fragment Exact-Mass Calculator
  SDF file        : examples/example.sdf
  Records found   : 1
  Tolerance       : ±0.5 Da
  Electron mode   : remove  (positive-ion EI  (m/z = M_neutral − m_e))

========================================================================
Compound        : Acetophenone
Formula         : C8H8O   [neutral mass = 120.057515 Da,  DBE = 5.0]
Ion mass (M+•)  : 120.056966 Da  [electron: − m_e = −0.000548580 Da]
Tolerance       : ±0.5 Da
Peaks in spectrum: 4
========================================================================

  m/z    51  —  1 candidate(s)
    Formula         Neutral mass      Ion m/z    Δ mass    DBE
    --------------  -------------  -------------  ---------  -----
    C4H3            51.023475      51.022926  +0.022926    3.0

  m/z    77  —  1 candidate(s)
    C6H5            77.039125      77.038576  +0.038576    4.5

  m/z   105  —  2 candidate(s)
    C7H5O          105.033978     105.033430  +0.033430    5.5
    C8H9           105.070425     105.069876  +0.069876    4.5

  m/z   120  —  1 candidate(s)
    C8H8O          120.057515     120.056966  +0.056966    5.0
```

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

To add more elements, extend `MONOISOTOPIC_MASSES` and `VALENCE` in `ei_fragment_calculator/constants.py`.

---

## Running Tests

```bash
pytest
```

---

## Project Structure

```
ei-fragment-calculator/
├── README.md
├── LICENSE
├── pyproject.toml
├── .gitignore
├── ei_fragment_calculator/
│   ├── __init__.py          # Public API exports
│   ├── constants.py         # Physical constants, element data, field names
│   ├── formula.py           # Formula parsing & Hill-notation formatting
│   ├── calculator.py        # Exact mass, DBE, electron correction, enumerator
│   ├── sdf_parser.py        # SDF file parsing, peak extraction
│   └── cli.py               # Command-line interface
├── tests/
│   ├── test_formula.py
│   ├── test_calculator.py
│   └── test_sdf_parser.py
└── examples/
    └── example.sdf
```
