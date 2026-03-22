# Installation Guide — EI Fragment Exact-Mass Calculator v1.5.0

This guide covers everything needed to get the tool running on a **fresh Windows PC**.

---

## Requirements

| Requirement | Version | Notes |
|---|---|---|
| **Python** | **3.10 or newer** | Only stdlib is used — no conda needed |
| **pip** | any recent version | bundled with Python |
| **setuptools** | ≥ 68 | upgraded automatically by `install.bat` |
| **wheel** | any | upgraded automatically by `install.bat` |
| matplotlib | optional | only for `scripts/generate_workflow_image.py` |

No other third-party packages are required to run the tool.

---

## Step 1 — Install Python (if not already installed)

1. Go to **https://www.python.org/downloads/**
2. Download **Python 3.11** or **3.12** (latest stable recommended)
3. Run the installer and on the first screen tick both:
   - `[x] Install launcher for all users`
   - `[x] Add Python to PATH`  ← **important**
4. Click **Install Now**

Verify afterwards in a new command prompt:

```
python --version
```

Expected output: `Python 3.11.x` (or 3.12.x / 3.10.x)

---

## Step 2 — Extract the archive

Unzip `ei-fragment-calculator-v1.5.0.zip` to any folder, e.g.:

```
C:\Tools\ei-fragment-calculator\
```

You should see these files in the folder:

```
install.bat         ← run this to install
INSTALL.md          ← this file
README.md
pyproject.toml
data\
ei_fragment_calculator\
Spectra\
tests\
docs\
```

---

## Step 3 — Run the installer

**Double-click `install.bat`** (or open a command prompt and run it):

```bat
install.bat
```

The script will:
1. Check that Python 3.10+ is installed and in PATH
2. Upgrade `pip`, `setuptools`, and `wheel`
3. Install `ei-fragment-calculator` via `pip install -e .`
4. Verify the `ei-fragment-calc` command is reachable
5. Print a quick-start summary

If everything succeeds you will see:

```
[OK] Python version is compatible.
[OK] pip is available.
[OK] pip and setuptools are up to date.
[OK] Package installed successfully.
[OK] Command 'ei-fragment-calc' is ready.
```

### Troubleshooting the installer

| Problem | Fix |
|---|---|
| `Python was not found in PATH` | Re-install Python with "Add to PATH" ticked, then restart the command prompt |
| `Python 3.10+ required. Found 3.9.x` | Download a newer Python from python.org |
| `pip is not available` | Run `python -m ensurepip --upgrade` |
| Installation failed (permissions) | Right-click `install.bat` → *Run as Administrator*, or install to user directory: `pip install --user -e .` |
| `ei-fragment-calc` not found after install | See note below |

> **If `ei-fragment-calc` is not found in PATH after installation:**
> Python's `Scripts\` folder is sometimes not added to PATH automatically.
> You can always run the tool as a module:
> ```
> python -m ei_fragment_calculator.cli  your_spectra.sdf
> ```
> Or add the Scripts folder to PATH manually:
> `C:\Users\<YourName>\AppData\Local\Programs\Python\Python311\Scripts\`

---

## Step 4 — Verify (optional)

Run the built-in test suite to confirm everything works:

```bat
pip install -e ".[dev]"
pytest
```

Expected: **68 passed** in < 1 second.

---

## How to Run

### Quick reference

```bat
REM  Run on the included Caffeine example (writes Caffeine-EXACT.sdf)
ei-fragment-calc Spectra\Caffeine.sdf

REM  Best candidate per peak + isotope patterns (recommended)
ei-fragment-calc Spectra\Caffeine.sdf --best-only --isotope

REM  Your own spectra file
ei-fragment-calc path\to\your_spectra.sdf --best-only --isotope

REM  Save text output to a file as well
ei-fragment-calc your_spectra.sdf --best-only --output results.txt

REM  Show all available options
ei-fragment-calc --help
```

### What happens when you run it

1. The tool reads your SDF file — finds the molecular formula and the peak list.
2. For each nominal m/z peak it enumerates all formula combinations within the parent formula and applies filters.
3. Results are printed to the terminal.
4. A file `<your_spectra>-EXACT.sdf` is written automatically beside the input file.

### The output SDF (`*-EXACT.sdf`)

The output is an SDF file with **exactly the same structure as the input** — one record per compound, same MOL block, all original fields preserved. Only two fields are changed:

- `MASS SPECTRAL PEAKS` — nominal integer m/z values are replaced by exact monoisotopic masses (6 decimal places). Peaks with no valid candidate are removed.
- `NUM PEAKS` — updated to the new peak count.

**Example (Caffeine):**

| Field | Input | Output |
|---|---|---|
| `NUM PEAKS` | 90 | 42 |
| `MASS SPECTRAL PEAKS` | `194 999` | `194.079827 999` |
| MOL block | unchanged | unchanged |
| All other fields | unchanged | unchanged |

---

## Input SDF Requirements

Your SDF must contain at minimum:

1. A **molecular formula** field — recognised field names (case-insensitive):
   `FORMULA`, `MOLECULAR FORMULA`, `MF`, `SUMFORMULA`, `SUMMENFORMEL`, …

2. A **mass spectral peaks** field — recognised field names:
   `MASS SPECTRAL PEAKS`, `MS_PEAKS`, `PEAK LIST`, `SPECTRUM`, `EI MASS SPECTRUM`, …

Peak data can be one pair per line or all on one line:
```
> <MASS SPECTRAL PEAKS>
51 100
77 999
105 850
```
or:
```
> <MASS SPECTRAL PEAKS>
51 100 77 999 105 850
```

If a field name in your file is not recognised, open an issue on GitHub or add it to the `PEAK_FIELD_CANDIDATES` list in `ei_fragment_calculator/constants.py`.

---

## Uninstall

```bat
pip uninstall ei-fragment-calculator
```

---

## GitHub

Source code, issues, updates:
**https://github.com/joriener/ei-fragment-calculator**
