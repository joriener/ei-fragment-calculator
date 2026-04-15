# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for EI Fragment Calculator GUI.
Run: pyinstaller build_windows.spec
Output: dist/EI-Fragment-Calculator/
"""

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['ei_fragment_calculator/gui.py'],
    pathex=[str(Path('.').resolve())],
    binaries=[],
    datas=[
        ('ei_fragment_calculator/data/elements.csv', 'ei_fragment_calculator/data'),
        ('examples', 'examples'),
    ],
    hiddenimports=[
        'ei_fragment_calculator',
        'ei_fragment_calculator.cli',
        'ei_fragment_calculator.calculator',
        'ei_fragment_calculator.confidence',
        'ei_fragment_calculator.constants',
        'ei_fragment_calculator.filters',
        'ei_fragment_calculator.formula',
        'ei_fragment_calculator.fragmentation_rules',
        'ei_fragment_calculator.input_reader',
        'ei_fragment_calculator.isotope',
        'ei_fragment_calculator.mol_merger',
        'ei_fragment_calculator.mol_parser',
        'ei_fragment_calculator.neutral_losses',
        'ei_fragment_calculator.preflight',
        'ei_fragment_calculator.sdf_parser',
        'ei_fragment_calculator.sdf_writer',
        'ei_fragment_calculator.stable_ions',
        'ei_fragment_calculator.structure_fetcher',
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        'tkinter.scrolledtext',
        'tkinter.font',
        'multiprocessing',
        'multiprocessing.pool',
        'multiprocessing.spawn',
        'importlib.metadata',
        'csv',
        'json',
        're',
        'threading',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['rdkit', 'numpy', 'matplotlib', 'pytest'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='EI-Fragment-Calculator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,       # no console window — pure GUI
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,           # add icon path here when available
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='EI-Fragment-Calculator',
)
