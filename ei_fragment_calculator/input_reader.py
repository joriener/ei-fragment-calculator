"""
input_reader.py
===============
Multi-format input reader for EI mass spectral data.

Supported formats
-----------------
SDF  (.sdf, .sd)        — MDL Structure-Data File (V2000 MOL + named fields)
MSP  (.msp, .mspec)     — NIST Mass Spectral format
JDX  (.jdx, .jcamp, .dx) — JCAMP-DX mass spectrum
CSV  (.csv, .tsv, .txt) — tabular peak lists (two layout variants)

All parsers return the same internal record schema used by parse_sdf():
    [{"name": str, "mol_block": str, "fields": dict[str, str]}, ...]

The ``fields`` dict always uses the standard field names expected by
get_formula_and_peaks() and cli.py:
    "MOLECULAR FORMULA"   — elemental formula string
    "MASS SPECTRAL PEAKS" — space- or newline-separated mz intensity pairs

Formula derivation from MOL block
----------------------------------
If the MOLECULAR FORMULA field is absent but the MOL block contains a
non-empty atom table, the formula is derived automatically using
parse_mol_block_full().  A ``"_derived_formula"`` flag is set in the
record's fields dict so callers can emit a [WARN] message.

Encoding
--------
SDF files are tried with UTF-8 first, then Latin-1 (ISO-8859-1), then
CP1252.  All other formats are read as UTF-8 with error replacement.
"""

import os
import re
from .sdf_parser import parse_sdf
from .mol_parser import parse_mol_block_full


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def read_records(filepath: str) -> list[dict]:
    """
    Auto-detect the format of *filepath* and return one dict per compound.

    Detection order:
      1. File extension (.sdf/.sd, .msp, .jdx/.jcamp/.dx, .csv/.tsv/.txt)
      2. Content sniff of the first 512 bytes if extension is ambiguous

    Parameters
    ----------
    filepath : str  Path to the input file.

    Returns
    -------
    list[dict]  Each dict has:
        ``name``      : str   Compound name / identifier.
        ``mol_block`` : str   MDL MOL block, or "" if unavailable.
        ``fields``    : dict  Named data fields including at minimum
                              "MOLECULAR FORMULA" and "MASS SPECTRAL PEAKS"
                              when available.

    Raises
    ------
    FileNotFoundError  if the file does not exist.
    ValueError         if the format cannot be determined.
    """
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"Input file not found: {filepath!r}")

    ext = os.path.splitext(filepath)[1].lower()

    if ext in (".sdf", ".sd"):
        return _read_sdf(filepath)
    if ext in (".msp", ".mspec"):
        return _read_msp(filepath)
    if ext in (".jdx", ".jcamp", ".dx"):
        return _read_jdx(filepath)
    if ext in (".csv", ".tsv", ".txt"):
        return _read_csv(filepath)

    # Extension ambiguous — sniff first 512 bytes
    return _sniff_and_read(filepath)


# ---------------------------------------------------------------------------
# Format: SDF
# ---------------------------------------------------------------------------

def _read_sdf(filepath: str) -> list[dict]:
    """
    Parse an SDF file using the existing sdf_parser.parse_sdf() with an
    encoding fallback cascade (UTF-8 → Latin-1 → CP1252).

    Adds formula derivation from MOL block when the MOLECULAR FORMULA field
    is absent but the atom table is non-empty.
    """
    records = _parse_sdf_with_encoding_fallback(filepath)
    for rec in records:
        _maybe_derive_formula(rec)
    return records


def _parse_sdf_with_encoding_fallback(filepath: str) -> list[dict]:
    for encoding in ("utf-8", "latin-1", "cp1252"):
        try:
            with open(filepath, "r", encoding=encoding, errors="strict") as fh:
                text = fh.read()
            break
        except (UnicodeDecodeError, LookupError):
            continue
    else:
        # Last resort: UTF-8 with replacement characters
        with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()

    # Re-use the SDF splitting/field logic from sdf_parser but feed it text
    # rather than a file.  We replicate parse_sdf() internals here because
    # parse_sdf() opens the file itself (always UTF-8).
    raw_records = text.split("$$$$")
    records: list[dict] = []

    for raw in raw_records:
        raw = raw.strip()
        if not raw:
            continue
        lines = raw.splitlines()
        name = lines[0].strip() if lines else ""
        mol_block_lines: list[str] = []
        fields: dict[str, str] = {}
        field_name: str | None = None
        value_lines: list[str] = []
        in_mol_block = True

        for line in lines:
            header_match = re.match(r"^>\s*<([^>]+)>", line)
            if header_match:
                in_mol_block = False
                if field_name is not None:
                    fields[field_name] = "\n".join(value_lines).strip()
                field_name = header_match.group(1).strip()
                value_lines = []
            elif in_mol_block:
                mol_block_lines.append(line)
            elif field_name is not None:
                value_lines.append(line)

        if field_name is not None:
            fields[field_name] = "\n".join(value_lines).strip()

        mol_block = "\n".join(mol_block_lines).strip()
        records.append({"name": name, "mol_block": mol_block, "fields": fields})

    return records


# ---------------------------------------------------------------------------
# Format: MSP
# ---------------------------------------------------------------------------

def _read_msp(filepath: str) -> list[dict]:
    """
    Parse a NIST Mass Spectral (.msp) file.

    MSP records are separated by one or more blank lines.
    Each record begins with ``Name: <compound>`` and ends with a block of
    ``mz intensity`` peak pairs, preceded by ``Num Peaks: N``.
    """
    with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()

    records: list[dict] = []
    current: dict[str, str] = {}
    peak_lines: list[str] = []
    reading_peaks = False
    peaks_remaining = 0

    def _flush(current, peak_lines):
        if not current:
            return
        fields: dict[str, str] = {}
        formula = current.get("formula") or current.get("mf") or current.get("cf")
        if formula:
            fields["MOLECULAR FORMULA"] = formula.strip()
        mw = current.get("mw") or current.get("molecular weight")
        if mw:
            fields["MW"] = mw.strip()
        comments = current.get("comments")
        if comments:
            fields["COMMENTS"] = comments.strip()
        if peak_lines:
            fields["MASS SPECTRAL PEAKS"] = "\n".join(peak_lines)
        records.append({
            "name": current.get("name", ""),
            "mol_block": "",
            "fields": fields,
        })

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if reading_peaks:
            if line == "" or re.match(r"^name\s*:", line, re.IGNORECASE):
                # End of peak block
                reading_peaks = False
                peaks_remaining = 0
                if line == "":
                    # blank line between records
                    _flush(current, peak_lines)
                    current = {}
                    peak_lines = []
                    continue
                # else fall through to handle the Name: line below
            else:
                # Parse one or more mz/intensity pairs on this line
                # NIST allows multiple pairs per line; delimiters: space, tab, comma, semicolon
                tokens = re.split(r"[\s,;]+", line)
                tokens = [t for t in tokens if t]
                for i in range(0, len(tokens) - 1, 2):
                    peak_lines.append(f"{tokens[i]} {tokens[i+1]}")
                if peaks_remaining > 0:
                    peaks_remaining -= len(tokens) // 2
                continue

        if not line:
            # Blank line between records — flush current
            if current:
                _flush(current, peak_lines)
                current = {}
                peak_lines = []
            continue

        # Key: value line
        kv = re.match(r"^([^:]+):\s*(.*)", line)
        if kv:
            key = kv.group(1).strip().lower()
            val = kv.group(2).strip()
            if key in ("num peaks", "num_peaks", "numpeaks"):
                try:
                    peaks_remaining = int(val)
                except ValueError:
                    peaks_remaining = 0
                reading_peaks = True
            else:
                current[key] = val

    # Flush last record
    _flush(current, peak_lines)
    return records


# ---------------------------------------------------------------------------
# Format: JCAMP-DX
# ---------------------------------------------------------------------------

def _read_jdx(filepath: str) -> list[dict]:
    """
    Parse a JCAMP-DX (.jdx) mass spectrum file.

    Each compound is delimited by ``##END=``.  Peak data follows
    ``##XYDATA=(XY..XY)`` or ``##PEAK TABLE=`` lines as X Y pairs.
    """
    with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()

    records: list[dict] = []

    # Split on ##END= (case-insensitive)
    blocks = re.split(r"##END\s*=.*", text, flags=re.IGNORECASE)

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        meta: dict[str, str] = {}
        peak_lines: list[str] = []
        reading_peaks = False

        for raw_line in block.splitlines():
            line = raw_line.strip()

            if reading_peaks:
                if line.startswith("##"):
                    reading_peaks = False
                    # Fall through to handle this ## line
                else:
                    if line:
                        peak_lines.append(line)
                    continue

            if line.startswith("##"):
                # Parse ##LABEL=value
                m = re.match(r"^##([^=]+)=\s*(.*)", line)
                if not m:
                    continue
                label = m.group(1).strip().upper()
                value = m.group(2).strip()

                if label == "TITLE":
                    meta["title"] = value
                elif label in ("FORMULA", "MOLECULAR FORMULA", "$FORMULA"):
                    meta["formula"] = value
                elif label in ("MW", "MOLECULAR WEIGHT"):
                    meta["mw"] = value
                elif label in ("XYDATA", "PEAK TABLE"):
                    reading_peaks = True
                    # value is the format specifier, e.g. "(XY..XY)" — ignore
                # other ## labels (JCAMP-DX, DATA TYPE, etc.) are silently ignored

        if not meta:
            continue

        fields: dict[str, str] = {}
        if meta.get("formula"):
            fields["MOLECULAR FORMULA"] = meta["formula"]
        if meta.get("mw"):
            fields["MW"] = meta["mw"]
        if peak_lines:
            fields["MASS SPECTRAL PEAKS"] = "\n".join(peak_lines)

        records.append({
            "name": meta.get("title", ""),
            "mol_block": "",
            "fields": fields,
        })

    return records


# ---------------------------------------------------------------------------
# Format: CSV / TSV
# ---------------------------------------------------------------------------

def _read_csv(filepath: str) -> list[dict]:
    """
    Parse a CSV or TSV file containing EI peak data.

    Two layout variants are supported:

    Layout A — per-compound key-value blocks (human-friendly):
        Name,Caffeine
        Formula,C8H10N4O2
        MW,194
        mz,intensity
        55,28
        ...
        (blank line separates compounds)

    Layout B — flat table (R/Python exports):
        compound,formula,mz,intensity
        Caffeine,C8H10N4O2,55,28
        Caffeine,C8H10N4O2,69,18
        ...

    Layout is auto-detected from the header row.  The column delimiter
    (comma or tab) is also auto-detected from the first line.
    """
    with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()

    lines = [ln.rstrip("\r\n") for ln in text.splitlines()]
    if not lines:
        return []

    # Detect delimiter
    first_non_empty = next((l for l in lines if l.strip()), "")
    delim = "\t" if first_non_empty.count("\t") >= first_non_empty.count(",") else ","

    # Detect layout
    header_lower = first_non_empty.split(delim)[0].strip().lower()
    if header_lower in ("compound", "name", "compounds"):
        # Check if second column is "formula" / "mz" — flat table
        cols = [c.strip().lower() for c in first_non_empty.split(delim)]
        if len(cols) >= 3 and any(c in cols for c in ("mz", "mass", "m/z")):
            return _read_csv_flat(lines, delim)

    return _read_csv_block(lines, delim)


def _read_csv_block(lines: list[str], delim: str) -> list[dict]:
    """Layout A: per-compound key-value blocks separated by blank lines."""
    records: list[dict] = []
    current_meta: dict[str, str] = {}
    current_peaks: list[str] = []
    reading_peaks = False

    def _flush(meta, peaks):
        if not meta and not peaks:
            return
        fields: dict[str, str] = {}
        formula = meta.get("formula") or meta.get("mf")
        if formula:
            fields["MOLECULAR FORMULA"] = formula.strip()
        mw = meta.get("mw") or meta.get("molecular weight")
        if mw:
            fields["MW"] = mw.strip()
        if peaks:
            fields["MASS SPECTRAL PEAKS"] = "\n".join(peaks)
        records.append({
            "name": meta.get("name", meta.get("compound", "")),
            "mol_block": "",
            "fields": fields,
        })

    for raw in lines:
        line = raw.strip()

        if not line:
            # Blank line: flush current compound
            if current_meta or current_peaks:
                _flush(current_meta, current_peaks)
                current_meta = {}
                current_peaks = []
                reading_peaks = False
            continue

        parts = [p.strip() for p in line.split(delim)]
        if len(parts) < 2:
            continue

        key_lower = parts[0].lower()

        if key_lower in ("name", "compound"):
            reading_peaks = False
            current_meta["name"] = parts[1]
        elif key_lower in ("formula", "mf", "molecular formula"):
            current_meta["formula"] = parts[1]
        elif key_lower in ("mw", "molecular weight", "mol weight"):
            current_meta["mw"] = parts[1]
        elif key_lower in ("mz", "m/z", "mass") and parts[1].lower() in ("intensity", "rel. abund.", "rel abund", "abundance"):
            # Header row of peak table
            reading_peaks = True
        elif reading_peaks:
            # Peak data line
            try:
                mz = int(float(parts[0]))
                int(float(parts[1]))   # validate intensity is numeric
                current_peaks.append(f"{mz} {parts[1]}")
            except (ValueError, IndexError):
                pass
        elif re.match(r"^\d+$", parts[0]) and re.match(r"^\d+", parts[1]):
            # Numeric row without explicit header → treat as peak
            current_peaks.append(f"{parts[0]} {parts[1]}")

    # Flush last record
    if current_meta or current_peaks:
        _flush(current_meta, current_peaks)

    return records


def _read_csv_flat(lines: list[str], delim: str) -> list[dict]:
    """Layout B: flat table with compound/formula/mz/intensity columns."""
    if not lines:
        return []

    header = [c.strip().lower() for c in lines[0].split(delim)]

    # Find column indices
    def _find_col(*names):
        for n in names:
            if n in header:
                return header.index(n)
        return None

    i_name    = _find_col("compound", "name", "compounds")
    i_formula = _find_col("formula", "mf", "molecular formula")
    i_mz      = _find_col("mz", "m/z", "mass")
    i_int     = _find_col("intensity", "rel. abund.", "abundance", "abund")

    if i_name is None or i_mz is None:
        return []

    # Group rows by compound name
    compound_order: list[str] = []
    compounds: dict[str, dict] = {}

    for raw in lines[1:]:
        raw = raw.strip()
        if not raw:
            continue
        parts = [p.strip() for p in raw.split(delim)]
        if len(parts) <= max(filter(lambda x: x is not None, [i_name, i_mz])):
            continue

        name = parts[i_name] if i_name < len(parts) else ""
        if name not in compounds:
            compound_order.append(name)
            compounds[name] = {"name": name, "formula": "", "peaks": []}

        if i_formula is not None and i_formula < len(parts):
            compounds[name]["formula"] = compounds[name]["formula"] or parts[i_formula]

        if i_mz < len(parts):
            try:
                mz = int(float(parts[i_mz]))
                intensity_str = parts[i_int] if (i_int is not None and i_int < len(parts)) else "999"
                compounds[name]["peaks"].append(f"{mz} {intensity_str}")
            except (ValueError, IndexError):
                pass

    records: list[dict] = []
    for name in compound_order:
        c = compounds[name]
        fields: dict[str, str] = {}
        if c["formula"]:
            fields["MOLECULAR FORMULA"] = c["formula"]
        if c["peaks"]:
            fields["MASS SPECTRAL PEAKS"] = "\n".join(c["peaks"])
        records.append({"name": c["name"], "mol_block": "", "fields": fields})

    return records


# ---------------------------------------------------------------------------
# Content sniff (unknown extension)
# ---------------------------------------------------------------------------

def _sniff_and_read(filepath: str) -> list[dict]:
    """Detect format from first 512 bytes and dispatch to the right parser."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
            head = fh.read(512)
    except OSError as exc:
        raise ValueError(f"Cannot read {filepath!r}: {exc}") from exc

    head_lower = head.lower()
    if "$$$$" in head or re.search(r"^>\s*<", head, re.MULTILINE):
        return _read_sdf(filepath)
    if re.search(r"^name\s*:", head, re.MULTILINE | re.IGNORECASE):
        return _read_msp(filepath)
    if re.search(r"^##title\s*=", head, re.MULTILINE | re.IGNORECASE):
        return _read_jdx(filepath)
    if re.search(r"^compound\s*[,\t]|^name\s*[,\t]|^mz\s*[,\t]", head, re.MULTILINE | re.IGNORECASE):
        return _read_csv(filepath)

    raise ValueError(
        f"Cannot determine format of {filepath!r}. "
        "Supported extensions: .sdf, .msp, .mspec, .jdx, .csv, .tsv"
    )


# ---------------------------------------------------------------------------
# Formula derivation from MOL block
# ---------------------------------------------------------------------------

_HILL_ORDER_PREFIX = ("C", "H")


def _derive_formula_from_mol(mol_block: str) -> str | None:
    """
    Derive an elemental formula string from a V2000 MOL atom table.

    Returns Hill-order formula (C first, H second, then alphabetical),
    or None if the MOL block has no atoms or cannot be parsed.

    Includes implicit hydrogens calculated from valence and bond degrees.
    """
    mol_data = parse_mol_block_full(mol_block)
    if mol_data is None:
        return None

    # Use the composition dict which includes implicit hydrogens
    counts = mol_data.get("composition", {})
    if not counts:
        return None

    # Build Hill-order formula string
    parts: list[str] = []
    for el in _HILL_ORDER_PREFIX:
        if el in counts:
            n = counts[el]
            parts.append(el if n == 1 else f"{el}{n}")
    for el in sorted(k for k in counts if k not in _HILL_ORDER_PREFIX):
        n = counts[el]
        parts.append(el if n == 1 else f"{el}{n}")

    return "".join(parts) if parts else None


def _maybe_derive_formula(record: dict) -> None:
    """
    If the record has no MOLECULAR FORMULA field but has a non-empty MOL
    block with atoms, derive the formula and set ``_derived_formula = "1"``.
    """
    fields = record.get("fields", {})
    # Check if formula already present (case-insensitive)
    upper_keys = {k.upper() for k in fields}
    if "MOLECULAR FORMULA" in upper_keys:
        return

    mol_block = record.get("mol_block", "")
    if not mol_block:
        return

    formula = _derive_formula_from_mol(mol_block)
    if formula:
        fields["MOLECULAR FORMULA"] = formula
        fields["_derived_formula"] = "1"
