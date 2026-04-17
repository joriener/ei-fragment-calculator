# SDF Viewer Freeze Fix - Technical Explanation

## Problem Summary
The SDF Viewer GUI was freezing immediately after selecting an SDF file. Debug logs showed that the file loaded successfully, but then `_show_record()` was called repeatedly in an infinite loop, freezing the application.

## Root Cause Analysis

### The Infinite Loop
The freeze was caused by a classic **event re-entry loop**:

1. **User selects a record in the Treeview**
   - Treeview generates a `<<TreeviewSelect>>` event
   
2. **Event handler is triggered**
   - `_on_compound_selected()` is called (line 1687)
   - Extracts the selected index from the tree: `idx = int(selection[0])`
   - Calls `_show_record(idx)` (line 1696)

3. **Inside _show_record() - THE PROBLEM**
   - At line 1771 (BEFORE fix): `self._compound_tree.selection_set(str(idx))`
   - This programmatically sets the tree selection
   - **Triggering the `<<TreeviewSelect>>` event again!**

4. **Back to step 2 → INFINITE LOOP**
   - The tree selection triggers the event again
   - Which calls `_show_record()` again
   - Which triggers the event again
   - Forever...

### Why This Wasn't Immediately Obvious
- File loading completed successfully (debug output confirmed this)
- The first `_show_record(0)` call was explicit from `_load_sdf()`
- Subsequent calls were triggered by tree selection events
- The infinite loop happened during the rendering phase (Canvas/RDKit/PIL)
- This made it seem like a rendering issue, but it was actually event handling

## Solution: Event Re-entry Prevention

### The Fix
Added a **guard parameter** `highlight_in_tree` to `_show_record()`:

```python
def _show_record(self, idx: int, highlight_in_tree: bool = False) -> None:
    """Display record at given index.
    
    Args:
        idx: Record index to display
        highlight_in_tree: If True, highlight this record in the tree.
                          Only set True when initially loading
                          (to avoid infinite loop from tree selection events).
    """
```

### Three Key Changes

**1. Initial Load (Line 1643) - ONLY TIME highlight_in_tree=True**
```python
self._show_record(0, highlight_in_tree=True)  # Explicitly show first record
```

**2. Event Handler (Line 1696) - Default behavior**
```python
self._show_record(idx)  # No parameter = highlight_in_tree defaults to False
```

**3. Guard the Selection (Lines 1774-1781)**
```python
# Highlight current record in compound list (only when initially loading)
# This prevents infinite loops from tree selection events
if highlight_in_tree and self._compound_tree:
    try:
        self._compound_tree.selection_set(str(idx))
        self._compound_tree.see(str(idx))
    except Exception as e:
        print(f"Warning: Could not highlight compound {idx}: {e}")
```

## Why This Works

### Execution Flow After Fix

**Scenario 1: Initial Load**
```
_load_sdf()
  ↓
_populate_compound_list()  (tree gets empty, no selection event)
  ↓
_show_record(0, highlight_in_tree=True)  (explicitly load first record)
  ↓
selection_set() is called → Tree selection event triggered
  ↓
_on_compound_selected() is triggered
  ↓
_show_record(0, highlight_in_tree=False)  (default parameter)
  ↓
selection_set() is NOT called (guarded by highlight_in_tree=True check)
  ↓
✓ No further events, display completes normally
```

**Scenario 2: User Selects Record #2**
```
User clicks record 2 in tree
  ↓
<<TreeviewSelect>> event → _on_compound_selected()
  ↓
_show_record(2, highlight_in_tree=False)  (default parameter)
  ↓
selection_set() is NOT called (guarded by highlight_in_tree check)
  ↓
✓ Record displays, no infinite loop
```

## Verification Checklist

The fix is properly implemented if ALL of these are true:

- [ ] `_show_record()` has parameter: `highlight_in_tree: bool = False`
- [ ] Selection guard is in place: `if highlight_in_tree and self._compound_tree:`
- [ ] Initial load passes True: `_show_record(0, highlight_in_tree=True)`
- [ ] Event handler uses default: `_show_record(idx)` (no parameter)

## Expected Behavior After Fix

1. ✓ User selects SDF file
2. ✓ File loads without freezing
3. ✓ First record automatically displays with structure and metadata
4. ✓ Record is highlighted in the tree (from initial load call)
5. ✓ User can click other records in tree
6. ✓ Records display instantly when selected (no freezing)
7. ✓ No infinite recursion or event loops

## Technical Details

### Why Tkinter Events Work This Way
In Tkinter, when you call a method that modifies a widget's state (like `selection_set()`), it can trigger the corresponding event. This is by design, but it can lead to infinite loops if not handled carefully.

### Pattern for Preventing Event Re-entry
This same pattern (using a guard parameter) can be used in any situation where:
- User action triggers an event handler
- Handler calls methods that trigger the same event
- Need to prevent circular dependencies

### Related Code Sections
- `_on_compound_selected()` - Event handler (line 1687)
- `_show_record()` - Record display logic (line 1701)
- `_load_sdf()` - Initial load function (line 1595)
- `_populate_compound_list()` - Tree population (line 1654)

## Files Modified
- `ei_fragment_calculator/gui.py` - Lines 1643, 1701, 1776

## Testing
The fix can be verified by:
1. Loading any SDF file with the GUI
2. Observing that the first record loads and displays without freezing
3. Clicking different records in the tree
4. Verifying that each record displays instantly without recursion
5. Checking console output for `highlight_in_tree=False` in event handler calls
