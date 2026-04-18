# CEF Viewer Documentation v1.95

## Table of Contents
1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [User Guide](#user-guide)
4. [Architecture](#architecture)
5. [Module Reference](#module-reference)
6. [Database Schema](#database-schema)
7. [Workflows](#workflows)
8. [API Reference](#api-reference)
9. [Troubleshooting](#troubleshooting)

---

## Overview

The CEF Viewer is a comprehensive tool for managing, analyzing, and consolidating mass spectrometry data in CEF (Compound Exchange Format) files. It provides:

- **Multi-file loading**: Import 10-20 CEF files into a project-local SQLite database
- **Hierarchical browsing**: Tree view of CEF files and their compounds
- **Compound identification**: Automatic detection of identified vs. unidentified compounds
- **Area and Height tracking**: Extract and display measurement values from CEF files
- **Matching and consolidation**: Identify duplicate compounds across files using mass/RT proximity
- **Multiple export formats**: Export consolidated compounds to CEF or CSV

### Key Features

| Feature | Description |
|---------|-------------|
| **Identified Compounds** | Display molecule name from `<Molecule>` elements in CEF files |
| **Unidentified Compounds** | Shown as RT@M/Z format (e.g., "4.08@45.068") |
| **Area & Height** | Extracted from Location attributes: `a=` and `y=` |
| **Hierarchical View** | CEF files → Compounds table with Name, M/Z, RT, Area, Height |
| **Matching** | Proximity-based matching by mass and retention time |
| **Consolidation** | Merge duplicate compounds with confidence scoring |
| **Persistence** | Project-scoped SQLite database (`.ei_fragment_calculator/compounds.db`) |

---

## Quick Start

### 1. Load CEF Files

1. Open the **CEF Viewer** tab in the GUI
2. Click **Load CEF** button
3. Select one or more `.cef` files
4. Wait for import to complete (progress dialog shows status)

### 2. Browse Compounds

The tree view displays:
```
Cal 1_100B_Q-TOF-AllBestHits.cef (45)
├── Metaldehyde          45.0677  4.08   536812   420832
├── Diphenamid           72.0444  20.65  1859347  364124
├── Furalaxyl            95.0126  21.79  1296226  234966
└── ... (42 more)
```

Columns: **Name** | **M/Z** | **RT (min)** | **Area** | **Height**

### 3. View Compound Details

Click any compound to see:
- Identification status (Identified/Unidentified)
- Molecule name and formula (if identified)
- Algorithm and device type
- Full mass spectrum (bar chart)
- Peak table with m/z, intensity, charge, annotation

### 4. Consolidate Duplicates

1. Click **Consolidate**
2. Adjust confidence threshold slider (0.0 - 1.0)
3. Review proposed merges
4. Click **Approve All** to merge

### 5. Export Results

**Export Consolidated:** CEF or CSV format with only merged compounds
**Export Aligned:** CEF or CSV format with all compounds

---

## User Guide

### Loading CEF Files

**Steps:**
1. Click **Load CEF** in toolbar
2. Select file(s) to import
3. Monitor progress in dialog box
4. Status bar shows "Imported X compounds from Y files"

**Database Location:**
```
<project_directory>/.ei_fragment_calculator/compounds.db
```

**What Gets Imported:**
- Compound name (from `<Molecule name="">` or RT@M/Z)
- Molecular mass (m/z value)
- Retention time (RT in minutes)
- Area (from Location `a=` attribute)
- Height (from Location `y=` attribute)
- Algorithm used (FindByAMDIS, MFE, etc.)
- Device type
- Polarity (+/-)
- Full spectrum (all peaks with m/z, intensity, charge, annotation)

### Understanding Compound Names

#### Identified Compounds
- **Source:** `<Compound><Results><Molecule name="...">` element
- **Display:** Molecule name (e.g., "Metaldehyde", "2-Methylphenol")
- **Includes:** Formula (e.g., "C8H16O4")

#### Unidentified Compounds
- **Source:** Compounds without Molecule element
- **Display:** RT@M/Z format (e.g., "4.08@45.068")
  - First number: Retention time in minutes
  - Second number: Mass-to-charge ratio
- **Rationale:** Self-documenting, allows unique identification

### Tree View Columns

| Column | Description | Format |
|--------|-------------|--------|
| **Name** | Compound name or RT@M/Z | String or "4.08@45.068" |
| **M/Z** | Mass-to-charge ratio | "45.0677" |
| **RT** | Retention time | "4.08" (minutes) |
| **Area** | Peak area from CEF | "536812" (integer) |
| **Height** | Peak height from CEF | "420832" (integer) |

### Compound Detail Panel

When you select a compound, the right panel shows:

**Metadata Section:**
```
Type: Identified
Name: Metaldehyde
M/Z: 45.0677
RT: 4.085 min
Molecule: Metaldehyde
Formula: C8H16O4
Algorithm: FindByAMDIS
Device: [device type]
Polarity: +
Consolidated: No
From: Cal 1_100B_Q-TOF-AllBestHits.cef
```

**Spectrum Graph:**
- Interactive bar chart showing peaks
- X-axis: m/z values
- Y-axis: Intensity
- Hover for peak details

**Peaks Table:**
```
M/Z          Intensity    Charge   Annotation
45.0677      12500.5      1        [M]+
44.0598      2340.2       1        [M-H]+
...
```

### Matching Parameters

**Available Methods:**
- `mass_rt`: Mass and retention time (default)
- `ppm_rt`: Parts per million and retention time
- `spectral`: Spectral similarity
- `ppm_spectral`: Combined PPM and spectral

**Adjustable Tolerances:**
| Parameter | Default | Range |
|-----------|---------|-------|
| PPM Tolerance | 5.0 ppm | 0.1 - 100 |
| Da Tolerance | 0.5 | 0.01 - 5 |
| RT Tolerance | 0.2 min | 0.01 - 5 |
| Spectral Threshold | 0.8 | 0.0 - 1.0 |
| Spectral Weight | 0.4 | 0.0 - 1.0 |

### Consolidation Workflow

**Step 1: Identify Duplicates**
```
Consolidate button → Analyze compounds → Find similar matches
```

**Step 2: Preview Results**
```
Confidence Threshold slider → Filter by minimum confidence
Shows: Group name | Confidence score | Master m/z | Master RT
```

**Step 3: Approve Merges**
```
Approve All → Create master compounds → Track sources in database
```

**Step 4: Export Consolidated List**
```
Export Consolidated → Select CEF or CSV format
```

---

## Architecture

### High-Level Design

```
┌─────────────────────────────────────────────────────────┐
│                    GUI Layer (tkinter)                   │
│                   [CEFViewerTab]                         │
│   ┌──────────────┬──────────────┬──────────────┐        │
│   │ File List    │   Spectrum   │  Metadata    │        │
│   │ Tree View    │   Graph      │  + Peaks     │        │
│   └──────────────┴──────────────┴──────────────┘        │
└─────────────────────────────────────────────────────────┘
           ↓                    ↓                    ↓
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  cef_viewer_tab  │  │   cef_matcher    │  │ cef_visualizer   │
│  (UI Control)    │  │  (Analysis)      │  │ (Visualization)  │
└──────────────────┘  └──────────────────┘  └──────────────────┘
           ↓                    ↓
        ┌──────────────────────────────────┐
        │      cef_db.py (Database)        │
        │  SQLite CRUD Operations          │
        │  - Import compounds              │
        │  - Query/Filter                  │
        │  - Consolidate groups            │
        └──────────────────────────────────┘
           ↓
        ┌──────────────────────────────────┐
        │   SQLite Database                │
        │  .ei_fragment_calculator/        │
        │  compounds.db                    │
        └──────────────────────────────────┘
           ↗        ↗        ↗        ↗
┌──────────┘  ┌──────────┘  ┌──────────┘  ┌──────────┐
│ cef_files  │ compounds   │ spectra    │ consolid. │
│ (metadata) │ (master)    │ (peaks)    │ (audit)   │
└────────────┘ ────────────┘ ────────────┘ ─────────┘

      ↕              ↕
   cef_parser.py (XML → Python dataclasses)
   write_cef() (Python dataclasses → XML)
```

### Data Flow

**Import:**
```
CEF File → cef_parser.parse_cef() → CEFCompound objects
         → cef_db.import_compounds() → SQLite storage
```

**Display:**
```
SQLite → cef_db.get_compound() → Dict object
      → cef_viewer_tab._display_compound() → GUI widgets
```

**Export:**
```
SQLite → cef_db.get_all_compounds() → List[Dict]
      → cef_viewer_tab._export_to_cef/csv()
      → CEF or CSV file
```

### Component Overview

| Module | Purpose | Key Classes |
|--------|---------|-------------|
| **cef_parser.py** | Parse CEF XML files | `CEFParser`, `CEFCompound`, `CEFSpectrum`, `CEFPeak`, `CEFLocation` |
| **cef_db.py** | Database operations | `CEFDatabase`, `_DBConnection` |
| **cef_matcher.py** | Matching algorithm | `CEFMatcher`, `CEFConsolidator`, `MatchParameters`, `Match`, `DuplicateGroup` |
| **cef_visualizer.py** | Visualization | `MatchTableViewer` |
| **cef_viewer_tab.py** | GUI tab | `CEFViewerTab` |

---

## Module Reference

### cef_parser.py

**Purpose:** Parse CEF (Compound Exchange Format) XML files into Python dataclasses.

**Key Classes:**

```python
@dataclass
class CEFPeak:
    mz: float              # Mass-to-charge ratio
    intensity: float       # Peak intensity
    charge: int = 1        # Ion charge
    annotation: str = None # Peak label (e.g., "[M]+")
    rt: float = None       # Retention time
    volume: float = None   # Peak volume
    is_saturated: bool = False

@dataclass
class CEFSpectrum:
    spectrum_type: str     # MFE, AMDIS, etc.
    polarity: str = "+"    # + or -
    algorithm: str = ""    # cpdAlgo attribute
    peaks: List[CEFPeak]   # All peaks in spectrum

@dataclass
class CEFLocation:
    molecular_mass: float  # m/z value
    retention_time: float  # RT in minutes
    area: float = None     # Peak area (Location.a)
    height: float = None   # Peak height (Location.y)
    volume: float = None   # Peak volume

@dataclass
class CEFCompound:
    name: str              # Compound name
    location: CEFLocation  # Mass and RT
    spectrum: CEFSpectrum  # Peaks and metadata
    algorithm: str = ""    # Algorithm used
    mppid: str = None      # Molecule PP ID
    device_type: str = None # Device type
    original_xml: str = "" # Original XML (round-trip fidelity)
    molecule_name: str = None       # Identified: molecule name
    molecule_formula: str = None    # Identified: formula
    is_identified: bool = False     # Identification flag
```

**Key Functions:**

```python
def parse_cef(filepath: Path | str) -> List[CEFCompound]:
    """Parse CEF file and return compounds."""
    
def write_cef(filepath: Path | str, compounds: List[CEFCompound]) -> None:
    """Write compounds back to CEF file."""
```

**Parsing Logic:**

1. Search for `<CompoundList>` → `<Compound>` elements
2. For each compound:
   - Extract Location (m/z, RT, area, height)
   - Extract Spectrum (polarity, peaks)
   - Search for Molecule in three locations:
     1. Direct child: `<Molecule>`
     2. Under Results: `<Results/Molecule>`
     3. Any descendant: `.//Molecule`
   - If Molecule found: Mark as identified, extract name and formula
   - If no Molecule: Mark as unidentified, generate RT@M/Z name

---

### cef_db.py

**Purpose:** SQLite database operations for CEF compound storage.

**Key Class:**

```python
class CEFDatabase:
    def __init__(self, project_dir: Path):
        """Initialize database for project."""
        # Creates: <project_dir>/.ei_fragment_calculator/compounds.db
        
    def import_compounds(self, cef_file_path: str, 
                        compounds: List[CEFCompound]) -> Tuple[int, int]:
        """Import compounds from CEF file. Returns (file_id, imported_count)."""
        
    def find_matches(self, compound_id: int, mass_tol: float = 0.5, 
                    rt_tol: float = 0.2) -> List[Dict]:
        """Find compounds matching mass/RT proximity."""
        
    def identify_duplicates(self, mass_tol: float = 0.5, 
                           rt_tol: float = 0.2) -> List[List[int]]:
        """Identify duplicate compound groups by proximity."""
        
    def consolidate_group(self, group_ids: List[int], 
                         master_name: str = None) -> int:
        """Merge duplicate compounds into master. Returns master_id."""
        
    def get_compound(self, compound_id: int) -> Optional[Dict]:
        """Retrieve single compound with all metadata."""
        
    def get_all_compounds(self, limit: int = None) -> List[Dict]:
        """Retrieve all compounds."""
        
    def get_all_cef_files(self) -> List[Dict]:
        """Retrieve all imported CEF files."""
        
    def get_compounds_by_file(self, cef_file_id: int) -> List[Dict]:
        """Retrieve compounds from specific CEF file."""
        
    def delete_compound(self, compound_id: int) -> None:
        """Delete compound and associated data."""
        
    def update_metadata(self, compound_id: int, 
                       metadata_dict: Dict) -> None:
        """Update compound metadata."""
```

**Returned Compound Dict:**

```python
{
    'id': int,
    'name': str,                    # Display name
    'mass': float,                  # m/z value
    'rt': float,                    # Retention time
    'algorithm': str,               # Algorithm used
    'device_type': str,             # Device type
    'polarity': str,                # + or -
    'is_consolidated': bool,        # Merged flag
    'peaks': [                       # List of peaks
        {
            'mz': float,
            'intensity': float,
            'charge': int,
            'annotation': str
        },
        ...
    ],
    'source_files': [str, ...],     # Source CEF filenames
    'molecule_name': str,           # If identified
    'molecule_formula': str,        # If identified
    'is_identified': bool,          # Identification flag
    'area': float,                  # Peak area
    'height': float                 # Peak height
}
```

---

### cef_matcher.py

**Purpose:** Find and match similar compounds using mass/RT proximity.

**Key Classes:**

```python
@dataclass
class MatchParameters:
    method: str = "mass_rt"         # Matching method
    mass_ppm: float = 5.0           # PPM tolerance
    mass_da: float = 0.5            # Da tolerance
    rt_tolerance: float = 0.2       # RT tolerance (min)
    spectral_threshold: float = 0.8 # Spectral similarity
    spectral_weight: float = 0.4    # Weight for spectral
    
    @staticmethod
    def preset_tof() -> MatchParameters:
        """TOF-optimized parameters."""

@dataclass
class Match:
    compound_id_1: int
    compound_id_2: int
    name_1: str
    name_2: str
    mass_1: float
    mass_2: float
    rt_1: float
    rt_2: float
    delta_mass: float               # |mass1 - mass2|
    delta_rt: float                 # |rt1 - rt2|
    confidence: float               # 0.0 - 1.0
    spectral_similarity: float = 0.0

@dataclass
class DuplicateGroup:
    compound_ids: List[int]
    names: List[str]
    confidence: float
    master_mass: float
    master_rt: float
    suggested_master_name: str

class CEFMatcher:
    @staticmethod
    def find_all_matches(compounds: List[Dict], 
                        params: MatchParameters) -> List[Match]:
        """Find all matching compound pairs."""

class CEFConsolidator:
    @staticmethod
    def identify_duplicate_groups(compounds: List[Dict],
                                 params: MatchParameters) -> List[DuplicateGroup]:
        """Identify groups of likely duplicate compounds."""
```

**Matching Methods:**

| Method | Formula | Use Case |
|--------|---------|----------|
| `mass_rt` | `sqrt((Δmass/tol)² + (ΔRT/tol)²)` | Standard matching |
| `ppm_rt` | PPM-adjusted mass + RT | High mass accuracy |
| `spectral` | Cosine similarity of peaks | Similar fragmentation patterns |
| `ppm_spectral` | Combined PPM + spectral | High mass accuracy + patterns |

---

### cef_visualizer.py

**Purpose:** Visualize compound matches in table format.

**Key Class:**

```python
class MatchTableViewer(ttk.Frame):
    def __init__(self, master):
        """Create match table viewer."""
        
    def display_matches(self, matches: List[Dict]) -> None:
        """Display match results in table."""
```

**Match Dict Format:**

```python
{
    'compound_id_1': int,
    'compound_id_2': int,
    'name_1': str,
    'name_2': str,
    'mass_1': float,
    'mass_2': float,
    'rt_1': float,
    'rt_2': float,
    'delta_mass': float,            # |mass1 - mass2|
    'delta_rt': float,              # |rt1 - rt2|
    'confidence': float,            # 0.0 - 1.0
    'spectral_similarity': float    # 0.0 - 1.0
}
```

---

### cef_viewer_tab.py

**Purpose:** Main GUI tab for CEF Viewer functionality.

**Key Class:**

```python
class CEFViewerTab(ttk.Frame):
    def __init__(self, master, settings=None):
        """Initialize CEF Viewer tab."""
        
    # Public methods
    def _load_cef(self) -> None:
        """Load CEF files."""
        
    def _clear_data(self) -> None:
        """Clear all loaded data and reset UI."""
        
    def _consolidate(self) -> None:
        """Run consolidation workflow."""
        
    def _align(self) -> None:
        """Find aligned compounds."""
        
    def _export(self) -> None:
        """Export consolidated compounds."""
        
    def _export_aligned(self) -> None:
        """Export aligned (pre-consolidation) compounds."""
```

**Toolbar Buttons:**

| Button | Action |
|--------|--------|
| **Load CEF** | Open file dialog, import CEF files |
| **Clear** | Delete database, reset all state |
| **Align** | Find matching compounds |
| **Export Aligned** | Export pre-consolidation compounds |
| **Consolidate** | Identify and merge duplicates |
| **Export Consolidated** | Export merged compounds |

---

## Database Schema

### Tables

```sql
-- Track imported CEF files
CREATE TABLE cef_files (
    id INTEGER PRIMARY KEY,
    project_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    filepath TEXT NOT NULL,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, filepath)
);

-- Master compound list
CREATE TABLE compounds (
    id INTEGER PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    molecular_mass_mz REAL NOT NULL,
    retention_time REAL NOT NULL,
    algorithm TEXT,
    device_type TEXT,
    polarity TEXT DEFAULT '+',
    xml_metadata TEXT,              -- JSON: molecule_name, formula, area, height
    is_consolidated BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(molecular_mass_mz, retention_time)
);

-- Compounds from source CEF files
CREATE TABLE compound_sources (
    id INTEGER PRIMARY KEY,
    compound_id INTEGER NOT NULL,
    cef_file_id INTEGER NOT NULL,
    original_name TEXT,
    original_xml TEXT,              -- Original CEF XML for round-trip
    FOREIGN KEY(compound_id) REFERENCES compounds(id),
    FOREIGN KEY(cef_file_id) REFERENCES cef_files(id)
);

-- Mass spectrum peaks
CREATE TABLE spectra (
    id INTEGER PRIMARY KEY,
    compound_id INTEGER NOT NULL,
    peak_mz REAL NOT NULL,
    peak_intensity REAL NOT NULL,
    peak_charge INTEGER DEFAULT 1,
    peak_annotation TEXT,
    peak_volume REAL,
    FOREIGN KEY(compound_id) REFERENCES compounds(id)
);

-- Audit trail of consolidations
CREATE TABLE consolidations (
    id INTEGER PRIMARY KEY,
    master_compound_id INTEGER NOT NULL,
    source_compound_ids TEXT,       -- JSON: [id1, id2, ...]
    confidence REAL,
    match_mass_ppm REAL,
    match_rt_tolerance REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(master_compound_id) REFERENCES compounds(id)
);

-- Indexes
CREATE INDEX idx_mass_rt ON compounds(molecular_mass_mz, retention_time);
CREATE INDEX idx_filename ON cef_files(filename);
CREATE INDEX idx_compound_sources ON compound_sources(compound_id);
CREATE INDEX idx_spectra ON spectra(compound_id);
```

### Metadata JSON Schema

**xml_metadata column in compounds table:**

```json
{
    "molecule_name": "Metaldehyde",
    "molecule_formula": "C8H16O4",
    "is_identified": true,
    "area": 536812.39,
    "height": 420832.19
}
```

---

## Workflows

### Workflow 1: Basic CEF Import and Browse

**Goal:** Load CEF files and view compounds

**Steps:**

```
1. Open CEF Viewer tab
2. Click Load CEF
3. Select Cal 1_100B_Q-TOF-AllBestHits.cef
4. Wait for import (45 compounds)
5. Expand file node in tree view
6. Click any compound to see details
7. Observe area and height values
```

**Expected Result:**
```
Tree displays:
Cal 1_100B_Q-TOF-AllBestHits.cef (45)
├── Metaldehyde               45.0677   4.08    536812    420832
├── Diphenamid                72.0444  20.65   1859347    364124
...
```

---

### Workflow 2: Consolidate Duplicate Compounds

**Goal:** Merge duplicate compounds across files

**Steps:**

```
1. Load multiple CEF files (2-3 files)
2. Click Consolidate
3. System analyzes compounds:
   - Compares mass/RT for all pairs
   - Calculates confidence scores
   - Groups likely duplicates
4. Adjust confidence threshold slider
5. Review proposed merges
6. Click Approve All
7. Database updated with consolidated flag
```

**Expected Result:**
```
Consolidation Preview:
Group 1: Metaldehyde (3 compounds)
  ├─ file1.cef: Metaldehyde 45.0677
  ├─ file2.cef: Metaldehyde peak 45.0675
  └─ file3.cef: MET compound 45.0679
  Confidence: 0.98 [Merge] [Skip]
```

---

### Workflow 3: Export for Downstream Analysis

**Goal:** Export consolidated compounds for unknown identification

**Steps:**

```
1. Consolidate compounds (see Workflow 2)
2. Click Export Consolidated
3. Choose format:
   - CEF: Full compound data for re-analysis
   - CSV: Spreadsheet format for scripts
4. Select output location
5. File created with consolidated compounds only
```

**CSV Export Example:**
```csv
id,name,mass,rt,area,height,algorithm,device_type,polarity,is_consolidated,peak_count,source_files
2,Metaldehyde,45.067700,4.085,536812,420832,FindByAMDIS,,+,Yes,34,"file1.cef, file2.cef"
40,Diphenamid,72.044420,20.650,1859347,364124,FindByAMDIS,,+,Yes,159,"file1.cef"
```

**CEF Export Example:**
```xml
<?xml version='1.0' encoding='utf-8'?>
<CEF version="1.0.0.0">
  <CompoundList>
    <Compound algo="FindByAMDIS">
      <Location m="45.0677" rt="4.085" a="536812.39" y="420832.19" name="Metaldehyde"/>
      <Spectrum type="MFE" cpdAlgo="FindByAMDIS">
        <MSDetails p="+" z="1"/>
        <MSPeaks>
          <p x="45.0677" y="12500.5" z="1"/>
          <p x="44.0598" y="2340.2" z="1"/>
          ...
        </MSPeaks>
      </Spectrum>
    </Compound>
    ...
  </CompoundList>
</CEF>
```

---

### Workflow 4: Multi-file Alignment

**Goal:** Find matches across multiple CEF files

**Steps:**

```
1. Load 10+ CEF files
2. Adjust tolerance parameters:
   - PPM Tolerance: 5 ppm
   - Da Tolerance: 0.5
   - RT Tolerance: 0.2 min
3. Click Align
4. System finds all matching compound pairs
5. Visualization shows heat map/network
6. Review confidence scores
7. Optionally export aligned compounds
```

**Match Output Example:**
```
Compound 1          Compound 2          ΔMass    ΔRT    Confidence
Metaldehyde (f1)    Metaldehyde (f2)    0.0002   0.01   0.99
Metaldehyde (f1)    MET peak (f3)       0.0012   0.05   0.95
Diphenamid (f1)     Diphenamid (f2)     0.0001   0.02   0.98
```

---

## API Reference

### High-Level Usage

```python
from pathlib import Path
from ei_fragment_calculator.cef_parser import parse_cef
from ei_fragment_calculator.cef_db import CEFDatabase
from ei_fragment_calculator.cef_matcher import CEFMatcher, MatchParameters

# 1. Parse CEF file
cef_file = Path("Cal 1_100B_Q-TOF-AllBestHits.cef")
compounds = parse_cef(cef_file)
print(f"Parsed {len(compounds)} compounds")

# 2. Create database and import
db = CEFDatabase(Path.cwd())
file_id, imported = db.import_compounds(str(cef_file), compounds)
print(f"Imported {imported} compounds")

# 3. Get all compounds
all_compounds = db.get_all_compounds()
for compound in all_compounds[:5]:
    print(f"{compound['name']}: {compound['mass']:.4f} m/z")

# 4. Find matches
params = MatchParameters.preset_tof()
matches = CEFMatcher.find_all_matches(all_compounds, params)
print(f"Found {len(matches)} matches")

# 5. Identify duplicates
groups = CEFConsolidator.identify_duplicate_groups(all_compounds, params)
for group in groups[:3]:
    print(f"Group: {group.names} (confidence: {group.confidence:.2f})")

# 6. Consolidate
for group in groups:
    db.consolidate_group(group.compound_ids, group.suggested_master_name)

# 7. Export
consolidated = [c for c in db.get_all_compounds() if c['is_consolidated']]
print(f"Consolidated {len(consolidated)} compounds")
```

### Common Tasks

**Get compound with all metadata:**
```python
compound = db.get_compound(compound_id)
print(f"Name: {compound['name']}")
print(f"Mass: {compound['mass']:.4f} m/z")
print(f"RT: {compound['rt']:.2f} min")
print(f"Area: {compound.get('area', 'N/A')}")
print(f"Height: {compound.get('height', 'N/A')}")
print(f"Identified: {compound['is_identified']}")
if compound['is_identified']:
    print(f"Molecule: {compound['molecule_name']}")
    print(f"Formula: {compound['molecule_formula']}")
```

**Find similar compounds to a reference:**
```python
ref_compound = db.get_compound(ref_id)
matches = db.find_matches(
    ref_id,
    mass_tol=0.5,  # Da tolerance
    rt_tol=0.2     # min tolerance
)
for match in matches:
    print(f"{match['name']}: Confidence {match['confidence']:.2f}")
```

**Export compounds to CSV:**
```python
import csv
from pathlib import Path

compounds = db.get_all_compounds()
output_path = Path("export.csv")

with open(output_path, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=[
        'id', 'name', 'mass', 'rt', 'area', 'height',
        'algorithm', 'is_consolidated', 'source_files'
    ])
    writer.writeheader()
    for compound in compounds:
        source_files = ', '.join(compound.get('source_files', []))
        writer.writerow({
            'id': compound['id'],
            'name': compound['name'],
            'mass': f"{compound['mass']:.6f}",
            'rt': f"{compound['rt']:.3f}",
            'area': compound.get('area', ''),
            'height': compound.get('height', ''),
            'algorithm': compound['algorithm'] or '',
            'is_consolidated': 'Yes' if compound['is_consolidated'] else 'No',
            'source_files': source_files
        })
```

---

## Troubleshooting

### Issue: CEF file doesn't load

**Symptoms:** Import fails or no compounds appear

**Causes & Solutions:**
1. **Invalid XML format**
   - Verify CEF file is valid XML
   - Open in text editor, check for syntax errors
   - Try a different CEF file to isolate

2. **Missing CompoundList element**
   - CEF file must have `<CompoundList>` section
   - Check file structure with XML viewer

3. **No Location element**
   - Each `<Compound>` must have `<Location>` element
   - Verify attributes: m (mass), rt (retention time)

**Debugging:**
```python
from ei_fragment_calculator.cef_parser import CEFParser
import traceback

try:
    compounds = CEFParser.parse_file(Path("file.cef"))
    print(f"Success: {len(compounds)} compounds")
except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc()
```

---

### Issue: Compounds show as unidentified

**Symptoms:** All compounds display as "RT@M/Z" format

**Causes & Solutions:**
1. **No Molecule element in CEF**
   - Verify CEF file has identified compounds
   - Check XML for `<Molecule name="..." formula="...">` elements
   - Element can be under `<Compound>`, `<Results>`, or deeper nesting

2. **Molecule element naming mismatch**
   - Parser searches for attribute: `name=`
   - Verify XML uses lowercase "name" attribute

**Debugging:**
```python
import xml.etree.ElementTree as ET

tree = ET.parse(Path("file.cef"))
root = tree.getroot()

for i, comp in enumerate(root.findall(".//Compound")[:3]):
    mol = comp.find(".//Molecule")
    if mol is not None:
        print(f"Compound {i}: {mol.get('name')} ({mol.get('formula')})")
    else:
        print(f"Compound {i}: No Molecule element")
```

---

### Issue: Area or Height values missing

**Symptoms:** Area and Height columns show blank

**Causes & Solutions:**
1. **Missing Location attributes**
   - Location element must have: `a=` (area), `y=` (height)
   - Values are optional in CEF spec; some files may not have them

2. **Database not updated**
   - Clear database and re-import
   - Old imports may not have stored area/height

**Debugging:**
```python
import xml.etree.ElementTree as ET

tree = ET.parse(Path("file.cef"))
root = tree.getroot()

for i, comp in enumerate(root.findall(".//Compound")[:3]):
    loc = comp.find("Location")
    if loc is not None:
        print(f"Compound {i}:")
        print(f"  m={loc.get('m')}, rt={loc.get('rt')}")
        print(f"  a={loc.get('a')}, y={loc.get('y')}")
```

---

### Issue: Database file grows too large

**Symptoms:** Slow performance, large disk usage

**Solutions:**
1. **Archive old projects**
   - Database files are project-specific
   - Move unused projects to archive folder
   - Delete `.ei_fragment_calculator/` folders

2. **Clear database**
   - Click **Clear** button to delete and reset
   - Remove all compounds and start fresh

3. **Export and archive**
   - Export consolidated compounds to CSV
   - Store in archive location
   - Delete CEF Viewer database

---

### Issue: Consolidation finds no matches

**Symptoms:** "No duplicates found" after consolidation

**Causes & Solutions:**
1. **Tolerance too strict**
   - Increase PPM tolerance
   - Increase Da tolerance
   - Increase RT tolerance

2. **No actual duplicates**
   - Compounds may be genuinely different
   - Different files may have different sets

3. **Confidence threshold too high**
   - Lower threshold slider to show more matches
   - Review at lower confidence levels

**Example: Adjusting tolerances**
```
Default: PPM 5, Da 0.5, RT 0.2 min
Try: PPM 10, Da 1.0, RT 0.5 min
For high variance: PPM 20, Da 2.0, RT 1.0 min
```

---

### Issue: Export file is incomplete

**Symptoms:** Exported CEF/CSV missing compounds

**Causes & Solutions:**
1. **Exporting consolidated only**
   - "Export Consolidated" only exports merged compounds
   - Use "Export Aligned" for all compounds

2. **No compounds to export**
   - Check that compounds were actually imported
   - Verify in tree view before exporting

3. **Export format mismatch**
   - CEF export: for CEF-compatible tools
   - CSV export: for spreadsheet analysis
   - Choose based on downstream usage

---

## Performance Considerations

### Typical Performance

| Operation | File Count | Compounds | Time |
|-----------|-----------|-----------|------|
| Load CEF files | 5 | 50-100 | <1 sec each |
| Import to DB | 5 | 500 | ~5 secs |
| Identify duplicates | - | 500 | <200 ms |
| Consolidate groups | - | 10 groups | ~100 ms |
| Export to CSV | - | 500 | ~200 ms |
| Export to CEF | - | 500 | ~500 ms |

### Optimization Tips

1. **Use selective filtering**
   - Filter compounds before consolidation
   - Reduce match calculation scope

2. **Batch operations**
   - Import all files at once, not sequentially
   - Consolidate all groups in one operation

3. **Archive old data**
   - Move completed projects to archive
   - Keep active projects with <5 files

---

## Integration with Downstream Tools

### EI Fragment Calculator Workflow

The CEF Viewer feeds consolidated compound lists to the EI Fragment Calculator:

```
CEF Files (10-20) → CEF Viewer → Consolidation
                                       ↓
                           Master Compound List
                                       ↓
                    Export to CSV/CEF for downstream
                                       ↓
                      EI Fragment Calculator
                      (Unknown identification)
```

### Expected Data Format

**CSV Export for downstream:**
```
id,name,mass,rt,area,height,algorithm,device_type
1,Metaldehyde,45.0677,4.085,536812,420832,FindByAMDIS,
2,Diphenamid,72.0444,20.650,1859347,364124,FindByAMDIS,
```

---

## Version History

### v1.95 (Current)
- ✓ CEF Viewer tab implementation
- ✓ Identified vs. unidentified compound detection
- ✓ Area and Height column support
- ✓ Consolidation with confidence scoring
- ✓ CSV and CEF export formats
- ✓ SQLite database persistence
- ✓ Compound matching and visualization

---

## Support & Resources

### Contact
For issues or feature requests, refer to the INTEGRATION_GUIDE.md

### Testing
Verify installation with test CEF file:
```
ei-fragment-calculator/tests/test_cef_integration.py
```

### Example Files
Sample CEF file:
```
Cal 1_100B_Q-TOF-AllBestHits.cef (45 compounds, 348 KB)
```

---

## Glossary

| Term | Definition |
|------|-----------|
| **CEF** | Compound Exchange Format - XML-based format for mass spectrometry data |
| **M/Z** | Mass-to-charge ratio, primary identifier for compounds |
| **RT** | Retention time in minutes, secondary identifier |
| **Area** | Peak area from Location element (a=) |
| **Height** | Peak height from Location element (y=) |
| **Polarity** | Ion charge: + (positive) or - (negative) |
| **PPM** | Parts per million, unit of mass measurement accuracy |
| **Da** | Dalton, unit of atomic mass |
| **Consolidation** | Process of merging duplicate compounds |
| **Confidence** | Score (0-1) indicating match quality |
| **RT@M/Z** | Self-documenting name format for unidentified compounds |

