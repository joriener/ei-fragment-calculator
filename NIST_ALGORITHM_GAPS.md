# NIST MS Interpreter vs Current EI Fragment Calculator — Algorithm Gap Analysis

**Date:** 2026-04-17  
**Reviewed documents:**
- imsc03_poster.pdf (NIST 2003, original MS Interpreter methodology)
- asms_2017_poster.pdf (high-res modes)
- asms_2018_poster.pdf (enhanced fragmenter)
- asms_2019_poster.pdf (current rule optimizations)

---

## Executive Summary

**What you have:** A rule-based fragmentor with chemical filters, multi-pass confidence scoring, and heuristic structural rules. **96.3% accuracy on matched peaks**.

**What NIST has:** A thermochemically-ranked fragmentor where fragmentation pathways are scored by **dissociation rates** computed from bond strengths, with reaction types weighted by **library statistics** (e.g., "70% of base peaks arise from dissociation in EI").

**The gap is not architectural—it's probabilistic weighting and explicit thermochemical ranking.**

---

## 1. NIST's Core Algorithm (from papers)

### 1.1 Bond Dissociation Rate Model

**NIST inputs per bond:**
- Bond type (C-C, C=O, ring, etc.)
- Atom environment (heteroatom neighbors, degree, aromaticity)
- Relative bond strength from NIST WebBook + group additivity

**NIST computes:**
```
dissociation_rate(bond_i) = thermochemical_estimate(BDE_i)
```
Scale: 0–120, normalized so weakest bond in molecule ≈ 120.

**Used for:**
- Rank bonds by likelihood of breaking first
- Predict fragment m/z in order of appearance
- Explain why certain peaks dominate

**Your system:**
- Has rule-based fragmentation (homolytic, alpha, inductive, McLafferty, RDA)
- Assigns fragments to peaks post-hoc without explicit rate ranking
- No intermediate rate values; just "is this fragment possible?"

---

### 1.2 Reaction Type Probability Weighting

**NIST's approach:**
Analyzed 267,166 EI spectra in NIST libraries to learn:

| Reaction Type | Fraction of Base Peaks | Example |
|---------------|------------------------|---------|
| Dissociation (simple) | 50% | M+• → [frag]+ + neutral• |
| Dissociation + H-loss | ~15% | M+• → [frag-H]+ + neutral• + H• |
| H-displacement | ~10% (Positive ESI; rare in EI) | — |
| 1,2-ring dissociation | ~8% | Ring opening + C-C break |
| γ-H shift + dissociation | ~7% | Rearrangement before break |
| **Other** (RDA, inductive, etc.) | ~10% | Remaining |

**Used for:**
- When multiple fragments are possible, rank by observed frequency
- Flag unlikely pathways as "unfiltered" (yellow, low confidence)

**Your system:**
- All rules weighted equally in the rule annotation step
- No library-derived probability ranking
- Confidence scoring uses isotope + stable-ion bonus, not reaction frequency

---

### 1.3 Formula Calculator (Reverse m/z → Composition)

**NIST's tool:**
- Input: exact m/z, parent formula, tolerance (ppm)
- Output: all possible formulas that:
  1. Match m/z within ppm tolerance
  2. Are subsets of parent formula (atom conservation)
  3. Have valid DBE (0, 0.5, 1, 1.5, ..., up to parent)
  4. Are chemically reasonable (nitrogen rule, H-deficiency, etc.)
- Displays for **each candidate:**
  - Exact m/z, formula, ppm error
  - Electron state (odd/even for radical cation)
  - Possible neutral losses from parent
  - Thermochemical feasibility

**Your system:**
- Has `find_fragment_candidates()` which enumerates formulas ✓
- Does NOT have an interactive formula calculator
- Reverse lookup (m/z → formula) only done during main pipeline

---

### 1.4 Multi-Step Fragmentation Tracking

**NIST's approach:**
- Allows **1–3 consecutive bond breaks** per fragment
- Tracks intermediate products
- Example: M+• → [inter]+ → [final]+ (two steps)
- Fig. 1 of 2018 poster shows this explicitly
- Displayed as "rate = 70 (step 1), rate = 45 (step 2)"

**Your system:**
- Tier 2 structural rules break single bonds
- `get_secondary_fragments()` applies rules recursively (depth 1)
- Does NOT explicitly score/rank the multi-step paths
- Secondary fragments are "just available", not ranked by stepwise rates

---

### 1.5 Unspecified Loss Handling

**NIST's approach:**
- Permits loss of **common stable molecules** when no mechanism is known:
  - Alkanes (CH₄, C₂H₆, ..., C₆H₁₄)
  - Simple oxides (CO, H₂O, NO, CO₂, SO₂, SO₃)
  - Halogens (HCl, HBr, HF, Cl•, Br•)
  - Nitrogen compounds (HCN, NH₃, N₂)
  - Organics (C₂H₂, C₂H₄, C₃H₆)
  - Phosphorus (PO₃H, H₃PO₄)
  - Sulfur (H₂S, COS, CS₂)

- A peak with unspecified loss is **still assigned** (shown in yellow/"unfiltered")
- Confidence is lower, but formula is provided
- User can inspect the neutral loss and decide

**Your system:**
- 36-entry neutral loss table in Tier 1 (Tier 1: formula-based)
- Tier 2: structure-based rules only
- **Gap:** No reverse formula calculator to use unspecified losses

---

## 2. What Your System Does BETTER

1. **Chemical validity filters** (F1–F6): More rigorous than NIST's simple checks
2. **Isotope pattern scoring**: 3-pass M+1/M+2 calculation vs. NIST's simpler approach
3. **Multiple library lookups**: NIST WebBook + SDBS (you added this post-2019)
4. **Golden Rules**: Kind & Fiehn element ratio filter (not mentioned in NIST papers)
5. **Cl/Br M+2 as hard constraint**: You enforce this; NIST scores it
6. **Secondary fragmentation ranking**: You have depth-1 recursive, NIST shows depth-3 examples
7. **Compound class templates**: You auto-detect; NIST manual only

---

## 3. Specific Algorithm Gaps (Prioritized)

### GAP-A1 (HIGH IMPACT): Thermochemical Bond Rating

**What it is:**
A function that scores each bond in the molecule on a 0–120 scale based on:
- Bond type (single, double, ring, etc.)
- Heteroatom neighbors
- Formal charge
- Aromatic vs. aliphatic

**Where it goes:**
- `fragmentation_rules.py` — new module `bond_thermochemistry.py`
- Call before `enumerate_homolytic_cleavages()` / `apply_alpha_cleavage()`
- Rank candidate bonds by score before generating fragments

**Why:**
- Current system generates **all possible bonds**, then filters
- NIST system predicts **most likely bond first** (rate-based)
- Example: In pentane, NIST predicts α-cleavage breaks fastest; you enumerate all and pick later

**Implementation sketch:**
```python
# New module: bond_thermochemistry.py

BDE_ESTIMATES = {
    ('C', 'C', 'single', False): 3.5,      # alkyl C-C, 350 kJ/mol relative
    ('C', 'C', 'single', True):  2.8,      # benzylic C-C, 280 kJ/mol
    ('C', 'O', 'single', False): 2.0,      # C-O aliphatic
    ('C', 'H', 'single', False): 4.2,      # C-H alkyl
    # ... ~30-40 entries covering common bonds
}

def compute_bond_rates(atoms, bonds, mol_block_data) -> dict:
    """
    For each bond (i,j), return dissociation rate 0-120.
    Weak bonds (likely to break) → high rate.
    Strong bonds → low rate.
    """
    rates = {}
    for bond_id, (atom_i, atom_j, bond_type, aromatic) in bonds:
        hetero_neighbors = count_heteroatom_neighbors(atom_i) + ...
        bde_key = (symbol_i, symbol_j, bond_type_str, aromatic)
        base_bde = BDE_ESTIMATES.get(bde_key, 3.0)
        
        # Heteroatom boost
        if hetero_neighbors > 0:
            base_bde *= 0.8  # faster for heteroatom-adjacent bonds
        
        # Ring strain
        if in_small_ring(bond_id):
            base_bde *= 0.7
        
        rates[bond_id] = normalize_to_scale(base_bde, 0, 120)
    
    return rates

def prioritize_fragmentation(atoms, bonds, rates) -> list:
    """Return bonds sorted by dissociation rate (descending)."""
    return sorted(rates.items(), key=lambda x: x[1], reverse=True)
```

**Effort:** 3–4 hours (estimate bond terms from literature; validate against NIST WebBook)

---

### GAP-A2 (HIGH IMPACT): Reaction Type Probability Ranking

**What it is:**
When multiple fragments match a peak, **weight them by reaction frequency** observed in the library.

**Where it goes:**
- `confidence.py` or new `probability_model.py`
- Called after Pass 3 (complementary-ion check) as Pass 4 (or integrated into Pass 1)

**Why:**
- NIST: "70% of base peaks = simple dissociation" → boosts confidence for dissociation fragments
- Your system: All rule types equally probable → isotope + stable-ion bonus only

**Implementation:**
```python
# In confidence.py or new probability_model.py

REACTION_PROBABILITIES_EI = {
    'dissociation_simple': 0.50,
    'dissociation_h_loss': 0.15,
    'dissociation_h_gain': 0.02,
    'alpha_cleavage': 0.12,
    '1_2_ring_dissociation': 0.08,
    'gamma_h_shift': 0.07,
    'mclafferty': 0.03,
    'retro_diels_alder': 0.01,
    'other': 0.02,
}

def apply_reaction_probability_bonus(all_candidates, parent_formula):
    """
    For each peak's candidates, look up fragmentation_rule.
    Apply +0.2 confidence boost if rule matches high-probability type.
    """
    for mz, candidates in all_candidates.items():
        for cand in candidates:
            rule = cand.get('fragmentation_rule', '')
            if not rule:
                continue
            
            # Parse rule type from fragmentation_rule string
            rule_type = extract_rule_type(rule)  # → 'dissociation_simple', etc.
            prob = REACTION_PROBABILITIES_EI.get(rule_type, 0.05)
            
            if prob > 0.15:
                # High-probability reaction
                cand['confidence'] = min(1.0, cand.get('confidence', 0.5) + 0.20)
                cand['evidence_tags'].append(f'HIGH_PROB_REACTION({prob:.0%})')
```

**Effort:** 2 hours (parse fragmentation_rule strings; apply weights)

---

### GAP-A3 (MEDIUM IMPACT): Formula Calculator CLI / Interactive Mode

**What it is:**
A standalone tool (or --mode flag in CLI) to reverse-lookup m/z → possible formulas.

**Input:** m/z, tolerance (ppm/mDa), parent formula  
**Output:** Table of all valid formulas with ppm error, DBE, electron state, possible neutral losses.

**Why:**
- NIST tool: helps interpret unassigned peaks (white peaks)
- Your system: Can't easily do this; must run full pipeline

**Implementation:**
```python
# New CLI subcommand: ei-fragment-calculator formula-calc

class FormulaCDest:
    def __init__(self, parent_formula, parent_mz, tolerance_ppm=5):
        self.parent = parse_formula(parent_formula)
        self.parent_mz = parent_mz
        self.tol_ppm = tolerance_ppm
    
    def find_formulas(self, observed_mz):
        """Return all subcompositions of parent within tolerance."""
        results = []
        # Use existing find_fragment_candidates() logic
        candidates = find_fragment_candidates(
            mz=observed_mz,
            parent_composition=self.parent,
            tolerance_ppm=self.tol_ppm,
            dbe_range=(0, 20),
        )
        
        for cand in candidates:
            dbe = calculate_dbe(cand['composition'])
            electron_state = 'odd' if is_odd_electron(cand) else 'even'
            neutral_loss = subtract_compositions(self.parent, cand['composition'])
            
            results.append({
                'mz_exact': exact_mass(cand['composition']),
                'formula': hill_formula(cand['composition']),
                'mz_error_ppm': abs(exact_mass(cand) - observed_mz) / observed_mz * 1e6,
                'dbe': dbe,
                'electron_state': electron_state,
                'possible_loss': hill_formula(neutral_loss),
                'filter_passed': pass_all_filters(cand, parent),
            })
        
        return sorted(results, key=lambda x: abs(x['mz_error_ppm']))
```

**Effort:** 4 hours (UI/formatting, integrate with existing filters)

---

### GAP-A4 (MEDIUM IMPACT): Explicit Multi-Step Fragmentation Scoring

**What it is:**
When a secondary fragment is generated, **track the rate of each step** and compute total pathway cost.

**Currently:**
- You generate secondary fragments (depth-1 recursive)
- But don't score them relative to primary fragments

**NIST:**
- Shows "rate = 70 (step 1), rate = 45 (step 2)" separately
- Uses to explain slow-appearing ions

**Implementation:**
```python
# In fragmentation_rules.py

def get_secondary_fragments(primary_frag, atoms, bonds, rates):
    """
    Generate secondary fragments from a primary fragment.
    Track the rate of each step.
    """
    secondaries = []
    
    for bond_id, (atom_i, atom_j, bond_type) in bonds:
        if not bond_connects_fragment(bond_id, frag_atoms=primary_frag):
            continue
        
        step1_rate = rates.get(bond_id, 50)
        step2_frag = break_bond(bond_id, primary_frag, ...)
        
        # For secondary, estimate rate as weaker (fragmentation is harder)
        step2_rate = estimate_secondary_rate(step2_frag)
        
        secondaries.append({
            'formula': step2_frag,
            'pathways': [
                {'step': 1, 'rate': step1_rate, 'type': 'primary_break'},
                {'step': 2, 'rate': step2_rate, 'type': 'secondary_break'},
            ],
            'total_score': step1_rate * 0.5 + step2_rate,  # Multi-step penalty
            'is_secondary': True,
        })
    
    return secondaries
```

**Effort:** 3 hours (refactor existing secondary logic, add rate tracking)

---

### GAP-A5 (LOW-MEDIUM IMPACT): High-Resolution Formula Matching

**What it is:**
NIST 2017/2018 papers emphasize high-resolution mode with **ppm-level accuracy**.

**Your system:**
- Has `--hr` flag for high-res input
- But doesn't have high-res formula calculator

**NIST's approach:**
- When m/z is exact (e.g., 192.1024), use ppm tolerance (5–10 ppm default)
- Show formula + exact m/z + ppm error + electron state all in one table

**Implementation:**
- Mostly already done in `find_fragment_candidates()` with `tolerance_ppm` parameter
- Missing: **interactive formula calculator for high-res** (same as GAP-A3, but mode-aware)

**Effort:** 2 hours (add --hr-formula-calc mode)

---

## 4. What NOT to Change

✅ **Keep these—they exceed NIST:**
1. Chemical validity filters (F1–F6)
2. Isotope pattern scoring (M+1/M+2, 3-pass)
3. Golden Rules (Kind & Fiehn)
4. Compound class templates
5. Library lookups (NIST WebBook + SDBS)
6. Neutral loss cross-checks (inter-peak)

✅ **Keep as-is:**
1. Formula enumeration (branch-and-bound is solid)
2. Input readers (SDF/MSP/MSPEC/JDX/CSV)
3. Confidence scoring structure (3-pass framework)
4. Rule annotation (Tier 1/2 structure)

---

## 5. Implementation Roadmap

| Priority | Gap | Effort | Impact | Tests Needed |
|----------|-----|--------|--------|--------------|
| 1 | A2 — Reaction type probability ranking | 2 hrs | ⭐⭐⭐⭐ | Verify base peak types on 10 spectra |
| 2 | A1 — Bond dissociation rate model | 4 hrs | ⭐⭐⭐⭐ | Unit tests for 20 common bonds |
| 3 | A3 — Formula calculator CLI | 4 hrs | ⭐⭐⭐ | Test on 5 unassigned peaks, compare NIST output |
| 4 | A4 — Multi-step rate tracking | 3 hrs | ⭐⭐⭐ | Verify secondary fragments ranked lower than primary |
| 5 | A5 — High-res formula calc | 2 hrs | ⭐⭐ | Test on synthetic exact-mass peaks (5–10 ppm) |

**Total estimate:** 15 person-hours over 2–3 sessions.

**Expected accuracy gain:** From 96.3% → ~97.5% (reaction weighting helps disambiguate close candidates).

---

## 6. Validation Against NIST Papers

### asms_2019.pdf (Latest):
- ✅ Dissociation + H-loss/gain rules → You have these
- ✅ Alpha cleavage → You have this
- ✅ Inductive cleavage → You have this
- ✅ McLafferty with H-detection → You fixed this 2026-04-17
- ❌ Explicit rate ranking → **GAP-A1**
- ❌ Library-derived probabilities → **GAP-A2**

### asms_2018.pdf:
- ✅ High-res mode with ppm matching → You have --hr
- ❌ High-res formula calculator → **GAP-A3**
- ✅ Multi-step fragmentation (shown) → You have secondary, but not scored → **GAP-A4**

### asms_2017.pdf:
- ✅ High-res mode introduction → Covered
- ✅ Formula calculator concept → **GAP-A3**

### imsc03_poster.pdf (Foundational):
- ✅ Thermochemical kinetics concept → Mentioned in theory, not implemented → **GAP-A1**
- ✅ H-transfer, ring opening, beta-cleavage → You have these rules
- ✅ Isotope grouping → You have this
- ✅ Unspecified losses → You have Tier 1 table, missing reverse lookup → **GAP-A3**

---

## 7. Next Steps

1. **Immediately:** Write `tests/test_fragmentation_rules.py` (no NIST gap here, just testing)
2. **Session 2:** Implement A2 (reaction probability ranking) — quick win, high impact
3. **Session 3:** Implement A1 (bond rate model) — more complex, validates NIST theory
4. **Session 4:** Add A3 (formula calculator) — user-facing, improves usability
5. **Polish:** A4, A5 (multi-step scoring, high-res calculator)

---

**End of Gap Analysis**
