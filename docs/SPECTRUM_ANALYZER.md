# Spectrum Analyzer Tab

## Overview

The **Spectrum Analyzer** tab provides an integrated compound browser and mass spectrum visualization with **automatic formula annotations** for assigned peaks.

## Features

### 1. Compound Browser
- **Search by name** with live filtering (case-insensitive)
- **Browse all compounds** in alphabetical order
- **Quick navigation** between compounds
- **View compound metadata** in the list

### 2. Annotated Mass Spectrum
- **Visual spectrum display** with matplotlib integration
- **Formula annotations** above each peak showing the best-matching formula
- **Interactive formula list** below spectrum showing top matches
- **Dynamic scaling** based on peak intensities
- **Color-coded display** with formulas in green

### 3. Formula Assignment Engine
- Uses the **formula_calculator module** for m/z-to-formula lookup
- Supports **multiple formula matches** per peak (displays top 3)
- **Respects parent formula constraints** - fragment formulas cannot exceed parent
- Filters by:
  - Nitrogen rule
  - DBE (Degree of Unsaturation) validity
  - Hydrogen deficiency ratio
  - Valence constraints

## UI Layout

```
┌─────────────────────────────────────────────────────────────────┐
│ [Search:        ] [Clear] [Refresh]                            │
├──────────────────┬─────────────────────────────────────────────┤
│ Compound Browser │  Mass Spectrum                              │
│                  │  ─────────────────────────────────────────  │
│ • Caffeine       │  │ (spectrum plot with annotations)         │
│ • Benzene        │  │                                          │
│ • Toluene        │  │                                          │
│ • Naphthalene    │  │                                          │
│ • n-Hexane       │  ├─────────────────────────────────────────┤
│                  │  │ Formulas:                               │
│                  │  │ m/z  77.0  →  C6H5                      │
│                  │  │ m/z  91.0  →  C7H7                      │
│                  │  │ m/z 110.0  →  C8H10                     │
│                  │  │ m/z 194.0  →  C8H10N4O2                 │
│                  │  │                                          │
└──────────────────┴─────────────────────────────────────────────┘
```

## Usage

### Loading Compounds
1. Go to the **Compound Database** tab
2. Load an SDF file or MSPEC file
3. The **Spectrum Analyzer** tab auto-populates with all compounds
4. Click on the **Spectrum Analyzer** tab to view spectra

### Searching and Browsing
1. Type in the search field to filter compounds
2. Results update in real-time
3. Click a compound to display its spectrum
4. Use **Clear** button to reset the search

### Viewing Formula Annotations
1. Spectrum displays with formula labels above peaks
2. **Formula List** below shows detailed matches:
   - m/z value (7 characters, right-aligned)
   - Arrow separator
   - Best-matching formula (Hill notation)
3. Formulas are sorted by m/z for easy reference

## Data Requirements

### Required Fields
- **Compound name**: `COMPOUNDNAME` or `NAME` field
- **Molecular formula**: `FORMULA` field
- **Mass spectrum**: Any of these field names:
  - `MASS SPECTRAL PEAKS`
  - `MASS SPECTRUM`
  - `PEAKS`
  - `MS PEAKS`
  - `SPECTRUM`

### Peak Format Support
The analyzer supports multiple peak formats:

**Format 1: Semicolon-separated pairs**
```
50 287; 51 144; 52 9; 77 120
```

**Format 2: Newline-separated pairs**
```
50 287
51 144
52 9
77 120
```

**Format 3: Space-separated alternating m/z and intensity**
```
50 287 51 144 52 9 77 120
```

## Formula Assignment Algorithm

### Method
1. Extract parent formula from compound record
2. For each mass peak:
   - Call `formula_calculator.find_formulas_at_mass(mz, parent_composition)`
   - Tolerance: ±0.5 Da (standard) or ±5 ppm (high-resolution)
   - Electron correction: -1 electron for EI+ ions
3. Apply chemical validity filters:
   - Nitrogen rule parity
   - DBE ≥ 0 and valid half-integer values
   - H/C ratio constraints
   - Valence connectivity rules
4. Return top 3 matching formulas

### Parameters
- **Tolerance**: ±0.5 Da (adjustable)
- **Electron mode**: "remove" (EI+)
- **Max depth**: 3 (fragment atom-removal recursion)

## Keyboard Shortcuts
- **Enter** (in search field): Navigate to first search result
- **Escape** (in compound list): Clear selection

## Integration with GUI

### Data Flow
```
Load SDF/MSPEC File
        ↓
SDFViewerTab parses file
        ↓
Extracts compound fields
        ↓
Calls spectrum_tab.set_records(records)
        ↓
SpectrumAnalyzerTab displays compounds
```

### Auto-sync with Compound Database
- When you select a compound in the **Compound Database** tab, you can see it highlighted in **Spectrum Analyzer**
- Changes to compound metadata are immediately visible

## Performance Notes

- **Formula matching**: ~50-200ms per peak (depends on tolerance)
- **Spectrum rendering**: ~500ms with ~50 peaks
- **Memory usage**: ~1-2 MB per 100 compounds

For large datasets (>1000 compounds), consider:
1. Using high-resolution m/z values (ppm tolerance)
2. Filtering to compound subset of interest
3. Displaying only base peaks and significant ions

## Examples

### Example 1: Caffeine
```
Parent Formula: C8H10N4O2
Peak at m/z 110:
  - Formula: C8H10 (matches ethylbenzene fragment)
  - DBE: 4.0 (benzene-like)
  - Status: Valid

Peak at m/z 194:
  - Formula: C8H10N4O2 (parent ion, M+)
  - DBE: 6.0
  - Status: Valid
```

### Example 2: Benzene
```
Parent Formula: C6H6
Peak at m/z 77:
  - Formula: C6H5 (loss of H•)
  - DBE: 4.0 (benzyne radical cation)
  - Status: Valid

Peak at m/z 78:
  - Formula: C6H6 (parent ion)
  - DBE: 4.0 (benzene)
  - Status: Valid
```

## Troubleshooting

### No annotations appear
- **Cause**: Formula field missing or misspelled
- **Solution**: Ensure compound has a `FORMULA` field with valid formula syntax

### Annotations don't match peaks
- **Cause**: Incorrect m/z values or spectrum format
- **Solution**: Verify spectrum data format matches supported patterns

### Spectrum not displaying
- **Cause**: Matplotlib not installed
- **Solution**: Install matplotlib: `pip install matplotlib`

### Formula matches seem wrong
- **Cause**: Parent composition doesn't contain required atoms
- **Solution**: Check parent formula includes all element types in fragments

## Module: spectrum_analyzer.py

### Main Class
```python
class SpectrumAnalyzerTab(ttk.Frame):
    def __init__(self, master: tk.Widget, records: list[dict] = None)
    def set_records(self, records: list[dict]) -> None
    def _display_spectrum(self, record: dict) -> None
    def _get_formula_annotations(self, mz_values, parent_formula_str) -> dict
```

### Key Methods
- `set_records()`: Update displayed compounds
- `_display_spectrum()`: Render mass spectrum with annotations
- `_get_formula_annotations()`: Look up formula assignments
- `_parse_peaks()`: Parse various peak format styles

## See Also
- [Formula Calculator](../ei_fragment_calculator/formula_calculator.py)
- [GUI Documentation](./GUI.md)
- [Algorithm Documentation](./EI_Fragment_Calculator_Algorithms.pdf)
