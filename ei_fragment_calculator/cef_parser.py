"""
cef_parser.py
=============
Pure Python CEF (Compound Exchange Format) XML parser.
Parses CEF files into Python dataclasses without external dependencies.

CEF is an XML-based format for analytical chemistry mass spectrometry data.
See: https://www.agilent.com/
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List


@dataclass
class CEFPeak:
    """Individual mass spectrum peak."""
    mz: float
    intensity: float
    charge: int = 1
    annotation: Optional[str] = None
    rt: Optional[float] = None
    volume: Optional[float] = None
    is_saturated: bool = False

    def __repr__(self):
        return f"Peak(m/z={self.mz:.3f}, intensity={self.intensity:.1f})"


@dataclass
class CEFSpectrum:
    """Mass spectrum container."""
    spectrum_type: str = "MFE"
    polarity: str = "+"
    algorithm: str = ""
    peaks: List[CEFPeak] = field(default_factory=list)

    def __repr__(self):
        return f"Spectrum({self.spectrum_type}, {len(self.peaks)} peaks)"


@dataclass
class CEFLocation:
    """Compound location (mass and retention time)."""
    molecular_mass: float
    retention_time: float
    area: Optional[float] = None
    height: Optional[float] = None
    volume: Optional[float] = None

    def __repr__(self):
        return f"Location(m/z={self.molecular_mass:.3f}, RT={self.retention_time:.2f})"


@dataclass
class CEFCompound:
    """Compound entry from CEF file."""
    name: str
    location: CEFLocation
    spectrum: CEFSpectrum
    algorithm: str = ""
    mppid: Optional[str] = None
    device_type: Optional[str] = None
    original_xml: str = ""
    molecule_name: Optional[str] = None
    molecule_formula: Optional[str] = None
    is_identified: bool = False

    def __repr__(self):
        return f"{self.name} (m/z={self.location.molecular_mass:.3f}, RT={self.location.retention_time:.2f})"


class CEFParser:
    """Parse CEF XML files."""

    @staticmethod
    def parse_file(filepath: Path) -> List[CEFCompound]:
        """Parse a CEF file and return list of compounds."""
        try:
            tree = ET.parse(filepath)
            root = tree.getroot()
            return CEFParser._parse_compound_list(root)
        except ET.ParseError as e:
            raise ValueError(f"Invalid CEF XML in {filepath}: {e}")
        except FileNotFoundError:
            raise FileNotFoundError(f"CEF file not found: {filepath}")

    @staticmethod
    def _parse_compound_list(root: ET.Element) -> List[CEFCompound]:
        """Extract compounds from root element."""
        compounds = []
        compound_list = root.find(".//CompoundList")

        if compound_list is None:
            return compounds

        for compound_elem in compound_list.findall("Compound"):
            try:
                compound = CEFParser._parse_compound(compound_elem)
                if compound:
                    compounds.append(compound)
            except Exception as e:
                print(f"  Skipping malformed compound: {e}")
                continue

        return compounds

    @staticmethod
    def _parse_compound(elem: ET.Element) -> Optional[CEFCompound]:
        """Parse a single Compound element."""
        algo = elem.get("algo", "Unknown")
        mppid = elem.get("mppid")

        location_elem = elem.find("Location")
        if location_elem is None:
            return None
        location = CEFParser._parse_location(location_elem)

        spectrum_elem = elem.find("Spectrum")
        spectrum = CEFParser._parse_spectrum(spectrum_elem) if spectrum_elem else CEFSpectrum()

        # Extract Molecule information (identified compounds)
        # Look for Molecule in Results or directly under Compound
        molecule_elem = elem.find("Molecule")
        if molecule_elem is None:
            molecule_elem = elem.find("Results/Molecule")
        if molecule_elem is None:
            molecule_elem = elem.find(".//Molecule")

        molecule_name = None
        molecule_formula = None
        is_identified = False

        if molecule_elem is not None:
            molecule_name = molecule_elem.get("name")
            molecule_formula = molecule_elem.get("formula")
            is_identified = molecule_name is not None

        name = _extract_compound_name(elem, algo, molecule_name)
        device_type = _extract_device_type(elem)

        # Store original XML for round-trip fidelity
        original_xml = ET.tostring(elem, encoding='unicode')

        return CEFCompound(
            name=name,
            location=location,
            spectrum=spectrum,
            algorithm=algo,
            mppid=mppid,
            device_type=device_type,
            original_xml=original_xml,
            molecule_name=molecule_name,
            molecule_formula=molecule_formula,
            is_identified=is_identified
        )

    @staticmethod
    def _parse_location(elem: ET.Element) -> CEFLocation:
        """Parse Location element (m/z, RT, area, height)."""
        try:
            m = float(elem.get("m", 0))
            rt = float(elem.get("rt", 0))
            area = _safe_float(elem.get("a"))
            height = _safe_float(elem.get("y"))
            volume = _safe_float(elem.get("v"))

            return CEFLocation(
                molecular_mass=m,
                retention_time=rt,
                area=area,
                height=height,
                volume=volume
            )
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid Location attributes: {e}")

    @staticmethod
    def _parse_spectrum(elem: ET.Element) -> CEFSpectrum:
        """Parse Spectrum element (peaks and metadata)."""
        spectrum_type = elem.get("type", "MFE")

        ms_details = elem.find("MSDetails")
        polarity = "+" if ms_details is None else ms_details.get("p", "+")

        algo = elem.get("cpdAlgo", "")

        peaks = []
        ms_peaks = elem.find("MSPeaks")
        if ms_peaks is not None:
            for peak_elem in ms_peaks.findall("p"):
                peak = CEFParser._parse_peak(peak_elem)
                if peak:
                    peaks.append(peak)

        return CEFSpectrum(
            spectrum_type=spectrum_type,
            polarity=polarity,
            algorithm=algo,
            peaks=peaks
        )

    @staticmethod
    def _parse_peak(elem: ET.Element) -> Optional[CEFPeak]:
        """Parse individual peak element."""
        try:
            mz = float(elem.get("x", 0))
            intensity = float(elem.get("y", 0))
            charge = int(elem.get("z", 1))
            annotation = elem.get("s")
            rt = _safe_float(elem.get("rt"))
            volume = _safe_float(elem.get("v"))
            is_saturated = elem.get("sat", "false").lower() == "true"

            return CEFPeak(
                mz=mz,
                intensity=intensity,
                charge=charge,
                annotation=annotation,
                rt=rt,
                volume=volume,
                is_saturated=is_saturated
            )
        except (ValueError, TypeError) as e:
            print(f"  Skipping malformed peak: {e}")
            return None


def _extract_compound_name(elem: ET.Element, algo: str, molecule_name: Optional[str] = None) -> str:
    """Extract compound name from element or generate default."""
    # Use molecule name if available (identified compound)
    if molecule_name:
        return molecule_name.strip()

    location = elem.find("Location")
    if location is not None:
        m = location.get("m", "?")
        rt = location.get("rt", "?")
        name = location.get("name")
        if name:
            return name.strip()
        # For unidentified compounds, use RT@M/Z format
        return f"{rt}@{m}"
    return f"{algo} (unknown)"


def _extract_device_type(elem: ET.Element) -> Optional[str]:
    """Extract device type from Spectrum/Device element."""
    device = elem.find(".//Device")
    if device is not None:
        return device.get("type")
    return None


def _safe_float(val: Optional[str]) -> Optional[float]:
    """Safely convert string to float, returning None on failure."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def parse_cef(filepath: Path | str) -> List[CEFCompound]:
    """Public function: parse CEF file and return compounds."""
    return CEFParser.parse_file(Path(filepath))


def write_cef(filepath: Path | str, compounds: List[CEFCompound]) -> None:
    """Write compounds back to CEF file (uses original XML for fidelity, builds new XML if needed)."""
    root = ET.Element("CEF", version="1.0.0.0")
    compound_list = ET.SubElement(root, "CompoundList")

    for compound in compounds:
        if compound.original_xml:
            # Use original XML for fidelity
            elem = ET.fromstring(compound.original_xml)
            compound_list.append(elem)
        else:
            # Build XML from compound data
            elem = _build_compound_xml(compound)
            compound_list.append(elem)

    tree = ET.ElementTree(root)
    tree.write(filepath, encoding='utf-8', xml_declaration=True)


def _build_compound_xml(compound: CEFCompound) -> ET.Element:
    """Build Compound XML element from CEFCompound data."""
    comp_elem = ET.Element("Compound")
    comp_elem.set("algo", compound.algorithm or "Unknown")
    if compound.mppid:
        comp_elem.set("mppid", compound.mppid)

    # Location element
    loc_elem = ET.SubElement(comp_elem, "Location")
    loc_elem.set("m", str(compound.location.molecular_mass))
    loc_elem.set("rt", str(compound.location.retention_time))
    if compound.location.area:
        loc_elem.set("a", str(compound.location.area))
    if compound.location.height:
        loc_elem.set("y", str(compound.location.height))
    if compound.location.volume:
        loc_elem.set("v", str(compound.location.volume))
    loc_elem.set("name", compound.name)

    # Spectrum element
    spec_elem = ET.SubElement(comp_elem, "Spectrum")
    spec_elem.set("type", compound.spectrum.spectrum_type)
    spec_elem.set("cpdAlgo", compound.spectrum.algorithm)

    # MSDetails
    ms_details = ET.SubElement(spec_elem, "MSDetails")
    ms_details.set("p", compound.spectrum.polarity)
    ms_details.set("z", str(1))

    # Device (if present)
    if compound.device_type:
        device = ET.SubElement(spec_elem, "Device")
        device.set("type", compound.device_type)

    # MSPeaks
    if compound.spectrum.peaks:
        peaks_elem = ET.SubElement(spec_elem, "MSPeaks")
        for peak in compound.spectrum.peaks:
            peak_elem = ET.SubElement(peaks_elem, "p")
            peak_elem.set("x", str(peak.mz))
            peak_elem.set("y", str(peak.intensity))
            peak_elem.set("z", str(peak.charge))
            if peak.annotation:
                peak_elem.set("s", peak.annotation)
            if peak.rt:
                peak_elem.set("rt", str(peak.rt))
            if peak.volume:
                peak_elem.set("v", str(peak.volume))
            if peak.is_saturated:
                peak_elem.set("sat", "true")

    return comp_elem
