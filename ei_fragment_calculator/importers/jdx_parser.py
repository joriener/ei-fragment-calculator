"""
JDX/JCAMP-DX Format Parser - JCAMP-DX spectroscopic data format

Parses .JDX/.JCAMP files which are text files with spectroscopic data in JCAMP-DX format:
- Header lines: "##KEY=VALUE" format
- Common fields: ##TITLE, ##FORMULA, ##MOLFORM, ##NPOINTS, ##PEAKSEARCH, etc.
- Peak data: various formats (XY, PEAKSEARCH, XYDATA, etc.)
- Records separated by ##END marker
"""

import re
from typing import Dict, List, Tuple, Optional, Any


def parse_jdx_file(filepath: str) -> List[Dict[str, Any]]:
    """
    Parse a .JDX/.JCAMP file and return list of compound records.

    Each record is a dictionary with fields:
    - Name: compound title/name
    - Formula: molecular formula
    - MOLFORM: alternative formula field
    - PEAKSEARCH: parsed peak data
    - peaks: list of (mz, intensity) tuples
    - Other metadata fields as-is

    Args:
        filepath: Path to .JDX/.JCAMP file

    Returns:
        List of record dictionaries
    """
    records = []

    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        # Split records by ##END marker or blank lines
        record_blocks = re.split(r'##END\s*\n?', content.strip())

        for block in record_blocks:
            if not block.strip():
                continue

            record = _parse_jdx_record(block)
            if record:
                records.append(record)

    except Exception as e:
        print(f"[ERROR] Failed to parse JDX file '{filepath}': {e}")
        raise

    return records


def _parse_jdx_record(block: str) -> Optional[Dict[str, Any]]:
    """
    Parse a single JDX record block.

    Returns dictionary with parsed fields or None if invalid.
    """
    record = {}
    lines = block.strip().split('\n')

    if not lines:
        return None

    # Parse header lines (##KEY=VALUE format)
    peak_data_started = False
    peak_lines = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check if this is a JDX header line
        if line.startswith('##'):
            # Extract key and value
            match = re.match(r'##([^=\s]+)\s*=\s*(.+)', line)
            if match:
                key = match.group(1).strip()
                value = match.group(2).strip()

                # Remove quotes if present
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]

                # Handle special keys
                if key.upper() == 'TITLE':
                    record['Name'] = value
                elif key.upper() == 'MOLFORM' or key.upper() == 'FORMULA':
                    record['Formula'] = value
                elif key.upper() == 'NPOINTS':
                    try:
                        record['NPOINTS'] = int(value)
                    except ValueError:
                        record['NPOINTS'] = value
                elif key.upper() == 'PEAKSEARCH':
                    peak_data_started = True
                    peak_lines.append(value)
                elif key.upper().startswith('XY') or key.upper() == 'XYDATA':
                    peak_data_started = True
                    peak_lines.append(value)
                else:
                    # Store other fields as metadata
                    record[key] = value
        elif peak_data_started:
            # Accumulate peak data lines
            peak_lines.append(line)

    # Parse accumulated peak data
    if peak_lines:
        peaks = _parse_jdx_peaks(peak_lines)
        if peaks:
            record['peaks'] = peaks

    return record if record else None


def _parse_jdx_peaks(lines: List[str]) -> List[Tuple[float, float]]:
    """
    Parse peak data from JDX format.

    Handles various formats:
    - PEAKSEARCH: "m/z=value intensity=value" format
    - XY/XYDATA: "m/z intensity" pairs (space or comma separated)
    - General: whitespace-separated pairs

    Returns list of (mz, intensity) tuples.
    """
    peaks = []

    # Join all lines
    text = ' '.join(lines)

    # Handle PEAKSEARCH format: "m/z=XXX intensity=YYY"
    peaksearch_pattern = r'm/z\s*=\s*([\d.]+)\s+intensity\s*=\s*([\d.]+)'
    peaksearch_matches = re.findall(peaksearch_pattern, text, re.IGNORECASE)
    if peaksearch_matches:
        for mz_str, intensity_str in peaksearch_matches:
            try:
                mz = float(mz_str)
                intensity = float(intensity_str)
                peaks.append((mz, intensity))
            except ValueError:
                continue
        if peaks:
            return peaks

    # Handle general format: space/comma/semicolon separated pairs
    # Remove common JCAMP markers
    text = re.sub(r'##\w+\s*=', '', text)
    text = re.sub(r'[(),]', ' ', text)

    # Split on whitespace and semicolons
    tokens = re.split(r'[\s;]+', text.strip())

    # Try to pair up tokens as (mz, intensity)
    for i in range(0, len(tokens) - 1, 2):
        try:
            mz = float(tokens[i])
            intensity = float(tokens[i + 1])

            # Basic validation: mz should be positive, intensity can be 0+
            if mz > 0:
                peaks.append((mz, intensity))
        except (ValueError, IndexError):
            continue

    return peaks


def parse_jdx_peaks_string(peak_string: str) -> List[Tuple[float, float]]:
    """
    Parse a single peak string in various JDX formats.

    Utility function for parsing individual peak data strings.
    """
    return _parse_jdx_peaks([peak_string])


# Utility function for testing
if __name__ == "__main__":
    import json

    # Test with sample JDX file
    test_file = r"D:\Test\test.jdx"
    try:
        records = parse_jdx_file(test_file)
        print(f"Parsed {len(records)} records from {test_file}")
        for i, record in enumerate(records):
            print(f"\nRecord {i+1}: {record.get('Name', 'Unknown')}")
            print(f"  Formula: {record.get('Formula', 'N/A')}")
            print(f"  Peaks: {len(record.get('peaks', []))} peaks")
            if record.get('peaks'):
                print(f"    First peak: m/z={record['peaks'][0][0]}, intensity={record['peaks'][0][1]}")
    except FileNotFoundError:
        print(f"Test file not found: {test_file}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
