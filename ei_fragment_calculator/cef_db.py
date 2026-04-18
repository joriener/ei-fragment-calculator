"""
cef_db.py
=========
SQLite database layer for CEF compounds (PRIMARY STORAGE).
Project-scoped: ~/.ei_fragment_calculator/compounds.db per project.
"""

from __future__ import annotations

import sqlite3
import json
from pathlib import Path
from dataclasses import asdict
from typing import Optional, List, Dict, Tuple
from datetime import datetime

from .cef_parser import CEFCompound, CEFLocation, CEFSpectrum, CEFPeak


class CEFDatabase:
    """SQLite database for compound storage."""

    def __init__(self, project_dir: Path):
        """Initialize database for a project."""
        self.project_dir = Path(project_dir)
        self.db_dir = self.project_dir / ".ei_fragment_calculator"
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.db_dir / "compounds.db"
        self._init_db()

    def _init_db(self):
        """Create tables if they don't exist."""
        with self.connection() as cursor:
            cursor.executescript("""
                CREATE TABLE IF NOT EXISTS cef_files (
                    id INTEGER PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    filepath TEXT NOT NULL,
                    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(project_id, filepath)
                );

                CREATE TABLE IF NOT EXISTS compounds (
                    id INTEGER PRIMARY KEY,
                    canonical_name TEXT NOT NULL,
                    molecular_mass_mz REAL NOT NULL,
                    retention_time REAL NOT NULL,
                    algorithm TEXT,
                    device_type TEXT,
                    polarity TEXT DEFAULT '+',
                    xml_metadata TEXT,
                    is_consolidated BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(molecular_mass_mz, retention_time)
                );

                CREATE TABLE IF NOT EXISTS compound_sources (
                    id INTEGER PRIMARY KEY,
                    compound_id INTEGER NOT NULL,
                    cef_file_id INTEGER NOT NULL,
                    original_name TEXT,
                    original_xml TEXT,
                    FOREIGN KEY(compound_id) REFERENCES compounds(id),
                    FOREIGN KEY(cef_file_id) REFERENCES cef_files(id)
                );

                CREATE TABLE IF NOT EXISTS spectra (
                    id INTEGER PRIMARY KEY,
                    compound_id INTEGER NOT NULL,
                    peak_mz REAL NOT NULL,
                    peak_intensity REAL NOT NULL,
                    peak_charge INTEGER DEFAULT 1,
                    peak_annotation TEXT,
                    peak_volume REAL,
                    FOREIGN KEY(compound_id) REFERENCES compounds(id)
                );

                CREATE TABLE IF NOT EXISTS consolidations (
                    id INTEGER PRIMARY KEY,
                    master_compound_id INTEGER NOT NULL,
                    source_compound_ids TEXT,
                    confidence REAL,
                    match_mass_ppm REAL,
                    match_rt_tolerance REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(master_compound_id) REFERENCES compounds(id)
                );

                CREATE INDEX IF NOT EXISTS idx_mass_rt ON compounds(molecular_mass_mz, retention_time);
                CREATE INDEX IF NOT EXISTS idx_filename ON cef_files(filename);
                CREATE INDEX IF NOT EXISTS idx_compound_sources ON compound_sources(compound_id);
                CREATE INDEX IF NOT EXISTS idx_spectra ON spectra(compound_id);
            """)

    def connection(self):
        """Context manager for database connection."""
        return _DBConnection(sqlite3.connect(self.db_path))

    def import_compounds(self, cef_file_path: str, compounds: List[CEFCompound]) -> Tuple[int, int]:
        """Import compounds from CEF file. Returns (file_id, imported_count)."""
        with self.connection() as cursor:

            cursor.execute("""
                INSERT OR IGNORE INTO cef_files (project_id, filename, filepath)
                VALUES (?, ?, ?)
            """, ("project_default", Path(cef_file_path).name, str(cef_file_path)))

            cursor.execute("SELECT id FROM cef_files WHERE filepath = ?", (str(cef_file_path),))
            file_id = cursor.fetchone()[0]

            imported = 0
            for compound in compounds:
                try:
                    # Store molecule info and location details in metadata
                    metadata = {
                        'molecule_name': compound.molecule_name,
                        'molecule_formula': compound.molecule_formula,
                        'is_identified': compound.is_identified,
                        'area': compound.location.area,
                        'height': compound.location.height
                    }

                    cursor.execute("""
                        INSERT OR IGNORE INTO compounds
                        (canonical_name, molecular_mass_mz, retention_time, algorithm, device_type, polarity, xml_metadata)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        compound.name,
                        compound.location.molecular_mass,
                        compound.location.retention_time,
                        compound.algorithm,
                        compound.device_type,
                        compound.spectrum.polarity,
                        json.dumps(metadata)
                    ))

                    cursor.execute(
                        "SELECT id FROM compounds WHERE molecular_mass_mz = ? AND retention_time = ?",
                        (compound.location.molecular_mass, compound.location.retention_time)
                    )
                    compound_id = cursor.fetchone()[0]

                    cursor.execute("""
                        INSERT INTO compound_sources (compound_id, cef_file_id, original_name, original_xml)
                        VALUES (?, ?, ?, ?)
                    """, (compound_id, file_id, compound.name, compound.original_xml))

                    for peak in compound.spectrum.peaks:
                        cursor.execute("""
                            INSERT INTO spectra
                            (compound_id, peak_mz, peak_intensity, peak_charge, peak_annotation, peak_volume)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (
                            compound_id, peak.mz, peak.intensity, peak.charge,
                            peak.annotation, peak.volume
                        ))

                    imported += 1
                except sqlite3.IntegrityError:
                    continue

            return file_id, imported

    def find_matches(self, compound_id: int, mass_tol: float = 0.5, rt_tol: float = 0.2) -> List[Dict]:
        """Find compounds matching mass/RT proximity."""
        with self.connection() as cursor:

            cursor.execute("SELECT molecular_mass_mz, retention_time FROM compounds WHERE id = ?", (compound_id,))
            result = cursor.fetchone()
            if not result:
                return []

            mass, rt = result

            cursor.execute("""
                SELECT id, canonical_name, molecular_mass_mz, retention_time
                FROM compounds
                WHERE ABS(molecular_mass_mz - ?) < ?
                  AND ABS(retention_time - ?) < ?
                  AND id != ?
            """, (mass, mass_tol, rt, rt_tol, compound_id))

            matches = []
            for row in cursor.fetchall():
                cid, name, m, r = row
                delta_mass = abs(m - mass)
                delta_rt = abs(r - rt)
                confidence = 1.0 - min(1.0, (delta_mass / mass_tol) ** 2 + (delta_rt / rt_tol) ** 2) ** 0.5
                matches.append({
                    'id': cid,
                    'name': name,
                    'mass': m,
                    'rt': r,
                    'delta_mass': delta_mass,
                    'delta_rt': delta_rt,
                    'confidence': confidence
                })

            return sorted(matches, key=lambda x: x['confidence'], reverse=True)

    def identify_duplicates(self, mass_tol: float = 0.5, rt_tol: float = 0.2) -> List[List[int]]:
        """Identify duplicate compound groups by proximity."""
        with self.connection() as cursor:

            cursor.execute("SELECT id, molecular_mass_mz, retention_time FROM compounds ORDER BY molecular_mass_mz, retention_time")
            compounds = cursor.fetchall()

            visited = set()
            groups = []

            for cid, mass, rt in compounds:
                if cid in visited:
                    continue

                group = [cid]
                visited.add(cid)

                for other_cid, other_mass, other_rt in compounds:
                    if other_cid in visited:
                        continue
                    if abs(mass - other_mass) < mass_tol and abs(rt - other_rt) < rt_tol:
                        group.append(other_cid)
                        visited.add(other_cid)

                if len(group) > 1:
                    groups.append(group)

            return groups

    def consolidate_group(self, group_ids: List[int], master_name: Optional[str] = None) -> int:
        """Merge duplicate compounds into master using average RT. Returns master_id."""
        with self.connection() as cursor:

            # Get all compounds in group to calculate average RT
            placeholders = ','.join('?' * len(group_ids))
            cursor.execute(
                f"SELECT molecular_mass_mz, retention_time FROM compounds WHERE id IN ({placeholders})",
                group_ids
            )
            rows = cursor.fetchall()

            if rows:
                mass = rows[0][0]  # Use mass from first compound
                avg_rt = sum(r[1] for r in rows) / len(rows)  # Calculate average RT
            else:
                return None

            cursor.execute(
                "SELECT canonical_name FROM compounds WHERE id = ? LIMIT 1",
                (group_ids[0] if master_name is None else group_ids[0],)
            )
            canonical_name = master_name or cursor.fetchone()[0]

            cursor.execute("""
                UPDATE compounds
                SET is_consolidated = 1, canonical_name = ?, retention_time = ?
                WHERE id = ?
            """, (canonical_name, avg_rt, group_ids[0]))

            cursor.execute("""
                INSERT INTO consolidations (master_compound_id, source_compound_ids, confidence)
                VALUES (?, ?, ?)
            """, (group_ids[0], json.dumps(group_ids), 1.0 if len(group_ids) <= 1 else 0.95))

            return group_ids[0]

    def get_compound(self, compound_id: int) -> Optional[Dict]:
        """Retrieve a single compound."""
        with self.connection() as cursor:
            cursor.execute("""
                SELECT id, canonical_name, molecular_mass_mz, retention_time,
                       algorithm, device_type, polarity, is_consolidated, xml_metadata
                FROM compounds WHERE id = ?
            """, (compound_id,))

            row = cursor.fetchone()
            if not row:
                return None

            cid, name, mass, rt, algo, device, pol, is_cons, xml_meta = row

            # Parse metadata
            metadata = json.loads(xml_meta) if xml_meta else {}
            molecule_name = metadata.get('molecule_name')
            molecule_formula = metadata.get('molecule_formula')
            is_identified = metadata.get('is_identified', False)
            area = metadata.get('area')
            height = metadata.get('height')

            cursor.execute(
                "SELECT peak_mz, peak_intensity, peak_charge, peak_annotation FROM spectra WHERE compound_id = ?",
                (compound_id,)
            )

            peaks = [{'mz': p[0], 'intensity': p[1], 'charge': p[2], 'annotation': p[3]} for p in cursor.fetchall()]

            # Get source files
            cursor.execute("""
                SELECT cf.filename FROM compound_sources cs
                JOIN cef_files cf ON cs.cef_file_id = cf.id
                WHERE cs.compound_id = ?
            """, (compound_id,))
            source_files = [row[0] for row in cursor.fetchall()]

            return {
                'id': cid,
                'name': name,
                'mass': mass,
                'rt': rt,
                'algorithm': algo,
                'device_type': device,
                'polarity': pol,
                'is_consolidated': bool(is_cons),
                'peaks': peaks,
                'source_files': source_files,
                'molecule_name': molecule_name,
                'molecule_formula': molecule_formula,
                'is_identified': is_identified,
                'area': area,
                'height': height
            }

    def get_all_compounds(self, limit: Optional[int] = None) -> List[Dict]:
        """Retrieve all compounds."""
        with self.connection() as cursor:
            query = "SELECT id FROM compounds ORDER BY molecular_mass_mz, retention_time"
            if limit:
                query += f" LIMIT {limit}"
            cursor.execute(query)
            ids = [row[0] for row in cursor.fetchall()]
            return [self.get_compound(cid) for cid in ids if self.get_compound(cid)]

    def get_all_cef_files(self) -> List[Dict]:
        """Retrieve all imported CEF files."""
        with self.connection() as cursor:
            cursor.execute("SELECT id, filename, filepath, imported_at FROM cef_files ORDER BY imported_at DESC")
            files = []
            for row in cursor.fetchall():
                # Count compounds from this file
                cursor.execute("SELECT COUNT(*) FROM compound_sources WHERE cef_file_id = ?", (row[0],))
                count = cursor.fetchone()[0]
                files.append({
                    'id': row[0],
                    'filename': row[1],
                    'filepath': row[2],
                    'imported_at': row[3],
                    'compound_count': count
                })
            return files

    def get_compounds_by_file(self, cef_file_id: int) -> List[Dict]:
        """Retrieve compounds from a specific CEF file."""
        with self.connection() as cursor:
            cursor.execute("""
                SELECT DISTINCT c.id FROM compounds c
                JOIN compound_sources cs ON c.id = cs.compound_id
                WHERE cs.cef_file_id = ?
                ORDER BY c.molecular_mass_mz, c.retention_time
            """, (cef_file_id,))
            ids = [row[0] for row in cursor.fetchall()]
            return [self.get_compound(cid) for cid in ids if self.get_compound(cid)]

    def delete_compound(self, compound_id: int) -> None:
        """Delete a compound and its associated data."""
        with self.connection() as cursor:
            cursor.execute("DELETE FROM spectra WHERE compound_id = ?", (compound_id,))
            cursor.execute("DELETE FROM compound_sources WHERE compound_id = ?", (compound_id,))
            cursor.execute("DELETE FROM compounds WHERE id = ?", (compound_id,))

    def update_metadata(self, compound_id: int, metadata_dict: Dict) -> None:
        """Update compound metadata (name, polarity, etc.)."""
        with self.connection() as cursor:
            if 'name' in metadata_dict:
                cursor.execute("UPDATE compounds SET canonical_name = ? WHERE id = ?",
                             (metadata_dict['name'], compound_id))
            if 'polarity' in metadata_dict:
                cursor.execute("UPDATE compounds SET polarity = ? WHERE id = ?",
                             (metadata_dict['polarity'], compound_id))
            cursor.execute("UPDATE compounds SET xml_metadata = ? WHERE id = ?",
                         (json.dumps(metadata_dict), compound_id))


class _DBConnection:
    """Context manager for database connections."""
    def __init__(self, conn):
        self.conn = conn
        self.cursor = conn.cursor()

    def __enter__(self):
        return self.cursor

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.conn.close()
