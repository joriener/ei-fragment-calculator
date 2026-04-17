"""
MSPEC Format Parser - NIST MassHunter Library Format

Parses .MSPEC files which are plain text files with record structure:
- Field lines: "Key: Value" format
- Multiple Synon: fields allowed (collect into list)
- Retention_index: special format with column types
- Peak data: space/semicolon delimited m/z intensity pairs
- Records separated by blank lines
"""

import re
from typing import Dict, List, Tuple, Optional, Any


def parse_retention_index(ri_string: str) -> Dict[str, Tuple[float, Optional[float], Optional[int]]]:
    """
    Parse Retention_index field with multiple column types.

    Format: "SemiStdNP=1404/7/125 StdNP=1361/11/49 StdPolar=2568/15/128"

    Each segment: ColumnType=RI_value/deviation/datapoints
    - RI_value: actual retention index
    - deviation: uncertainty/standard deviation
    - datapoints: number of measurements

    Returns: {
        'SemiStdNP': (1404.0, 7.0, 125),
        'StdNP': (1361.0, 11.0, 49),
        'StdPolar': (2568.0, 15.0, 128)
    }
    """
    result = {}
    for pair in ri_string.split():
        if '=' in pair:
            column_type, value_str = pair.split('=', 1)
            parts = value_str.split('/')
            try:
                if len(parts) == 3:
                    ri_val = float(parts[0])
                    deviation = float(parts[1])
                    datapoints = int(parts[2])
                    result[column_type] = (ri_val, deviation, datapoints)
                elif len(parts) == 1:
                    ri_val = float(parts[0])
                    result[column_type] = (ri_val, None, None)
            except (ValueError, TypeError) as e:
                print(f"[WARN] Failed to parse RI value '{pair}': {e}")
                continue
    return result


def parse_peaks_from_mspec(lines: List[str]) -> List[Tuple[float, float]]:
    """
    Parse peak data from MSPEC format.

    Input lines like:
    "14 1; 15 10; 25 1; 26 7; 27 26;"
    "28 1; 29 38; 30 2; 31 6; 36 1;"

    Returns list of (mz, intensity) tuples.
    """
    peaks = []
    # Join all lines and split on delimiters
    text = ' '.join(lines)
    # Split on space, comma, or semicolon
    tokens = re.split(r'[\s,;]+', text.strip())

    for i in range(0, len(tokens) - 1, 2):
        try:
            mz = float(tokens[i])
            intensity = float(tokens[i + 1])
            peaks.append((mz, intensity))
        except (ValueError, IndexError):
            continue

    return peaks


def parse_mspec_file(filepath: str) -> List[Dict[str, Any]]:
    """
    Parse a .MSPEC file and return list of compound records.

    Each record is a dictionary with fields:
    - Name: compound name
    - Formula: molecular formula
    - MW: molecular weight
    - ExactMass: exact mass
    - CAS#: CAS registry number
    - Synon: list of synonyms
    - Retention_index: dict of column_type -> (ri_val, deviation, datapoints)
    - peaks: list of (mz, intensity) tuples
    - Other fields as metadata

    Args:
        filepath: Path to .MSPEC file

    Returns:
        List of record dictionaries
    """
    records = []

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # Split records by blank lines (one or more)
        record_blocks = re.split(r'\n\s*\n+', content.strip())

        for block in record_blocks:
            if not block.strip():
                continue

            record = _parse_record_block(block)
            if record:  # Only add non-empty records
                records.append(record)

    except Exception as e:
        print(f"[ERROR] Failed to parse MSPEC file '{filepath}': {e}")
        raise

    return records


def _parse_record_block(block: str) -> Optional[Dict[str, Any]]:
    """
    Parse a single record block from MSPEC file.

    Returns dictionary with parsed fields or None if invalid.
    """
    record = {}
    lines = block.strip().split('\n')

    if not lines:
        return None

    current_field = None
    current_value_lines = []
    peak_mode = False
    peak_lines = []

    for line in lines:
        line = line.rstrip()
        if not line:
            continue

        # Check if this is a field line (Key: Value format)
        if ':' in line and not peak_mode:
            # Save previous field if exists
            if current_field:
                _store_field(record, current_field, current_value_lines)
            current_value_lines = []

            # Parse new field
            parts = line.split(':', 1)
            current_field = parts[0].strip()
            value = parts[1].strip() if len(parts) > 1 else ""

            # Check if this is Num Peaks field (start of peak data)
            if current_field == "Num Peaks":
                try:
                    num_peaks = int(value)
                    record["Num Peaks"] = num_peaks
                    current_field = None
                    peak_mode = True
                    continue
                except ValueError:
                    pass

            current_value_lines = [value] if value else []

        elif peak_mode:
            # Accumulate peak data lines
            peak_lines.append(line)
        else:
            # Continuation of previous field value
            if current_field:
                current_value_lines.append(line)

    # Save last field
    if current_field:
        _store_field(record, current_field, current_value_lines)

    # Parse accumulated peak lines
    if peak_lines:
        peaks = parse_peaks_from_mspec(peak_lines)
        record["peaks"] = peaks

    return record if record else None


def _store_field(record: Dict[str, Any], field_name: str, value_lines: List[str]) -> None:
    """
    Store a parsed field in the record dictionary.

    Handles special fields:
    - Synon: accumulate into list
    - Retention_index: parse special format
    - Other fields: join and store
    """
    if not value_lines:
        return

    value_text = ' '.join(v.strip() for v in value_lines if v.strip())

    if field_name == "Synon":
        # Accumulate synonyms into list
        if "Synon" not in record:
            record["Synon"] = []
        record["Synon"].append(value_text)

    elif field_name == "Retention_index":
        # Parse Retention_index format
        ri_dict = parse_retention_index(value_text)
        record["Retention_index"] = ri_dict

    else:
        # Store other fields as-is
        record[field_name] = value_text if value_text else None


# Utility function for testing
if __name__ == "__main__":
    import json

    # Test with sample MSPEC file
    test_file = r"D:\Test\test.MSPEC"
    try:
        records = parse_mspec_file(test_file)
        print(f"Parsed {len(records)} records from {test_file}")
        for i, record in enumerate(records):
            print(f"\nRecord {i+1}: {record.get('Name', 'Unknown')}")
            print(f"  RI data: {record.get('Retention_index', {})}")
            print(f"  Peaks: {len(record.get('peaks', []))} peaks")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
