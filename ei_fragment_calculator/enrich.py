"""
enrich.py
=========
Retrieve missing compound metadata from external free databases and add it to
SDF records.

Databases queried (all free, no API key required)
-------------------------------------------------
PubChem   https://pubchem.ncbi.nlm.nih.gov/rest/pug
          formula, MW, SMILES, InChI, InChIKey, CAS, synonyms, PubChem CID
ChEBI     https://www.ebi.ac.uk/webservices/chebi/2.0/test
          CHEBI accession (by InChIKey)
KEGG      https://rest.kegg.jp
          KEGG compound C-number (by CAS or name)
HMDB      https://hmdb.ca
          HMDB metabolite accession (by InChIKey)

Fields NOT retrieved (measurement-specific, must come from the instrument):
  RETENTION TIME, ION MODE, IONIZATION, INSTRUMENT TYPE, COLLISION ENERGY

Fields calculated locally (no network needed):
  EXACT MASS  -- from FORMULA using data/elements.csv

SPLASH (spectral hash) is computed from the spectrum peaks if the optional
package ``splashpy`` is installed; otherwise it is skipped.

Usage
-----
>>> from ei_fragment_calculator.enrich import enrich_record, EnrichConfig
>>> from ei_fragment_calculator.sdf_parser import parse_sdf
>>> records = parse_sdf("my_spectra.sdf")
>>> enriched_fields, log = enrich_record(records[0])
>>> for line in log:
...     print(line)
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field as dc_field

# ---------------------------------------------------------------------------
# API base URLs
# ---------------------------------------------------------------------------

_PUBCHEM = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
_CHEBI   = "https://www.ebi.ac.uk/webservices/chebi/2.0/test"
_KEGG    = "https://rest.kegg.jp"
_HMDB    = "https://hmdb.ca"

_USER_AGENT = "ei-fragment-calculator/1.6.0 (https://github.com/joriener/ei-fragment-calculator)"

# regex for CAS registry numbers
_CAS_RE = re.compile(r"^\d{2,7}-\d{2}-\d$")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class EnrichConfig:
    """
    Toggle individual API sources and set rate-limit delay.

    Parameters
    ----------
    pubchem  : bool   Query PubChem (default True).
    chebi    : bool   Query ChEBI   (default True).
    kegg     : bool   Query KEGG    (default True).
    hmdb     : bool   Query HMDB    (default True).
    calc_exact_mass : bool  Calculate EXACT MASS from formula (default True).
    calc_splash     : bool  Calculate SPLASH hash if splashpy is available (default True).
    delay    : float  Seconds to wait between API calls (default 0.5).
    overwrite: bool   Overwrite existing non-empty field values (default False).
    """
    pubchem:          bool  = True
    chebi:            bool  = True
    kegg:             bool  = True
    hmdb:             bool  = True
    calc_exact_mass:  bool  = True
    calc_splash:      bool  = True
    delay:            float = 0.5
    overwrite:        bool  = False


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _get_json(url: str) -> dict | None:
    """HTTP GET, return parsed JSON or None on any error."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return None


def _get_text(url: str) -> str | None:
    """HTTP GET, return raw text or None on any error."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# PubChem
# ---------------------------------------------------------------------------

def query_pubchem(name: str, inchikey: str = "") -> dict:
    """
    Query PubChem by compound name or InChIKey.

    Returns a dict with keys (all str, empty string if not found):
        cid, formula, mw, smiles, inchi, inchikey, iupac_name, cas, synonyms

    References
    ----------
    PubChem PUG REST API: https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest
    Kim S. et al. (2023) Nucleic Acids Res. https://doi.org/10.1093/nar/gkad407
    """
    result: dict = {}

    # 1. Resolve to CID --------------------------------------------------
    if inchikey:
        url  = "{}/compound/inchikey/{}/cids/JSON".format(
            _PUBCHEM, urllib.parse.quote(inchikey, safe=""))
        data = _get_json(url)
        cids = (data or {}).get("IdentifierList", {}).get("CID", [])
        if not cids and name:
            # fall back to name
            url  = "{}/compound/name/{}/cids/JSON".format(
                _PUBCHEM, urllib.parse.quote(name, safe=""))
            data = _get_json(url)
            cids = (data or {}).get("IdentifierList", {}).get("CID", [])
    else:
        url  = "{}/compound/name/{}/cids/JSON".format(
            _PUBCHEM, urllib.parse.quote(name, safe=""))
        data = _get_json(url)
        cids = (data or {}).get("IdentifierList", {}).get("CID", [])

    if not cids:
        return result

    cid = cids[0]
    result["cid"] = str(cid)

    # 2. Properties ------------------------------------------------------
    props = ("MolecularFormula,MolecularWeight,IUPACName,"
             "CanonicalSMILES,IsomericSMILES,InChI,InChIKey")
    url  = "{}/compound/cid/{}/property/{}/JSON".format(_PUBCHEM, cid, props)
    data = _get_json(url)
    if data:
        p = (data.get("PropertyTable") or {}).get("Properties", [{}])[0]
        result["formula"]    = p.get("MolecularFormula", "")
        result["mw"]         = str(p.get("MolecularWeight", ""))
        result["smiles"]     = p.get("IsomericSMILES") or p.get("CanonicalSMILES", "")
        result["inchi"]      = p.get("InChI", "")
        result["inchikey"]   = p.get("InChIKey", "")
        result["iupac_name"] = p.get("IUPACName", "")

    # 3. Synonyms (also extracts CAS) ------------------------------------
    url  = "{}/compound/cid/{}/synonyms/JSON".format(_PUBCHEM, cid)
    data = _get_json(url)
    if data:
        info = (data.get("InformationList") or {}).get("Information", [{}])
        syns = info[0].get("Synonym", []) if info else []
        result["synonyms"] = syns
        cas_hits = [s for s in syns if _CAS_RE.match(s)]
        if cas_hits:
            result["cas"] = cas_hits[0]

    return result


# ---------------------------------------------------------------------------
# ChEBI
# ---------------------------------------------------------------------------

def query_chebi(inchikey: str) -> str:
    """
    Query ChEBI SOAP/REST by InChIKey.  Returns a CHEBI ID string
    (e.g. ``"CHEBI:27432"``) or empty string if not found.

    References
    ----------
    ChEBI web services: https://www.ebi.ac.uk/chebi/webServices.do
    Hastings J. et al. (2016) J. Cheminform. https://doi.org/10.1186/s13321-016-0153-2
    """
    if not inchikey:
        return ""
    url  = ("{}/getLiteEntityByInChIKey"
            "?searchTerm={}&maximumResults=5&stars=ALL").format(
        _CHEBI, urllib.parse.quote(inchikey, safe=""))
    text = _get_text(url)
    if not text:
        return ""
    m = re.search(r"<chebiId>(CHEBI:\d+)</chebiId>", text)
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------
# KEGG
# ---------------------------------------------------------------------------

def query_kegg(name: str, cas: str = "") -> str:
    """
    Query KEGG Compound database by CAS registry number or compound name.
    Returns a KEGG C-number string (e.g. ``"C06427"``) or empty string.

    References
    ----------
    KEGG REST API: https://www.kegg.jp/kegg/rest/keggapi.html
    Kanehisa M. et al. (2023) Nucleic Acids Res. https://doi.org/10.1093/nar/gkac963
    """
    # Try by CAS first (more unique than name)
    if cas:
        url  = "{}/find/compound/{}/cas".format(
            _KEGG, urllib.parse.quote(cas, safe=""))
        text = _get_text(url)
        if text:
            m = re.search(r"cpd:(C\d+)", text)
            if m:
                return m.group(1)

    # Fall back to name search
    if name:
        url  = "{}/find/compound/{}".format(
            _KEGG, urllib.parse.quote(name, safe=""))
        text = _get_text(url)
        if text:
            m = re.search(r"cpd:(C\d+)", text)
            if m:
                return m.group(1)

    return ""


# ---------------------------------------------------------------------------
# HMDB
# ---------------------------------------------------------------------------

def query_hmdb(inchikey: str) -> str:
    """
    Query HMDB (Human Metabolome Database) by InChIKey.
    Returns an HMDB accession string (e.g. ``"HMDB0001388"``) or empty string.

    References
    ----------
    HMDB REST API: https://hmdb.ca/api
    Wishart D.S. et al. (2022) Nucleic Acids Res. https://doi.org/10.1093/nar/gkab1062
    """
    if not inchikey:
        return ""

    # Try PubChem cross-references first (often faster and more reliable)
    url  = "{}/compound/inchikey/{}/xrefs/RegistryID/JSON".format(
        _PUBCHEM, urllib.parse.quote(inchikey, safe=""))
    data = _get_json(url)
    if data:
        info  = (data.get("InformationList") or {}).get("Information", [{}])
        ids   = info[0].get("RegistryID", []) if info else []
        hmdb_hits = [x for x in ids if re.match(r"^HMDB\d+$", x)]
        if hmdb_hits:
            return hmdb_hits[0]

    # Fall back to direct HMDB search
    url  = "{}/metabolites/search.json?q={}".format(
        _HMDB, urllib.parse.quote(inchikey, safe=""))
    text = _get_text(url)
    if text:
        m = re.search(r"HMDB\d{5,7}", text)
        if m:
            return m.group(0)

    return ""


# ---------------------------------------------------------------------------
# SPLASH calculation
# ---------------------------------------------------------------------------

def _calc_splash(peaks_text: str) -> str:
    """
    Calculate the SPLASH spectral hash if ``splashpy`` is installed.
    Returns the SPLASH string or empty string if unavailable.

    References
    ----------
    Wohlgemuth G. et al. (2016) Nat. Biotechnol. https://doi.org/10.1038/nbt.3689
    SPLASH specification: https://splash.fiehnlab.ucdavis.edu/
    Install: pip install splashpy
    """
    try:
        from splashpy import splash, SpectrumType
    except ImportError:
        return ""

    tokens = re.findall(r"[\d.]+", peaks_text)
    if len(tokens) < 2:
        return ""
    if len(tokens) % 2 != 0:
        tokens = tokens[1:]
    try:
        pairs = [(float(tokens[i]), float(tokens[i + 1]))
                 for i in range(0, len(tokens) - 1, 2)]
        return splash(pairs, SpectrumType.MS)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Local exact-mass calculation
# ---------------------------------------------------------------------------

def _calc_exact_mass(formula: str) -> str:
    """
    Calculate exact monoisotopic mass from a molecular formula string.
    Uses the local elements.csv data (no network call).
    Returns a formatted string (6 d.p.) or empty string on failure.
    """
    if not formula:
        return ""
    try:
        from .formula    import parse_formula
        from .calculator import exact_mass
        comp = parse_formula(formula)
        return "{:.6f}".format(exact_mass(comp))
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Core enrichment function
# ---------------------------------------------------------------------------

def enrich_record(record: dict, config: EnrichConfig | None = None) -> tuple[dict, list[str]]:
    """
    Query external APIs to fill in missing metadata fields in one SDF record.

    Only fields that are **absent or empty** in the record are added (unless
    ``config.overwrite=True``).  Existing non-empty values are never changed by
    default, so it is safe to run enrichment on already-partially-filled records.

    Parameters
    ----------
    record : dict
        One record as returned by :func:`~ei_fragment_calculator.sdf_parser.parse_sdf`.
        Expected keys: ``name`` (str), ``mol_block`` (str), ``fields`` (dict).
    config : EnrichConfig | None
        Which APIs to query and rate-limit settings.  Defaults to all enabled
        with 0.5 s delay.

    Returns
    -------
    (enriched_fields : dict, log : list[str])
        ``enriched_fields`` - updated copy of ``record["fields"]`` with all
        newly retrieved entries appended.
        ``log`` - human-readable status lines (one per added/skipped field).
    """
    if config is None:
        config = EnrichConfig()

    fields    = dict(record.get("fields", {}))
    name      = (record.get("name") or "").strip()
    log: list[str] = []

    _upper: dict[str, str] = {k.upper(): k for k in fields}

    def _get(key: str) -> str:
        k = _upper.get(key.upper())
        return (fields.get(k) or "").strip() if k else ""

    def _set(key: str, val: str) -> None:
        if not val:
            return
        existing_key = _upper.get(key.upper())
        if existing_key:
            if fields.get(existing_key, "").strip() and not config.overwrite:
                return
            fields[existing_key] = val
        else:
            fields[key] = val
            _upper[key.upper()] = key
        log.append("  + {:<22s} {}".format(key, val[:70]))

    # PubChem
    pc: dict = {}
    if config.pubchem:
        ik = _get("INCHIKEY")
        log.append("[PubChem] querying '{}'...".format(name or ik))
        pc = query_pubchem(name, inchikey=ik)
        time.sleep(config.delay)
        if pc:
            _set("FORMULA",     pc.get("formula",    ""))
            _set("INCHIKEY",    pc.get("inchikey",   ""))
            _set("INCHI",       pc.get("inchi",      ""))
            _set("SMILES",      pc.get("smiles",     ""))
            _set("IUPAC_NAME",  pc.get("iupac_name", ""))
            _set("PUBCHEM_CID", pc.get("cid",        ""))
            if pc.get("cas"):
                _set("CAS",   pc["cas"])
                _set("CASNO", pc["cas"])
            if pc.get("synonyms"):
                _set("SYNONYMS", "\n".join(pc["synonyms"][:20]))
        else:
            log.append("  ! PubChem: no result for '{}'".format(name or ik))

    # ChEBI
    if config.chebi:
        ik = _get("INCHIKEY")
        if ik:
            log.append("[ChEBI]   querying InChIKey {}...".format(ik))
            chebi = query_chebi(ik)
            time.sleep(config.delay)
            if chebi:
                _set("CHEBI", chebi)
            else:
                log.append("  ! ChEBI: no result for {}".format(ik))

    # KEGG
    if config.kegg:
        cas = _get("CASNO") or _get("CAS")
        log.append("[KEGG]    querying '{}' (CAS={})...".format(name, cas or "n/a"))
        kegg = query_kegg(name, cas=cas)
        time.sleep(config.delay)
        if kegg:
            _set("KEGG", kegg)
        else:
            log.append("  ! KEGG: no result for '{}'".format(name))

    # HMDB
    if config.hmdb:
        ik = _get("INCHIKEY")
        if ik:
            log.append("[HMDB]    querying InChIKey {}...".format(ik))
            hmdb = query_hmdb(ik)
            time.sleep(config.delay)
            if hmdb:
                _set("HMDB", hmdb)
            else:
                log.append("  ! HMDB: no result for {}".format(ik))

    # Local: exact mass
    if config.calc_exact_mass:
        formula = _get("FORMULA")
        if formula and not _get("EXACT MASS"):
            em = _calc_exact_mass(formula)
            if em:
                _set("EXACT MASS", em)

    # SPLASH
    if config.calc_splash:
        peaks_text = _get("MASS SPECTRAL PEAKS")
        if peaks_text and not _get("SPLASH"):
            sp = _calc_splash(peaks_text)
            if sp:
                _set("SPLASH", sp)

    return fields, log


# ---------------------------------------------------------------------------
# Convenience: enrich an entire list of records
# ---------------------------------------------------------------------------

def enrich_records(
    records:  list[dict],
    config:   EnrichConfig | None = None,
    verbose:  bool = True,
) -> list[dict]:
    """
    Enrich a list of SDF records in-place and return the updated records.

    Each record's ``fields`` dict is replaced with the enriched version.
    The ``mol_block`` and ``name`` keys are left unchanged.
    """
    if config is None:
        config = EnrichConfig()

    for i, rec in enumerate(records):
        compound_name = rec.get("name") or "(unnamed)"
        if verbose:
            print("  [{}/{}] {}".format(i + 1, len(records), compound_name))
        enriched_fields, log = enrich_record(rec, config)
        rec["fields"] = enriched_fields
        if verbose:
            for line in log:
                print("   ", line)

    return records
