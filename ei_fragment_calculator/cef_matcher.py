"""
cef_matcher.py
==============
Compound matching and consolidation logic for CEF analysis.
Supports PPM-based mass matching, spectral similarity, and multiple matching strategies.
"""

from __future__ import annotations

from typing import List, Dict, Tuple, Optional
from typing import TYPE_CHECKING
from dataclasses import dataclass, field
import math


@dataclass
class MatchParameters:
    """Configuration for compound matching algorithm."""
    method: str = "mass_rt"  # "mass_rt", "ppm_rt", "spectral", "ppm_spectral"
    mass_ppm: float = 5.0  # PPM tolerance for mass matching (TOF default)
    mass_da: float = 0.5  # Absolute Da tolerance (quadrupole default)
    rt_tolerance: float = 0.2  # Minutes
    spectral_threshold: float = 0.8  # Minimum spectral similarity (0-1)
    spectral_weight: float = 0.4  # Weight in combined scoring
    peak_intensity_threshold: float = 0.05  # Ignore peaks <5% of base peak
    instrument_type: str = "tof"  # "tof", "quadrupole", "gc_ei"

    @classmethod
    def preset_tof(cls) -> MatchParameters:
        """High-resolution TOF parameters (5 ppm)."""
        return cls(method="ppm_rt", mass_ppm=5.0, rt_tolerance=0.2,
                   instrument_type="tof")

    @classmethod
    def preset_quadrupole(cls) -> MatchParameters:
        """Quadrupole parameters (±0.5 m/z)."""
        return cls(method="mass_rt", mass_da=0.5, rt_tolerance=0.2,
                   instrument_type="quadrupole")

    @classmethod
    def preset_gc_ei(cls) -> MatchParameters:
        """GC-EI parameters (spectral >0.8, then RT)."""
        return cls(method="spectral", spectral_threshold=0.8, rt_tolerance=0.1,
                   spectral_weight=0.8, instrument_type="gc_ei")


@dataclass
class Match:
    """A match between two compounds."""
    compound_id_1: int
    compound_id_2: int
    name_1: str
    name_2: str
    mass_1: float
    mass_2: float
    rt_1: float
    rt_2: float
    delta_mass: float
    delta_rt: float
    confidence: float
    spectral_similarity: float = 0.0
    method: str = "mass_rt"

    def __repr__(self):
        return (f"Match({self.name_1} <-> {self.name_2}, "
                f"dm={self.delta_mass:.4f}, drt={self.delta_rt:.3f}, "
                f"conf={self.confidence:.2f})")


class CEFMatcher:
    """Find matching compounds across CEF files with flexible matching strategies."""

    @staticmethod
    def compute_spectral_similarity(peaks_1: List[Dict], peaks_2: List[Dict],
                                    intensity_threshold: float = 0.05) -> float:
        """
        Compute cosine similarity between two spectra.
        Ignores peaks below intensity_threshold * max_intensity.
        Returns score in [0, 1].
        """
        if not peaks_1 or not peaks_2:
            return 0.0

        # Find base peaks and filter
        max_intensity_1 = max(p['intensity'] for p in peaks_1)
        max_intensity_2 = max(p['intensity'] for p in peaks_2)

        filtered_1 = {p['mz']: p['intensity']
                     for p in peaks_1
                     if p['intensity'] >= intensity_threshold * max_intensity_1}
        filtered_2 = {p['mz']: p['intensity']
                     for p in peaks_2
                     if p['intensity'] >= intensity_threshold * max_intensity_2}

        if not filtered_1 or not filtered_2:
            return 0.0

        # Find common m/z values (with 0.01 tolerance for floating point)
        mz_set_1 = set(filtered_1.keys())
        mz_set_2 = set(filtered_2.keys())

        # Build aligned vectors
        all_mz = sorted(set(list(mz_set_1) + list(mz_set_2)))
        intensity_vector_1 = []
        intensity_vector_2 = []

        for mz in all_mz:
            # Find matching peak within 0.01 Da
            int1 = next((filtered_1[m] for m in mz_set_1 if abs(m - mz) < 0.01), 0.0)
            int2 = next((filtered_2[m] for m in mz_set_2 if abs(m - mz) < 0.01), 0.0)
            intensity_vector_1.append(int1)
            intensity_vector_2.append(int2)

        # Compute cosine similarity
        dot_product = sum(a * b for a, b in zip(intensity_vector_1, intensity_vector_2))
        norm_1 = math.sqrt(sum(a ** 2 for a in intensity_vector_1))
        norm_2 = math.sqrt(sum(b ** 2 for b in intensity_vector_2))

        if norm_1 == 0 or norm_2 == 0:
            return 0.0

        similarity = dot_product / (norm_1 * norm_2)
        return max(0.0, min(1.0, similarity))  # Clamp to [0, 1]

    @staticmethod
    def compute_confidence(mass_delta: float, rt_delta: float,
                          mass_tol: float = 0.5, rt_tol: float = 0.2) -> float:
        """Compute match confidence score [0, 1]."""
        normalized_dist = math.sqrt(
            (mass_delta / mass_tol) ** 2 + (rt_delta / rt_tol) ** 2
        )
        confidence = 1.0 - min(normalized_dist, 1.0)
        return max(0.0, confidence)

    @staticmethod
    def compute_mass_delta_ppm(mass_1: float, mass_2: float) -> float:
        """Compute mass difference in PPM."""
        if mass_1 == 0:
            return float('inf')
        return abs(mass_2 - mass_1) / mass_1 * 1e6

    @staticmethod
    def check_mass_match(mass_1: float, mass_2: float, params: MatchParameters) -> bool:
        """Check if masses match within tolerance."""
        if params.method in ["ppm_rt", "ppm_spectral"]:
            # PPM-based (using average mass for more robust calculation)
            avg_mass = (abs(mass_1) + abs(mass_2)) / 2
            if avg_mass == 0:
                return False
            mass_delta_ppm = abs(mass_2 - mass_1) / avg_mass * 1e6
            return mass_delta_ppm <= params.mass_ppm
        else:
            # Absolute Da tolerance
            mass_delta_da = abs(mass_2 - mass_1)
            return mass_delta_da <= params.mass_da

    @staticmethod
    def check_rt_match(rt_1: float, rt_2: float, params: MatchParameters) -> bool:
        """Check if retention times match within tolerance."""
        return abs(rt_2 - rt_1) <= params.rt_tolerance

    @staticmethod
    def compute_combined_confidence(mass_delta: float, rt_delta: float,
                                   spectral_sim: float, params: MatchParameters) -> float:
        """Compute confidence based on selected method."""
        if params.method == "mass_rt":
            # Simple mass + RT
            return CEFMatcher.compute_confidence(mass_delta, rt_delta,
                                               params.mass_da, params.rt_tolerance)
        elif params.method == "ppm_rt":
            # PPM + RT: convert mass_delta (Da) to approximate ppm
            # Assume ~100 m/z average for rough conversion
            avg_mz = 150  # Typical analytical range
            mass_ppm = (mass_delta / avg_mz) * 1e6 if avg_mz > 0 else float('inf')
            # Normalize to 0-1 score
            mass_score = 1.0 - min(1.0, mass_ppm / params.mass_ppm) if params.mass_ppm > 0 else 0.0
            rt_score = 1.0 - min(1.0, rt_delta / params.rt_tolerance) if params.rt_tolerance > 0 else 0.0
            return (mass_score + rt_score) / 2
        elif params.method == "spectral":
            # Spectral dominant
            if spectral_sim < params.spectral_threshold:
                return 0.0
            # RT as secondary criterion
            rt_score = 1.0 - min(1.0, rt_delta / max(params.rt_tolerance, 0.01))
            return (spectral_sim * params.spectral_weight +
                   max(0, rt_score) * (1 - params.spectral_weight))
        elif params.method == "ppm_spectral":
            # Combined PPM + spectral
            avg_mz = 150
            mass_ppm = (mass_delta / avg_mz) * 1e6 if avg_mz > 0 else float('inf')
            mass_score = 1.0 - min(1.0, mass_ppm / params.mass_ppm) if params.mass_ppm > 0 else 0.0
            rt_score = 1.0 - min(1.0, rt_delta / max(params.rt_tolerance, 0.01))
            return (spectral_sim * params.spectral_weight +
                   mass_score * 0.3 +
                   max(0, rt_score) * 0.3)

        return 0.0

    @staticmethod
    def find_matches_for_compound(
        target_compound: Dict,
        all_compounds: List[Dict],
        params: Optional[MatchParameters] = None,
        top_n: Optional[int] = None
    ) -> List[Match]:
        """Find all matches for a single compound using specified parameters."""
        if params is None:
            params = MatchParameters()

        target_mass = target_compound['mass']
        target_rt = target_compound['rt']
        target_id = target_compound['id']
        target_name = target_compound['name']
        target_peaks = target_compound.get('peaks', [])

        matches = []

        for other in all_compounds:
            if other['id'] == target_id:
                continue

            # Check mass match
            if not CEFMatcher.check_mass_match(target_mass, other['mass'], params):
                continue

            # Check RT match
            if not CEFMatcher.check_rt_match(target_rt, other['rt'], params):
                continue

            # Compute deltas
            delta_mass = abs(other['mass'] - target_mass)
            delta_rt = abs(other['rt'] - target_rt)

            # Compute spectral similarity if available
            spectral_sim = 0.0
            if "spectral" in params.method and target_peaks and other.get('peaks'):
                spectral_sim = CEFMatcher.compute_spectral_similarity(
                    target_peaks, other['peaks'], params.peak_intensity_threshold
                )

            # Compute confidence
            confidence = CEFMatcher.compute_combined_confidence(
                delta_mass, delta_rt, spectral_sim, params
            )

            if confidence > 0.0:
                matches.append(Match(
                    compound_id_1=target_id,
                    compound_id_2=other['id'],
                    name_1=target_name,
                    name_2=other['name'],
                    mass_1=target_mass,
                    mass_2=other['mass'],
                    rt_1=target_rt,
                    rt_2=other['rt'],
                    delta_mass=delta_mass,
                    delta_rt=delta_rt,
                    confidence=confidence,
                    spectral_similarity=spectral_sim,
                    method=params.method
                ))

        matches.sort(key=lambda m: m.confidence, reverse=True)
        if top_n:
            matches = matches[:top_n]

        return matches

    @staticmethod
    def find_all_matches(
        all_compounds: List[Dict],
        params: Optional[MatchParameters] = None,
        top_n_per_compound: Optional[int] = None
    ) -> List[Match]:
        """Find all pairwise matches across all compounds using specified parameters."""
        if params is None:
            params = MatchParameters()

        all_matches = []

        for compound in all_compounds:
            matches = CEFMatcher.find_matches_for_compound(
                compound, all_compounds, params, top_n_per_compound
            )
            all_matches.extend(matches)

        return all_matches

    @staticmethod
    def find_best_matches_multirun(
        all_compounds: List[Dict],
        param_list: List[MatchParameters]
    ) -> Dict[str, List[Match]]:
        """
        Run matching multiple times with different parameters.
        Returns results indexed by method name.
        """
        results = {}
        for params in param_list:
            matches = CEFMatcher.find_all_matches(all_compounds, params)
            results[f"{params.instrument_type}_{params.method}"] = matches
        return results

    @staticmethod
    def build_match_heatmap(
        compounds_file_a: List[Dict],
        compounds_file_b: List[Dict],
        mass_tol: float = 0.5,
        rt_tol: float = 0.2,
        top_n: int = 3
    ) -> Dict:
        """Build heatmap data for two files."""
        heatmap = {
            'file_a_compounds': compounds_file_a,
            'file_b_compounds': compounds_file_b,
            'matches': []
        }

        for compound_a in compounds_file_a:
            matches = CEFMatcher.find_matches_for_compound(
                compound_a, compounds_file_b, mass_tol, rt_tol, top_n
            )
            heatmap['matches'].extend(matches)

        return heatmap

    @staticmethod
    def group_by_confidence_threshold(
        matches: List[Match],
        high_threshold: float = 0.8,
        med_threshold: float = 0.5
    ) -> Dict[str, List[Match]]:
        """Group matches by confidence level."""
        return {
            'high': [m for m in matches if m.confidence >= high_threshold],
            'medium': [m for m in matches if med_threshold <= m.confidence < high_threshold],
            'low': [m for m in matches if m.confidence < med_threshold]
        }


@dataclass
class DuplicateGroup:
    """Group of duplicate compounds to consolidate."""
    compound_ids: List[int]
    names: List[str]
    master_mass: float
    master_rt: float
    confidence: float
    suggested_master_name: str
    base_peak_mz: Optional[float] = None

    def __repr__(self):
        names_str = ', '.join(self.names)
        return f"DuplicateGroup([{names_str}], conf={self.confidence:.2f})"


class CEFConsolidator:
    """Identify and consolidate duplicate compounds."""

    @staticmethod
    def identify_duplicate_groups(
        all_compounds: List[Dict],
        params: Optional[MatchParameters] = None
    ) -> List[DuplicateGroup]:
        """Find groups of compounds that should be merged using specified parameters."""
        if params is None:
            params = MatchParameters()

        visited = set()
        groups = []

        for i, compound in enumerate(all_compounds):
            if i in visited:
                continue

            group_ids = [compound['id']]
            group_names = [compound['name']]
            visited.add(i)

            target_mass = compound['mass']
            target_rt = compound['rt']
            target_peaks = compound.get('peaks', [])

            for j, other in enumerate(all_compounds[i+1:], start=i+1):
                if j in visited:
                    continue

                # Check mass match
                if not CEFMatcher.check_mass_match(target_mass, other['mass'], params):
                    continue

                # Check RT match
                if not CEFMatcher.check_rt_match(target_rt, other['rt'], params):
                    continue

                # Check spectral if needed
                if "spectral" in params.method and target_peaks and other.get('peaks'):
                    spectral_sim = CEFMatcher.compute_spectral_similarity(
                        target_peaks, other['peaks'], params.peak_intensity_threshold
                    )
                    if spectral_sim < params.spectral_threshold:
                        continue

                group_ids.append(other['id'])
                group_names.append(other['name'])
                visited.add(j)

            if len(group_ids) > 1:
                delta_mass = 0
                delta_rt = 0
                confidence = CEFMatcher.compute_combined_confidence(
                    delta_mass, delta_rt, 1.0, params
                )

                # Find base peak (highest intensity) from all peaks in group
                base_peak_mz = None
                all_peaks = []
                all_rts = []
                for cid in group_ids:
                    c = next((comp for comp in all_compounds if comp['id'] == cid), None)
                    if c:
                        all_peaks.extend(c.get('peaks', []))
                        all_rts.append(c.get('rt', 0))

                # Calculate average RT for the group
                avg_rt = sum(all_rts) / len(all_rts) if all_rts else target_rt

                if all_peaks:
                    base_peak = max(all_peaks, key=lambda p: p['intensity'])
                    base_peak_mz = base_peak['mz']

                # Generate RT@M/Z format name using average RT
                if base_peak_mz is not None:
                    master_name = f"{avg_rt:.2f}@{base_peak_mz:.4f}"
                else:
                    master_name = f"{avg_rt:.2f}@{target_mass:.4f}"

                groups.append(DuplicateGroup(
                    compound_ids=group_ids,
                    names=group_names,
                    master_mass=target_mass,
                    master_rt=avg_rt,
                    confidence=confidence,
                    suggested_master_name=master_name,
                    base_peak_mz=base_peak_mz
                ))

        return groups

    @staticmethod
    def merge_compound_data(
        compounds: List[Dict]
    ) -> Dict:
        """Merge data from multiple compound entries."""
        if not compounds:
            return {}

        master = compounds[0].copy()
        all_peaks = compounds[0].get('peaks', [])

        for compound in compounds[1:]:
            all_peaks.extend(compound.get('peaks', []))

        all_peaks.sort(key=lambda p: p['mz'])

        peak_map = {}
        for peak in all_peaks:
            key = (round(peak['mz'], 3), peak.get('annotation', ''))
            if key not in peak_map or peak['intensity'] > peak_map[key]['intensity']:
                peak_map[key] = peak

        master['peaks'] = list(peak_map.values())
        master['source_count'] = len(compounds)
        master['source_names'] = [c['name'] for c in compounds]

        return master
