#!/usr/bin/env python3
"""
Test script to demonstrate the new metadata enrichment feature.
Shows how PubChem data can be used to fill empty metadata fields.
"""

import sys
import sqlite3
from ei_fragment_calculator.gui import _SDFViewerTab

def test_metadata_enrichment():
    """Demonstrate the metadata enrichment feature."""

    print("=" * 70)
    print("EI Fragment Calculator - Metadata Enrichment with PubChem")
    print("=" * 70)
    print()

    # Create a test instance
    print("1. Creating SDF Viewer instance...")
    viewer = _SDFViewerTab(None)

    # Load a test SDF file
    print("2. Loading test SDF file...")
    test_file = r"D:\tmp\ei-fragment-calculator\examples\three_compounds.sdf"
    try:
        viewer._load_sdf(test_file)
        print(f"   [OK] Loaded {test_file}")
    except Exception as e:
        print(f"   [ERROR] Failed to load: {e}")
        return
    print()

    # Get first compound ID
    if viewer._db_cursor:
        viewer._db_cursor.execute("SELECT id, name, formula FROM compounds LIMIT 1")
        row = viewer._db_cursor.fetchone()
        if row:
            compound_id, compound_name, formula = row
            print(f"3. Test Compound: ID={compound_id}, Name={compound_name}, Formula={formula}")
            print()

            # Get current metadata
            print("4. Current Metadata:")
            viewer._db_cursor.execute(
                "SELECT field_name, field_value FROM metadata WHERE compound_id = ? ORDER BY field_name",
                (compound_id,)
            )
            metadata = viewer._db_cursor.fetchall()
            for field_name, field_value in metadata[:5]:  # Show first 5 fields
                print(f"   - {field_name}: {field_value if field_value else '(empty)'}")
            print(f"   ... ({len(metadata)} total metadata fields)")
            print()

            # Test enrichment function
            print("5. Testing Metadata Enrichment with PubChem:")
            print("   Calling: _enrich_metadata_with_pubchem()")
            print()

            enriched = viewer._enrich_metadata_with_pubchem(compound_id)

            if enriched:
                print(f"   [OK] Enrichment successful! Retrieved {len(enriched)} fields:")
                for field, value in list(enriched.items())[:5]:
                    print(f"   - {field}: {value}")
                if len(enriched) > 5:
                    print(f"   ... and {len(enriched) - 5} more fields")
            else:
                print("   [NOTE] No enrichment data retrieved")
                print("     (sdf-enricher may not be installed)")
            print()

            print("6. Feature Summary:")
            print("   [+] New method: _enrich_metadata_with_pubchem(record_id)")
            print("   [+] Returns: Dict of enriched field:value pairs")
            print("   [+] Integration: Metadata editor dialog button")
            print("   [+] Button location: 'Enrich with PubChem' in metadata editor")
            print("   [+] Behavior: Fills empty fields only, never overwrites existing data")
            print()

            print("7. To use this feature in the GUI:")
            print("   1. Load an SDF file (Ctrl+L)")
            print("   2. Select a compound")
            print("   3. Click 'Edit Metadata' button in metadata header")
            print("   4. Click 'Enrich with PubChem' button in dialog")
            print("   5. Review enriched fields and click 'Save & Close'")
            print()

    print("=" * 70)
    print("Test Complete!")
    print("=" * 70)

if __name__ == "__main__":
    test_metadata_enrichment()
