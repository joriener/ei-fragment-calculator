"""
structure_fetcher.py
====================
Fetch 2-D MOL blocks from PubChem for SDF records that have no
structure (atom count = 0).

Uses only the Python standard library (urllib) — no extra dependencies.

PubChem REST API reference
--------------------------
https://pubchemdocs.ncbi.nlm.nih.gov/pug-rest

Query priority
--------------
1. ``<CASNO>``   field  — most precise; CAS numbers are unique identifiers
2. ``<NAME>``    field  — falls back to compound name if no CAS is present
3. ``<FORMULA>`` field  — last resort (many compounds share a formula; skipped
                          if a name was already tried and failed)

Rate limiting
-------------
PubChem asks for ≤5 requests/second from a single IP.  A 0.22 s sleep
between requests keeps comfortably below that limit.
"""

import re
import time
import urllib.error
import urllib.parse
import urllib.request


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PUBCHEM_URL = (
    "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
    "/compound/name/{identifier}/SDF?record_type=2d"
)
_REQUEST_INTERVAL = 0.22   # seconds between requests (≤5 req/s)
_TIMEOUT          = 12     # seconds per HTTP request


def _mol_block_has_atoms(mol_block: str) -> bool:
    """Return True if the MOL block contains at least one atom (non-zero counts line)."""
    if not mol_block:
        return False
    lines = mol_block.splitlines()
    # The counts line is line index 3 in a standard MOL block.
    # It starts with the atom count as a right-justified integer in columns 0-2.
    for line in lines[3:5]:          # be tolerant of slight offsets
        m = re.match(r"^\s*(\d+)\s+(\d+)", line)
        if m and int(m.group(1)) > 0:
            return True
    return False


def _fetch_from_pubchem(identifier: str) -> str | None:
    """
    Query PubChem for a 2-D SDF by *identifier* (CAS number or name).

    Returns the MOL block string (everything before ``$$$$``), or ``None``
    if the compound was not found or the request failed.
    """
    encoded = urllib.parse.quote(str(identifier).strip())
    url     = _PUBCHEM_URL.format(identifier=encoded)
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT) as resp:
            sdf_text = resp.read().decode("utf-8", errors="replace")
        # SDF from PubChem contains one record; extract its MOL block.
        mol_block = sdf_text.split("$$$$")[0].strip()
        if _mol_block_has_atoms(mol_block):
            return mol_block
        return None
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None          # compound not found — not an error
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_structure(fields: dict, mol_block: str) -> str:
    """
    Try to obtain a 2-D MOL block for one SDF record.

    If the existing ``mol_block`` already has atoms, it is returned
    unchanged.  Otherwise PubChem is queried using the CAS number and/or
    compound name found in ``fields``.

    Parameters
    ----------
    fields    : dict  SDF data fields for this record (key → value).
    mol_block : str   Existing MOL block (may be empty or "No Structure").

    Returns
    -------
    str  The best available MOL block (original if already has atoms,
         fetched from PubChem if successful, or original otherwise).
    """
    if _mol_block_has_atoms(mol_block):
        return mol_block          # already has structure — nothing to do

    # --- try CAS number first (most reliable) ---
    cas = (fields.get("CASNO") or fields.get("CAS") or
           fields.get("CAS NUMBER") or fields.get("CAS_NO") or "").strip()
    if cas:
        result = _fetch_from_pubchem(cas)
        time.sleep(_REQUEST_INTERVAL)
        if result:
            return result

    # --- fall back to compound name ---
    name = (fields.get("NAME") or fields.get("COMPOUND NAME") or
            fields.get("COMPOUND_NAME") or "").strip()
    if name and name.lower() not in ("no structure", "unknown", ""):
        result = _fetch_from_pubchem(name)
        time.sleep(_REQUEST_INTERVAL)
        if result:
            return result

    return mol_block              # could not find a structure — keep original


def enrich_mol_blocks(
    records: list[dict],
    progress_callback=None,
) -> list[dict]:
    """
    For every record in *records* that has no 2-D structure, attempt to
    fetch one from PubChem and update ``record["mol_block"]`` in-place.

    Parameters
    ----------
    records           : list[dict]  Records as returned by ``parse_sdf()``.
    progress_callback : callable | None
        Optional ``callback(done: int, total: int, name: str)`` called
        after each record is processed.  Useful for progress bars.

    Returns
    -------
    list[dict]  The same list, with ``mol_block`` fields updated where
                possible (records that already have a structure are
                unchanged and skipped quickly).
    """
    total = len(records)
    for i, record in enumerate(records, 1):
        mol_block = record.get("mol_block", "")
        if not _mol_block_has_atoms(mol_block):
            new_block = fetch_structure(record.get("fields", {}), mol_block)
            record["mol_block"] = new_block
        if progress_callback:
            name = (record.get("fields", {}).get("NAME") or
                    record.get("name") or "")
            progress_callback(i, total, name)
    return records
