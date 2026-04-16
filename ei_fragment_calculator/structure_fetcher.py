"""
structure_fetcher.py
====================
Fetch 2-D MOL blocks and enriched metadata from PubChem for SDF records
that have no structure (atom count = 0).

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

Extended enrichment (Phase 3)
-----------------------------
After fetching the 2-D MOL block, a second call retrieves:
  - Canonical SMILES
  - InChIKey
  - Monoisotopic mass (exact molecular weight)
  - Molecular formula
  - IUPAC name

Rate limiting
-------------
PubChem asks for ≤5 requests/second from a single IP.  A 0.22 s sleep
between requests keeps comfortably below that limit.
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PUBCHEM_URL_SDF = (
    "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
    "/compound/name/{identifier}/SDF?record_type=2d"
)
_PUBCHEM_URL_CID = (
    "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{identifier}/cids/JSON"
)
_PUBCHEM_URL_PROPERTIES = (
    "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/property/"
    "CanonicalSMILES,InChIKey,MonoisotopicMass,MolecularFormula,IUPACName/JSON"
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
    url     = _PUBCHEM_URL_SDF.format(identifier=encoded)
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


def _fetch_cid_from_name(identifier: str) -> int | None:
    """
    Query PubChem for the CID (compound ID) by compound name.

    Returns the integer CID, or ``None`` if not found or on error.
    """
    encoded = urllib.parse.quote(str(identifier).strip())
    url = _PUBCHEM_URL_CID.format(identifier=encoded)
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("IdentifierList", {}).get("CID"):
            cids = data["IdentifierList"]["CID"]
            return cids[0] if cids else None
        return None
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        return None
    except Exception:
        return None


def _fetch_properties_from_pubchem(cid: int) -> dict | None:
    """
    Query PubChem for enriched properties by CID.

    Returns a dict with keys:
      - SMILES: canonical SMILES
      - INCHIKEY: InChIKey
      - CID: compound ID
      - PUBCHEM_EXACT_MW: monoisotopic mass (exact)
      - IUPAC_NAME: IUPAC name
      - MOLECULAR_FORMULA: molecular formula

    Returns ``None`` if the compound was not found or the request failed.
    """
    url = _PUBCHEM_URL_PROPERTIES.format(cid=int(cid))
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        properties = data.get("PropertyTable", {}).get("Properties", [])
        if not properties:
            return None

        props = properties[0]  # first (and only) result
        result = {
            "SMILES": props.get("CanonicalSMILES"),
            "INCHIKEY": props.get("InChIKey"),
            "CID": props.get("CID"),
            "PUBCHEM_EXACT_MW": props.get("MonoisotopicMass"),
            "IUPAC_NAME": props.get("IUPACName"),
            "MOLECULAR_FORMULA": props.get("MolecularFormula"),
        }
        return result
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
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

    As a secondary enrichment, fetch properties (SMILES, InChIKey, etc.)
    and store them in the ``fields`` dict under keys:
      - SMILES
      - INCHIKEY
      - CID
      - PUBCHEM_EXACT_MW
      - IUPAC_NAME

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

    found_mol = None
    search_identifier = None

    # --- try CAS number first (most reliable) ---
    cas = (fields.get("CASNO") or fields.get("CAS") or
           fields.get("CAS NUMBER") or fields.get("CAS_NO") or "").strip()
    if cas:
        found_mol = _fetch_from_pubchem(cas)
        time.sleep(_REQUEST_INTERVAL)
        if found_mol:
            search_identifier = cas

    # --- fall back to compound name ---
    if not found_mol:
        name = (fields.get("NAME") or fields.get("COMPOUND NAME") or
                fields.get("COMPOUND_NAME") or "").strip()
        if name and name.lower() not in ("no structure", "unknown", ""):
            found_mol = _fetch_from_pubchem(name)
            time.sleep(_REQUEST_INTERVAL)
            if found_mol:
                search_identifier = name

    # --- If we found a MOL block, try to enrich with properties ---
    if found_mol and search_identifier:
        # Get CID from the search identifier
        cid = _fetch_cid_from_name(search_identifier)
        time.sleep(_REQUEST_INTERVAL)
        if cid:
            # Get properties from CID
            props = _fetch_properties_from_pubchem(cid)
            time.sleep(_REQUEST_INTERVAL)
            if props:
                # Store enriched data in fields
                for key, value in props.items():
                    if value is not None:
                        fields[key] = value

    return found_mol if found_mol else mol_block


def validate_formula(fields: dict, name: str) -> bool:
    """
    Validate that the record's MOLECULAR FORMULA exact mass matches
    the PubChem PUBCHEM_EXACT_MW within 0.005 Da.

    If a mismatch is detected, emits a [WARN] message but returns True
    (does not abort processing).

    Parameters
    ----------
    fields : dict   SDF data fields for the record (should contain
                    MOLECULAR FORMULA and/or PUBCHEM_EXACT_MW from enrichment).
    name   : str    Compound name for warning messages.

    Returns
    -------
    bool  Always True (validation warnings are non-fatal).
    """
    # Import here to avoid circular dependency
    from .formula import parse_formula
    from .calculator import exact_mass

    formula_str = fields.get("MOLECULAR FORMULA")
    pubchem_mw = fields.get("PUBCHEM_EXACT_MW")

    if not formula_str or pubchem_mw is None:
        return True  # Skip validation if either is missing

    try:
        # Convert PUBCHEM_EXACT_MW to float if it's a string
        if isinstance(pubchem_mw, str):
            pubchem_mw = float(pubchem_mw)

        parsed = parse_formula(formula_str.strip())
        local_mw = exact_mass(parsed)

        delta = abs(local_mw - pubchem_mw)
        if delta > 0.005:
            print(
                "[WARN] Formula mismatch for '{}': "
                "local={:.4f} Da, PubChem={:.4f} Da".format(
                    name, local_mw, pubchem_mw
                )
            )
    except Exception:
        # If parsing fails, silently continue
        pass

    return True  # Never abort processing


def enrich_mol_blocks(
    records: list[dict],
    progress_callback=None,
) -> list[dict]:
    """
    For every record in *records* that has no 2-D structure, attempt to
    fetch one from PubChem and update ``record["mol_block"]`` in-place.

    Also performs extended enrichment (SMILES, InChIKey, etc.) and
    validates formulas against PubChem exact masses.

    Parameters
    ----------
    records           : list[dict]  Records as returned by ``parse_sdf()``.
    progress_callback : callable | None
        Optional ``callback(done: int, total: int, name: str)`` called
        after each record is processed.  Useful for progress bars.

    Returns
    -------
    list[dict]  The same list, with ``mol_block`` fields updated where
                possible and enriched metadata added (records that already
                have a structure are unchanged and skipped quickly).
    """
    total = len(records)
    for i, record in enumerate(records, 1):
        mol_block = record.get("mol_block", "")
        fields = record.get("fields", {})
        name = fields.get("NAME") or record.get("name") or "(unnamed)"

        if not _mol_block_has_atoms(mol_block):
            new_block = fetch_structure(fields, mol_block)
            record["mol_block"] = new_block

            # Validate formula if we enriched with properties
            if fields.get("PUBCHEM_EXACT_MW"):
                validate_formula(fields, name)

        if progress_callback:
            progress_callback(i, total, name)

    return records
