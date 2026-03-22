# Installation Guide - EI Fragment Exact-Mass Calculator

This guide explains how to install the tool from scratch on any Windows, macOS
or Linux machine and verify that everything works correctly.

---

## System requirements

| Requirement | Minimum | Recommended |
|---|---|---|
| **Python** | 3.10 | 3.11 or 3.12 |
| **pip** | 21+ | latest |
| **OS** | Windows 10 / macOS 11 / Ubuntu 20.04 | any modern OS |
| **Internet** | - | required for `ei-enrich-sdf` API lookups |
| **Disk** | ~5 MB | - |
| **RAM** | 64 MB | - |

No third-party Python packages are required to run `ei-fragment-calc`.
Optional packages add extra features (see below).

---

## Step 1 - Install Python 3.10+

### Windows
1. Download the official installer from https://www.python.org/downloads/
2. Run the installer - **check "Add Python to PATH"**
3. Verify: open a new PowerShell or Command Prompt and run:
   ```
   python --version
   ```
   Expected: `Python 3.10.x` or newer.

### macOS
```bash
brew install python@3.11
```
or download from https://www.python.org/downloads/macos/

### Linux (Ubuntu/Debian)
```bash
sudo apt update && sudo apt install python3.11 python3.11-pip
```

---

## Step 2 - Get the project

### Option A - from the ZIP archive (no git needed)
1. Unzip `ei-fragment-calculator-v1.5.0.zip` to any folder, e.g.:
   - Windows: `C:\Tools\ei-fragment-calculator\`
   - macOS/Linux: `~/tools/ei-fragment-calculator/`
2. Open a terminal and `cd` into that folder.

### Option B - from GitHub (git required)
```bash
git clone https://github.com/joriener/ei-fragment-calculator.git
cd ei-fragment-calculator
```

---

## Step 3 - Install the package

Run this once inside the project folder:

```bash
pip install -e .
```

For development (includes pytest for running tests):
```bash
pip install -e ".[dev]"
```

> **Windows note:** if `pip` is not recognised, try `python -m pip install -e .`

### What this does
- Registers `ei-fragment-calc` and `ei-enrich-sdf` as system-wide commands
- No files are copied - the source folder is used directly (editable install)

---

## Step 4 - Verify the installation

Run the included requirements checker:

```bash
python scripts/check_requirements.py
```

Expected output ends with:
```
All required checks passed.  You can run:

    ei-fragment-calc  your_spectrum.sdf  --best-only --isotope
    ei-enrich-sdf     your_spectrum.sdf
```

---

## Step 5 - Optional packages

Install these to unlock extra features:

| Package | Feature | Install |
|---|---|---|
| `matplotlib` | Workflow diagram (`scripts/generate_workflow_image.py`) | `pip install matplotlib` |
| `splashpy` | SPLASH spectral hash in `ei-enrich-sdf` | `pip install splashpy` |

---

## Running the tools

### Calculate exact masses for every peak

```bat
ei-fragment-calc  your_spectrum.sdf  --best-only --isotope
```

Output is printed to the terminal **and** saved as `your_spectrum-EXACT.sdf`
next to the input file.  Add `--no-save-sdf` to suppress the SDF output.

Full option reference:
```bat
ei-fragment-calc --help
```

### Enrich an SDF file with database metadata

```bat
ei-enrich-sdf  your_spectrum.sdf
```

Queries PubChem, ChEBI, KEGG, and HMDB to add missing fields (FORMULA, MW,
INCHI, INCHIKEY, SMILES, CAS, SYNONYMS, CHEBI, KEGG, HMDB, EXACT MASS).
Writes `your_spectrum-ENRICHED.sdf`.

```bat
ei-enrich-sdf  your_spectrum.sdf  --no-hmdb --no-kegg   # skip slower sources
ei-enrich-sdf  your_spectrum.sdf  --output  output.sdf  # custom output path
ei-enrich-sdf  --help
```

> **Note:** `ei-enrich-sdf` requires an internet connection. Fields that are
> already present in the SDF are never overwritten (use `--overwrite` to
> change this).

### Typical workflow

```
your_spectrum.sdf           (from instrument / ChemVista / NIST)
        |
        +-- ei-enrich-sdf   ->   your_spectrum-ENRICHED.sdf
        |       (adds: FORMULA, CAS, SMILES, INCHI, CHEBI, KEGG, HMDB ...)
        |
        +-- ei-fragment-calc --best-only --isotope
                (input from enriched SDF)
                ->   your_spectrum-EXACT.sdf
                        (exact masses in MASS SPECTRAL PEAKS)
```

---

## Running the tests

```bash
pytest
```

Expected: `68 passed` in under 1 second.

---

## Uninstalling

```bash
pip uninstall ei-fragment-calculator
```

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `ei-fragment-calc: command not found` | Run `pip install -e .` from the project folder |
| `ModuleNotFoundError: No module named 'ei_fragment_calculator'` | Same as above |
| `FileNotFoundError: data/elements.csv` | Ensure you run from or after installing from the correct folder |
| API timeouts in `ei-enrich-sdf` | Use `--delay 1.0` to slow down requests; check internet |
| `pip` not found | Use `python -m pip` instead |
| Python 3.9 or older | Upgrade Python; the tool requires >= 3.10 |
