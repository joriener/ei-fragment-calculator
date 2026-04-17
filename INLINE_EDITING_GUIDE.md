# Inline Editing Guide

## Overview

The Edit Metadata and Edit Mass Spectrum dialogs have been refactored to support inline editing directly within the main dialog window, eliminating the need for separate popup windows.

## Edit Metadata Dialog (`_edit_metadata`)

### Features

**Inline Field Editing:**
- Double-click on any field's **Value** column to edit it directly
- The cell converts to an editable Entry widget
- Press **Return** or click elsewhere to save the change
- Changes are tracked automatically

**Add New Fields Inline:**
- At the bottom of the dialog, use the inline "Add Field" frame
- Enter **Field Name** and **Field Value** in the text fields
- Click the **Add** button to insert the new field into the tree
- Fields are immediately visible and ready for editing

**Delete Fields:**
- Select a field row in the tree
- Click the **Delete Field** button to remove it
- The field is removed from the tree and marked for database deletion

**Auto-Save:**
- All changes are automatically saved when the dialog closes
- Click **Save & Close** or close the window normally (X button)
- Click **Cancel** to discard changes without saving

### Workflow Example

1. Load an SDF file
2. Select a compound in the list
3. Click **Edit Metadata** button
4. To edit an existing field:
   - Double-click the Value column
   - Type the new value
   - Press Return or click elsewhere
5. To add a new field:
   - Type field name in "Field Name" box
   - Type field value in "Field Value" box
   - Click "Add" button
6. To delete a field:
   - Click on the field row to select it
   - Click "Delete Field" button
7. Click "Save & Close" to save all changes and close

## Edit Mass Spectrum Dialog (`_edit_mass_spectrum`)

### Features

**Inline Peak Editing:**
- Double-click on a **m/z** or **Intensity** value to edit it
- Entry validation ensures m/z > 0 and intensity ≥ 0
- Press **Return** or click elsewhere to save

**Toggle Base Peak:**
- Double-click on the **Base Peak** column to toggle between ● (true) and ○ (false)
- No popup dialog needed

**Add New Peaks Inline:**
- At the bottom, use the inline "Add Peak" frame
- Enter **m/z** value
- Enter **Intensity** value
- Check **Base Peak** if this is the base peak
- Click **Add** button to insert the peak
- Fields clear automatically for adding more peaks

**Sort by Column:**
- Click on **m/z** or **Intensity** column header to sort
- Click again to reverse sort direction

**Delete Peaks:**
- Select a peak row in the tree
- Click **Delete Peak** button to remove it

**Auto-Save:**
- All changes are automatically saved when the dialog closes
- Click **Save & Close** or close the window normally (X button)
- Click **Cancel** to discard changes without saving

### Workflow Example

1. Load an SDF file
2. Select a compound in the list
3. Click **Edit Spectrum** button
4. To edit a peak:
   - Double-click the m/z or Intensity value
   - Type the new value
   - Press Return
5. To toggle base peak status:
   - Double-click the ● or ○ symbol
6. To add a new peak:
   - Enter m/z value
   - Enter Intensity value
   - Check "Base Peak" if applicable
   - Click "Add" button
7. To delete a peak:
   - Click on the peak row to select it
   - Click "Delete Peak" button
8. Click "Save & Close" to save all changes

## Database Operations

### Auto-Save Mechanism

Both dialogs implement auto-save via the `WM_DELETE_WINDOW` protocol:

```python
dialog.protocol("WM_DELETE_WINDOW", on_close)
```

This ensures that:
- Changes are saved even if the user closes the dialog with the X button
- The `save_changes(show_message=False)` call silently saves changes
- Users don't see a success message when auto-saving

### Transaction Handling

- All changes are tracked in a `changes` dictionary:
  - `changes["modified"]`: Dictionary of field/value changes
  - `changes["added"]`: Dictionary (metadata) or list (spectrum) of new items
  - `changes["deleted"]`: Set of deleted items
- Changes are committed to the database in `save_changes()`
- After saving, the display is refreshed to show the updated data

## Testing the Changes

### Manual Testing

1. Open the application
2. Load the example SDF file
3. Select a compound
4. Test Edit Metadata:
   - Double-click a value to edit
   - Add new fields inline
   - Delete a field
   - Close the dialog (changes should save)
5. Test Edit Spectrum:
   - Double-click a peak's m/z or intensity
   - Toggle base peak status
   - Add new peaks inline
   - Close the dialog (changes should save)
6. Verify changes persisted by reopening the dialogs

### Programmatic Testing

Use `test_inline_editing.py` to verify the database operations:

```bash
python test_inline_editing.py
```

This tests:
- Database access for metadata and spectrum data
- UPDATE operations for inline edits
- INSERT operations for new items
- Proper data retrieval after changes

## Key Improvements

1. **Better UX**: No popup dialogs cluttering the screen
2. **Efficiency**: Inline editing is faster than opening/closing dialogs
3. **Visibility**: All fields visible at once for comparison
4. **Auto-Save**: Changes persist automatically without extra clicks
5. **Consistency**: Both dialogs follow the same interaction pattern

## Known Limitations

- Entry validation happens on Return/FocusOut, not character-by-character
- Numeric validation (m/z > 0, intensity ≥ 0) shows error dialogs
- Base peak toggle is binary (●/○) with no validation
- Inline editing uses single-line Entry widgets (suitable for most data)

## Future Enhancements

- Right-click context menus for delete/edit operations
- Drag-and-drop reordering of items
- Copy/paste support for field values
- Undo/redo functionality
- Multi-line editing for long text values
