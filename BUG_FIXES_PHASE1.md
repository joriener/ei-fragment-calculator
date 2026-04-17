# Phase 1: Critical Bug Fixes

## Bugs Fixed

### 1. ✅ Inline Metadata Editing Not Working
**Issue**: Double-click to edit metadata values did nothing
**Root Cause**: 
- Wrong column index check (`col == "#2"` when only columns #0 and #1 exist)
- Entry widget created but never positioned over the cell

**Solution**:
- Changed column check from `"#2"` to `"#1"` (the Value column)
- Added proper cell positioning using `entry.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])`
- Added text selection on focus for better UX

### 2. ✅ Edit Metadata Dialog Shows "Record X" Instead of Compound Name
**Issue**: Title showed "Edit Metadata - Record 1" instead of actual compound name
**Solution**:
- Query database to get compound name
- Title now shows: `f"Edit Metadata - {compound_name}"`

### 3. ✅ Mass Spectral Peaks Displayed in Metadata
**Issue**: MASS SPECTRAL PEAKS field appeared in metadata editor
**Solution**:
- Added SQL filter in metadata query: `AND field_name NOT LIKE '%PEAK%' AND field_name NOT LIKE '%SPECTRUM%'`
- Peaks now excluded from metadata display

### 4. ✅ Inline Spectrum Editing Not Working
**Issue**: Double-click to edit m/z or intensity values didn't work
**Root Cause**: Same as metadata - Entry widget not positioned over cell

**Solution**:
- Added proper cell positioning with bounding box
- Entry now appears directly over the cell
- Added validation with proper error handling
- Added Escape key to cancel editing

### 5. ✅ Edit Spectrum Dialog Shows "Record X" Instead of Compound Name
**Issue**: Title showed "Edit Mass Spectrum - Record 1"
**Solution**:
- Same fix as metadata: query database for compound name
- Title now shows: `f"Edit Spectrum - {compound_name}"`

## Technical Details

### Inline Editing Implementation
Both dialogs now properly implement inline editing using Tkinter Entry widgets:

```python
# Get cell location
bbox = tree.bbox(item, col)

# Create entry in correct parent frame
entry = tk.Entry(parent_frame, width=width)
entry.insert(0, current_value)

# Position over cell
entry.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])

# Bind events
entry.bind("<Return>", save_function)
entry.bind("<FocusOut>", save_function)
entry.bind("<Escape>", cancel_function)
```

## Files Modified
- `ei_fragment_calculator/gui.py`
  - `_edit_metadata()` method (lines 2444-2700)
  - `_edit_mass_spectrum()` method (lines 2700-2950)

## Testing Checklist
- [ ] Open Edit Metadata dialog
- [ ] Verify title shows compound name (e.g., "Edit Metadata - Vanillin")
- [ ] Double-click a value field
- [ ] Verify Entry widget appears directly in the cell
- [ ] Type new value
- [ ] Press Return to save
- [ ] Verify change persisted
- [ ] Press Escape to cancel edit
- [ ] Verify MASS SPECTRAL PEAKS not shown
- [ ] Verify can delete fields
- [ ] Open Edit Spectrum dialog
- [ ] Verify title shows compound name
- [ ] Double-click m/z value
- [ ] Verify Entry appears in cell
- [ ] Edit m/z (test validation m/z > 0)
- [ ] Double-click intensity
- [ ] Edit intensity (test validation intensity ≥ 0)
- [ ] Toggle base peak
- [ ] Add new peak
- [ ] Verify auto-save on close

## Next Steps
After these fixes are verified:
1. Implement database selection menu
2. Add multi-format import (SDF, MSPEC, MSP, JDX, mzXML)
3. Implement RI/RT multi-column support
4. Integrate SDF Enricher
5. Add CSV/XML metadata import
