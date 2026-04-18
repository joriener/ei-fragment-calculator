# CEF Viewer Quick Reference v1.95

## 10-Second Overview

**What it does:** Load mass spectrometry CEF files, identify common compounds, merge duplicates, export results.

**Where it is:** "CEF Viewer" tab in the GUI

**Database location:** `.ei_fragment_calculator/compounds.db` (project-local)

---

## Essential Buttons

| Button | What It Does | When to Use |
|--------|-------------|------------|
| **Load CEF** | Import CEF files | Starting fresh / Adding more files |
| **Clear** | Delete database, reset UI | Changing projects / Cleaning up |
| **Align** | Find matching compounds across files | Before consolidation / Quality check |
| **Consolidate** | Merge duplicate compounds | Main analysis task |
| **Export Aligned** | Save all compounds (pre-merge) | Backup / Intermediate results |
| **Export Consolidated** | Save merged compounds only | Final results for downstream tools |

---

## Common Workflows (Copy-Paste)

### Workflow A: Load and Browse

```
1. Click Load CEF
2. Select your .cef files (Ctrl+Click for multiple)
3. Wait for progress dialog to complete
4. Click any compound in tree view to see details
```

**Expected:** Compounds appear organized by file, with Name, M/Z, RT, Area, Height columns

---

### Workflow B: Find Duplicates Across Files

```
1. Load 2+ CEF files (Workflow A)
2. Click Consolidate
3. System analyzes for ~5-30 seconds
4. Review preview dialog showing proposed merges
5. Click Approve All
6. Status shows "Consolidated X groups"
```

**Expected:** Master compounds created with `is_consolidated` flag set

---

### Workflow C: Export for Next Tool

```
1. Complete Workflow B (consolidation)
2. Click Export Consolidated
3. Choose output type:
   - CSV → For spreadsheet analysis / Python scripts
   - CEF → For CEF-compatible tools / Re-analysis
4. Select save location
5. File created with only consolidated compounds
```

**Expected:** File contains ~30-50% of original compounds (duplicates merged)

---

## Column Definitions

| Column | Source | What It Means |
|--------|--------|---------------|
| **Name** | `<Molecule name="">` or calculated | Compound identifier |
| **M/Z** | Location `m=` | Mass-to-charge ratio |
| **RT** | Location `rt=` | Retention time in minutes |
| **Area** | Location `a=` | Peak area (intensity × width) |
| **Height** | Location `y=` | Peak height at max intensity |

---

## Display Examples

### Identified Compound
```
Name: Metaldehyde           (Molecule name from CEF)
M/Z:  45.0677               (mass-to-charge)
RT:   4.08                  (minutes)
Area: 536812                (peak area)
Height: 420832              (peak height)
```

### Unidentified Compound (if present)
```
Name: 4.08@45.0677          (RT@M/Z auto-format)
M/Z:  45.0677
RT:   4.08
Area: [value or blank]
Height: [value or blank]
```

---

## Tolerance Settings

**For TOF (Time-of-Flight) instruments:**
```
PPM Tolerance:      5 ppm      (default)
Da Tolerance:       0.5        (default)
RT Tolerance:       0.2 min    (default)
```

**If finding too many matches:** Decrease tolerances
**If finding too few matches:** Increase tolerances

**Rule of thumb:**
- 5 ppm = 0.0023 Da at m/z 500
- Loose matching: PPM 10, Da 1.0, RT 0.5 min
- Strict matching: PPM 3, Da 0.2, RT 0.1 min

---

## Data Storage

**Database file:** `.ei_fragment_calculator/compounds.db`

**What's stored:**
- Compound metadata (name, mass, RT, algorithm)
- Area and Height values
- Full spectrum (all peaks)
- Source file references
- Consolidation history (audit trail)

**Backup:** Copy `.ei_fragment_calculator/` folder to archive

**Delete:** Remove folder to clear database (same as Clear button)

---

## Export Formats

### CSV Export
```
id,name,mass,rt,area,height,algorithm,...
2,Metaldehyde,45.067700,4.085,536812,420832,FindByAMDIS,...
```
**Use when:** Spreadsheet analysis, Python/R scripts, data inspection

### CEF Export
```xml
<Compound algo="FindByAMDIS">
  <Location m="45.0677" rt="4.085" a="536812" y="420832"/>
  <Spectrum type="MFE">
    <MSPeaks>
      <p x="45.0677" y="12500.5" z="1"/>
      ...
    </MSPeaks>
  </Spectrum>
</Compound>
```
**Use when:** Re-analysis in CEF tools, preservation of full data, round-trip integrity

---

## Status Messages

| Message | Meaning | Action |
|---------|---------|--------|
| "Imported X compounds from Y files" | ✓ Success | Continue to next step |
| "No duplicates found" | No similar compounds detected | Lower tolerance, try Align first |
| "Found X alignments" | Matches detected | Review in alignment visualization |
| "Consolidated X groups" | ✓ Merges complete | Ready to export |
| "Exported X consolidated compounds" | ✓ Export successful | File ready for use |

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+Click (tree) | Select multiple compounds |
| Enter (in search) | Execute search |
| Escape | Close dialogs |

---

## File Size Reference

| Input | Output | Ratio |
|-------|--------|-------|
| 45 identified compounds | 15-20 compounds after consolidation | ~33% remain |
| 500-600 compounds from 10 files | ~200-250 after consolidation | ~40% remain |

---

## Compound Name Rules

### When Does Parser Show "Metaldehyde" vs "4.08@45.0677"?

**Shows molecule name ("Metaldehyde") if:**
- CEF has `<Molecule name="Metaldehyde" formula="C8H16O4">`
- Element found in three locations:
  1. Direct child of `<Compound>`
  2. Under `<Compound><Results><Molecule>`
  3. Anywhere in Compound subtree (`.//Molecule`)

**Shows RT@M/Z ("4.08@45.0677") if:**
- No Molecule element found
- OR Molecule element has no `name` attribute

**Note:** RT@M/Z format is intentionally self-documenting
- "4.08" = retention time in minutes
- "45.0677" = mass-to-charge ratio

---

## Troubleshooting Checklist

### Files won't load
- [ ] File is valid CEF (open in text editor, check for `<CEF>` tag)
- [ ] File has `<CompoundList>` element
- [ ] File is readable (not in use by another program)

### Compounds show blank data
- [ ] Reload database: Click Clear, then Load CEF again
- [ ] Check data in original CEF file with text editor

### No matches found in Consolidate
- [ ] Tolerance too strict? Increase PPM/Da/RT values
- [ ] Try Align first to see what matches exist
- [ ] Files may have genuinely different compounds

### Export is incomplete
- [ ] Check: "Export Consolidated" shows only merged compounds
- [ ] Use "Export Aligned" to export all compounds
- [ ] Verify consolidation was actually run

### Database too large
- [ ] Move old projects to archive folder
- [ ] Click Clear to reset (deletes all data)
- [ ] Use CSV export instead of CEF for archival

---

## Integration Points

**Output feed to:** EI Fragment Calculator (unknown compound identification)

**Expected downstream format:**
```
CSV with columns: id, name, mass, rt, area, height, algorithm
```

---

## Performance Tips

1. **Load all files at once** (not one-by-one)
2. **Consolidate all groups together** (not iteratively)
3. **Use selective filtering** if working with 1000+ compounds
4. **Archive old projects** to keep active database <5 files

---

## Dataset Examples

### Small Dataset
- 1-3 CEF files
- 50-200 total compounds
- Load: <1 sec per file
- Consolidate: <1 sec
- Export: <1 sec

### Medium Dataset
- 5-10 CEF files
- 500-1000 total compounds
- Load: ~5 secs total
- Consolidate: ~2-5 secs
- Export: ~1-2 secs

### Large Dataset
- 15-20 CEF files
- 1500-3000 total compounds
- Load: ~30 secs total
- Consolidate: ~10-30 secs
- Export: ~5-10 secs
- Note: Consider archival strategy

---

## Help & Support

**Full documentation:** See `CEF_VIEWER_DOCUMENTATION.md`

**Integration guide:** See `INTEGRATION_GUIDE.md`

**Example test:** `tests/test_cef_integration.py`

**Report issues:** Include:
- CEF file (if possible)
- Steps to reproduce
- Error message from status bar
- Database size (check .ei_fragment_calculator folder)

---

## One-Page Summary

```
LOAD → [Import CEF files into SQLite database]
         ↓
BROWSE → [View compounds with Name, M/Z, RT, Area, Height]
         ↓
ALIGN → [Find matching compounds across files]
         ↓
CONSOLIDATE → [Merge duplicates, flag as consolidated]
         ↓
EXPORT → [Save merged compounds to CSV or CEF]
         ↓
DOWNSTREAM → [Feed to EI Fragment Calculator for unknown ID]
```

