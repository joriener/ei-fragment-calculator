# Complete EI Fragment Calculator Workflow & Pipeline

**Date:** 2026-04-17  
**Version:** 1.8.0 → 1.9.0 (post-NIST enhancements)  
**Scope:** Full end-to-end pipeline with 5 NIST algorithm gaps integrated  

---

## Table of Contents

1. [Workflow Overview (ASCII Diagram)](#1-workflow-overview-ascii-diagram)
2. [Detailed Stage Descriptions](#2-detailed-stage-descriptions)
3. [Data Structures (per stage)](#3-data-structures-per-stage)
4. [Integration Points for 5 Gaps](#4-integration-points-for-5-gaps)
5. [Confidence Scoring (4-Pass Model)](#5-confidence-scoring-4-pass-model)
6. [Decision Trees & Thresholds](#6-decision-trees--thresholds)
7. [Error Handling & Fallbacks](#7-error-handling--fallbacks)
8. [Testing & Validation Points](#8-testing--validation-points)

---

## 1. Workflow Overview (ASCII Diagram)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         INPUT PARSING (input_reader.py)                      │
│  .sdf / .msp / .mspec / .jdx / .csv → normalized compound + peak list       │
└────────────────────────┬────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    STAGE 0: ENRICHMENT (Optional)                            │
│  ├─ --fetch-structures: PubChem → 2D MOL + SMILES + InChIKey + CID + MW    │
│  └─ --merge-structures: Copy MOL blocks from reference SDF by name          │
└────────────────────────┬────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              STAGE 1: SPECTRAL LIBRARY LOOKUP (Optional)                    │
│  --nist-lookup: Query InChIKey → NIST WebBook / SDBS                       │
│  If HIT: assign formulas (conf=0.99) → skip Stages 2-6 for matched peaks   │
│  If MISS: continue to Stage 2                                              │
└────────────────────────┬────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              STAGE 2: PARENT SETUP (per compound)                           │
│  ├─ Parse formula → composition dict                                        │
│  ├─ Compute exact mass (neutral) + ion m/z (M+•, -electron)                │
│  ├─ Calculate DBE (degree of unsaturation)                                 │
│  ├─ Parse 2D MOL block → heavy-atom adjacency graph (no explicit H)        │
│  ├─ [NEW] Compute bond dissociation rates (0–120 scale) → A1               │
│  ├─ Classify compound type (aromatic, heteroatom, acyclic, etc.)           │
│  ├─ E6: Molecular ion confirmation + peaks-above-M+• warning               │
│  └─ Store parent_context = {formula, mz, dbe, graph, rates, class}         │
└────────────────────────┬────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│        STAGE 3: STRUCTURAL FRAGMENT GENERATION (if MOL block given)         │
│  ├─ Tier 2.1 Homolytic cleavage (C-C, C-H bonds)                           │
│  ├─ Tier 2.2 Alpha cleavage (heteroatom-adjacent bonds)                    │
│  ├─ Tier 2.3 Inductive cleavage (electron-withdrawing groups)              │
│  ├─ Tier 2.4 McLafferty (γ-H rearrangement + C=C cleavage)                 │
│  ├─ Tier 2.5 Retro-Diels-Alder (6-membered ring + C=C)                     │
│  ├─ [NEW] Weight each rule by A2 (reaction probability)                    │
│  ├─ Tier 2.6 Secondary fragmentation (depth-1 recursive, all rules)        │
│  │           [NEW] Track step-by-step rates (A4)                           │
│  └─ → structural_whitelist = {formula → mechanism + rate + confidence}     │
└────────────────────────┬────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│        STAGE 4: FORMULA ENUMERATION (per peak, after intensity filter)      │
│  ├─ Pre-filter: drop peaks < 2% of base peak (E4)                          │
│  ├─ For each peak m/z:                                                     │
│  │   └─ find_fragment_candidates(mz, parent, tolerance_ppm)                │
│  │       ├─ Branch-and-bound over element counts (atom conservation)       │
│  │       ├─ Mass window: nominal_mz ± tolerance + electron correction      │
│  │       ├─ DBE validity: ≥0, multiple of 0.5, ≤ parent DBE + 1           │
│  │       └─ Store: mass_error_ppm, mass_defect_per_da (MDD)               │
│  └─ → candidates = {mz: [{formula, composition, mz_exact, mz_error, ...}]}│
└────────────────────────┬────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│        STAGE 5A: CHEMICAL VALIDITY FILTERS (per candidate)                  │
│  ├─ F1  Nitrogen rule (odd/even electron awareness)                        │
│  ├─ F2  H-deficiency check (DBE/C ≤ 1.0)                                   │
│  ├─ F3  Lewis & Senior rules (ring count, valence)                         │
│  ├─ F4  Isotope pattern score (±30 ppm tolerance on M+1)                   │
│  ├─ F5  Ring-count upper bound (from SMILES if available)                 │
│  ├─ F6  RDKit validation (optional --rdkit flag)                           │
│  ├─ Cl/Br M+2 hard constraint (filter_passed = False if violated)          │
│  ├─ Plausible neutral validation (element budget for loss)                 │
│  └─ 7 Golden Rules (Kind & Fiehn 2007 element ratios)                      │
└────────────────────────┬────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│    STAGE 5B: FRAGMENTATION RULE ANNOTATION (--fragmentation-rules)          │
│  ├─ Tier 1: Neutral loss from M+• (36 known losses)                        │
│  │           {H2O, CO, CO2, NH3, HCN, CH3, C2H5, ..., Si(CH3)3}           │
│  │           → fragmentation_rule = "loss_H2O", rule_score = 0.1           │
│  ├─ Tier 2: Structural whitelist (from Stage 3)                            │
│  │           → fragmentation_rule = "homolytic_C_C", rule_score = 0.0      │
│  │           [NEW] Apply A1 bond rates to rerank candidates               │
│  └─ --strict-structure: filter_passed = False if no rule matched           │
└────────────────────────┬────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│        STAGE 6: CONFIDENCE SCORING (--confidence flag)                      │
│  ├─────────────────────────────────────────────────────────────────────────┤
│  │ PASS 1 — Per-Candidate Individual Scoring                              │
│  │  A  M+1 isotope score: pred vs I(mz+1)/I(mz)                           │
│  │     └─ Disabled below 50% parent mass (M+1 guard)                       │
│  │  B  Fragmentation score: 0.0 if rule matched, 1.0 if not               │
│  │  C  [NEW] Reaction probability bonus (A2): +0.20 if high-freq type    │
│  │  D  DBE penalty: −0.25 if frag_DBE > parent_DBE + 1                    │
│  │  E  Stable-ion bonus: +0.35 if in stable_ions.py library               │
│  │  F  Even/odd electron: weights by mass range (low mass: prefer odd)     │
│  │  G  Mass accuracy: 1 − |Δm| / tol                                       │
│  │  H  Filter pass: 1.0 if ok, 0.3 if failed                              │
│  │  → confidence_1 = weighted_sum(A–H)  ∈ [0.0, 1.0]                      │
│  │                                                                          │
│  ├─────────────────────────────────────────────────────────────────────────┤
│  │ PASS 2 — Neutral-Loss Inter-Peak Cross-Check                           │
│  │  For each pair (mz_1, mz_2) where mz_1 > mz_2:                         │
│  │    delta = mz_1 − mz_2                                                  │
│  │    If delta matches a known neutral loss:                               │
│  │      AND candidate_1.formula − candidate_2.formula == loss_composition  │
│  │      → boost confidence of both by +0.15                               │
│  │      → add evidence_tag = "NEUTRAL_LOSS_PAIR(H2O)" etc.                │
│  │  → re-rank candidates_per_mz by confidence_2 DESC                      │
│  │                                                                          │
│  ├─────────────────────────────────────────────────────────────────────────┤
│  │ PASS 3 — Complementary-Ion Pair Check                                  │
│  │  For each mz_frag with top-ranked candidate:                            │
│  │    mz_complementary = parent_mz − mz_frag                               │
│  │    If mz_complementary exists in spectrum:                              │
│  │      AND mz_complementary's top candidate + mz_frag's formula           │
│  │          = parent_formula (atom conservation check)                      │
│  │      AND both are even-electron (or both odd-electron)                  │
│  │      → boost both by +0.25                                             │
│  │      → add evidence_tag = "COMPLEMENTARY_ION_PAIR"                      │
│  │  → re-rank by confidence_3 DESC                                        │
│  │                                                                          │
│  ├─────────────────────────────────────────────────────────────────────────┤
│  │ [NEW] PASS 4 — Kendrick Homologous Series (E1)                          │
│  │  For each delta ∈ {14 (CH2), 26 (C2H2), 18 (H2O)}:                     │
│  │    Find chains of 3+ peaks spaced by delta m/z:                         │
│  │      mz, mz+14, mz+28, ... or mz, mz+26, mz+52, ... etc.               │
│  │    For consecutive pair (mz_i, mz_i+delta):                             │
│  │      If top_candidate(mz_i+delta).formula − top(mz_i).formula            │
│  │         == composition(delta):                                          │
│  │        Series is internally consistent                                  │
│  │    If all pairs in chain are consistent:                                │
│  │      → boost all members by +0.15                                      │
│  │      → add evidence_tag = "SERIES(CH2)" or "SERIES(C2H2)" or "..."     │
│  │  → re-rank by confidence_4 DESC                                        │
│  │                                                                          │
│  └─────────────────────────────────────────────────────────────────────────┘
│  Final: confidence = confidence_4, sorted DESC per peak                    │
└────────────────────────┬────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│            STAGE 7: RANKING & CANDIDATE SELECTION                           │
│  Without --confidence:                                                       │
│    ├─ Sort by MDD (mass-defect-per-Da) ASC                                 │
│    └─ Then by |Δm| ASC                                                     │
│  With --confidence:                                                         │
│    └─ Sort by confidence DESC                                              │
│  Selection logic:                                                           │
│    ├─ Default: return all candidates per peak (ranked)                     │
│    ├─ --best-only: take top candidate per peak                            │
│    └─ --confidence-threshold N: drop peak if confidence < N                │
└────────────────────────┬────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         STAGE 8: OUTPUT GENERATION                          │
│  ├─ Console: tabular results (mz | formula | confidence | evidence_tags)   │
│  ├─ --output FILE: write console output to text file                       │
│  ├─ --output-sdf FILE: write annotated SDF with exact masses per peak      │
│  └─ --output-msp FILE: write annotated MSP with formulas as comments       │
└────────────────────────┬────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            END (Success)                                     │
│  All peaks assigned (or marked unassigned); confidence scores available      │
└─────────────────────────────────────────────────────────────────────────────┘

Legend:
  [NEW] = New component or enhancement from NIST gaps
  A1–A5 = NIST gap numbers (see NIST_ALGORITHM_GAPS.md)
  F1–F6 = Chemical validity filters
  E1–E6 = Additional enhancements
  --flag = Command-line option
```

---

## 2. Detailed Stage Descriptions

### STAGE 0: Enrichment (Optional)

**Trigger:** `--fetch-structures` or `--merge-structures`

**Input:** Compound records with name/CASNO but no MOL block

**Process:**

1. **PubChem fetch** (if `--fetch-structures`):
   - Query by CASNO → name → formula
   - Fetch: 2D MOL block, SMILES, InChIKey, CID, monoisotopic mass
   - Validate formula against PubChem MonoisotopicMass
   - If formula mismatch: log warning, use PubChem formula

2. **MOL merger** (if `--merge-structures`):
   - Load reference SDF
   - For each input record, find match by name in reference
   - Copy MOL block from reference to input record

**Output:** Same records, now with MOL blocks

**Error handling:**
- PubChem timeout/HTTP 429 → retry 3×, then skip
- Name not found → log, skip enrichment for this record
- Formula mismatch → use PubChem formula, flag as `source=pubchem_override`

---

### STAGE 1: Spectral Library Lookup (Optional)

**Trigger:** `--nist-lookup`

**Input:** Compounds with InChIKey (from formula or PubChem fetch)

**Process:**

1. Query NIST WebBook by InChIKey
   - If HIT: returns `{nominal_mz: formula_str, ...}` for all peaks
   - Mark all returned peaks: `confidence=0.99, evidence=NIST_LIBRARY`
   - **Skip Stages 2–6 for these peaks**
   - Continue to next compound

2. If MISS: query SDBS (AIST) as fallback
   - Same return format
   - Confidence: 0.95 (slightly lower than NIST)

3. If both miss: continue to Stage 2

**Output:** Partially assigned compound (some peaks from library, others queued for Stages 2–6)

**Error handling:**
- InChIKey missing → skip lookup
- Network timeout → fallback to Stage 2
- Library entry malformed → log, skip this peak

---

### STAGE 2: Parent Setup

**Trigger:** Every compound (always runs)

**Input:** Compound record with formula (required) and MOL block (optional)

**Process:**

#### 2a. Formula Parsing
```
formula_str = "C7H15NO2"
↓
composition = {"C": 7, "H": 15, "N": 1, "O": 2}
```

#### 2b. Exact Mass Calculation
```
mass_neutral = sum(MONOISOTOPIC_MASSES[el] * count for el, count in composition)
             = (7 × 12.000000) + (15 × 1.007825) + (1 × 14.003074) + (2 × 15.994915)
             = 84.000000 + 15.117375 + 14.003074 + 31.989830
             = 145.110279 Da
```

#### 2c. Ion m/z Calculation
```
EI positive mode (default):
  m/z_ion = mass_neutral − m_electron
          = 145.110279 − 0.000549
          = 145.109730 m/z    (this is M+•, the molecular ion radical cation)

EI negative mode (--electron-mode add):
  m/z_ion = mass_neutral + m_electron
```

#### 2d. DBE Calculation
```
DBE = (2C + 2 + N − H − X) / 2
    = (2×7 + 2 + 1 − 15 − 0) / 2
    = (14 + 2 + 1 − 15) / 2
    = 2 / 2
    = 1.0   (1 degree of unsaturation: could be 1 ring or 1 double bond)
```

#### 2e. MOL Block Parsing (if present)
```
V2000 MOL block
  ↓
parse_mol_block_full(mol_text)
  ↓
Adjacency graph:
  - Nodes: heavy atoms (C, N, O, S, F, Cl, Br, I, P, Si, ...)
  - Edges: bonds {(atom_i, atom_j, bond_type, aromatic), ...}
  - NO explicit H atoms stored (PubChem style)

atoms = [
  {index: 0, symbol: 'C', formal_charge: 0, aromatic: False, ...},
  {index: 1, symbol: 'C', formal_charge: 0, aromatic: False, ...},
  ...
]
bonds = [
  (0, 1, 'single', False),
  (1, 2, 'single', False),
  (2, 3, 'double', False),  # C=O
  ...
]
```

#### 2f. [NEW] Bond Dissociation Rate Calculation (A1)

**New component:** `bond_thermochemistry.py`

For each bond, compute a dissociation rate 0–120 based on:
- Bond type (single, double, triple, aromatic)
- Heteroatom neighbors (e.g., C-O weaker than C-C)
- Ring strain (small rings more reactive)
- Electron-withdrawing groups (inductive effect)

```python
# Pseudocode
for bond_id, (atom_i, atom_j, bond_type, aromatic) in bonds:
    # Base BDE estimate from NIST WebBook analogs
    bde_base = BDE_ESTIMATES[(sym_i, sym_j, bond_type, aromatic)]
    
    # Heteroatom boost (C-O, C-N more reactive)
    if is_heteroatom(sym_i) or is_heteroatom(sym_j):
        bde_base *= 0.80  # Weaker = faster dissociation
    
    # Ring strain penalty (small rings dissociate faster)
    if in_ring_size_3_4(bond_id):
        bde_base *= 0.70
    elif in_ring_size_5_6(bond_id):
        bde_base *= 0.85
    
    # Electron-withdrawing group (e.g., next to Cl, NO2, CF3)
    if has_ewg_neighbor(atom_i) or has_ewg_neighbor(atom_j):
        bde_base *= 0.75
    
    # Normalize to 0–120 scale (weakest ≈ 120, strongest ≈ 0)
    rate = normalize_to_scale(bde_base, min_val=10, max_val=120)
    
    bond_rates[bond_id] = rate

# Sort bonds by rate (descending)
priority_bonds = sorted(bond_rates.items(), key=lambda x: x[1], reverse=True)
```

**Output:** `bond_rates = {bond_id: rate_0_120, ...}`

**Used in Stage 3:** Prioritize which bonds to break first

#### 2g. Compound Classification
```
Detect compound type:
  - aromatic (if ≥3 aromatic rings)
  - heteroatom (N, S, halogen present)
  - acyclic (DBE=0, no rings)
  - cyclic (DBE>0, has rings)
  - carbohydrate (C:H:O ratio ≈ 1:2:1)
  - peptide (multiple C=O, N-C)
  - lipid (long alkyl chain + ester)
  
→ class_label = "aromatic_amine" or "aliphatic_ketone" or ...

Look up CLASS_TEMPLATES[class_label] → template fragments
Example:
  "aromatic_amine" → {benzene, pyridine, aniline cation, ...}
```

#### 2h. Molecular Ion Confirmation (E6)

```
Check if parent m/z is present in spectrum:
  If M+• peak present:
    → confidence boost for all candidates (library is curated)
  If M+• missing but other peaks exist:
    → Check if any peak > M+•
       If yes, emit warning: "Peaks above M+•; possible contamination or misassignment"
    → If M+• + isotope pattern detectable:
       → Still OK (sometimes weak in high DBE compounds)
```

#### 2i. Output from Stage 2

```python
parent_context = {
    'formula': 'C7H15NO2',
    'composition': {'C': 7, 'H': 15, 'N': 1, 'O': 2},
    'mass_exact': 145.110279,
    'mz_ion': 145.109730,
    'dbe': 1.0,
    'atoms': [...],            # Heavy-atom nodes
    'bonds': [...],            # Edge list
    'bond_rates': {0: 95, 1: 87, 2: 120, ...},  # [NEW] A1
    'class': 'aliphatic_amine',
    'has_mol_block': True,
    'mol_ion_present': True,
    'mol_ion_abundance': 5.2,
    'has_peaks_above_mol_ion': False,
}
```

---

### STAGE 3: Structural Fragment Generation

**Trigger:** If MOL block present and `--fragmentation-rules` flag

**Input:** `parent_context` from Stage 2

**Process:**

For each fragmentation rule type (homolytic, alpha, inductive, McLafferty, RDA, secondary):

#### 3a. Homolytic Cleavage (C-C, C-H bonds)

```python
def enumerate_homolytic_cleavages(atoms, bonds, bond_rates):
    """
    Break single non-ring bonds → two radical products (each has odd electrons).
    """
    fragments = []
    
    # [NEW] A1: prioritize by bond dissociation rate
    sorted_bonds = sorted(
        [(bid, rate) for bid, rate in bond_rates.items() if is_single_bond(bid)],
        key=lambda x: x[1], reverse=True
    )
    
    for bond_id, rate in sorted_bonds:
        atom_i, atom_j = bond_id
        frag_i = {atom_i, ...connected atoms...}
        frag_j = {atom_j, ...connected atoms...}
        
        # Compute H-adjusted compositions
        comp_i = compute_fragment_composition(frag_i, atoms, bonds)
        comp_j = compute_fragment_composition(frag_j, atoms, bonds)
        
        # Both fragments are odd-electron (radicals) after loss of C-C single bond
        fragments.append({
            'formula': hill_formula(comp_i),
            'composition': comp_i,
            'is_radical': True,
            'pathways': [
                {
                    'rule_type': 'homolytic_cleavage',
                    'bond_id': bond_id,
                    'step': 1,
                    'rate': rate,  # [NEW] A1
                    'description': f'C-C bond cleavage (rate {rate})',
                }
            ],
            'is_primary': True,
            'evidence': ['structural_rule'],
        })
    
    return fragments
```

#### 3b. Alpha Cleavage (heteroatom-directed)

```python
def apply_alpha_cleavage(atoms, bonds, bond_rates):
    """
    Break α-bond adjacent to heteroatom (N, O, S, X) → stable cation.
    Example: R-CH2-O-R' → [R-CH2-O]+ (charge on O)
    """
    fragments = []
    
    # Find heteroatoms
    heteroatoms = [atom for atom in atoms if atom['symbol'] in {'N', 'O', 'S', 'F', 'Cl', 'Br', 'I', 'P'}]
    
    for hetero_atom in heteroatoms:
        # Find bonds to this heteroatom
        for neighbor_atom in neighbors(hetero_atom):
            # Cleave bond between neighbor and heteroatom
            # Positive charge stays with heteroatom
            
            frag_comp = compute_fragment(hetero_atom, neighbor_atom)
            fragments.append({
                'formula': hill_formula(frag_comp),
                'composition': frag_comp,
                'is_radical': False,  # Even-electron cation
                'charge': +1,
                'pathways': [
                    {
                        'rule_type': 'alpha_cleavage',
                        'heteroatom': hetero_atom['symbol'],
                        'step': 1,
                        'rate': bond_rates.get((neighbor_atom, hetero_atom), 50),
                        'description': f'α-cleavage next to {hetero_atom["symbol"]}',
                    }
                ],
                'is_primary': True,
            })
    
    return fragments
```

#### 3c. Inductive Cleavage

(Conceptually similar: bond adjacent to electron-withdrawing group)

#### 3d. McLafferty (γ-H Rearrangement)

```python
def apply_mclafferty(atoms, bonds, bond_rates):
    """
    Requires:
      1. C=O (carbonyl)
      2. γ-hydrogen available (on third atom from C)
      3. Even-electron fragment (with rearrangement)
    """
    fragments = []
    
    # Find all C=O double bonds
    for bond_id, (atom_i, atom_j, bond_type, _) in enumerate(bonds):
        if bond_type != 'double':
            continue
        
        c_atom, o_atom = (atom_i, atom_j) if atoms[atom_i]['symbol'] == 'C' else (atom_j, atom_i)
        
        # Find γ-position (3 bonds away from C)
        for gamma_atom in find_gamma_atoms(c_atom):
            if not has_hydrogen(gamma_atom):  # [FIXED] use implicit H, not explicit
                continue
            
            # Rearrangement: H transfers from γ to O
            # Fragment: [C=O-H]+ (enol cation, even-electron)
            enol_comp = {
                'C': atoms[c_atom]['C'] + 1,
                'H': atoms[o_atom]['H'] + 1,  # +1 from γ-H transfer
                'O': atoms[o_atom]['O'],
                ...
            }
            neutral_comp = subtract_compositions(parent, enol_comp)
            
            fragments.append({
                'formula': hill_formula(enol_comp),
                'composition': enol_comp,
                'neutral_loss': neutral_comp,
                'is_radical': False,  # Even-electron after rearrangement
                'pathways': [
                    {
                        'rule_type': 'mclafferty',
                        'c_atom_idx': c_atom,
                        'gamma_atom_idx': gamma_atom,
                        'step': 1,
                        'rate': bond_rates.get((c_atom, o_atom), 60),
                        'description': 'McLafferty γ-H rearrangement',
                    }
                ],
                'is_primary': True,
            })
    
    return fragments
```

#### 3e. Retro-Diels-Alder

```python
def apply_retro_diels_alder(atoms, bonds):
    """
    Requires:
      - 6-membered ring (saturated or partially unsaturated)
      - ≥1 C=C double bond in the ring
      → Retro-DA breaks ring into 2 even-electron fragments
    """
    fragments = []
    
    # Find all 6-membered rings
    for ring_atoms in find_rings_by_size(atoms, bonds, size=6):
        # Check if ring has C=C
        if not has_double_bond_in_ring(ring_atoms, bonds):
            continue
        
        # Retro-DA cleavage: ring breaks at C=C, produces 2 linear/cyclic fragments
        # Both fragments even-electron
        frag1, frag2 = compute_rda_fragments(ring_atoms, bonds)
        
        fragments.append({
            'formula': hill_formula(frag1),
            'composition': frag1,
            'is_radical': False,
            'pathways': [
                {
                    'rule_type': 'retro_diels_alder',
                    'ring_atoms': ring_atoms,
                    'step': 1,
                    'rate': 45,
                    'description': 'Retro-DA ring fragmentation',
                }
            ],
            'is_primary': True,
        })
        
        fragments.append({
            'formula': hill_formula(frag2),
            'composition': frag2,
            'is_radical': False,
            'pathways': [{'rule_type': 'retro_diels_alder', ...}],
            'is_primary': True,
        })
    
    return fragments
```

#### 3f. [NEW] Reaction Type Weighting (A2)

**After all primary fragments are generated:**

```python
# In confidence.py or new probability_model.py

REACTION_FREQ_EI = {
    'homolytic_cleavage': 0.50,
    'alpha_cleavage': 0.12,
    'mclafferty': 0.07,
    'inductive_cleavage': 0.05,
    'retro_diels_alder': 0.02,
    'other': 0.24,
}

# Store base probability per fragment (used later in confidence scoring)
for frag in all_primary_fragments:
    rule_type = frag['pathways'][0]['rule_type']
    frag['base_probability'] = REACTION_FREQ_EI.get(rule_type, 0.05)
```

#### 3g. Secondary Fragmentation (Depth-1 Recursive)

```python
def get_secondary_fragments(primary_frag, atoms, bonds, bond_rates):
    """
    Each primary fragment is re-fragmented using the same rules.
    Only one level deep (depth 1).
    
    [NEW] A4: Track step-by-step rates explicitly.
    """
    secondaries = []
    
    frag_atoms = primary_frag['atom_indices']
    
    # Apply all rules again, only on frag_atoms subset
    for rule_type in ['homolytic', 'alpha', 'mclafferty', 'rda']:
        sub_fragments = apply_rule(rule_type, frag_atoms, bonds, bond_rates)
        
        for sub_frag in sub_fragments:
            # Track two-step pathway
            step1_rate = primary_frag['pathways'][0]['rate']  # Parent → primary
            step2_rate = sub_frag['pathways'][0]['rate']      # Primary → secondary
            
            secondaries.append({
                'formula': sub_frag['formula'],
                'composition': sub_frag['composition'],
                'is_radical': sub_frag['is_radical'],
                'pathways': [
                    {'step': 1, 'rate': step1_rate, 'rule_type': primary_frag['pathways'][0]['rule_type'], ...},
                    {'step': 2, 'rate': step2_rate, 'rule_type': rule_type, ...},
                ],
                'is_secondary': True,
                'parent_primary_frag': primary_frag['formula'],
                'total_rate_score': step1_rate * 0.5 + step2_rate,  # Multi-step penalty
            })
    
    return secondaries
```

#### 3h. Whitelist Construction

```python
structural_whitelist = {}

for frag in all_primary_fragments + all_secondary_fragments:
    formula = frag['formula']
    mechanism = frag['pathways'][-1]['rule_type']  # Last step rule
    rate = frag['pathways'][-1]['rate']
    
    if formula not in structural_whitelist:
        structural_whitelist[formula] = []
    
    structural_whitelist[formula].append({
        'mechanism': mechanism,
        'rate': rate,
        'is_secondary': frag.get('is_secondary', False),
        'base_probability': frag.get('base_probability', 0.05),
        'total_rate_score': frag.get('total_rate_score', rate),
    })
```

**Output from Stage 3:**
```python
structural_whitelist = {
    'C5H11O': [
        {'mechanism': 'homolytic_cleavage', 'rate': 95, 'base_probability': 0.50, ...},
        {'mechanism': 'alpha_cleavage', 'rate': 65, 'base_probability': 0.12, ...},
    ],
    'C3H7': [
        {'mechanism': 'homolytic_cleavage', 'rate': 85, 'base_probability': 0.50, ...},
    ],
    ...
}
```

---

### STAGE 4: Formula Enumeration

**Trigger:** Every peak (always runs)

**Input:** Peak m/z, parent composition, tolerance

**Process:**

```python
def find_fragment_candidates(mz, parent_composition, tolerance_ppm=5):
    """
    Enumerate all subcompositions of parent that:
    1. Have exact mass within tolerance of mz
    2. Have valid DBE (≥0, step 0.5)
    3. Satisfy atom conservation
    """
    candidates = []
    
    # Branch-and-bound search over element counts
    # For each element, try count = 0 to parent_count
    for c_count in range(parent['C'] + 1):
        for h_count in range(0, parent['H'] + 1):
            for n_count in range(parent['N'] + 1):
                for o_count in range(parent['O'] + 1):
                    # ... and so on for each element
                    
                    comp = {'C': c_count, 'H': h_count, 'N': n_count, 'O': o_count, ...}
                    
                    # Check mass
                    exact_mass = sum(MONOISOTOPIC_MASSES[el] * cnt for el, cnt in comp)
                    mz_error_ppm = abs(exact_mass - mz) / mz * 1e6
                    
                    if mz_error_ppm > tolerance_ppm:
                        continue  # Mass filter
                    
                    # Check DBE
                    dbe = calculate_dbe(comp)
                    if dbe < 0 or (dbe % 0.5) != 0:
                        continue  # DBE filter
                    
                    if dbe > parent_dbe + 1:
                        continue  # No fragment can be much more unsaturated than parent
                    
                    # Passed all checks
                    candidates.append({
                        'formula': hill_formula(comp),
                        'composition': comp,
                        'mz_exact': exact_mass,
                        'mz_error': mz - exact_mass,
                        'mz_error_ppm': mz_error_ppm,
                        'dbe': dbe,
                        'mdd': mz_error / mz,  # mass-defect-per-Da
                        'filter_passed': None,  # TBD in Stage 5
                    })
    
    return candidates
```

**Output:** `candidates = {mz: [{formula, composition, mz_exact, mz_error, dbe, ...}, ...], ...}`

---

### STAGE 5A: Chemical Validity Filters

(See PROJECT_REFERENCE.md for detailed filter descriptions)

**Trigger:** Every candidate

**Process:**
```python
for peak_mz, candidates in candidates.items():
    for cand in candidates:
        cand['filter_passed'] = True
        
        # F1 Nitrogen rule
        if not nitrogen_rule(cand['composition']):
            cand['filter_passed'] = False
            cand['filter_reason'] = 'nitrogen_rule'
        
        # F2 H-deficiency
        if hdeficiency_check(cand, parent) < 0:
            cand['filter_passed'] = False
            cand['filter_reason'] = 'hdeficiency'
        
        # ... (continue for F3–F6)
        
        # Cl/Br M+2 hard constraint
        if cand['composition'].get('Cl', 0) > 0 or cand['composition'].get('Br', 0) > 0:
            mz_plus_2 = peak_mz + 2
            if mz_plus_2 not in observed_spectrum:
                cand['filter_passed'] = False
                cand['filter_reason'] = 'clbr_no_m2_peak'
        
        # Golden Rules
        if not apply_golden_rules(cand['composition']):
            cand['filter_passed'] = False
            cand['filter_reason'] = 'golden_rules'
```

**Output:** `candidates` with `filter_passed` and `filter_reason` added

---

### STAGE 5B: Fragmentation Rule Annotation

**Trigger:** Every candidate (if `--fragmentation-rules` and MOL block exists)

**Process:**

#### Tier 1: Neutral Loss

```python
for peak_mz, candidates in candidates.items():
    for cand in candidates:
        # Compute neutral loss: parent − fragment
        neutral_loss_comp = subtract_compositions(parent, cand['composition'])
        neutral_loss_mass = exact_mass(neutral_loss_comp)
        
        # Check against NEUTRAL_LOSSES table
        for loss_name, (loss_mass, loss_comp, description) in NEUTRAL_LOSSES.items():
            if abs(neutral_loss_mass - loss_mass) < 0.1:  # Mass match within 0.1 Da
                if neutral_loss_comp == loss_comp:  # Composition match
                    cand['fragmentation_rule'] = f'loss_{loss_name}'
                    cand['rule_score'] = 0.1  # Low penalty for matched rule
                    cand['evidence_tags'].append(f'NEUTRAL_LOSS({loss_name})')
                    break
```

#### Tier 2: Structural Whitelist

```python
if cand['formula'] in structural_whitelist:
    # Found in whitelist → structural rule matched
    rules = structural_whitelist[cand['formula']]
    best_rule = min(rules, key=lambda x: x['rate'])  # Prefer highest rate (fastest break)
    
    cand['fragmentation_rule'] = best_rule['mechanism']
    cand['rule_score'] = 0.0  # Perfect score for matched rule
    cand['rule_type_probability'] = best_rule['base_probability']  # [NEW] A2
    cand['evidence_tags'].append(f'STRUCTURAL_RULE({best_rule["mechanism"]})')
    
    if best_rule['is_secondary']:
        cand['evidence_tags'].append('SECONDARY_FRAGMENTATION')
else:
    # Not in whitelist
    cand['fragmentation_rule'] = None
    cand['rule_score'] = 1.0  # High penalty for unmatched
    cand['rule_type_probability'] = 0.0
    cand['evidence_tags'].append('UNMATCHED_RULE')

# --strict-structure gate: reject if no rule
if args.strict_structure and not cand['fragmentation_rule']:
    cand['filter_passed'] = False
    cand['filter_reason'] = 'strict_structure_no_rule'
```

**Output:** `candidates` with `fragmentation_rule`, `rule_score`, `rule_type_probability` added

---

### STAGE 6: Confidence Scoring (4-Pass Model)

See Section 5 below for full details.

---

## 3. Data Structures (per stage)

### Candidate Dictionary (evolves through pipeline)

```python
candidate = {
    # From Stage 4
    'formula': 'C5H11O',
    'composition': {'C': 5, 'H': 11, 'O': 1},
    'mz_exact': 87.084064,
    'mz_error': 0.001,
    'mz_error_ppm': 11.5,
    'mz_defect_per_da': 0.000000115,
    'dbe': 1.0,
    
    # From Stage 5A
    'filter_passed': True,
    'filter_reason': None,
    'nitrogen_rule_ok': True,
    'hdeficiency_ok': True,
    'lewis_senior_ok': True,
    'isotope_pattern_score': 0.85,
    'clbr_m2_ok': None,  # Not applicable
    'neutral_valid': True,
    'golden_rules_ok': True,
    
    # From Stage 5B
    'fragmentation_rule': 'loss_H2O',
    'rule_score': 0.1,
    'rule_type_probability': 0.15,  # [NEW] A2
    'evidence_tags': ['NEUTRAL_LOSS(H2O)', ...],
    
    # From Stage 6, Pass 1
    'confidence_pass1': 0.75,
    'isotope_score': 0.90,
    'fragmentation_score': 0.10,
    'reaction_prob_bonus': 0.15,  # [NEW] A2
    'dbe_penalty': 0.0,
    'stable_ion_bonus': 0.0,
    'even_odd_weight': 0.85,
    'mass_accuracy_score': 0.88,
    'filter_pass_score': 1.0,
    
    # From Stage 6, Pass 2
    'confidence_pass2': 0.85,
    'neutral_loss_pair_bonus': 0.15,
    'neutral_loss_pair_info': 'NEUTRAL_LOSS_PAIR(H2O) with mz=105',
    
    # From Stage 6, Pass 3
    'confidence_pass3': 0.95,
    'complementary_ion_bonus': 0.25,
    'complementary_ion_mz': 57,
    'complementary_atom_conservation': True,
    
    # From Stage 6, Pass 4 [NEW] E1
    'confidence_pass4': 0.98,
    'kendrick_series_bonus': 0.15,
    'kendrick_series_type': 'CH2',
    'kendrick_series_members': [70, 84, 98],
    
    # Final
    'confidence': 0.98,
    'rank_order': 1,
}
```

### Parent Context Dictionary

```python
parent_context = {
    'compound_name': 'Pentan-2-one',
    'formula': 'C5H10O',
    'composition': {'C': 5, 'H': 10, 'O': 1},
    'mass_exact': 86.078429,
    'mz_ion': 86.077880,
    'dbe': 1.0,
    'charge': +1,
    'electron_mode': 'remove',
    
    # MOL block info
    'has_mol_block': True,
    'atoms': [...],  # List of {index, symbol, formal_charge, aromatic, ...}
    'bonds': [...],  # List of (atom_i, atom_j, type, aromatic)
    'bond_rates': {(0, 1): 95, (1, 2): 87, (2, 3): 120, ...},  # [NEW] A1
    
    # Structure info
    'class': 'aliphatic_ketone',
    'has_aromatic_ring': False,
    'has_heteroatom': True,
    'num_rings': 0,
    'is_acyclic': True,
    
    # Spectral info
    'mol_ion_mz': 86.078,
    'mol_ion_present': True,
    'mol_ion_abundance': 12.5,
    'base_peak_mz': 43,
    'num_peaks': 18,
    'has_peaks_above_mol_ion': False,
    
    # Libraries
    'inchikey': 'ZHSOHHNMQAHNFR-UHFFFAOYSA-N',
    'nist_library_hit': False,
    'pubchem_cid': 3850,
    'pubchem_formula_validated': True,
}
```

---

## 4. Integration Points for 5 Gaps

| Gap | Stage | Component | Data Flow |
|-----|-------|-----------|-----------|
| **A1** Bond rates | 2 | `bond_thermochemistry.py` (NEW) | `parent_context['bond_rates']` |
| **A1** Rate-based prioritization | 3 | `fragmentation_rules.py` (refactored) | Sort bonds by rate DESC before cleavage |
| **A2** Reaction probability | 3 | `fragmentation_rules.py` (add base_probability) | Store in `fragmentation_whitelist` |
| **A2** Confidence bonus | 6 | `confidence.py` Pass 1 | Add `reaction_prob_bonus` field |
| **A3** Formula calculator | CLI | New subcommand (TBD) | Use `find_fragment_candidates()` output |
| **A4** Multi-step rates | 3 | `fragmentation_rules.py` (`get_secondary_fragments()`) | Track `pathways[].step` and `pathways[].rate` |
| **A4** Rate penalty | 6 | `confidence.py` | Penalize secondary frags (optional) |
| **E1** Kendrick series | 6 | `confidence.py` Pass 4 (NEW) | Detect 3+ peaks spaced by 14/18/26 Da |

---

## 5. Confidence Scoring (4-Pass Model)

### Pass 1: Per-Candidate Individual Scoring

**Formula:**
```
confidence_1 = 0.15·A + 0.20·B + 0.15·C + 0.05·D + 0.10·E + 0.10·F + 0.15·G + 0.10·H

where:
  A = M+1 isotope score (0.0–1.0)
  B = fragmentation_score (0.0 if rule matched, 1.0 if not)
  C = reaction_probability_bonus [NEW] A2 (0.0–1.0, based on library frequency)
  D = DBE penalty (1.0 if OK, 0.0 if DBE > parent+1)
  E = stable_ion_bonus (0.0 if in library, 1.0 if not)
  F = even/odd_electron weight (mass-range dependent: 0.5–1.0)
  G = mass_accuracy_score (1.0 if error < 5 ppm, 0.0 if > 50 ppm)
  H = filter_pass_score (1.0 if all filters passed, 0.3 if failed)
```

**Code:**
```python
def score_pass_1(cand, parent_context, intensity_map, enable_isotope):
    scores = {}
    
    # A: M+1 isotope
    if enable_isotope and cand['mz'] >= parent_context['mz_ion'] * 0.5:
        pred_m1, obs_m1 = calculate_isotope_score(cand, intensity_map)
        scores['A'] = pred_m1  # 0.0–1.0
    else:
        scores['A'] = 0.5  # Neutral (disabled)
    
    # B: Fragmentation score
    scores['B'] = cand['rule_score']  # 0.0 if rule matched, 1.0 if not
    
    # C: [NEW] Reaction probability bonus
    prob = cand.get('rule_type_probability', 0.0)
    if prob > 0.15:
        scores['C'] = 0.8 + (prob - 0.15) * 2  # Boost for high-freq reactions
    else:
        scores['C'] = max(0.0, prob * 2)
    
    # D: DBE penalty
    if cand['dbe'] > parent_context['dbe'] + 1:
        scores['D'] = 0.0
    else:
        scores['D'] = 1.0
    
    # E: Stable ion bonus
    if lookup_stable_ion(cand['formula']):
        scores['E'] = 0.0  # Excellent match
    else:
        scores['E'] = 1.0  # No bonus
    
    # F: Even/odd preference
    is_odd = (sum(cand['composition'].get(el, 0) for el in {'N'}) % 2) == 1
    if cand['mz'] < 100:
        scores['F'] = 1.0 if is_odd else 0.7  # Prefer odd at low mass
    else:
        scores['F'] = 0.8 if is_odd else 1.0  # Prefer even at high mass
    
    # G: Mass accuracy
    ppm_error = abs(cand['mz_error_ppm'])
    if ppm_error < 5:
        scores['G'] = 1.0
    elif ppm_error < 20:
        scores['G'] = 0.5 + (20 - ppm_error) / 30
    else:
        scores['G'] = max(0.0, 1.0 - ppm_error / 100)
    
    # H: Filter pass
    scores['H'] = 1.0 if cand['filter_passed'] else 0.3
    
    # Weighted sum
    weights = [0.15, 0.20, 0.15, 0.05, 0.10, 0.10, 0.15, 0.10]
    conf_1 = sum(scores[chr(65 + i)] * weights[i] for i in range(8))
    
    return conf_1, scores
```

### Pass 2: Neutral-Loss Inter-Peak Cross-Check

**Algorithm:**
```
For each pair (mz_high, mz_low) where mz_high > mz_low:
  delta = mz_high - mz_low
  If delta ≈ mass of known neutral loss (±0.2 Da):
    For each candidate pair (cand_high, cand_low):
      neutral_loss_comp = cand_high.composition - cand_low.composition
      If neutral_loss_comp matches the known loss exactly:
        → boost both confidences by +0.15
        → add evidence_tag = "NEUTRAL_LOSS_PAIR(loss_name)"
        → re-rank pairs by confidence DESC
```

**Code:**
```python
def score_pass_2(all_candidates, intensity_map, enable_neutral_loss_check):
    if not enable_neutral_loss_check:
        return all_candidates  # No-op
    
    scored = all_candidates.copy()
    peak_mzs = sorted(scored.keys())
    
    for i, mz_high in enumerate(peak_mzs):
        for mz_low in peak_mzs[:i]:
            delta = mz_high - mz_low
            
            # Find matching neutral loss
            for loss_name, (loss_mass, loss_comp, _) in NEUTRAL_LOSSES.items():
                if abs(delta - loss_mass) > 0.2:
                    continue
                
                # Check composition match
                for cand_high in scored[mz_high]:
                    for cand_low in scored[mz_low]:
                        comp_diff = {
                            el: cand_high['composition'].get(el, 0) - cand_low['composition'].get(el, 0)
                            for el in set(cand_high['composition']) | set(cand_low['composition'])
                        }
                        comp_diff = {el: v for el, v in comp_diff.items() if v != 0}
                        
                        if comp_diff == loss_comp:
                            # Match found
                            cand_high['confidence'] = min(1.0, cand_high['confidence'] + 0.15)
                            cand_low['confidence'] = min(1.0, cand_low['confidence'] + 0.15)
                            cand_high['evidence_tags'].append(f'NEUTRAL_LOSS_PAIR({loss_name})')
                            cand_low['evidence_tags'].append(f'NEUTRAL_LOSS_PAIR({loss_name})')
    
    # Re-rank per peak
    for mz in scored:
        scored[mz] = sorted(scored[mz], key=lambda c: c['confidence'], reverse=True)
    
    return scored
```

### Pass 3: Complementary-Ion Pair Check

**Algorithm:**
```
For each peak mz_frag with top-ranked candidate:
  mz_comp = parent_mz - mz_frag
  If mz_comp exists in spectrum:
    cand_comp = top-ranked candidate for mz_comp
    If composition_match(cand_frag + cand_comp = parent_formula):
      AND electron_parity_match(both odd or both even):
        → boost both by +0.25
        → add evidence_tag = "COMPLEMENTARY_ION_PAIR"
```

**Code:**
```python
def score_pass_3(all_candidates, parent_mz, parent_composition):
    scored = copy.deepcopy(all_candidates)
    
    for mz_frag in scored:
        mz_comp = parent_mz - mz_frag
        
        if mz_comp not in scored or mz_comp == mz_frag:
            continue  # Complementary mz not in spectrum
        
        cand_frag = scored[mz_frag][0]  # Top candidate
        cand_comp = scored[mz_comp][0]
        
        # Check composition
        comp_sum = {
            el: cand_frag['composition'].get(el, 0) + cand_comp['composition'].get(el, 0)
            for el in set(cand_frag['composition']) | set(cand_comp['composition'])
        }
        
        if comp_sum != parent_composition:
            continue  # No match
        
        # Check electron parity
        frag_odd = (sum(cand_frag['composition'].get(el, 0) for el in {'N'}) % 2) == 1
        comp_odd = (sum(cand_comp['composition'].get(el, 0) for el in {'N'}) % 2) == 1
        
        if frag_odd != comp_odd:
            continue  # Parity mismatch
        
        # Match found
        cand_frag['confidence'] = min(1.0, cand_frag['confidence'] + 0.25)
        cand_comp['confidence'] = min(1.0, cand_comp['confidence'] + 0.25)
        cand_frag['evidence_tags'].append('COMPLEMENTARY_ION_PAIR')
        cand_comp['evidence_tags'].append('COMPLEMENTARY_ION_PAIR')
    
    # Re-rank per peak
    for mz in scored:
        scored[mz] = sorted(scored[mz], key=lambda c: c['confidence'], reverse=True)
    
    return scored
```

### [NEW] Pass 4: Kendrick Homologous Series (E1)

**Algorithm:**
```
For each delta ∈ {14 (CH2), 26 (C2H2), 18 (H2O)}:
  Find all chains of 3+ peaks spaced by delta m/z:
    mz, mz+delta, mz+2·delta, ...
  For each consecutive pair (mz_i, mz_{i+delta}):
    If top_candidate(mz_{i+delta}).composition - top(mz_i).composition == composition(delta):
      Series is internally consistent
  If entire chain is consistent:
    → boost all members by +0.15
    → add evidence_tag = "SERIES(CH2)" etc.
```

**Code:**
```python
def score_pass_4_kendrick(all_candidates, enable_kendrick):
    if not enable_kendrick:
        return all_candidates
    
    scored = copy.deepcopy(all_candidates)
    peak_mzs = sorted(scored.keys())
    
    SERIES = {
        14: {'C': 1, 'H': 2},   # CH2
        26: {'C': 2, 'H': 2},   # C2H2
        18: {'H': 2, 'O': 1},   # H2O
    }
    
    for delta, delta_comp in SERIES.items():
        # Find chains of 3+ peaks
        for start_mz in peak_mzs:
            chain = [start_mz]
            current_mz = start_mz
            
            while current_mz + delta in scored:
                chain.append(current_mz + delta)
                current_mz += delta
            
            if len(chain) < 3:
                continue  # Too short
            
            # Check consistency
            consistent = True
            for i in range(len(chain) - 1):
                mz_i = chain[i]
                mz_next = chain[i + 1]
                
                cand_i = scored[mz_i][0]
                cand_next = scored[mz_next][0]
                
                comp_diff = {
                    el: cand_next['composition'].get(el, 0) - cand_i['composition'].get(el, 0)
                    for el in set(cand_next['composition']) | set(cand_i['composition'])
                }
                comp_diff = {el: v for el, v in comp_diff.items() if v != 0}
                
                if comp_diff != delta_comp:
                    consistent = False
                    break
            
            if consistent:
                # Boost all members
                series_name = 'CH2' if delta == 14 else ('C2H2' if delta == 26 else 'H2O')
                for mz_s in chain:
                    for cand in scored[mz_s]:
                        cand['confidence'] = min(1.0, cand['confidence'] + 0.15)
                        cand['evidence_tags'].append(f'SERIES({series_name})')
    
    # Re-rank per peak
    for mz in scored:
        scored[mz] = sorted(scored[mz], key=lambda c: c['confidence'], reverse=True)
    
    return scored
```

---

## 6. Decision Trees & Thresholds

### Input Validation

```
BEGIN
  ├─ Formula provided?
  │   ├─ Yes → Continue
  │   └─ No → ERROR: formula required
  │
  ├─ Peaks provided?
  │   ├─ Yes → Continue
  │   └─ No → WARNING: no peaks, skip spectrum analysis
  │
  └─ MOL block provided?
      ├─ Yes → will_use_structural_rules = True
      └─ No → will_use_structural_rules = False, tier 1 only
```

### Neutral Loss Matching

```
delta_mz = parent_mz - peak_mz
tolerance = 0.2 Da  (nominal mass, unit resolution)

For each known loss in NEUTRAL_LOSSES:
  If |delta_mz - loss_mass| ≤ tolerance:
    Candidate matches this loss
```

### Filter Hard Gates

```
Candidate filtered IF:
  ├─ Nitrogen rule FAILS
  ├─ H-deficiency FAILS
  ├─ Lewis/Senior FAILS
  ├─ Cl/Br M+2 constraint violated (if Cl/Br present)
  ├─ --strict-structure and no fragmentation rule
  └─ Confidence < threshold (if --confidence-threshold set)
```

### Confidence Thresholding

```
IF --confidence-threshold T is set:
  Discard peaks with confidence < T
ELSE:
  All peaks retained (ranked by confidence)

IF --best-only is set:
  Return only top candidate per peak
ELSE:
  Return all candidates (ranked by confidence or MDD)
```

---

## 7. Error Handling & Fallbacks

### MOL Block Parsing Errors

```
Try parse_mol_block_full(mol_text)
  ├─ Success → use adjacency graph
  └─ Failure (malformed V2000):
      ├─ Log warning
      └─ Set has_mol_block = False
         (continue with Tier 1 only)
```

### PubChem Fetch Timeouts

```
Try fetch_pubchem(casno, name)
  ├─ Success → continue
  ├─ HTTP timeout:
  │   ├─ Retry × 3
  │   └─ If still fails: skip enrichment, log warning
  ├─ HTTP 429 (rate limit):
  │   ├─ Sleep 60s, retry × 3
  │   └─ If still fails: skip
  └─ HTTP 404 (not found):
      └─ Log, skip to next compound
```

### NIST Library Lookup Failure

```
Try nist_lookup.query_by_inchikey(inchikey)
  ├─ Success → return {mz: formula}
  ├─ Network error:
  │   ├─ Try SDBS fallback
  │   └─ If SDBS also fails: continue to Stage 2 (manual analysis)
  └─ Malformed response:
      └─ Log, skip to Stage 2
```

### Formula Enumeration Timeout

```
find_fragment_candidates() with branch-and-bound
  ├─ If iteration_count > MAX_ITERATIONS (10M):
  │   ├─ Log warning
  │   └─ Return candidates found so far
  └─ Complete within timeout:
      └─ Return all candidates
```

---

## 8. Testing & Validation Points

### Unit Tests by Stage

| Stage | Module | Test File | Coverage |
|-------|--------|-----------|----------|
| 0 | `structure_fetcher.py` | `test_*` (mock HTTP) | ✅ |
| 1 | `nist_lookup.py` | `test_nist_sdbs_lookup.py` | ✅ 20 tests |
| 2 | `calculator.py` | `test_calculator.py` | ✅ 18 tests |
| 2 | `bond_thermochemistry.py` (NEW) | `test_bond_thermochemistry.py` (NEW) | ❌ To write |
| 3 | `fragmentation_rules.py` | `test_fragmentation_rules.py` (NEW) | ❌ To write |
| 4 | `calculator.py` | `test_calculator.py` | ✅ 18 tests |
| 5A | `filters.py` | `test_filters.py` | ✅ 19 tests |
| 5B | `fragmentation_rules.py` | `test_fragmentation_rules.py` (NEW) | ❌ To write |
| 6 | `confidence.py` | `test_confidence.py` | ✅ 49 tests → expand to 55 (add Pass 4) |

### Integration Tests

```
test_end_to_end.py
  ├─ Three-compound example (SDF + MSPEC)
  ├─ Run with all flags: --fetch-structures --nist-lookup --confidence --fragmentation-rules
  ├─ Check output format (text, SDF, MSP)
  └─ Validate accuracy vs reference
```

### Accuracy Benchmark

```
compare_accuracy.py
  ├─ Input: Test2.MSPEC (unit-mass EI) vs ChemVista reference (high-res)
  ├─ For each peak with ChemVista reference:
  │   ├─ Compare top-ranked formula
  │   ├─ Log correct / incorrect / no_reference
  │   └─ Track by compound class
  └─ Report: % accuracy on matched peaks
      Current: 96.3% (26/27)
      Target:  97.5% after A1–A4 implementation
```

---

## Implementation Sequence

### Phase 1: Testing & Documentation (immediate)

- [ ] Write `test_fragmentation_rules.py` (18 hrs estimated)
- [ ] Write COMPLETE_WORKFLOW_PIPELINE.md (this document)

### Phase 2: Algorithm Enhancements (2–4 weeks)

- [ ] **A2** Reaction probability ranking (2 hrs) — confidence.py Pass 1
- [ ] **A1** Bond dissociation rates (4 hrs) — new bond_thermochemistry.py
- [ ] **A3** Formula calculator CLI (4 hrs) — new subcommand
- [ ] **A4** Multi-step rate tracking (3 hrs) — refactor fragmentation_rules.py
- [ ] **A5** High-res formula calc (2 hrs) — add --hr-formula-calc flag

### Phase 3: Validation & Polish

- [ ] Run full test suite (must maintain 169+ tests passing)
- [ ] Run compare_accuracy.py; expect 97.0–97.5%
- [ ] Git commit + tag v1.9.0

---

**End of COMPLETE_WORKFLOW_PIPELINE.md**

