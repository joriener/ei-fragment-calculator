# Phase 1 Bug Fixes - Manual Testing Guide

## Quick Test Procedure

### Setup
1. Load the application
2. Load an SDF file (e.g., from examples/ directory)
3. Select a compound from the list

### Test 1: Edit Metadata Dialog Title ✅

**Steps:**
1. Click "Edit Metadata" button
2. Look at the dialog window title

**Expected:**
- Title should show: `Edit Metadata - [Compound Name]`
- Example: `Edit Metadata - Vanillin` (not "Edit Metadata - Record 1")

**Pass/Fail**: ___

---

### Test 2: Inline Metadata Editing ✅

**Steps:**
1. In Edit Metadata dialog, double-click on a **Value** cell
2. An Entry box should appear in the cell
3. Type a new value
4. Press Return

**Expected:**
- Entry widget appears directly over the cell with a cursor
- Value updates in the tree
- Entry disappears
- Change is visible in metadata list

**Test Cases:**
- [ ] Edit NAME field
- [ ] Edit FORMULA field
- [ ] Edit any custom field
- [ ] Press Escape to cancel (entry should disappear without saving)

**Pass/Fail**: ___

---

### Test 3: Metadata - No Mass Spectral Peaks ✅

**Steps:**
1. In Edit Metadata dialog, scroll through the list of fields
2. Look for any field containing "PEAK" or "SPECTRUM"

**Expected:**
- NO field named "MASS SPECTRAL PEAKS" should appear
- Only metadata fields visible
- (Peaks are shown in Edit Spectrum, not here)

**Pass/Fail**: ___

---

### Test 4: Delete Metadata Field ✅

**Steps:**
1. Select a field in the tree
2. Click "- Delete Field" button
3. Field should disappear

**Expected:**
- Field removed from list
- Works for any field except system fields (NAME, FORMULA, etc.)

**Pass/Fail**: ___

---

### Test 5: Add Metadata Field Inline ✅

**Steps:**
1. Scroll to bottom of Edit Metadata dialog
2. Find "Add Field:" section with two Entry boxes
3. Type field name in first box (e.g., "CUSTOM_FIELD")
4. Type field value in second box (e.g., "my_value")
5. Click "Add" button

**Expected:**
- New field appears in the tree immediately
- Entry boxes clear automatically
- Field ready for editing or deletion

**Pass/Fail**: ___

---

### Test 6: Edit Spectrum Dialog Title ✅

**Steps:**
1. Click "Edit Spectrum" button
2. Look at the dialog title

**Expected:**
- Title should show: `Edit Spectrum - [Compound Name]`
- Example: `Edit Spectrum - Vanillin` (not "Edit Mass Spectrum - Record 1")

**Pass/Fail**: ___

---

### Test 7: Inline Peak m/z Editing ✅

**Steps:**
1. In Edit Spectrum dialog, double-click a **m/z** value
2. Entry should appear over the cell
3. Type a new value (e.g., 123.45)
4. Press Return

**Expected:**
- Entry widget appears with cursor
- Value updates in tree
- Validation: If you enter 0 or negative → Error message, no change
- Validation: If you enter non-numeric → Error message
- Valid values save successfully

**Test Cases:**
- [ ] Valid positive number (e.g., 150.5)
- [ ] Zero (should reject)
- [ ] Negative (should reject)
- [ ] Non-numeric text (should reject)

**Pass/Fail**: ___

---

### Test 8: Inline Peak Intensity Editing ✅

**Steps:**
1. Double-click an **Intensity** value
2. Type new value (e.g., 99.9)
3. Press Return

**Expected:**
- Entry appears over cell
- Validation: If negative → Error, no change
- Validation: If non-numeric → Error
- Valid values save successfully

**Test Cases:**
- [ ] Valid positive number
- [ ] Zero (should accept)
- [ ] Negative (should reject)
- [ ] Non-numeric text (should reject)

**Pass/Fail**: ___

---

### Test 9: Toggle Base Peak ✅

**Steps:**
1. Double-click a **Base Peak** cell (showing ● or ○)
2. Symbol should toggle

**Expected:**
- ● becomes ○ (or vice versa)
- No dialog appears
- Change is immediate

**Pass/Fail**: ___

---

### Test 10: Inline Peak Addition ✅

**Steps:**
1. Scroll to bottom of Edit Spectrum dialog
2. Find "Add Peak:" section
3. Enter m/z value (e.g., 200.5)
4. Enter Intensity value (e.g., 50.0)
5. Check "Base Peak" if desired
6. Click "Add" button

**Expected:**
- New peak appears in tree with correct values
- Entry boxes clear automatically
- Peak numbered correctly

**Pass/Fail**: ___

---

### Test 11: Delete Peak ✅

**Steps:**
1. Select a peak row in tree
2. Click "- Delete Peak" button
3. Peak should disappear

**Expected:**
- Peak removed from list
- Index numbers update for remaining peaks

**Pass/Fail**: ___

---

### Test 12: Auto-Save on Close ✅

**Steps:**
1. Make changes in Edit Metadata:
   - Edit a field
   - Add a new field
   - Delete a field
2. Click **Save & Close** button
3. Make changes in Edit Spectrum:
   - Edit m/z or intensity
   - Add a peak
   - Delete a peak
4. Close window with **X** button

**Expected:**
- Changes persist when dialog closes
- Can reopen dialog and see updated values
- "Save & Close" shows success message
- X button closes silently (no message, but auto-saves)

**Pass/Fail**: ___

---

### Test 13: Cancel Without Saving ✅

**Steps:**
1. Edit a metadata field
2. Click "Cancel" button
3. Reopen "Edit Metadata"

**Expected:**
- Changes NOT saved
- Original values still there

**Pass/Fail**: ___

---

## Summary

| Test | Pass | Fail | Notes |
|------|------|------|-------|
| 1. Metadata title | [ ] | [ ] | |
| 2. Inline metadata edit | [ ] | [ ] | |
| 3. No peaks in metadata | [ ] | [ ] | |
| 4. Delete metadata field | [ ] | [ ] | |
| 5. Add metadata field | [ ] | [ ] | |
| 6. Spectrum title | [ ] | [ ] | |
| 7. Edit m/z inline | [ ] | [ ] | |
| 8. Edit intensity inline | [ ] | [ ] | |
| 9. Toggle base peak | [ ] | [ ] | |
| 10. Add peak inline | [ ] | [ ] | |
| 11. Delete peak | [ ] | [ ] | |
| 12. Auto-save on close | [ ] | [ ] | |
| 13. Cancel without save | [ ] | [ ] | |

**Overall Status**: 
- [ ] All tests passed ✅
- [ ] Some issues found 🔴

If any tests fail, please note the test number and what went wrong.
