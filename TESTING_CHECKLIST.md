# Testing Checklist for Inline Editing

Use this checklist to manually verify that the inline editing features work correctly.

## Edit Metadata Dialog Tests

### Basic Functionality
- [ ] Load SDF file and select a compound
- [ ] Click "Edit Metadata" button
- [ ] Dialog opens and shows metadata fields
- [ ] All compound fields visible (NAME, FORMULA, MW, etc.)
- [ ] Any custom metadata fields visible

### Inline Editing
- [ ] Double-click on a field's Value column
- [ ] Entry widget appears with current value highlighted
- [ ] Type a new value
- [ ] Press Return
- [ ] Value updates in tree immediately
- [ ] Entry widget disappears
- [ ] Try editing another field
- [ ] Click elsewhere (not pressing Return) to save
- [ ] Verify change was saved

### Adding Fields
- [ ] Scroll down to bottom of dialog
- [ ] Find "Add Field:" section with two Entry fields
- [ ] Type a new field name (e.g., "CUSTOM_FIELD")
- [ ] Type a field value (e.g., "test_value")
- [ ] Click "Add" button
- [ ] New field appears in tree immediately
- [ ] Field name and value are correct
- [ ] Can add multiple fields without closing dialog
- [ ] Entry fields clear after each addition

### Deleting Fields
- [ ] Select a field row in tree
- [ ] Click "- Delete Field" button
- [ ] Field disappears from tree
- [ ] Try to add, edit, and delete multiple fields in sequence

### Auto-Save on Close
- [ ] Make several changes (edit, add, delete)
- [ ] Click "Save & Close" button
- [ ] Dialog closes
- [ ] Success message appears
- [ ] Close dialog with X button
- [ ] Auto-save triggers without success message
- [ ] Reopen "Edit Metadata"
- [ ] Verify all changes were persisted

### Cancel Without Saving
- [ ] Make changes to a field
- [ ] Click "Cancel" button
- [ ] Dialog closes without saving
- [ ] Reopen "Edit Metadata"
- [ ] Verify changes were NOT saved

### Error Handling
- [ ] Try entering very long field values (>1000 chars)
- [ ] Try editing with special characters (é, ß, ™, etc.)
- [ ] Try adding a field with empty name (should warn)
- [ ] Try rapid double-clicking (should handle gracefully)

## Edit Mass Spectrum Dialog Tests

### Basic Functionality
- [ ] Select a compound with peaks
- [ ] Click "Edit Spectrum" button
- [ ] Dialog opens and shows peaks in tree
- [ ] Each peak shows: Index, m/z, Intensity, Base Peak
- [ ] Base peak column shows ● or ○ symbols
- [ ] Peaks sorted by m/z by default

### Inline Peak Editing (m/z)
- [ ] Double-click a peak's m/z value
- [ ] Entry widget appears with current value
- [ ] Type a new m/z value
- [ ] Press Return
- [ ] Value updates and entry closes
- [ ] Try entering invalid value (0 or negative)
- [ ] Error message appears and value not changed
- [ ] Try entering non-numeric value
- [ ] Error message appears

### Inline Peak Editing (Intensity)
- [ ] Double-click a peak's Intensity value
- [ ] Entry widget appears
- [ ] Type a new intensity
- [ ] Press Return
- [ ] Value updates
- [ ] Try entering negative value
- [ ] Error message appears
- [ ] Try entering non-numeric value
- [ ] Error message appears

### Toggle Base Peak
- [ ] Double-click the ● or ○ symbol in Base Peak column
- [ ] Symbol toggles immediately (● ↔ ○)
- [ ] No error dialog appears
- [ ] Can toggle multiple peaks in sequence
- [ ] Changes persist when dialog closes

### Adding Peaks
- [ ] Scroll down to "Add Peak:" section
- [ ] Enter m/z value (e.g., 100.5)
- [ ] Enter Intensity value (e.g., 75.0)
- [ ] Check "Base Peak" if desired
- [ ] Click "Add" button
- [ ] New peak appears at bottom of tree
- [ ] Peak has correct index number
- [ ] m/z and intensity display correctly
- [ ] Base peak symbol is correct
- [ ] Entry fields clear automatically
- [ ] Can add multiple peaks in sequence
- [ ] Try adding invalid values
- [ ] Error message shows, peak not added

### Sorting Peaks
- [ ] Click "m/z" column header
- [ ] Peaks sort by m/z ascending
- [ ] Index numbers update (1, 2, 3, ...)
- [ ] Click "m/z" header again
- [ ] Peaks sort by m/z descending
- [ ] Click "Intensity" header
- [ ] Peaks sort by intensity ascending
- [ ] Click "Intensity" header again
- [ ] Peaks sort by intensity descending

### Deleting Peaks
- [ ] Select a peak row
- [ ] Click "- Delete Peak" button
- [ ] Peak disappears from tree
- [ ] Index numbers of remaining peaks update correctly
- [ ] Try deleting when no peak selected
- [ ] Warning message appears
- [ ] Delete multiple peaks in sequence

### Auto-Save on Close
- [ ] Make several changes (edit, add, delete, toggle)
- [ ] Click "Save & Close" button
- [ ] Dialog closes
- [ ] Success message appears
- [ ] Close dialog with X button
- [ ] Auto-save triggers without success message
- [ ] Reopen "Edit Spectrum"
- [ ] Verify all changes were persisted
- [ ] Verify peaks can be plotted in spectrum view

### Cancel Without Saving
- [ ] Add a new peak
- [ ] Edit an existing peak
- [ ] Click "Cancel" button
- [ ] Dialog closes without saving
- [ ] Reopen "Edit Spectrum"
- [ ] Verify changes were NOT saved

### Error Handling
- [ ] Try adding peak with m/z = 0
- [ ] Error appears, peak not added
- [ ] Try adding peak with negative intensity
- [ ] Error appears
- [ ] Try entering very large values (e.g., 10^20)
- [ ] Should handle gracefully
- [ ] Try rapid double-clicking
- [ ] Should handle without crashes

## Navigation Tests

### Compound Navigation with Auto-Save
- [ ] Edit metadata for Compound 1
- [ ] Close dialog (auto-save)
- [ ] Edit spectrum for Compound 1
- [ ] Close dialog (auto-save)
- [ ] Navigate to Compound 2 in list
- [ ] Verify Compound 2 data displayed
- [ ] Verify Compound 1 changes were saved (navigate back to check)

### Multiple Dialogs
- [ ] Open "Edit Metadata"
- [ ] Open "Edit Spectrum" (without closing metadata)
- [ ] Both dialogs visible
- [ ] Edit in both dialogs
- [ ] Close metadata first (auto-save)
- [ ] Close spectrum (auto-save)
- [ ] Verify all changes saved

## Database Persistence Tests

### Persistent Database File
- [ ] Check that database file exists
- [ ] Close application
- [ ] Reopen application
- [ ] Load same SDF file
- [ ] Edit data again
- [ ] Close and reopen
- [ ] Verify changes still there

### In-Memory Database
- [ ] Uncheck "Persistent Database" checkbox
- [ ] Load SDF file
- [ ] Edit metadata and spectrum
- [ ] Close application
- [ ] Reopen application
- [ ] Load same SDF file
- [ ] Verify no custom edits remain (expected behavior)

## Performance Tests

### Large Dataset
- [ ] Load SDF with 100+ compounds
- [ ] Edit metadata (should be fast)
- [ ] Add many fields (>20)
- [ ] Open spectrum with many peaks (>100)
- [ ] Add many peaks
- [ ] Sort peaks (should be instant)
- [ ] Scroll in dialogs
- [ ] Performance should remain acceptable

### Memory Usage
- [ ] Open and close dialogs repeatedly
- [ ] Edit many fields and peaks
- [ ] Monitor for memory leaks
- [ ] Application should not slow down

## Edge Cases

### Special Characters
- [ ] Add field with name containing spaces
- [ ] Add field with special characters (ñ, ü, etc.)
- [ ] Edit values to contain quotes (")
- [ ] Edit values to contain newlines
- [ ] Verify data persists correctly

### Boundary Values
- [ ] m/z = 0.001 (very small)
- [ ] m/z = 999999.99 (very large)
- [ ] Intensity = 0.01 (very small)
- [ ] Intensity = 999999.99 (very large)
- [ ] Field values with 1000+ characters
- [ ] Field names with special characters

### Concurrent Edits
- [ ] Select same peak, edit both fields
- [ ] Add, edit, delete same field/peak
- [ ] Edit and sort simultaneously
- [ ] Should not crash or corrupt data

## Summary

**Total Test Cases: 90+**

After completing all tests:
- [ ] All basic functionality works
- [ ] All inline editing features work
- [ ] Auto-save works correctly
- [ ] Database persistence works
- [ ] Navigation works smoothly
- [ ] No crashes or errors
- [ ] Performance is acceptable
- [ ] Edge cases handled gracefully

If any test fails, note:
1. Test number/name
2. Steps to reproduce
3. Expected behavior
4. Actual behavior
5. Error message (if any)
