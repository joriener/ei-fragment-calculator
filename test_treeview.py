#!/usr/bin/env python3
"""Test Treeview insertion with the fixed configuration."""

import tkinter as tk
import tkinter.ttk as ttk

root = tk.Tk()
root.title("Treeview Test")
root.geometry("400x300")

# Create Treeview with the FIXED configuration
tree = ttk.Treeview(root, columns=("Name",), show="tree headings", height=15)
tree.column("#0", width=180)
tree.column("Name", width=0)
tree.heading("#0", text="Compound")
tree.heading("Name", text="")
tree.pack(fill=tk.BOTH, expand=True)

# Test inserting items like the SDF viewer does
test_records = [
    {"name": "Benzoic acid, 3-chloro-"},
    {"name": "Histamine Dihydrochloride"},
    {"name": "Phenol, 2,4-dichloro-"},
    {"name": "Tridecane"},
    {"name": "2-Undecanone"}
]

print("[TEST] Inserting test records...")
for idx, record in enumerate(test_records):
    try:
        name = record["name"]
        display_text = f"{idx + 1}. {name}"
        print(f"[TEST] Inserting record {idx} with text: {display_text}")
        tree.insert("", tk.END, iid=str(idx), text=display_text)
        print(f"[TEST] Successfully inserted record {idx}")
    except Exception as e:
        print(f"[TEST] ERROR inserting record {idx}: {e}")
        import traceback
        traceback.print_exc()

print("[TEST] Test completed. Window should show 5 items.")
root.mainloop()
