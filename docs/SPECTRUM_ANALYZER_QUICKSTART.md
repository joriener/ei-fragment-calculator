# Spectrum Analyzer - Quick Start Guide

## What is it?
The **Spectrum Analyzer** tab is a new GUI feature that shows:
1. A **searchable list of compounds** on the left
2. An **annotated mass spectrum** on the right
3. **Formula assignments** automatically matched to each peak

## How to Use It

### Step 1: Load Compounds
1. Open the **EI Fragment Calculator** GUI
2. Go to the **Compound Database** tab
3. Click **Load Compounds** and select an SDF or MSPEC file
4. Wait for the file to load

### Step 2: View Spectrum
1. Click the **Spectrum Analyzer** tab
2. You'll see a list of compounds on the left
3. Click on any compound to see its mass spectrum

### Step 3: See Formula Annotations
1. The **mass spectrum** displays with **green formula labels** above peaks
2. Below the spectrum, the **Formula Assignments** list shows all matches:
   ```
   m/z  77.0  →  C6H5
   m/z  91.0  →  C7H7
   m/z 110.0  →  C8H10
   ```

### Step 4: Search for Compounds
1. Type in the **Search box** at the top
2. Results update in real-time
3. Click a compound to display its spectrum
4. Use **Clear** to reset the search

## Example

### Input: Benzene (C6H6)
```
Compound Name: Benzene
Parent Formula: C6H6
Mass Spectrum Peaks:
  m/z 50 (intensity 28)
  m/z 77 (intensity 999)
  m/z 78 (intensity 999)
```

### Output: Annotated Spectrum
```
Mass Spectrum Display:
    C6H5
      ↓
  ──────────
  50  77  78  m/z
  
Formula Assignments:
m/z  50.0  →  C3H2
m/z  77.0  →  C6H5  (benzyne radical)
m/z  78.0  →  C6H6  (parent ion)
```

## How It Works

The analyzer automatically:
1. Extracts the **parent molecule formula** (e.g., C6H6)
2. For each **mass peak** (m/z value):
   - Looks up all possible **elemental compositions** that match
   - Filters by chemical validity rules (nitrogen rule, DBE, valence)
   - Returns top 3 **formula matches**
3. Displays results with **formulas above peaks**

## Supported Peak Formats

The tool works with these peak data formats:

**Semicolon-separated:**
```
50 287; 51 144; 52 9; 77 120
```

**Newline-separated:**
```
50 287
51 144
52 9
77 120
```

**Space-separated:**
```
50 287 51 144 52 9 77 120
```

## Required Fields in Your Data

Your compounds need:
- **Compound Name**: Field like `COMPOUNDNAME` or `NAME`
- **Molecular Formula**: Field like `FORMULA`
- **Mass Spectrum**: Field like `MASS SPECTRAL PEAKS` or `MASS SPECTRUM`

### Example SDF Entry
```
> <COMPOUNDNAME>
Caffeine

> <FORMULA>
C8H10N4O2

> <MASS SPECTRAL PEAKS>
50 287; 51 144; 77 120; 110 999; 194 150
```

## Features

✓ **Live search** - Filter compounds as you type  
✓ **Visual spectrum** - Color-coded bar chart display  
✓ **Formula annotations** - Green labels above peaks  
✓ **Multiple matches** - Shows top 3 formulas per peak  
✓ **Parent constraints** - Respects parent composition  
✓ **Multiple formats** - Handles various peak data formats  
✓ **Fast lookup** - ~100ms per peak  

## Tips & Tricks

### Tip 1: Narrow Your Search
Type part of a compound name to quickly find it:
- Type "benz" to find Benzene, Toluene, etc.
- Type "hex" to find all hexane compounds
- Type "caf" to jump straight to Caffeine

### Tip 2: Check Fragment Ions
The formula annotations help identify:
- **M+ ion**: Parent formula (largest m/z)
- **Common losses**: M-15 (CH₃), M-29 (CHO), M-45 (OEt)
- **Characteristic ions**: Tropylium (C₇H₇⁺ = m/z 91)

### Tip 3: Verify Spectra
Compare with expected fragments:
- Benzene derivatives → expect C₇H₇⁺ at m/z 91
- Alcohols → expect loss of H₂O
- Aldehydes/Ketones → expect loss of CO

### Tip 4: Export/Save
While formulas are shown in the GUI, you can:
- Screenshot the spectrum for reports
- Note formula assignments manually
- Export the spectrum as a matplotlib figure (future feature)

## Troubleshooting

### No Compounds Showing?
- Did you load a file in the **Compound Database** tab first?
- Try clicking the **Refresh** button

### No Spectrum Displayed?
- Make sure the compound has a `MASS SPECTRAL PEAKS` or `MASS SPECTRUM` field
- Check that peak data is in a supported format

### No Formula Annotations?
- Ensure the compound has a `FORMULA` field
- Verify the formula is valid (e.g., "C6H6" not "Benzene")

### Slow Performance?
- Large datasets (>1000 compounds) may be slow
- Try searching to narrow down the compound list
- Use high-resolution m/z values (ppm tolerance) instead

## Test the Feature

### Run the Test
```bash
python test_spectrum_analyzer.py
```

This launches a standalone demo with 5 sample compounds:
- Caffeine
- Benzene
- Toluene
- Naphthalene
- n-Hexane

### Try It With Your Data
1. Start the GUI: `ei-fragment-gui`
2. Load your SDF file
3. Switch to **Spectrum Analyzer** tab
4. Explore your compounds!

## FAQ

**Q: Can I edit the compound list?**  
A: Not yet. The list is read-only. Edit compounds in the **Compound Database** tab.

**Q: How are the formulas calculated?**  
A: Uses the internal `formula_calculator` module which performs:
1. Elemental composition enumeration
2. Mass accuracy filtering (±0.5 Da)
3. Chemical validity rules (nitrogen rule, DBE, valence)

**Q: Can I see why a formula was rejected?**  
A: Not in the current UI, but the list shows only valid matches. For more detail, check the source code in `formula_calculator.py`.

**Q: What if I want different tolerance or settings?**  
A: Currently hardcoded to ±0.5 Da. Future enhancement will add UI controls.

**Q: Can I export the annotated spectrum?**  
A: Not yet. You can take a screenshot for now. Export feature planned.

## Related Documentation
- **Spectrum Analyzer Module**: [spectrum_analyzer.py](../ei_fragment_calculator/spectrum_analyzer.py)
- **Formula Calculator**: [formula_calculator.py](../ei_fragment_calculator/formula_calculator.py)
- **Full Architecture**: [SPECTRUM_ANALYZER_ARCHITECTURE.txt](./SPECTRUM_ANALYZER_ARCHITECTURE.txt)
- **Detailed Guide**: [SPECTRUM_ANALYZER.md](./SPECTRUM_ANALYZER.md)

## Need Help?
1. Check the **Troubleshooting** section above
2. Read the detailed [SPECTRUM_ANALYZER.md](./SPECTRUM_ANALYZER.md)
3. Review the [architecture diagram](./SPECTRUM_ANALYZER_ARCHITECTURE.txt)
4. Run the test: `python test_spectrum_analyzer.py`

---
**Version**: 1.0  
**Added**: 2026-04-17  
**Status**: Ready for use ✓
