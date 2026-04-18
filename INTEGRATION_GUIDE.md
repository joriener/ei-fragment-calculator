# EI Fragment Calculator - Integration Guide

## Overview of Enhancements

### ✓ Completed Features

#### 1. **Progress Bar During CEF Loading**
- Visual progress bar shows file loading status
- No more "not responding" appearance
- Updates filename and progress in real-time

#### 2. **Match → Align Terminology**
- Renamed "Match" button to "Align"
- Renamed "Matching Parameters" to "Align Parameters"
- Reflects consolidation workflow: Load → Align → Consolidate

#### 3. **Confidence Threshold in Consolidation**
- Slider to filter consolidation groups by confidence level
- Shows "X of Y groups" matching threshold
- Only consolidates groups above threshold

#### 4. **Compound Naming (RT@M/Z Format)** ✓ IMPLEMENTED
Consolidated compounds are automatically renamed to `RT_VALUE@M_Z_VALUE` format:
```
Example: 5.23@180.0633  (retention time 5.23 min, m/z 180.0633)
```
- Base peak m/z is identified during consolidation
- Format makes compound identity self-documenting
- Applied to all consolidated (merged) compounds
- Single-file compounds retain original names

#### 5. **Direct CEF Export** ✓ IMPLEMENTED
- Export dialog supports both **CEF** and **CSV** formats
- Click "Export" → select `.cef` or `.csv` extension → file saved
- **CEF Format:** Standard Agilent CEF XML with all compound metadata
  - Preserves: mass, RT, spectrum peaks, device type, algorithm
  - Uses RT@M/Z naming for consolidated compounds
  - Round-trip compatible with other CEF tools
- **CSV Format:** Tabular data export with source file tracking
  - Fields: id, name, mass, rt, algorithm, device_type, polarity, is_consolidated, peak_count, source_files
  - Includes column tracking which CEF files each compound originated from

---

## Integration with External Tools

### **MetFrag Compatibility** ✓ YES
Your consolidated compound data **IS compatible with MetFrag**. Here's how to use it:

**Data Export Format for MetFrag:**
```csv
mz,rt,name,peaks_mz,peaks_intensity
180.0633,5.23,5.23@180.0633,"[100.05,150.12,180.06]","[100,80,50]"
```

**Steps to use with MetFrag:**
1. Export consolidated compounds as CSV (current button)
2. Convert to MetFrag format using:
   - MetFrag's input template (XML-based)
   - Or custom Python script to reformat the CSV
3. Upload to MetFrag web server or local installation
4. MetFrag uses m/z and intensity peaks to predict fragmentation patterns

**Key fields MetFrag needs:**
- Neutral mass (m/z value) ✓
- Retention time (optional, for context) ✓
- Peak intensities (for scoring) ✓

---

### **NIST Mass Spectrum Search** ⚠ Limited Integration

#### **Current Options:**

##### **Option A: Manual NIST Search** (Current)
1. Export consolidated compounds as CSV or CEF
2. Visit: https://webbook.nist.gov/chemistry/
3. Search by:
   - **Molecular weight** (m/z value)
   - **Retention time** (GC retention index)
   - **Spectrum similarity** (upload peak list)
4. Review matches in NIST library

**Workflow:**
```
export_consolidated.cef → NIST webbook → Manual matching
```

##### **Option B: Programmatic NIST Search** (Future Enhancement)
To add "Right-click → Search NIST" functionality:

```
NIST MS Search API Requirements:
- Commercial license or institutional access
- Not publicly available API (unlike CHEMSPIDER or PUBCHEM)
- Requires: NIST Tandem MS Library or NIST 17 software license
- Cost: ~$2,000-5,000 USD per license
- Contact: https://www.nist.gov/srm/nist-mass-spectrometry-data-center
```

**Alternative Free Options:**
- **CHEMSPIDER API** (https://developer.rsc.org/api-docs)
  - Free API with registration
  - Search by molecular weight or formula
  - Returns structure info but not EI spectra
- **PUBCHEM** (https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest)
  - Free REST API
  - Limited spectrum data
- **MassBank** (https://www.massbank.jp)
  - Free MS/MS spectral database
  - No programmatic API, manual search only

---

## Detailed Feature Guide

### **Align Parameters**
```
Method:              mass_rt | ppm_rt | spectral | ppm_spectral
├─ mass_rt:          Fixed m/z tolerance (±0.5 Da)
├─ ppm_rt:           Relative PPM tolerance (5 ppm for TOF)
├─ spectral:         Spectral similarity matching (>0.8 threshold)
└─ ppm_spectral:     Combined PPM + spectral

PPM Tolerance:       5.0 ppm (high-res instruments)
Da Tolerance:        0.5 Da (low-res instruments)
RT Tolerance:        0.2 min
Spectral Threshold:  0.8 (0-1 scale)
Spectral Weight:     0.4 (importance in scoring)
```

### **Multi-Stage Consolidation Workflow**

#### **1. Load CEF Files**
- All CEF files imported with progress bar
- **Tree View Display:**
  ```
  cef_1.cef (25 compounds)
    ├─ Glucose [M+H]+ (m/z: 181.070, RT: 5.23)
    ├─ Fructose [M+H]+ (m/z: 181.070, RT: 6.45)
    └─ ... (23 more compounds)
  cef_2.cef (18 compounds)
    ├─ Glucose (m/z: 181.068, RT: 5.24)
    └─ ... (17 more compounds)
  ```
- Hierarchical view shows file → compound structure
- Original compound names displayed (not yet consolidated)

#### **2. Align**
- Find compounds across files using configurable parameters
- Method options: `mass_rt`, `ppm_rt`, `spectral`, `ppm_spectral`
- Live parameter editing in left panel
- Results displayed in alignment table
- Confidence scores show match quality [0-1]

#### **3. Export Aligned Data** (Optional intermediate export)
- Exports all compounds with alignment information
- File format: CEF or CSV
- Compound names still use original naming (not yet consolidated)
- Use case: Archive alignment results before consolidation

#### **4. Consolidate**
- Preview shows proposed merges with confidence threshold slider
- Adjust threshold to filter groups
- **Consolidation Updates:**
  - Compounds renamed to `RT@M/Z` format
    - RT = **average retention time** of all merged compounds
    - M/Z = base peak (highest intensity) from merged spectra
  - Master compound stores source file references
  - Example: `5.24@180.0632` (avg RT 5.24 min, base peak 180.0632 m/z)

#### **5. Export Consolidated Data** (Final export)
- Exports only consolidated (merged) compounds
- File format: CEF or CSV
- **CEF Format:** Includes average RT for each consolidated compound
- **CSV Format:** Shows source files + consolidation status

### **Data Output Formats**

#### **CSV Export** (Updated)
```csv
id,name,mass,rt,algorithm,device_type,polarity,is_consolidated,peak_count,source_files
1,5.23@180.0633,180.0633,5.23,MFE,Q-TOF,+,Yes,3,file1.cef, file2.cef, file3.cef
2,6.45@157.126,157.126,6.45,MFE,Q-TOF,+,No,2,file2.cef
```
- **source_files:** Comma-separated list of CEF files compound came from
- **is_consolidated:** "Yes" for consolidated compounds, "No" for originals
- **name:** Uses RT@M/Z format for consolidated compounds

#### **CEF Export** (Ready)
- Standard Agilent CEF format
- Preserves all compound data + source file metadata
- Can re-import into other tools

---

## Recommendations

### **For MetFrag Users:**
1. Use `ppm_rt` align method (5 ppm tolerance)
2. Consolidate with confidence > 0.8
3. Export as CSV
4. Convert CSV → MetFrag XML template
5. Upload to MetFrag server

### **For NIST Integration:**
1. If you frequently use NIST:
   - Request NIST API access (free research accounts available)
   - We can add right-click "Send to NIST" feature
   - Results would display in-app

2. For now:
   - Export as CSV
   - Manually search NIST web interface
   - Cross-reference results

---

## Technical Notes

### **Alignment vs. Consolidation**
- **Align**: Find potential matches across files (shows all candidates)
- **Consolidate**: Merge groups of duplicates into single "master" compound
  - Master gets average RT and unified name
  - All sources tracked in database
  - Marks duplicates for reference

### **Confidence Scoring**
```
score = 1.0 - sqrt((Δm/m_tol)² + (ΔRT/rt_tol)²)
```
- 1.0 = perfect match
- 0.5 = borderline (should review)
- <0.3 = weak match (likely false positive)

### **RT@M/Z Compound Naming**
During consolidation, merged compounds are automatically renamed to `RT@M/Z` format:
```
Format: RT_VALUE@M_Z_VALUE
Example: 5.23@180.0633

Meaning:
  - 5.23 = Averaged retention time (minutes)
  - 180.0633 = Base peak m/z (highest intensity peak from merged spectra)
```
**Benefits:**
- Self-documenting: name contains key identification parameters
- Compatible with downstream tools (MetFrag, NIST search)
- Prevents naming conflicts from multiple source files
- Unique within a project workspace

### **Peak Filtering**
Spectral similarity ignores peaks <5% of base peak intensity (noise reduction).

---

## FAQ

**Q: Can I use the aligned data directly in mass spectrometry software?**  
A: Yes! Export as CEF (Agilent format) or CSV. Most tools accept both.

**Q: Does MetFrag support spectral matching?**  
A: Yes, but use `ppm_rt` align method + CSV export for best results.

**Q: Why does NIST search require manual setup?**  
A: NIST MS/MS Spectral Library API requires institutional access. Once you have credentials, we can automate the right-click search.

**Q: What's the RT@M/Z naming format for?**  
A: Makes compounds self-documenting. `5.23@180.06` tells you: RT 5.23 min, mass 180.06.

---

## Next Steps

1. **Export your consolidated data** as CEF or CSV
2. **Test with MetFrag** using ppm_rt align method
3. **For NIST integration**: Reach out if you have NIST API credentials (institutional access)
4. **Right-click NIST search** can be added as a plugin once API is configured

Questions? Check tool documentation or see below.
