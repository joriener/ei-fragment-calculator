#!/usr/bin/env python3
"""Test persistent database creation and data storage"""

import sys
import os
import sqlite3
import tempfile
sys.path.insert(0, r"D:\tmp\ei-fragment-calculator")

from ei_fragment_calculator.gui import _SDFViewerTab
import tkinter as tk

def test_persistent_db():
    """Test that persistent database is created and data is stored."""
    print("=" * 60)
    print("TEST: Persistent Database Creation and Data Storage")
    print("=" * 60)

    test_file = r"D:\tmp\ei-fragment-calculator\examples\three_compounds.sdf"
    if not os.path.exists(test_file):
        print("[FAIL] Test SDF file not found!")
        return False

    # Create a temporary database file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
        db_file = f.name
    
    print(f"\n[INFO] Using temporary database file: {db_file}")
    
    root = tk.Tk()
    root.withdraw()

    try:
        viewer = _SDFViewerTab(root)
        
        print("\n[TEST 1] Setting persistent database options...")
        viewer._persist_db_var.set(True)
        viewer._db_path_var.set(db_file)
        print(f"[PASS] Database path set to: {db_file}")
        print(f"[INFO] Persist checkbox: {viewer._persist_db_var.get()}")

        print("\n[TEST 2] Loading SDF file with persistent database...")
        viewer._load_sdf(test_file)
        print("[PASS] SDF file loaded")

        print("\n[TEST 3] Checking if database file was created...")
        if os.path.exists(db_file):
            file_size = os.path.getsize(db_file)
            print(f"[PASS] Database file created: {db_file}")
            print(f"[INFO] File size: {file_size} bytes")
            
            if file_size == 0:
                print("[WARN] Database file is empty!")
        else:
            print(f"[FAIL] Database file not created at {db_file}")
            return False

        print("\n[TEST 4] Querying database file directly...")
        try:
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()
            
            # Check tables exist
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            print(f"[PASS] Found {len(tables)} tables:")
            for table in tables:
                print(f"       - {table[0]}")
            
            # Check compound count
            cursor.execute("SELECT COUNT(*) FROM compounds")
            count = cursor.fetchone()[0]
            print(f"[PASS] Compounds in database: {count}")
            
            if count == 0:
                print("[WARN] No compounds in database!")
                return False
            
            # Check compound data
            cursor.execute("SELECT id, name, formula FROM compounds LIMIT 1")
            compound = cursor.fetchone()
            if compound:
                print(f"[PASS] Sample compound: ID={compound[0]}, Name={compound[1]}, Formula={compound[2]}")
            
            # Check metadata count
            cursor.execute("SELECT COUNT(*) FROM metadata")
            meta_count = cursor.fetchone()[0]
            print(f"[PASS] Metadata fields in database: {meta_count}")
            
            conn.close()
            
        except Exception as e:
            print(f"[FAIL] Error querying database: {e}")
            return False

        print("\n" + "=" * 60)
        print("PERSISTENT DATABASE TEST PASSED")
        print("=" * 60)
        print(f"\nDatabase file location: {db_file}")
        return True

    except Exception as e:
        print(f"\n[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        root.destroy()
        # Clean up
        if os.path.exists(db_file):
            print(f"\n[INFO] Cleaning up temp database file")
            os.remove(db_file)

if __name__ == "__main__":
    success = test_persistent_db()
    sys.exit(0 if success else 1)
