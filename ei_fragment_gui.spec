# -*- mode: python ; coding: utf-8 -*-
#
# ei_fragment_gui.spec
# ====================
# PyInstaller build specification for the EI Fragment Exact-Mass Calculator
# desktop application.
#
# Usage (run from the project root):
#   pyinstaller ei_fragment_gui.spec --noconfirm
#
# Output:
#   dist/ei-fragment-gui/          -- application directory
#   dist/ei-fragment-gui.exe       -- NOT produced here; Inno Setup wraps the
#                                     directory into a proper installer.
#
# To also build a single-file portable EXE (slower startup, larger file):
#   pyinstaller ei_fragment_gui.spec --noconfirm --onefile
# ---------------------------------------------------------------------------

import importlib.util
import sys
from pathlib import Path

# ── Project root (directory containing this .spec file) ─────────────────────
ROOT = Path(SPECPATH)

# ── Optional packages: include them when installed on the build machine ──────
_extra_datas    = []
_extra_binaries = []
_extra_hidden   = []

def _try_collect(pkg_name: str) -> None:
    """Add all files + hidden imports for an optional package if installed."""
    if importlib.util.find_spec(pkg_name) is not None:
        from PyInstaller.utils.hooks import collect_all
        d, b, h = collect_all(pkg_name)
        _extra_datas.extend(d)
        _extra_binaries.extend(b)
        _extra_hidden.extend(h)
        _extra_hidden.append(pkg_name)
        print(f"[spec] Including optional package: {pkg_name}")
    else:
        print(f"[spec] Optional package not installed, skipping: {pkg_name}")

_try_collect("sdf_enricher")
_try_collect("splashpy")

# ── Icon (optional) ──────────────────────────────────────────────────────────
# Place a 256×256 icon at  docs/icon.ico  to use a custom icon.
# The build will succeed without it (default Python icon is used).
_icon_path = str(ROOT / "docs" / "icon.ico")
_icon = _icon_path if Path(_icon_path).exists() else None

# ── Analysis ─────────────────────────────────────────────────────────────────
a = Analysis(
    [str(ROOT / "launch_gui.py")],
    pathex=[str(ROOT)],
    binaries=_extra_binaries,
    datas=[
        # Required: element masses / abundances / valences
        (str(ROOT / "data" / "elements.csv"),  "data"),
        # Sample spectra shipped with the project
        (str(ROOT / "Spectra" / "*.sdf"),  "Spectra"),
        (str(ROOT / "Spectra" / "*.SDF"),  "Spectra"),
    ] + _extra_datas,
    hiddenimports=[
        # Core package — enumerate every sub-module so nothing is missed
        "ei_fragment_calculator",
        "ei_fragment_calculator.gui",
        "ei_fragment_calculator.cli",
        "ei_fragment_calculator.calculator",
        "ei_fragment_calculator.constants",
        "ei_fragment_calculator.filters",
        "ei_fragment_calculator.formula",
        "ei_fragment_calculator.isotope",
        "ei_fragment_calculator.mol_parser",
        "ei_fragment_calculator.preflight",
        "ei_fragment_calculator.sdf_parser",
        "ei_fragment_calculator.sdf_writer",
        "ei_fragment_calculator.enrich",
        "ei_fragment_calculator.enrich_cli",
        # tkinter — bundled with Python on Windows; list sub-modules explicitly
        "tkinter",
        "tkinter.ttk",
        "tkinter.filedialog",
        "tkinter.messagebox",
        "tkinter.scrolledtext",
        "tkinter.font",
        "_tkinter",
    ] + _extra_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Keep the bundle lean — matplotlib is only needed for the diagram
        # script, not the GUI itself.  Users can still install it separately.
        "matplotlib",
        "numpy",
        "scipy",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# ── EXE (inside the onedir bundle) ───────────────────────────────────────────
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,       # binaries go into COLLECT, not the EXE itself
    name="ei-fragment-gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,                    # compress with UPX if available (smaller output)
    upx_exclude=[],
    console=False,               # no console window — pure GUI app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon,
    version=None,                # optional: path to a Windows version-info file
)

# ── COLLECT — gather all files into dist/ei-fragment-gui/ ────────────────────
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ei-fragment-gui",
)
