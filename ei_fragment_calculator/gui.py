"""
gui.py
======
Full-featured Tkinter desktop application for the EI Fragment Exact-Mass
Calculator.

Tabs
----
1. Fragment Calculator  — all CLI options, editable defaults, custom I/O paths
2. Element Table        — inline CRUD editor for data/elements.csv
3. SDF Enricher         — (visible only when sdf-enricher is installed)
4. SDF Viewer           — browse structures, view metadata, plot mass spectra (requires RDKit, Pillow & Matplotlib)
5. Packages             — check and auto-install optional dependencies

Launch
------
    ei-fragment-gui
    python -m ei_fragment_calculator.gui
"""

from __future__ import annotations

import csv
import importlib.util
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font, messagebox, scrolledtext, ttk

# ---------------------------------------------------------------------------
# Optional dependencies
# ---------------------------------------------------------------------------

try:
    import sdf_enricher as _se          # noqa: F401
    _HAS_ENRICHER = True
except ImportError:
    _HAS_ENRICHER = False

try:
    from rdkit import Chem              # noqa: F401
    _HAS_RDKIT = True
except ImportError:
    _HAS_RDKIT = False

try:
    import matplotlib                   # noqa: F401
    matplotlib.use('TkAgg')  # Use TkAgg backend for Tkinter integration
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    _HAS_MATPLOTLIB = True
except ImportError:
    _HAS_MATPLOTLIB = False
    Figure = None
    FigureCanvasTkAgg = None

# ---------------------------------------------------------------------------
# Paths — handle both normal installs and PyInstaller-frozen builds.
# PyInstaller 6+ places data files under  <dist>/_internal/  and sets
# sys._MEIPASS to that directory at runtime.
# ---------------------------------------------------------------------------
def _find_elements_csv() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "data" / "elements.csv"
    return Path(__file__).parent.parent / "data" / "elements.csv"

_ELEMENTS_CSV  = _find_elements_csv()
_SETTINGS_FILE = Path.home() / ".ei_fragment_calculator_gui.json"

# ---------------------------------------------------------------------------
# Log colour palette (light theme)
# ---------------------------------------------------------------------------
_LOG_BG  = "#f8f8f8"
_LOG_FG  = "#000000"
_LOG_OK      = "#007000"
_LOG_FAIL    = "#cc0000"
_LOG_HEADER  = "#0055aa"
_LOG_MZ      = "#6600aa"
_LOG_ADDED   = "#007000"
_LOG_WARN    = "#996600"
_LOG_BRACKET = "#6600aa"

# ---------------------------------------------------------------------------
# Factory defaults (values the app ships with)
# ---------------------------------------------------------------------------
_FACTORY: dict = {
    "tolerance":       0.5,
    "electron_mode":   "remove",
    "best_only":       False,
    "hide_empty":      False,
    "show_isotope":    False,
    "no_save_sdf":     False,
    "no_nitrogen":     False,
    "no_hd":           False,
    "no_lewis":        False,
    "no_isotope_score": False,
    "no_smiles":       False,
    "isotope_tolerance": 30.0,
    "max_ring_ratio":  0.5,
    "workers":              1,
    "fetch_structures":     False,
    "ppm_mode":             False,
    "ppm_value":            5.0,
    "fragmentation_rules":  False,
    "rdkit_validation":     False,
    "hr_mode":              False,
    "auto_hr":              False,
    "hr_ppm":               20.0,
    "confidence":           False,
    "confidence_threshold": 0.0,
    "merge_structures":     "",
    "last_input_dir":       "",
    "last_output_dir":      "",
    "mode":                 "gc",
    # enricher
    "e_no_pubchem":    False,
    "e_no_chebi":      False,
    "e_no_kegg":       False,
    "e_no_hmdb":       False,
    "e_no_exact_mass": False,
    "e_no_splash":     False,
    "e_overwrite":     False,
    "e_delay":         0.5,
    "e_fetch_mol":     True,
}

# ---------------------------------------------------------------------------
# Optional packages table  (name, pip-name, purpose)
# ---------------------------------------------------------------------------
_OPT_PACKAGES = [
    ("sdf_enricher",  "sdf-enricher", "SDF Enricher tab — fill missing metadata"),
    ("splashpy",      "splashpy",     "SPLASH spectral hash calculation"),
    ("matplotlib",    "matplotlib",   "Workflow diagram generation"),
]


# ===========================================================================
# Settings  (persistent JSON)
# ===========================================================================

class _Settings:
    def __init__(self):
        self._data: dict = dict(_FACTORY)
        self._load()

    def _load(self) -> None:
        if _SETTINGS_FILE.exists():
            try:
                with open(_SETTINGS_FILE, encoding="utf-8") as fh:
                    saved = json.load(fh)
                self._data.update(saved)
            except Exception:
                pass

    def save(self) -> None:
        try:
            with open(_SETTINGS_FILE, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2)
        except Exception:
            pass

    def reset(self) -> None:
        self._data = dict(_FACTORY)
        self.save()

    def __getitem__(self, key):
        return self._data.get(key, _FACTORY.get(key))

    def __setitem__(self, key, val):
        self._data[key] = val

    def get(self, key, default=None):
        """Get setting value with optional default."""
        return self._data.get(key, _FACTORY.get(key, default))

    def add_recent_file(self, filepath: str) -> None:
        """Add file to recent files list (max 10)."""
        recent = self.get("recent_files", [])
        # Remove if already exists
        if filepath in recent:
            recent.remove(filepath)
        # Add to front
        recent.insert(0, filepath)
        # Keep only 10 most recent
        recent = recent[:10]
        self._data["recent_files"] = recent
        self.save()

    def get_recent_files(self):
        """Get list of recent files."""
        return self.get("recent_files", [])

    def clear_recent_files(self) -> None:
        """Clear all recent files."""
        self._data["recent_files"] = []
        self.save()


# ===========================================================================
# Thread-safe stdout redirector
# ===========================================================================

class _Redirector:
    """Route write() calls into a Tk Text widget via the event loop."""

    def __init__(self, widget: scrolledtext.ScrolledText, root: tk.Tk):
        self._w    = widget
        self._root = root

    def write(self, text: str) -> None:
        self._root.after(0, self._append, text)

    def _append(self, text: str) -> None:
        w = self._w
        w.configure(state="normal")
        for line in text.splitlines(keepends=True):
            tag = ""
            if re.search(r"\bOK\b",   line): tag = "ok"
            elif re.search(r"\bFAIL\b", line): tag = "fail"
            elif re.match(r"^={3,}", line.strip()): tag = "header"
            elif re.match(r"^\s+m/z\s+\d", line): tag = "mz"
            elif re.match(r"^\s*\+\s", line): tag = "added"
            elif re.match(r"^\s*!\s",  line): tag = "warn"
            elif re.match(r"^\s*\[",   line): tag = "bracket"
            w.insert(tk.END, line, tag or None)
        w.see(tk.END)
        w.configure(state="disabled")

    def flush(self) -> None:
        pass


# ===========================================================================
# Helpers
# ===========================================================================

def _make_log(parent: tk.Widget) -> scrolledtext.ScrolledText:
    log = scrolledtext.ScrolledText(
        parent, state="disabled", wrap=tk.WORD,
        font=("Consolas", 9),
        bg=_LOG_BG, fg=_LOG_FG,
        relief=tk.FLAT, borderwidth=0,
    )
    log.tag_configure("ok",      foreground=_LOG_OK)
    log.tag_configure("fail",    foreground=_LOG_FAIL)
    log.tag_configure("header",  foreground=_LOG_HEADER)
    log.tag_configure("mz",      foreground=_LOG_MZ)
    log.tag_configure("added",   foreground=_LOG_ADDED)
    log.tag_configure("warn",    foreground=_LOG_WARN)
    log.tag_configure("bracket", foreground=_LOG_BRACKET)
    return log


def _clear_log(log: scrolledtext.ScrolledText) -> None:
    log.configure(state="normal")
    log.delete("1.0", tk.END)
    log.configure(state="disabled")


def _apply_style() -> None:
    s = ttk.Style()
    for theme in ("vista", "winnative", "xpnative", "clam", "default"):
        try:
            s.theme_use(theme)
            break
        except tk.TclError:
            continue
    s.configure("Accent.TButton",
        background="#0078D4", foreground="white",
        font=("Segoe UI", 9, "bold"), borderwidth=0)
    s.map("Accent.TButton",
        background=[("active", "#106EBE"), ("disabled", "#AAAAAA"), ("pressed", "#005A9E")])


def _sep(parent: tk.Widget) -> None:
    ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)


# ===========================================================================
# Tab 1 — Fragment Calculator
# ===========================================================================

class _CalcTab(ttk.Frame):

    def __init__(self, master: tk.Widget, settings: _Settings):
        super().__init__(master, padding=10)
        self._settings = settings
        self._running  = False
        self._out_sdf  = tk.StringVar()
        self._out_msp  = tk.StringVar()
        self._parsed_records = []  # Loaded compounds
        self._current_compound_idx = -1  # Selected compound
        self._spectrum_fig = None
        self._spectrum_ax = None
        self._spectrum_canvas = None
        self._compounds_tree = None
        self._peak_table = None
        self._build()
        self._load_settings()

    # ── Build UI ─────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # ── Files Section ────────────────────────────────────────────────────
        io = ttk.LabelFrame(self, text=" Files ", padding=8)
        io.pack(fill=tk.X, pady=(0, 6))
        io.columnconfigure(1, weight=1)

        # Row 0: Spectral data
        ttk.Label(io, text="Spectral data:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self._in_var = tk.StringVar()
        self._in_var.trace_add("write", self._update_out_sdf)
        ttk.Entry(io, textvariable=self._in_var).grid(
            row=0, column=1, sticky=tk.EW, padx=(6, 4))
        ttk.Button(io, text="Browse…", command=self._browse_in).grid(
            row=0, column=2, padx=(0, 2))
        ttk.Label(io, text="MSP · MSPEC · SDF · JDX · CSV",
                  foreground="#666666").grid(row=0, column=3, padx=6, sticky=tk.W)

        # Row 1: Structures SDF
        ttk.Label(io, text="Structures SDF:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self._merge_sdf_var = tk.StringVar()
        ttk.Entry(io, textvariable=self._merge_sdf_var).grid(
            row=1, column=1, sticky=tk.EW, padx=(6, 4))
        ttk.Button(io, text="Browse…", command=self._browse_merge_sdf).grid(
            row=1, column=2, padx=(0, 2))
        ttk.Label(io, text="Optional — for M+1/M+2 isotope scoring",
                  foreground="#666666").grid(row=1, column=3, padx=6, sticky=tk.W)

        # Row 2: Output SDF
        ttk.Label(io, text="Output SDF:").grid(row=2, column=0, sticky=tk.W, pady=2)
        ttk.Entry(io, textvariable=self._out_sdf).grid(
            row=2, column=1, sticky=tk.EW, padx=(6, 4))
        ttk.Button(io, text="Browse…", command=self._browse_out_sdf).grid(
            row=2, column=2, padx=(0, 2))

        # Row 3: Output MSP
        ttk.Label(io, text="Output MSP:").grid(row=3, column=0, sticky=tk.W, pady=2)
        ttk.Entry(io, textvariable=self._out_msp).grid(
            row=3, column=1, sticky=tk.EW, padx=(6, 4))
        ttk.Button(io, text="Browse…", command=self._browse_out_msp).grid(
            row=3, column=2, padx=(0, 2))
        ttk.Label(io, text="Optional — exact-mass MSP",
                  foreground="#666666").grid(row=3, column=3, padx=6, sticky=tk.W)

        # Row 4: Log to file
        ttk.Label(io, text="Log to file:").grid(row=4, column=0, sticky=tk.W, pady=2)
        self._log_file_var = tk.StringVar()
        ttk.Entry(io, textvariable=self._log_file_var, width=40).grid(
            row=4, column=1, sticky=tk.EW, padx=(6, 4))
        ttk.Button(io, text="Browse…", command=self._browse_log_file).grid(
            row=4, column=2, padx=(0, 2))
        ttk.Label(io, text="(optional)",
                  foreground="#666666").grid(row=4, column=3, padx=6, sticky=tk.W)

        # ── Mode LabelFrame ──────────────────────────────────────────────────
        mode_fr = ttk.LabelFrame(self, text=" Mode ", padding=8)
        mode_fr.pack(fill=tk.X, pady=(0, 6))

        self._mode_var = tk.StringVar(value="gc")

        # Left radio: GC
        gc_sub = ttk.Frame(mode_fr)
        gc_sub.pack(side=tk.LEFT, padx=(0, 24))
        ttk.Radiobutton(gc_sub, text="GC / Unit-Mass (Low Resolution)",
                        variable=self._mode_var, value="gc",
                        command=self._on_mode_change).pack(anchor=tk.W)
        ttk.Label(gc_sub,
                  text="Tolerance \u00b10.5 Da  \u00b7  Confidence scoring ON  \u00b7  H-deficiency filter relaxed",
                  foreground="#666666").pack(anchor=tk.W)

        # Right radio: HRAM
        hr_sub = ttk.Frame(mode_fr)
        hr_sub.pack(side=tk.LEFT)
        ttk.Radiobutton(hr_sub, text="HRAM (High-Resolution Accurate Mass)",
                        variable=self._mode_var, value="hram",
                        command=self._on_mode_change).pack(anchor=tk.W)
        ttk.Label(hr_sub,
                  text="Auto-detect HR peaks  \u00b7  \u00b120 ppm  \u00b7  Best-only ON",
                  foreground="#666666").pack(anchor=tk.W)

        # ── Collapsible advanced container (hidden initially) ────────────────
        self._adv_open = False
        self._adv_container = ttk.Frame(self)
        self._adv_container.pack(fill=tk.X)
        self._adv_frame = ttk.LabelFrame(self._adv_container,
                                         text=" Advanced Settings ", padding=8)
        # do NOT pack self._adv_frame yet — it starts collapsed
        self._build_advanced(self._adv_frame)

        # ── Button row ───────────────────────────────────────────────────────
        toggle_fr = ttk.Frame(self)
        toggle_fr.pack(fill=tk.X, pady=(0, 4))
        ttk.Button(toggle_fr, text="Save as Default",
                   command=self._save_defaults).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(toggle_fr, text="Reset to Factory",
                   command=self._reset_defaults).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(toggle_fr, text="Element Table",
                   command=self._open_element_table).pack(side=tk.LEFT)

        ttk.Separator(self, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)

        # ── Main Content Area (Compound list, Spectrum, Peak Table) ──────────
        content_fr = ttk.Frame(self)
        content_fr.pack(fill=tk.BOTH, expand=True, pady=(0, 6))
        content_fr.columnconfigure(0, minsize=150)  # Left pane min width
        content_fr.columnconfigure(1, weight=1)      # Right pane expands
        content_fr.rowconfigure(0, weight=1)

        # Left pane: Compound list
        left_fr = ttk.LabelFrame(content_fr, text=" Compounds ", padding=4)
        left_fr.grid(row=0, column=0, sticky=tk.NSEW, padx=(0, 4))
        self._build_compound_list(left_fr)

        # Right pane: PanedWindow for Spectrum (top) and Peak Table (bottom)
        right_paned = tk.PanedWindow(content_fr, orient=tk.VERTICAL,
                                      bg="#e0e0e0", sashwidth=4)
        right_paned.grid(row=0, column=1, sticky=tk.NSEW)

        # Upper: Spectrum view
        spectrum_fr = ttk.LabelFrame(right_paned, text=" Spectrum ", padding=4)
        self._build_spectrum_canvas(spectrum_fr)
        right_paned.add(spectrum_fr, height=200, sticky=tk.NSEW)

        # Lower: Peak results table
        table_fr = ttk.LabelFrame(right_paned, text=" Peak Results ", padding=4)
        self._build_peak_table(table_fr)
        right_paned.add(table_fr, height=200, sticky=tk.NSEW)

        # ── Run row ──────────────────────────────────────────────────────────
        run_fr = ttk.Frame(self)
        run_fr.pack(fill=tk.X, pady=(0, 4))
        self._run_btn = ttk.Button(run_fr, text="  Exactify!  ",
                                   style="Accent.TButton", command=self._run)
        self._run_btn.pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(run_fr, text="Clear",
                   command=lambda: _clear_log(self._log)).pack(side=tk.LEFT, padx=(0, 6))
        self._open_btn = ttk.Button(run_fr, text="Open Output Folder",
                                    state="disabled", command=self._open_folder)
        self._open_btn.pack(side=tk.LEFT)
        self._status = tk.StringVar(value="Ready.")
        ttk.Label(run_fr, textvariable=self._status).pack(side=tk.RIGHT)

        self._pb = ttk.Progressbar(self, mode="indeterminate",
                                   style="Horizontal.TProgressbar")
        self._pb.pack(fill=tk.X, pady=(0, 4))

        # ── Log ──────────────────────────────────────────────────────────────
        log_fr = ttk.LabelFrame(self, text=" Output ", padding=4)
        log_fr.pack(fill=tk.BOTH, expand=True)
        self._log = _make_log(log_fr)
        self._log.pack(fill=tk.BOTH, expand=True)

    def _build_advanced(self, parent: ttk.LabelFrame) -> None:
        """Populate the collapsible Advanced Settings panel."""
        # Row 0 — tolerance (Da / ppm) + workers + electron mode
        r0 = ttk.Frame(parent); r0.pack(fill=tk.X, pady=(0, 4))
        self._ppm_mode = tk.BooleanVar()
        ttk.Radiobutton(r0, text="Da", variable=self._ppm_mode, value=False,
                        command=self._on_tol_mode).pack(side=tk.LEFT)
        ttk.Radiobutton(r0, text="ppm", variable=self._ppm_mode, value=True,
                        command=self._on_tol_mode).pack(side=tk.LEFT, padx=(2, 6))
        self._tol_lbl = ttk.Label(r0, text="Tolerance \u00b1Da:")
        self._tol_lbl.pack(side=tk.LEFT)
        self._tol = tk.StringVar()
        self._tol_spin = _spin(r0, self._tol, 0.05, 2.0, 0.05)
        self._tol_spin.pack(side=tk.LEFT, padx=(4, 4))
        self._ppm_lbl = ttk.Label(r0, text="Tolerance \u00b1ppm:")
        self._ppm_lbl.pack(side=tk.LEFT)
        self._ppm_val = tk.StringVar()
        self._ppm_spin = _spin(r0, self._ppm_val, 1.0, 50.0, 1.0)
        self._ppm_spin.pack(side=tk.LEFT, padx=(4, 24))

        ttk.Label(r0, text="Workers:").pack(side=tk.LEFT)
        self._workers = tk.StringVar()
        w_spin = _spin(r0, self._workers, 1, os.cpu_count() or 1, 1)
        w_spin.pack(side=tk.LEFT, padx=(4, 4))
        _tooltip(w_spin,
            "Parallel CPU workers (default = all cores). "
            "Set to 1 to disable multiprocessing.")
        ttk.Label(r0, text="/ {} cores".format(os.cpu_count() or 1),
                  foreground="#888888").pack(side=tk.LEFT, padx=(0, 24))

        ttk.Label(r0, text="Electron-mass correction:").pack(side=tk.LEFT)
        self._elec = tk.StringVar()
        for val, lbl, tip in [
            ("remove", "remove  (EI +)", "Subtract m_e — standard positive-ion EI"),
            ("add",    "add     (EI \u2212)", "Add m_e — negative-ion EI"),
            ("none",   "none",           "No correction"),
        ]:
            rb = ttk.Radiobutton(r0, text=lbl, variable=self._elec, value=val)
            rb.pack(side=tk.LEFT, padx=4)
            _tooltip(rb, tip)

        # Row 1 — toggles
        r1 = ttk.Frame(parent); r1.pack(fill=tk.X, pady=(0, 4))
        self._best_only           = tk.BooleanVar()
        self._hide_empty          = tk.BooleanVar()
        self._show_iso            = tk.BooleanVar()
        self._no_sdf              = tk.BooleanVar()
        self._fetch_structures    = tk.BooleanVar()
        self._frag_rules          = tk.BooleanVar()
        self._rdkit_validation    = tk.BooleanVar()
        for var, lbl, tip in [
            (self._best_only,  "Best-only",
             "Keep only the highest-ranked candidate per peak; drop unmatched peaks"),
            (self._hide_empty, "Hide empty",
             "Do not print peaks that have no matching candidate formula"),
            (self._show_iso,   "Show isotope patterns",
             "Display theoretical M / M+1 / M+2 percentages for every candidate"),
            (self._no_sdf,     "Skip SDF output",
             "Do not write the *-EXACT.sdf output file"),
            (self._fetch_structures, "Fetch structures (PubChem)",
             "For records with no 2-D structure, query PubChem by CAS/name "
             "and add the MOL block to the output SDF. Requires internet."),
            (self._frag_rules, "Fragmentation rules",
             "Annotate candidates with EI fragmentation rules: neutral losses "
             "(H2O, CO, HCl\u2026) and structure-based cleavages (\u03b1-cleavage, McLafferty)"),
            (self._rdkit_validation, "RDKit validation (Filter 6)",
             "Reject candidates with unknown element symbols via RDKit. "
             "Requires: pip install rdkit-pypi"),
        ]:
            cb = ttk.Checkbutton(r1, text=lbl, variable=var)
            cb.pack(side=tk.LEFT, padx=(0, 16))
            _tooltip(cb, tip)

        # Row 2 — HR input mode
        r2 = ttk.Frame(parent); r2.pack(fill=tk.X, pady=(0, 4))
        self._hr_mode  = tk.BooleanVar()
        self._auto_hr  = tk.BooleanVar()
        self._hr_ppm   = tk.StringVar()
        cb_hr = ttk.Checkbutton(r2, text="HR Input", variable=self._hr_mode)
        cb_hr.pack(side=tk.LEFT, padx=(0, 4))
        _tooltip(cb_hr,
            "Treat peak m/z values as exact masses (high-resolution mode).\n"
            "Matches candidates within \u00b1HR ppm instead of the fixed Da tolerance.\n"
            "Use for spectra from QTOF / Orbitrap / ChemVista / MassBank HR.")
        cb_ahr = ttk.Checkbutton(r2, text="Auto-detect HR", variable=self._auto_hr)
        cb_ahr.pack(side=tk.LEFT, padx=(0, 16))
        _tooltip(cb_ahr,
            "Automatically enable HR mode if the majority of m/z values\n"
            "have a fractional part > 0.010 Da (heuristic detection).")
        ttk.Label(r2, text="HR ppm \u00b1:").pack(side=tk.LEFT)
        hr_spin = _spin(r2, self._hr_ppm, 1.0, 200.0, 1.0)
        hr_spin.pack(side=tk.LEFT, padx=(4, 0))
        _tooltip(hr_spin, "ppm tolerance for HR input matching (default: 20 ppm).")

        # Row 3 — Confidence scoring
        r3 = ttk.Frame(parent); r3.pack(fill=tk.X, pady=(0, 4))
        self._confidence      = tk.BooleanVar()
        self._conf_threshold  = tk.StringVar()
        cb_conf = ttk.Checkbutton(r3, text="Confidence Scoring", variable=self._confidence)
        cb_conf.pack(side=tk.LEFT, padx=(0, 4))
        _tooltip(cb_conf,
            "Enable v1.8 unit-mass confidence scoring:\n"
            "  A. \u00b9\u00b3C M+1 isotope match\n"
            "  B. M+2 heavy-atom isotope (S, Cl, Br)\n"
            "  C. Neutral-loss cross-check (CO, H\u2082O, HCN, \u2026)\n"
            "  D. Complementary ion pairs\n"
            "  E. DBE plausibility + even/odd-electron rule\n"
            "  F. Stable-ion library (tropylium, phenyl, \u2026)\n"
            "Adds Conf% and Evidence columns to the output table.\n"
            "Ignored when --hr / --auto-hr is active (HR mode has exact mass).")
        ttk.Label(r3, text="Min confidence %:").pack(side=tk.LEFT, padx=(8, 0))
        conf_spin = _spin(r3, self._conf_threshold, 0.0, 100.0, 5.0)
        conf_spin.pack(side=tk.LEFT, padx=(4, 16))
        _tooltip(conf_spin,
            "In --best-only mode, skip peaks whose top candidate has\n"
            "confidence below this threshold (0 = keep all, default).")

        # ── Filter Options ───────────────────────────────────────────────────
        flt = ttk.LabelFrame(parent, text=" Algorithm Filters  (all ON by default) ",
                             padding=8)
        flt.pack(fill=tk.X, pady=(4, 0))

        fA = ttk.Frame(flt); fA.pack(fill=tk.X, pady=(0, 4))
        self._no_n  = tk.BooleanVar()
        self._no_hd = tk.BooleanVar()
        self._no_ls = tk.BooleanVar()
        self._no_is = tk.BooleanVar()
        self._no_sm = tk.BooleanVar()
        for var, lbl, tip in [
            (self._no_n,  "Disable Nitrogen Rule",
             "McLafferty: odd nominal m/z \u2194 odd N count for even-electron ions"),
            (self._no_hd, "Disable H-Deficiency",
             "Pretsch: reject DBE/C > max_ring_ratio (extraordinarily H-poor)"),
            (self._no_ls, "Disable Lewis / Senior",
             "Senior 1951: valence-sum must be even and \u2265 2\u00d7(atoms\u22121)"),
            (self._no_is, "Disable Isotope Score",
             "Gross: reject if |theo% \u2212 obs%| sum exceeds isotope_tolerance pp"),
            (self._no_sm, "Disable SMILES Constraints",
             "Weininger: fragment DBE cannot exceed ring count of parent molecule"),
        ]:
            cb = ttk.Checkbutton(fA, text=lbl, variable=var)
            cb.pack(side=tk.LEFT, padx=(0, 14))
            _tooltip(cb, tip)

        fB = ttk.Frame(flt); fB.pack(fill=tk.X)
        ttk.Label(fB, text="Isotope tolerance (pp):").pack(side=tk.LEFT)
        self._iso_tol = tk.StringVar()
        _spin(fB, self._iso_tol, 1.0, 100.0, 1.0).pack(side=tk.LEFT, padx=(4, 24))
        _tooltip_label(fB, "Max \u03a3|theo% \u2212 obs%| deviation; default 30 pp")

        ttk.Label(fB, text="Max ring ratio  (DBE/C):").pack(side=tk.LEFT)
        self._ring = tk.StringVar()
        _spin(fB, self._ring, 0.1, 2.0, 0.05).pack(side=tk.LEFT, padx=(4, 0))
        _tooltip_label(fB, "H-deficiency upper bound; default 0.5")

    # ── Mode change ──────────────────────────────────────────────────────────

    def _on_mode_change(self) -> None:
        """Apply GC or HRAM preset to the advanced settings."""
        mode = self._mode_var.get()
        if mode == "gc":
            self._tol.set("0.5")
            self._ppm_mode.set(False)
            self._on_tol_mode()
            self._best_only.set(True)
            self._confidence.set(True)
            self._no_hd.set(True)
            self._ring.set("1.0")
            self._auto_hr.set(False)
            self._hr_mode.set(False)
        else:  # hram
            self._auto_hr.set(True)
            self._hr_ppm.set("20.0")
            self._hr_mode.set(False)
            self._best_only.set(True)
            self._confidence.set(False)
            self._no_hd.set(False)
            self._ring.set("0.5")

    def _toggle_advanced(self) -> None:
        """Toggle visibility of Advanced Settings frame."""
        if self._adv_open:
            self._adv_frame.pack_forget()
            self._adv_open = False
        else:
            self._adv_frame.pack(fill=tk.X, pady=(0, 6))
            self._adv_open = True
        # Force layout recalculation so other widgets rearrange
        self.update_idletasks()

    def _build_compound_list(self, parent: tk.Widget) -> None:
        """Build the compound list treeview in the left pane."""
        # Create scrollbar and treeview
        scrollbar = ttk.Scrollbar(parent)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._compounds_tree = ttk.Treeview(parent, columns=(), show="tree",
                                            height=20, yscrollcommand=scrollbar.set)
        scrollbar.config(command=self._compounds_tree.yview)
        self._compounds_tree.pack(fill=tk.BOTH, expand=True)

        self._compounds_tree.bind("<<TreeviewSelect>>", self._on_compound_selected)

    def _build_spectrum_canvas(self, parent: tk.Widget) -> None:
        """Build the spectrum visualization in the upper right pane."""
        try:
            import matplotlib
            matplotlib.use('TkAgg')
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

            self._spectrum_fig, self._spectrum_ax = plt.subplots(figsize=(6, 3), dpi=100)
            self._spectrum_fig.patch.set_facecolor('#f0f0f0')
            self._spectrum_canvas = FigureCanvasTkAgg(self._spectrum_fig, parent)
            canvas_widget = self._spectrum_canvas.get_tk_widget()
            canvas_widget.pack(fill=tk.BOTH, expand=True)

            # Initial placeholder
            self._spectrum_ax.clear()
            self._spectrum_ax.text(0.5, 0.5, "Select a compound to view spectrum",
                                   ha="center", va="center", transform=self._spectrum_ax.transAxes,
                                   fontsize=10, color="gray")
            self._spectrum_ax.set_xlim(0, 1)
            self._spectrum_ax.set_ylim(0, 1)
            self._spectrum_fig.tight_layout()
            self._spectrum_canvas.draw()
        except ImportError as e:
            # Fallback if matplotlib not available
            print(f"[WARNING] matplotlib not available: {e}")
            ttk.Label(parent, text="matplotlib not installed\n\nInstall with:\npip install matplotlib",
                      foreground="#cc0000").pack(fill=tk.BOTH, expand=True)
            self._spectrum_canvas = None
            self._spectrum_fig = None
            self._spectrum_ax = None
        except Exception as e:
            print(f"[ERROR] Failed to build spectrum canvas: {e}")
            ttk.Label(parent, text=f"Error initializing spectrum:\n{str(e)}",
                      foreground="#cc0000").pack(fill=tk.BOTH, expand=True)
            self._spectrum_canvas = None
            self._spectrum_fig = None
            self._spectrum_ax = None

    def _build_peak_table(self, parent: tk.Widget) -> None:
        """Build the mass peak results table in the lower right pane."""
        cols = ("Input m/z", "Intensity", "Fragment Formula", "Ion m/z",
                "Delta mass", "DBE", "Filter")
        widths = [70, 80, 130, 80, 100, 50, 70]

        # Create scrollbars
        vsb = ttk.Scrollbar(parent, orient=tk.VERTICAL)
        hsb = ttk.Scrollbar(parent, orient=tk.HORIZONTAL)

        self._peak_table = ttk.Treeview(parent, columns=cols, show="headings",
                                        height=15, yscrollcommand=vsb.set,
                                        xscrollcommand=hsb.set)
        vsb.config(command=self._peak_table.yview)
        hsb.config(command=self._peak_table.xview)

        # Configure columns
        for col, width in zip(cols, widths):
            self._peak_table.heading(col, text=col)
            self._peak_table.column(col, width=width, minwidth=50)

        # Tag colors
        self._peak_table.tag_configure("pass", foreground="#007000")
        self._peak_table.tag_configure("fail", foreground="#cc0000")

        # Layout
        self._peak_table.grid(row=0, column=0, sticky=tk.NSEW)
        vsb.grid(row=0, column=1, sticky=tk.NS)
        hsb.grid(row=1, column=0, sticky=tk.EW)
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)

    def _on_compound_selected(self, event) -> None:
        """Handle compound selection: update spectrum and clear results."""
        selection = self._compounds_tree.selection()
        if not selection:
            return

        item_id = selection[0]
        # Get the compound index from the item ID
        try:
            idx = int(item_id) - 1  # Item IDs are 1-based
            if 0 <= idx < len(self._parsed_records):
                self._current_compound_idx = idx
                record = self._parsed_records[idx]

                # Extract and render spectrum
                peak_text = record["fields"].get("MASS SPECTRAL PEAKS", "")
                if peak_text:
                    from .sdf_parser import parse_peaks_with_intensity
                    pairs = parse_peaks_with_intensity(peak_text)
                    if pairs:
                        mz_vals, intensities = zip(*pairs)
                        self._cleanup_spectrum()
                        self._render_spectrum(list(mz_vals), list(intensities))
                    else:
                        self._clear_spectrum()
                else:
                    self._clear_spectrum()

                # Clear results table (show only input peaks)
                self._peak_table.delete(*self._peak_table.get_children())
                if peak_text:
                    from .sdf_parser import parse_peaks_with_intensity
                    pairs = parse_peaks_with_intensity(peak_text)
                    for mz, intensity in pairs:
                        self._peak_table.insert("", tk.END,
                                               values=(mz, f"{intensity:.0f}",
                                                       "", "", "", "", ""))
        except (ValueError, IndexError, KeyError):
            pass

    def _render_spectrum(self, mz_vals, intensities) -> None:
        """Render a bar chart of m/z vs intensity."""
        if not self._spectrum_ax or not self._spectrum_fig or not self._spectrum_canvas or not mz_vals:
            return

        try:
            self._spectrum_ax.clear()
            self._spectrum_ax.bar(mz_vals, intensities, color="#0078D4", width=0.8)
            self._spectrum_ax.set_xlabel("m/z", fontsize=9)
            self._spectrum_ax.set_ylabel("Intensity", fontsize=9)
            self._spectrum_ax.grid(True, alpha=0.3, axis="y")
            self._spectrum_fig.tight_layout()
            self._spectrum_canvas.draw()
        except (AttributeError, RuntimeError, ValueError) as e:
            print(f"[ERROR] Failed to render spectrum: {e}")
            self._clear_spectrum()

    def _clear_spectrum(self) -> None:
        """Clear spectrum and show placeholder."""
        if not self._spectrum_ax or not self._spectrum_fig:
            return

        try:
            self._spectrum_ax.clear()
            self._spectrum_ax.text(0.5, 0.5, "No spectrum data",
                                   ha="center", va="center",
                                   transform=self._spectrum_ax.transAxes,
                                   fontsize=10, color="gray")
            self._spectrum_fig.canvas.draw()
        except (AttributeError, RuntimeError):
            pass

    def _cleanup_spectrum(self) -> None:
        """Close matplotlib figure to prevent resource leak."""
        if self._spectrum_fig is not None:
            try:
                import matplotlib.pyplot as plt
                plt.close(self._spectrum_fig)
            except (ImportError, RuntimeError):
                pass
            finally:
                self._spectrum_fig = None
                self._spectrum_ax = None
                self._spectrum_canvas = None

    def _populate_peak_results(self, results: list[dict]) -> None:
        """Populate peak table with Exactify results."""
        # Clear current data
        for item in self._peak_table.get_children():
            self._peak_table.delete(item)

        # Add result rows
        for result in results:
            tag = "pass" if result.get("filter", "FAIL") == "PASS" else "fail"
            self._peak_table.insert("", tk.END,
                                   values=(result.get("input_mz", ""),
                                           result.get("intensity", ""),
                                           result.get("formula", ""),
                                           f"{result.get('ion_mz', ''):.4f}" if result.get('ion_mz') else "",
                                           f"{result.get('delta_mass', ''):.4f}" if result.get('delta_mass') else "",
                                           result.get("dbe", ""),
                                           result.get("filter", "")),
                                   tags=(tag,))

    # ── Settings helpers ─────────────────────────────────────────────────────

    def _on_tol_mode(self) -> None:
        """Show/hide Da vs ppm spinboxes based on radio button selection."""
        ppm = self._ppm_mode.get()
        if ppm:
            self._tol_lbl.pack_forget()
            self._tol_spin.pack_forget()
            self._ppm_lbl.pack(side=tk.LEFT)
            self._ppm_spin.pack(side=tk.LEFT, padx=(4, 24))
        else:
            self._ppm_lbl.pack_forget()
            self._ppm_spin.pack_forget()
            self._tol_lbl.pack(side=tk.LEFT)
            self._tol_spin.pack(side=tk.LEFT, padx=(4, 24))

    def _load_settings(self) -> None:
        s = self._settings
        self._tol.set(str(s["tolerance"]))
        self._ppm_mode.set(s["ppm_mode"])
        self._ppm_val.set(str(s["ppm_value"]))
        self._on_tol_mode()
        self._elec.set(s["electron_mode"])
        self._best_only.set(s["best_only"])
        self._hide_empty.set(s["hide_empty"])
        self._show_iso.set(s["show_isotope"])
        self._no_sdf.set(s["no_save_sdf"])
        self._fetch_structures.set(s["fetch_structures"])
        self._frag_rules.set(s["fragmentation_rules"])
        self._rdkit_validation.set(s["rdkit_validation"])
        self._hr_mode.set(s["hr_mode"])
        self._auto_hr.set(s["auto_hr"])
        self._hr_ppm.set(str(s["hr_ppm"]))
        self._confidence.set(s["confidence"])
        self._conf_threshold.set(str(s["confidence_threshold"]))
        self._merge_sdf_var.set(str(s["merge_structures"]))
        self._no_n.set(s["no_nitrogen"])
        self._no_hd.set(s["no_hd"])
        self._no_ls.set(s["no_lewis"])
        self._no_is.set(s["no_isotope_score"])
        self._no_sm.set(s["no_smiles"])
        self._iso_tol.set(str(s["isotope_tolerance"]))
        self._ring.set(str(s["max_ring_ratio"]))
        self._workers.set(str(s["workers"]))
        self._mode_var.set(s["mode"])

    def _save_defaults(self) -> None:
        try:
            s = self._settings
            s["tolerance"]           = float(self._tol.get())
            s["ppm_mode"]            = self._ppm_mode.get()
            s["ppm_value"]           = float(self._ppm_val.get())
            s["electron_mode"]       = self._elec.get()
            s["best_only"]           = self._best_only.get()
            s["hide_empty"]          = self._hide_empty.get()
            s["show_isotope"]        = self._show_iso.get()
            s["no_save_sdf"]         = self._no_sdf.get()
            s["fetch_structures"]    = self._fetch_structures.get()
            s["fragmentation_rules"] = self._frag_rules.get()
            s["rdkit_validation"]    = self._rdkit_validation.get()
            s["hr_mode"]             = self._hr_mode.get()
            s["auto_hr"]             = self._auto_hr.get()
            s["hr_ppm"]              = float(self._hr_ppm.get())
            s["confidence"]          = self._confidence.get()
            s["confidence_threshold"] = float(self._conf_threshold.get() or "0")
            s["merge_structures"]    = self._merge_sdf_var.get().strip()
            s["no_nitrogen"]         = self._no_n.get()
            s["no_hd"]               = self._no_hd.get()
            s["no_lewis"]            = self._no_ls.get()
            s["no_isotope_score"]    = self._no_is.get()
            s["no_smiles"]           = self._no_sm.get()
            s["isotope_tolerance"]   = float(self._iso_tol.get())
            s["max_ring_ratio"]      = float(self._ring.get())
            s["workers"]             = max(1, int(float(self._workers.get())))
            s["mode"]                = self._mode_var.get()
            s.save()
            self._status.set("Defaults saved.")
        except Exception as exc:
            messagebox.showerror("Save error", str(exc))

    def _reset_defaults(self) -> None:
        self._settings.reset()
        self._load_settings()
        self._status.set("Reset to factory defaults.")

    # ── File pickers ─────────────────────────────────────────────────────────

    def _browse_in(self) -> None:
        init = self._settings["last_input_dir"] or str(Path.home())
        path = filedialog.askopenfilename(
            initialdir=init,
            title="Select input file",
            filetypes=[
                ("All supported", "*.sdf *.SDF *.msp *.MSP *.mspec *.MSPEC *.jdx *.JDX *.jcamp *.csv *.tsv"),
                ("SDF", "*.sdf *.SDF"),
                ("MSP / MSPEC (NIST)", "*.msp *.MSP *.mspec *.MSPEC"),
                ("JCAMP-DX", "*.jdx *.JDX *.jcamp"),
                ("CSV / TSV", "*.csv *.tsv"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self._in_var.set(path)
            self._settings["last_input_dir"] = str(Path(path).parent)

    def _browse_out_sdf(self) -> None:
        init_dir = self._settings["last_output_dir"] or str(Path.home())
        init_file = Path(self._out_sdf.get()).name if self._out_sdf.get() else "output-EXACT.sdf"
        path = filedialog.asksaveasfilename(
            initialdir=init_dir,
            initialfile=init_file,
            title="Save exact-mass SDF as\u2026",
            defaultextension=".sdf",
            filetypes=[("SDF files", "*.sdf"), ("All files", "*.*")],
        )
        if path:
            self._out_sdf.set(path)
            self._settings["last_output_dir"] = str(Path(path).parent)

    def _browse_out_msp(self) -> None:
        init_dir = self._settings["last_output_dir"] or str(Path.home())
        init_file = Path(self._out_msp.get()).name if self._out_msp.get() else "output-EXACT.msp"
        path = filedialog.asksaveasfilename(
            initialdir=init_dir,
            initialfile=init_file,
            title="Save exact-mass MSP as\u2026",
            defaultextension=".msp",
            filetypes=[("MSP files", "*.msp"), ("All files", "*.*")],
        )
        if path:
            self._out_msp.set(path)
            self._settings["last_output_dir"] = str(Path(path).parent)

    def _browse_log_file(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save text log as\u2026",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if path:
            self._log_file_var.set(path)

    def _browse_merge_sdf(self) -> None:
        init = self._settings["last_input_dir"] or str(Path.home())
        path = filedialog.askopenfilename(
            initialdir=init,
            title="Select structure SDF for --merge-structures",
            filetypes=[("SDF files", "*.sdf *.SDF"), ("All files", "*.*")],
        )
        if path:
            self._merge_sdf_var.set(path)

    def _update_out_sdf(self, *_) -> None:
        """Auto-derive output SDF and MSP paths when input changes."""
        p = self._in_var.get().strip()
        if p:
            from .sdf_writer import exact_sdf_path, exact_msp_path
            self._out_sdf.set(exact_sdf_path(p))
            self._out_msp.set(exact_msp_path(p))

            # Load compounds from input file
            self._load_compounds_from_file(p)

    def _load_compounds_from_file(self, filepath: str) -> None:
        """Load compounds from input file and populate compound list."""
        try:
            if not filepath or not Path(filepath).exists():
                self._parsed_records = []
                self._current_compound_idx = -1
                if self._compounds_tree:
                    self._compounds_tree.delete(*self._compounds_tree.get_children())
                if self._peak_table:
                    self._peak_table.delete(*self._peak_table.get_children())
                self._clear_spectrum()
                return

            from .sdf_parser import parse_sdf
            self._parsed_records = parse_sdf(filepath)
            self._current_compound_idx = -1

            # Populate compound list
            if self._compounds_tree:
                self._compounds_tree.delete(*self._compounds_tree.get_children())
                for idx, record in enumerate(self._parsed_records):
                    compound_name = record.get("name", f"Compound {idx + 1}").strip()
                    if not compound_name:
                        compound_name = f"Compound {idx + 1}"
                    self._compounds_tree.insert("", tk.END, iid=str(idx + 1),
                                               text=f"{idx + 1}. {compound_name}")

            # Clear peak table and spectrum
            if self._peak_table:
                self._peak_table.delete(*self._peak_table.get_children())
            self._clear_spectrum()

        except Exception as e:
            self._log.insert(tk.END, f"Error loading compounds: {e}\n", "error")
            self._log.see(tk.END)

    def _open_folder(self) -> None:
        p = self._out_sdf.get()
        if p:
            folder = str(Path(p).parent)
            try:
                os.startfile(folder)
            except AttributeError:
                subprocess.Popen(["xdg-open", folder])

    # ── Run ──────────────────────────────────────────────────────────────────

    def _run(self) -> None:
        if self._running:
            return
        sdf = self._in_var.get().strip()
        if not sdf:
            messagebox.showwarning("No input file", "Please select an input file (SDF, MSP, JDX, or CSV).")
            return
        if not Path(sdf).exists():
            messagebox.showerror("File not found", "Input file does not exist:\n" + sdf)
            return
        try:
            tol       = float(self._tol.get())
            iso_tol   = float(self._iso_tol.get())
            ring      = float(self._ring.get())
        except ValueError as exc:
            messagebox.showerror("Invalid value", str(exc))
            return

        out_sdf  = self._out_sdf.get().strip() or None
        log_file = self._log_file_var.get().strip() or None

        argv = [sdf, "--electron", self._elec.get(),
                "--isotope-tolerance", str(iso_tol), "--max-ring-ratio", str(ring)]
        if self._ppm_mode.get():
            try:
                ppm_val = float(self._ppm_val.get())
            except ValueError:
                ppm_val = 5.0
            argv += ["--ppm", str(ppm_val)]
        else:
            argv += ["--tolerance", str(tol)]
        if self._best_only.get():           argv.append("--best-only")
        if self._hide_empty.get():          argv.append("--hide-empty")
        if self._show_iso.get():            argv.append("--isotope")
        if self._no_sdf.get():              argv.append("--no-save-sdf")
        if self._fetch_structures.get():    argv.append("--fetch-structures")
        if self._frag_rules.get():          argv.append("--fragmentation-rules")
        if self._rdkit_validation.get():    argv.append("--rdkit")
        if self._hr_mode.get():             argv.append("--hr")
        if self._auto_hr.get():             argv.append("--auto-hr")
        try:
            hr_ppm_val = float(self._hr_ppm.get())
        except ValueError:
            hr_ppm_val = 20.0
        argv += ["--hr-ppm", str(hr_ppm_val)]
        if self._confidence.get():          argv.append("--confidence")
        try:
            conf_thr = float(self._conf_threshold.get() or "0")
        except ValueError:
            conf_thr = 0.0
        if conf_thr > 0.0:
            argv += ["--confidence-threshold", str(conf_thr / 100.0)]
        merge_sdf = self._merge_sdf_var.get().strip()
        if merge_sdf:                       argv += ["--merge-structures", merge_sdf]
        if self._no_n.get():                argv.append("--no-nitrogen-rule")
        if self._no_hd.get():               argv.append("--no-hd-check")
        if self._no_ls.get():               argv.append("--no-lewis-senior")
        if self._no_is.get():               argv.append("--no-isotope-score")
        if self._no_sm.get():               argv.append("--no-smiles-constraints")
        argv += ["--workers", str(max(1, int(float(self._workers.get()))))]
        if out_sdf:                         argv += ["--output-sdf", out_sdf]
        out_msp = self._out_msp.get().strip() or None
        if out_msp:                         argv += ["--output-msp", out_msp]
        if log_file:                        argv += ["--output", log_file]

        self._run_btn.configure(state="disabled")
        self._open_btn.configure(state="disabled")
        self._status.set("Running\u2026")
        self._pb.start(12)
        self._running = True
        _clear_log(self._log)

        rd = _Redirector(self._log, self.winfo_toplevel())
        threading.Thread(target=self._worker, args=(argv, rd), daemon=True).start()

    def _worker(self, argv: list, rd: _Redirector) -> None:
        from .cli import main as cli_main
        old_o, old_e = sys.stdout, sys.stderr
        sys.stdout = rd; sys.stderr = rd
        ok = True
        try:
            cli_main(argv)
        except SystemExit as exc:
            ok = exc.code in (None, 0)
        except Exception as exc:
            sys.stderr.write("\nERROR: {}\n".format(exc))
            ok = False
        finally:
            sys.stdout = old_o; sys.stderr = old_e
        self.winfo_toplevel().after(0, self._done, ok)

    def _done(self, ok: bool) -> None:
        self._running = False
        self._pb.stop()
        self._run_btn.configure(state="normal")
        self._status.set("Done." if ok else "Finished with errors.")
        out = self._out_sdf.get()
        if not self._no_sdf.get() and out and Path(out).exists():
            self._open_btn.configure(state="normal")

            # Try to populate peak results from output SDF
            if ok and self._peak_table and self._current_compound_idx >= 0:
                self._load_results_from_sdf(out, self._current_compound_idx)

    def _load_results_from_sdf(self, output_sdf: str, compound_idx: int) -> None:
        """Load results from output SDF and populate peak table."""
        try:
            from .sdf_parser import parse_sdf
            from .formula import parse_formula
            from .calculator import calculate_dbe, ion_mass

            results_records = parse_sdf(output_sdf)
            if compound_idx >= len(results_records):
                return

            result_record = results_records[compound_idx]
            input_record = self._parsed_records[compound_idx]

            # Get input peaks
            input_peak_text = input_record["fields"].get("MASS SPECTRAL PEAKS", "")
            from .sdf_parser import parse_peaks_with_intensity
            input_pairs = parse_peaks_with_intensity(input_peak_text)

            # Get result formula assignments
            result_formulas = result_record["fields"].get("EXACT MASS FORMULAS", "")

            # Clear and populate peak table
            self._peak_table.delete(*self._peak_table.get_children())

            if input_pairs:
                # Build a map of m/z to formula assignments from results
                formula_map = {}
                if result_formulas:
                    # Parse the result format (assumed to be "mz: formula" per line)
                    for line in result_formulas.split("\n"):
                        line = line.strip()
                        if ":" in line:
                            try:
                                mz_str, formula_str = line.split(":", 1)
                                mz = int(mz_str.strip())
                                formula = formula_str.strip()
                                if formula not in formula_map.get(mz, []):
                                    formula_map.setdefault(mz, []).append(formula)
                            except ValueError:
                                pass

                # Populate table with input peaks and matched formulas
                for input_mz, intensity in input_pairs:
                    formula_list = formula_map.get(int(input_mz), [])
                    if formula_list:
                        # Show first matching formula
                        formula = formula_list[0]
                        try:
                            parsed = parse_formula(formula)
                            exact_mass = ion_mass(parsed)
                            delta = input_mz - exact_mass
                            dbe = calculate_dbe(parsed)
                            tag = "pass"
                        except Exception:
                            exact_mass, delta, dbe = "", "", ""
                            tag = "fail"

                        self._peak_table.insert("", tk.END,
                                               values=(input_mz, f"{intensity:.0f}",
                                                       formula,
                                                       f"{exact_mass:.4f}" if exact_mass else "",
                                                       f"{delta:.4f}" if delta else "",
                                                       dbe,
                                                       "PASS"),
                                               tags=(tag,))
                    else:
                        # No formula found
                        self._peak_table.insert("", tk.END,
                                               values=(input_mz, f"{intensity:.0f}",
                                                       "", "", "", "", "FAIL"),
                                               tags=("fail",))

        except Exception as e:
            # Silently fail if results can't be loaded
            pass

    def _open_element_table(self) -> None:
        """Open Element Table as a modal window."""
        modal = tk.Toplevel(self.winfo_toplevel())
        modal.title("Element Table Editor")
        modal.geometry("950x500")
        modal.resizable(True, True)
        modal.transient(self.winfo_toplevel())
        modal.grab_set()

        elem_frame = _ElementTab(modal)
        elem_frame.pack(fill=tk.BOTH, expand=True)


# ===========================================================================
# Tab 2 — Element Table Editor
# ===========================================================================

_CSV_COLS = ["Symbol", "Name", "Isotope", "ExactMass",
             "Abundance", "Valence", "MonoisotopicFlag"]

class _ElementTab(ttk.Frame):

    def __init__(self, master: tk.Widget):
        super().__init__(master, padding=10)
        self._dirty = False
        self._build()
        self._load_csv()

    def _build(self) -> None:
        info = ttk.Label(
            self,
            text=(
                "Edit element masses, isotope abundances and valences. "
                "Double-click any cell to edit.  "
                "Changes are written to  data/elements.csv  "
                "and take effect after restarting the application."
            ),
            foreground="#666666", wraplength=860, justify=tk.LEFT,
        )
        info.pack(anchor=tk.W, pady=(0, 6))

        # Treeview + scrollbars
        tv_fr = ttk.Frame(self)
        tv_fr.pack(fill=tk.BOTH, expand=True)

        vsb = ttk.Scrollbar(tv_fr, orient=tk.VERTICAL)
        hsb = ttk.Scrollbar(tv_fr, orient=tk.HORIZONTAL)
        self._tree = ttk.Treeview(
            tv_fr, columns=_CSV_COLS, show="headings",
            yscrollcommand=vsb.set, xscrollcommand=hsb.set,
        )
        vsb.configure(command=self._tree.yview)
        hsb.configure(command=self._tree.xview)
        vsb.pack(side=tk.RIGHT,  fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self._tree.pack(fill=tk.BOTH, expand=True)

        col_widths = {"Symbol": 60, "Name": 110, "Isotope": 55,
                      "ExactMass": 160, "Abundance": 100,
                      "Valence": 60, "MonoisotopicFlag": 120}
        for col in _CSV_COLS:
            self._tree.heading(col, text=col)
            self._tree.column(col, width=col_widths.get(col, 90),
                              anchor=tk.CENTER if col != "Name" else tk.W,
                              stretch=(col == "ExactMass"))

        self._tree.bind("<Double-1>", self._on_double_click)

        # Buttons
        btn_fr = ttk.Frame(self)
        btn_fr.pack(fill=tk.X, pady=(6, 0))

        ttk.Button(btn_fr, text="\u2795  Add Row",    command=self._add_row
                   ).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_fr, text="\U0001f5d1  Delete Row", command=self._delete_row
                   ).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Button(btn_fr, text="\U0001f4be  Save to elements.csv",
                   style="Accent.TButton", command=self._save_csv
                   ).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_fr, text="\u21ba  Reload from disk", command=self._load_csv
                   ).pack(side=tk.LEFT)

        self._elem_status = tk.StringVar(value="")
        ttk.Label(btn_fr, textvariable=self._elem_status, foreground="#666666"
                  ).pack(side=tk.RIGHT)

    # ── CSV I/O ──────────────────────────────────────────────────────────────

    def _load_csv(self) -> None:
        self._tree.delete(*self._tree.get_children())
        if not _ELEMENTS_CSV.exists():
            self._elem_status.set("elements.csv not found: " + str(_ELEMENTS_CSV))
            return
        with open(_ELEMENTS_CSV, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                values = [row.get(c, "") for c in _CSV_COLS]
                self._tree.insert("", tk.END, values=values)
        self._dirty = False
        self._elem_status.set("Loaded  {}  rows from elements.csv".format(
            len(self._tree.get_children())))

    def _save_csv(self) -> None:
        rows = []
        for iid in self._tree.get_children():
            vals = self._tree.item(iid, "values")
            rows.append(dict(zip(_CSV_COLS, vals)))
        try:
            with open(_ELEMENTS_CSV, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=_CSV_COLS)
                writer.writeheader()
                writer.writerows(rows)
            self._dirty = False
            self._elem_status.set(
                "Saved {} rows.  Restart the application for changes to take effect.".format(
                    len(rows)))
        except Exception as exc:
            messagebox.showerror("Save error", str(exc))

    # ── Inline cell editor ───────────────────────────────────────────────────

    def _on_double_click(self, event: tk.Event) -> None:
        region = self._tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        col  = self._tree.identify_column(event.x)   # "#1", "#2", …
        item = self._tree.identify_row(event.y)
        if not item:
            return
        bbox = self._tree.bbox(item, col)
        if not bbox:
            return
        x, y, w, h = bbox
        col_idx  = int(col[1:]) - 1
        col_name = _CSV_COLS[col_idx]
        current  = self._tree.set(item, col)

        entry = ttk.Entry(self._tree, font=("Consolas", 9))
        entry.insert(0, current)
        entry.select_range(0, tk.END)
        entry.place(x=x, y=y, width=w, height=h)
        entry.focus_set()

        def _commit(event=None):
            self._tree.set(item, col, entry.get())
            self._dirty = True
            entry.destroy()
            self._elem_status.set("Unsaved changes — press 'Save to elements.csv'.")

        def _cancel(event=None):
            entry.destroy()

        entry.bind("<Return>",   _commit)
        entry.bind("<Tab>",      _commit)
        entry.bind("<Escape>",   _cancel)
        entry.bind("<FocusOut>", _commit)

    # ── Row management ───────────────────────────────────────────────────────

    def _add_row(self) -> None:
        self._tree.insert("", tk.END, values=["", "", "", "", "", "", ""])
        # Scroll to and select the new row
        last = self._tree.get_children()[-1]
        self._tree.see(last)
        self._tree.selection_set(last)
        self._dirty = True

    def _delete_row(self) -> None:
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("No selection", "Select a row to delete.")
            return
        for iid in sel:
            self._tree.delete(iid)
        self._dirty = True
        self._elem_status.set("Row deleted — unsaved changes.")


# ===========================================================================
# SDF Enricher Tab
# ===========================================================================

class _EnrichTab(ttk.Frame):

    def __init__(self, master: tk.Widget, settings: _Settings):
        super().__init__(master, padding=10)
        self._settings = settings
        self._running  = False
        self._stop_event = threading.Event()
        self._out_path = tk.StringVar(value="")
        self._build()
        self._load_settings()

    def _build(self) -> None:
        io = ttk.LabelFrame(self, text=" Files ", padding=8)
        io.pack(fill=tk.X, pady=(0, 6))
        io.columnconfigure(1, weight=1)

        ttk.Label(io, text="Input SDF:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self._in_var = tk.StringVar()
        self._in_var.trace_add("write", self._update_out)
        ttk.Entry(io, textvariable=self._in_var).grid(
            row=0, column=1, sticky=tk.EW, padx=(6, 4))
        ttk.Button(io, text="Browse…", command=self._browse_in
                   ).grid(row=0, column=2)

        ttk.Label(io, text="Output SDF:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Entry(io, textvariable=self._out_path).grid(
            row=1, column=1, sticky=tk.EW, padx=(6, 4))
        ttk.Button(io, text="Browse…", command=self._browse_out
                   ).grid(row=1, column=2)

        # Sources
        src = ttk.LabelFrame(self, text=" Data Sources  (all ON by default) ",
                             padding=8)
        src.pack(fill=tk.X, pady=(0, 6))

        rA = ttk.Frame(src); rA.pack(fill=tk.X, pady=(0, 4))
        self._no_pc  = tk.BooleanVar()
        self._no_ch  = tk.BooleanVar()
        self._no_kg  = tk.BooleanVar()
        self._no_hm  = tk.BooleanVar()
        self._no_em  = tk.BooleanVar()
        self._no_sp  = tk.BooleanVar()
        for var, lbl, tip in [
            (self._no_pc, "Skip PubChem",    "Formula, SMILES, InChI, CASNO, synonyms, CID"),
            (self._no_ch, "Skip ChEBI",      "ChEBI accession (by InChIKey)"),
            (self._no_kg, "Skip KEGG",       "KEGG C-number (by CAS or name)"),
            (self._no_hm, "Skip HMDB",       "HMDB accession (by InChIKey)"),
            (self._no_em, "Skip Exact Mass", "Calculate from FORMULA locally"),
            (self._no_sp, "Skip SPLASH",     "Spectral hash (requires splashpy)"),
        ]:
            cb = ttk.Checkbutton(rA, text=lbl, variable=var)
            cb.pack(side=tk.LEFT, padx=(0, 14))
            _tooltip(cb, tip)

        rB = ttk.Frame(src); rB.pack(fill=tk.X)
        self._fetch_mol = tk.BooleanVar()
        cb_mol = ttk.Checkbutton(rB, text="Fetch 2-D structures (PubChem)",
                                  variable=self._fetch_mol)
        cb_mol.pack(side=tk.LEFT, padx=(0, 14))
        _tooltip(cb_mol, "Download MOL block from PubChem for records without a 2-D structure")
        self._overwr = tk.BooleanVar()
        ttk.Checkbutton(rB, text="Overwrite existing values", variable=self._overwr
                        ).pack(side=tk.LEFT, padx=(0, 24))
        ttk.Label(rB, text="API delay (s):").pack(side=tk.LEFT)
        self._delay = tk.StringVar()
        _spin(rB, self._delay, 0.0, 5.0, 0.1).pack(side=tk.LEFT, padx=4)

        def_fr = ttk.Frame(self); def_fr.pack(fill=tk.X, pady=(0, 4))
        ttk.Button(def_fr, text="\U0001f4be  Save as Default",
                   command=self._save_defaults).pack(side=tk.LEFT, padx=(0, 6))

        _sep(self)

        run_fr = ttk.Frame(self); run_fr.pack(fill=tk.X, pady=(0, 4))
        self._run_btn = ttk.Button(run_fr, text="\u25b6  Enrich",
                                   style="Accent.TButton", command=self._run)
        self._run_btn.pack(side=tk.LEFT, padx=(0, 6))
        self._stop_btn = ttk.Button(run_fr, text="\u23f9  Stop",
                                    state="disabled", command=self._stop)
        self._stop_btn.pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(run_fr, text="Clear",
                   command=lambda: _clear_log(self._log)).pack(side=tk.LEFT, padx=(0, 6))
        self._open_btn = ttk.Button(run_fr, text="\U0001f4c2  Open output folder",
                                    state="disabled", command=self._open_folder)
        self._open_btn.pack(side=tk.LEFT)
        self._status = tk.StringVar(value="Ready.")
        ttk.Label(run_fr, textvariable=self._status, foreground="#666666"
                  ).pack(side=tk.RIGHT)

        self._pb = ttk.Progressbar(self, mode="indeterminate",
                                   style="Horizontal.TProgressbar")
        self._pb.pack(fill=tk.X, pady=(0, 4))

        log_fr = ttk.LabelFrame(self, text=" Output ", padding=4)
        log_fr.pack(fill=tk.BOTH, expand=True)
        self._log = _make_log(log_fr)
        self._log.pack(fill=tk.BOTH, expand=True)

    def _load_settings(self) -> None:
        s = self._settings
        self._no_pc.set(s["e_no_pubchem"])
        self._no_ch.set(s["e_no_chebi"])
        self._no_kg.set(s["e_no_kegg"])
        self._no_hm.set(s["e_no_hmdb"])
        self._no_em.set(s["e_no_exact_mass"])
        self._no_sp.set(s["e_no_splash"])
        self._overwr.set(s["e_overwrite"])
        self._delay.set(str(s["e_delay"]))
        self._fetch_mol.set(s["e_fetch_mol"])

    def _save_defaults(self) -> None:
        s = self._settings
        s["e_no_pubchem"]    = self._no_pc.get()
        s["e_no_chebi"]      = self._no_ch.get()
        s["e_no_kegg"]       = self._no_kg.get()
        s["e_no_hmdb"]       = self._no_hm.get()
        s["e_no_exact_mass"] = self._no_em.get()
        s["e_no_splash"]     = self._no_sp.get()
        s["e_overwrite"]     = self._overwr.get()
        s["e_delay"]         = float(self._delay.get())
        s["e_fetch_mol"]     = self._fetch_mol.get()
        s.save()
        self._status.set("Defaults saved.")

    def _browse_in(self) -> None:
        init = self._settings["last_input_dir"] or str(Path.home())
        path = filedialog.askopenfilename(
            initialdir=init,
            title="Select SDF file to enrich",
            filetypes=[("SDF files", "*.sdf *.SDF"), ("All files", "*.*")],
        )
        if path:
            self._in_var.set(path)
            self._settings["last_input_dir"] = str(Path(path).parent)

    def _browse_out(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save enriched SDF as\u2026",
            defaultextension=".sdf",
            filetypes=[("SDF files", "*.sdf"), ("All files", "*.*")],
        )
        if path:
            self._out_path.set(path)

    def _update_out(self, *_) -> None:
        p = self._in_var.get().strip()
        if p:
            try:
                from sdf_enricher.sdf_io import enriched_path
                self._out_path.set(enriched_path(p))
            except ImportError:
                pass

    @staticmethod
    def _find_field_key(fields: dict, candidates: list) -> str | None:
        """Find actual dict key matching a candidate (case-insensitive)."""
        upper_map = {k.upper(): k for k in fields}
        for candidate in candidates:
            if candidate.upper() in upper_map:
                return upper_map[candidate.upper()]
        return None

    def _format_cas_numbers(self, records: list) -> None:
        """Format CAS numbers and extract compound names from <NAME> field."""
        name_candidates = ["NAME", "COMPOUND NAME", "COMPOUND_NAME"]
        cas_candidates = ["CASNO", "CAS NO", "CAS_NO", "CAS NUMBER"]
        formatted_count = 0
        name_count = 0

        for record in records:
            fields = record.get("fields", {})
            mol_block = record.get("mol_block", "")

            name_key = self._find_field_key(fields, name_candidates)
            if name_key:
                real_name = fields[name_key].strip()
                if real_name and real_name != "No Structure":
                    record["compound_name"] = real_name
                    record["name"] = real_name
                    if mol_block:
                        newline_idx = mol_block.find("\n")
                        if newline_idx >= 0:
                            record["mol_block"] = real_name[:80] + mol_block[newline_idx:]
                    name_count += 1

            cas_key = self._find_field_key(fields, cas_candidates)
            if cas_key:
                cas_val = fields[cas_key].strip()
                formatted = self._format_single_cas(cas_val)
                if formatted != cas_val:
                    fields["CAS"] = formatted
                    formatted_count += 1

        if name_count > 0:
            print(f"  Updated {name_count} MOL block header(s) with real compound name(s).")
        if formatted_count > 0:
            print(f"  Added {formatted_count} formatted <CAS> field(s).")

    def _format_single_cas(self, cas_str: str) -> str:
        """Format a single CAS number string."""
        cas_str = cas_str.strip()
        if "-" in cas_str:
            return cas_str
        digits = re.sub(r"\D", "", cas_str)
        if len(digits) < 5:
            return cas_str
        main = digits[:-3]
        part2 = digits[-3:-1]
        part3 = digits[-1]
        return f"{main}-{part2}-{part3}"

    def _open_folder(self) -> None:
        p = self._out_path.get()
        if p:
            try:
                os.startfile(str(Path(p).parent))
            except AttributeError:
                subprocess.Popen(["xdg-open", str(Path(p).parent)])

    def _run(self) -> None:
        if self._running:
            return
        sdf = self._in_var.get().strip()
        if not sdf:
            messagebox.showwarning("No file", "Select an input SDF file first.")
            return
        try:
            delay = float(self._delay.get())
        except ValueError:
            messagebox.showerror("Invalid value", "Delay must be a number.")
            return
        cfg = dict(
            pubchem         = not self._no_pc.get(),
            chebi           = not self._no_ch.get(),
            kegg            = not self._no_kg.get(),
            hmdb            = not self._no_hm.get(),
            calc_exact_mass = not self._no_em.get(),
            calc_splash     = not self._no_sp.get(),
            overwrite       = self._overwr.get(),
            delay           = delay,
        )
        out = self._out_path.get().strip() or None

        self._stop_event.clear()
        self._run_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._open_btn.configure(state="disabled")
        self._status.set("Enriching\u2026")
        self._pb.start(12)
        self._running = True
        _clear_log(self._log)

        rd = _Redirector(self._log, self.winfo_toplevel())
        fetch_mol = self._fetch_mol.get() and not self._no_pc.get()
        threading.Thread(target=self._worker, args=(sdf, cfg, out, rd, fetch_mol),
                         daemon=True).start()

    def _stop(self) -> None:
        """Signal the worker thread to stop."""
        self._stop_event.set()
        self._stop_btn.configure(state="disabled")
        self._status.set("Stopping\u2026")

    def _worker(self, sdf_path: str, cfg: dict, out_path: str | None,
                rd: _Redirector, fetch_mol: bool = True) -> None:
        from sdf_enricher.sdf_io   import read_sdf, write_sdf, enriched_path
        from sdf_enricher.enricher import EnrichConfig, enrich_records
        old_o, old_e = sys.stdout, sys.stderr
        sys.stdout = rd
        sys.stderr = rd
        ok = True
        final_out = out_path
        try:
            records = read_sdf(sdf_path)
            print(f"SDF Enricher\n  Input   : {sdf_path}\n  Records : {len(records)}\n")

            if self._stop_event.is_set():
                print("\nEnrichment cancelled by user.")
                return

            self._format_cas_numbers(records)

            if self._stop_event.is_set():
                print("\nEnrichment cancelled by user.")
                return

            print("\nEnriching with public chemical databases…")
            print("(This step cannot be stopped once it starts)")
            enrich_records(records, config=EnrichConfig(**cfg), verbose=True)

            if self._stop_event.is_set():
                print("\nEnrichment cancelled by user.")
                return

            if fetch_mol:
                from .structure_fetcher import enrich_mol_blocks, _mol_block_has_atoms
                records_missing_mol = [r for r in records if not _mol_block_has_atoms(r.get("mol_block", ""))]
                if records_missing_mol:
                    print(f"\nFetching 2-D structures from PubChem ({len(records_missing_mol)} record(s) without structure)…")
                    def _prog(done, total, name):
                        if self._stop_event.is_set():
                            raise KeyboardInterrupt("Enrichment cancelled by user.")
                        print(f"  [{done}/{total}] {name or '(unnamed)'}")
                    enrich_mol_blocks(records, progress_callback=_prog)
                else:
                    print("\nAll records already have 2-D structures — skipping PubChem fetch.")

            if self._stop_event.is_set():
                print("\nEnrichment cancelled by user.")
                return

            final_out = out_path or enriched_path(sdf_path)
            n = write_sdf(records, final_out)
            print(f"\nSaved {n} record(s) to '{final_out}'.")
        except KeyboardInterrupt:
            sys.stderr.write("\nEnrichment stopped by user.\n")
            ok = False
        except Exception as exc:
            sys.stderr.write(f"\nERROR: {exc}\n")
            ok = False
        finally:
            sys.stdout = old_o
            sys.stderr = old_e
        self.winfo_toplevel().after(0, self._done, ok, final_out or "")

    def _done(self, ok: bool, out_path: str) -> None:
        self._running = False
        self._pb.stop()
        self._run_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")
        self._status.set("Done." if ok else "Finished with errors.")
        if out_path and Path(out_path).exists():
            self._out_path.set(out_path)
            self._open_btn.configure(state="normal")


# ===========================================================================
# SDF Viewer Tab
# ===========================================================================

class _SDFViewerTab(ttk.Frame):

    def __init__(self, master: tk.Widget):
        super().__init__(master, padding=10)
        self._records = []
        self._current_idx = 0
        self._sdf_path = tk.StringVar()  # Legacy - kept for backward compat
        self._file_path = tk.StringVar()  # Unified file loader
        self._compound_tree = None
        self._photo = None
        self._canvas = None
        self._meta_text = None
        self._info_label = None
        self._nav_label = None
        self._filter_label = None
        self._clear_filter_btn = None
        self._spec_canvas_frame = None
        self._edit_metadata_btn = None
        self._edit_spectrum_btn = None
        self._search_var = None
        self._search_result_label = None

        # Database attributes for SQLite backend
        self._db_conn = None
        self._db_cursor = None
        self._current_query_results = []
        self._db_path_var = tk.StringVar()
        self._persist_db_var = tk.BooleanVar(value=False)
        self._db_file_label = None

        # Undo/Redo stack for metadata changes
        self._undo_redo_stack = _UndoRedoStack(max_size=50)

        try:
            self._build()
        except Exception as e:
            print(f"Error building SDF Viewer: {e}")
            import traceback
            traceback.print_exc()

    def _build(self) -> None:
        # ── Status Bar (minimal database info) ──────────────────────────────
        try:
            status_fr = ttk.Frame(self)
            status_fr.pack(fill=tk.X, pady=(0, 4))
            status_fr.columnconfigure(1, weight=1)

            ttk.Label(status_fr, text="Database:").pack(side=tk.LEFT, padx=(0, 6))
            self._db_file_label = ttk.Label(status_fr, text="(in-memory) | 0 compounds", foreground="#666666")
            self._db_file_label.pack(side=tk.LEFT)
        except Exception as e:
            print(f"Error building status bar: {e}")

        # ── Main Content Area ──────────────────────────────────────────────
        try:
            content_fr = ttk.Frame(self)
            content_fr.pack(fill=tk.BOTH, expand=True, pady=(0, 0))
            content_fr.columnconfigure(0, weight=0)
            content_fr.columnconfigure(1, weight=0)
            content_fr.columnconfigure(2, weight=1)
            content_fr.rowconfigure(0, weight=1)
            content_fr.rowconfigure(1, weight=1)

            # Left panel: Compound List (Simplified)
            list_fr = ttk.LabelFrame(content_fr, text=" Compounds ", padding=4)
            list_fr.grid(row=0, column=0, sticky=tk.NSEW, padx=(0, 4))
            list_fr.columnconfigure(0, weight=1)
            list_fr.rowconfigure(1, weight=1)

            # Search controls - inside compound list frame
            search_fr = ttk.Frame(list_fr)
            search_fr.grid(row=0, column=0, sticky=tk.EW, pady=(0, 4))
            search_fr.columnconfigure(1, weight=1)

            ttk.Label(search_fr, text="Search:").grid(row=0, column=0, padx=(0, 6))

            self._search_var = tk.StringVar()
            self._search_var.trace('w', self._on_search_changed)
            search_entry = ttk.Entry(search_fr, textvariable=self._search_var, width=20)
            search_entry.grid(row=0, column=1, sticky=tk.EW, padx=(0, 6))

            self._search_result_label = ttk.Label(search_fr, text="", foreground="#666666", font=("Arial", 8))
            self._search_result_label.grid(row=0, column=2, sticky=tk.W)

            self._compound_tree = ttk.Treeview(list_fr, columns=("Name",), show="tree headings",
                                               height=15)
            self._compound_tree.column("#0", width=180)
            self._compound_tree.column("Name", width=0)
            self._compound_tree.heading("#0", text="Compound")
            self._compound_tree.heading("Name", text="")
            self._compound_tree.grid(row=1, column=0, sticky=tk.NSEW)
            self._compound_tree.bind("<<TreeviewSelect>>", self._on_compound_selected)
        except Exception as e:
            print(f"Error building content area: {e}")
            import traceback
            traceback.print_exc()
            self._compound_tree = None

        try:
            # Middle panel: Structure image
            mid_fr = ttk.LabelFrame(content_fr, text=" Structure ", padding=4)
            mid_fr.grid(row=0, column=1, sticky=tk.NSEW, padx=(0, 4))
            mid_fr.columnconfigure(0, weight=1)
            mid_fr.rowconfigure(0, weight=1)

            self._canvas = tk.Canvas(mid_fr, bg="#f0f0f0", height=300, width=300)
            self._canvas.grid(row=0, column=0, sticky=tk.NSEW)
        except Exception as e:
            print(f"Error building structure panel: {e}")

        try:
            # Right panel: Metadata
            right_fr = ttk.LabelFrame(content_fr, text=" Metadata ", padding=4)
            right_fr.grid(row=0, column=2, sticky=tk.NSEW)
            right_fr.columnconfigure(0, weight=1)
            right_fr.rowconfigure(1, weight=1)

            # Header with label and button
            header_fr = ttk.Frame(right_fr)
            header_fr.grid(row=0, column=0, sticky=tk.EW, pady=(0, 4))
            header_fr.columnconfigure(0, weight=1)

            self._info_label = ttk.Label(header_fr, text="No file loaded", foreground="#666666")
            self._info_label.pack(side=tk.LEFT)

            self._edit_metadata_btn = ttk.Button(header_fr, text="Edit Metadata",
                                                command=self._edit_metadata, state=tk.DISABLED)
            self._edit_metadata_btn.pack(side=tk.RIGHT)

            self._meta_text = scrolledtext.ScrolledText(right_fr, height=15, width=40,
                                                         font=("Courier", 9),
                                                         bg="#f8f8f8", fg="#000000")
            self._meta_text.grid(row=1, column=0, sticky=tk.NSEW)
            self._meta_text.configure(state="disabled")
        except Exception as e:
            print(f"Error building metadata panel: {e}")

        try:
            # Bottom panel: Mass Spectrum Plot
            spec_fr = ttk.LabelFrame(content_fr, text=" Mass Spectrum ", padding=4)
            spec_fr.grid(row=1, column=0, columnspan=3, sticky=tk.NSEW, pady=(4, 0))
            spec_fr.columnconfigure(1, weight=1)
            spec_fr.rowconfigure(1, weight=1)

            # Header with button
            spec_header_fr = ttk.Frame(spec_fr)
            spec_header_fr.grid(row=0, column=0, columnspan=2, sticky=tk.EW, pady=(0, 4))
            spec_header_fr.columnconfigure(0, weight=1)

            self._edit_spectrum_btn = ttk.Button(spec_header_fr, text="Edit Spectrum",
                                               command=self._edit_mass_spectrum, state=tk.DISABLED)
            self._edit_spectrum_btn.pack(side=tk.RIGHT)

            self._spec_canvas_frame = ttk.Frame(spec_fr)
            self._spec_canvas_frame.grid(row=1, column=0, columnspan=2, sticky=tk.NSEW)
            self._spec_canvas_frame.columnconfigure(0, weight=1)
            self._spec_canvas_frame.rowconfigure(0, weight=1)
        except Exception as e:
            print(f"Error building mass spectrum panel: {e}")

        # ── Minimal Navigation Status Bar ──────────────────────────────────
        try:
            nav_fr = ttk.Frame(self)
            nav_fr.pack(fill=tk.X, pady=(4, 0))

            # Navigation label showing current position
            self._nav_label = ttk.Label(nav_fr, text="", foreground="#666666")
            self._nav_label.pack(side=tk.LEFT, padx=(0, 6))

            # Filter status (hidden by default)
            self._filter_label = ttk.Label(nav_fr, text="", foreground="#0066cc")
            self._filter_label.pack(side=tk.LEFT)

        except Exception as e:
            print(f"Error building navigation bar: {e}")


    def _browse_file(self) -> None:
        """Unified file browser for all supported formats."""
        path = filedialog.askopenfilename(
            filetypes=[
                ("All Supported", "*.sdf *.SDF *.mspec *.MSPEC *.jdx *.JDX *.jcamp"),
                ("SDF Files", "*.sdf *.SDF"),
                ("MSPEC Files (NIST)", "*.mspec *.MSPEC"),
                ("JDX Files (JCAMP)", "*.jdx *.JDX *.jcamp"),
                ("All Files", "*.*")
            ],
            title="Load Compound File"
        )
        if path:
            self._file_path.set(path)

    def _load_file(self, path: str = None) -> None:
        """Unified file loader - auto-detect format and load appropriately."""
        if path is None:
            path = self._file_path.get()

        if not path or not path.strip():
            messagebox.showwarning("No File", "Please select a file to load")
            return

        # Auto-detect format from extension
        import os
        if not os.path.isfile(path):
            messagebox.showerror("File Error", f"File not found:\n{path}")
            return

        ext = os.path.splitext(path)[1].lower()

        try:
            if ext == '.sdf':
                print(f"[DEBUG] Loading SDF file: {path}")
                self._load_sdf(path)
            elif ext in ('.mspec', '.msp'):
                print(f"[DEBUG] Loading MSPEC file: {path}")
                self._load_mspec(path)
            elif ext in ('.jdx', '.jcamp'):
                print(f"[DEBUG] Loading JDX file: {path}")
                self._load_jdx(path)
            else:
                messagebox.showerror("Unsupported Format",
                    f"Cannot load .{ext[1:] if ext else 'unknown'} files.\n\n"
                    f"Supported formats: SDF, MSPEC, JDX")
        except Exception as e:
            messagebox.showerror("Load Error", f"Failed to load file:\n{str(e)[:300]}")

    def _load_jdx(self, path: str) -> None:
        """Load JDX/JCAMP spectral file and insert into database."""
        try:
            print(f"[DEBUG] Loading JDX file: {path}")

            # Import JDX parser
            from ei_fragment_calculator.importers.jdx_parser import parse_jdx_file

            # Ensure database is initialized
            if not self._db_conn:
                self._init_database(db_path=None)

            records = parse_jdx_file(path)
            print(f"[DEBUG] Parsed {len(records)} records from JDX file")

            if not records:
                messagebox.showwarning("No Data", "No valid records found in JDX file")
                return

            # Insert records into database
            inserted_count = 0
            peak_count = 0

            for record in records:
                name = record.get('Name', '')
                formula = record.get('Formula', '')

                if not name:
                    continue  # Skip records without names

                self._db_cursor.execute("""
                    INSERT INTO compounds (name, formula)
                    VALUES (?, ?)
                """, (name, formula))

                compound_id = self._db_cursor.lastrowid
                inserted_count += 1

                # Insert peaks
                peaks = record.get('peaks', [])
                for mz, intensity in peaks:
                    self._db_cursor.execute("""
                        INSERT INTO mass_spectrum (compound_id, mz, intensity, base_peak)
                        VALUES (?, ?, ?, ?)
                    """, (compound_id, mz, intensity, 0))
                    peak_count += 1

                # Insert metadata fields
                excluded = {'Name', 'TITLE', 'Formula', 'peaks', 'NPOINTS'}
                for key, value in record.items():
                    if key not in excluded and value:
                        self._db_cursor.execute("""
                            INSERT INTO metadata (compound_id, field_name, field_value)
                            VALUES (?, ?, ?)
                        """, (compound_id, key, str(value)))

            self._db_conn.commit()
            self._file_path.set(path)

            # Update UI
            self._records = list(range(inserted_count))
            self._current_idx = 0
            self._populate_compound_list()
            if inserted_count > 0:
                self._show_record(0, highlight_in_tree=True)
            self._update_nav_label()

            print(f"[DEBUG] JDX loaded: {inserted_count} compounds, {peak_count} peaks")
            messagebox.showinfo("Success",
                f"Loaded {inserted_count} compounds with {peak_count} peaks from JDX file")

        except ImportError as e:
            messagebox.showerror("Import Error",
                f"Failed to import JDX parser:\n{str(e)[:300]}")
            print(f"[ERROR] Import error: {e}")
        except Exception as e:
            messagebox.showerror("Load Error",
                f"Failed to load JDX file:\n{str(e)[:300]}")
            print(f"[ERROR] Exception in _load_jdx: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Error", f"Failed to load JDX file:\n{str(e)[:300]}")

    def _on_persist_toggled(self) -> None:
        """Handle persistent database checkbox toggle."""
        if self._persist_db_var.get():
            self._choose_db_btn.config(state=tk.NORMAL)
            self._db_file_label.config(text="(choose location below)", foreground="#666666")
        else:
            self._choose_db_btn.config(state=tk.DISABLED)
            self._db_path_var.set("")
            self._db_file_label.config(text="(in-memory database)", foreground="#666666")

    def _choose_db_file(self) -> None:
        """Choose location for persistent database file."""
        file_path = filedialog.asksaveasfilename(
            defaultextension=".db",
            filetypes=[("SQLite Database", "*.db"), ("All files", "*.*")],
            title="Save Database As"
        )
        if file_path:
            self._db_path_var.set(file_path)
            filename = file_path.split('\\')[-1] if '\\' in file_path else file_path.split('/')[-1]
            self._db_file_label.config(
                text=f"({filename})",
                foreground="#0066cc"
            )
            print(f"[DEBUG] Persistent database will be saved to: {file_path}")

    def _init_database(self, db_path: str = None) -> None:
        """Initialize SQLite database with 4-table schema."""
        try:
            # Close existing connection if any
            if self._db_conn:
                try:
                    self._db_conn.close()
                except (sqlite3.Error, AttributeError):
                    pass

            # Use provided path or in-memory
            if db_path is None:
                db_path = ":memory:"

            self._db_conn = sqlite3.connect(db_path)
            self._db_conn.execute("PRAGMA foreign_keys = ON")
            self._db_cursor = self._db_conn.cursor()

            # Table 1: compounds (main compound data)
            self._db_cursor.execute("""
                CREATE TABLE compounds (
                    id INTEGER PRIMARY KEY,
                    name TEXT,
                    formula TEXT,
                    molecular_weight REAL,
                    cas_number TEXT,
                    iupac_name TEXT,
                    smiles TEXT,
                    inchi TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Indexes for common search operations
            self._db_cursor.execute("CREATE INDEX idx_name ON compounds(name)")
            self._db_cursor.execute("CREATE INDEX idx_formula ON compounds(formula)")
            self._db_cursor.execute("CREATE INDEX idx_cas ON compounds(cas_number)")

            # Table 2: metadata (all other SDF fields)
            self._db_cursor.execute("""
                CREATE TABLE metadata (
                    id INTEGER PRIMARY KEY,
                    compound_id INTEGER,
                    field_name TEXT,
                    field_value TEXT,
                    FOREIGN KEY(compound_id) REFERENCES compounds(id)
                )
            """)
            self._db_cursor.execute("CREATE INDEX idx_compound_id ON metadata(compound_id)")

            # Table 3: mass_spectrum (peak data)
            self._db_cursor.execute("""
                CREATE TABLE mass_spectrum (
                    id INTEGER PRIMARY KEY,
                    compound_id INTEGER,
                    mz REAL,
                    intensity REAL,
                    base_peak INTEGER,
                    FOREIGN KEY(compound_id) REFERENCES compounds(id)
                )
            """)
            self._db_cursor.execute("CREATE INDEX idx_compound_spectrum ON mass_spectrum(compound_id)")
            self._db_cursor.execute("CREATE INDEX idx_mz ON mass_spectrum(mz)")

            # Table 4: mol_data (RDKit molecule references)
            self._db_cursor.execute("""
                CREATE TABLE mol_data (
                    compound_id INTEGER PRIMARY KEY,
                    mol_reference TEXT,
                    FOREIGN KEY(compound_id) REFERENCES compounds(id)
                )
            """)

            # Table 5: retention_indices
            self._db_cursor.execute("""
                CREATE TABLE IF NOT EXISTS retention_indices (
                    id INTEGER PRIMARY KEY,
                    compound_id INTEGER,
                    gc_column TEXT,
                    ri_value REAL,
                    deviation REAL,
                    data_points INTEGER,
                    FOREIGN KEY(compound_id) REFERENCES compounds(id),
                    UNIQUE(compound_id, gc_column)
                )
            """)

            # Table 6: retention_times
            self._db_cursor.execute("""
                CREATE TABLE IF NOT EXISTS retention_times (
                    id INTEGER PRIMARY KEY,
                    compound_id INTEGER,
                    gc_method TEXT,
                    gc_column TEXT,
                    rt_value REAL,
                    temperature_program TEXT,
                    FOREIGN KEY(compound_id) REFERENCES compounds(id),
                    UNIQUE(compound_id, gc_method, gc_column)
                )
            """)

            # Create indexes
            self._db_cursor.execute("CREATE INDEX IF NOT EXISTS idx_ri_compound ON retention_indices(compound_id)")
            self._db_cursor.execute("CREATE INDEX IF NOT EXISTS idx_ri_value ON retention_indices(ri_value)")
            self._db_cursor.execute("CREATE INDEX IF NOT EXISTS idx_rt_compound ON retention_times(compound_id)")
            self._db_cursor.execute("CREATE INDEX IF NOT EXISTS idx_rt_value ON retention_times(rt_value)")

            self._db_conn.commit()
            print("[DEBUG] Database initialized with schema")
        except Exception as e:
            print(f"[ERROR] Failed to initialize database: {e}")
            raise

    def _update_db_status(self, status_text: str) -> None:
        """Update the database status label in the UI."""
        if hasattr(self, '_db_file_label'):
            self._db_file_label.config(text=status_text, foreground="#0066cc")

    def _close_database(self) -> None:
        """Close the current database connection."""
        if self._db_conn:
            try:
                self._db_conn.close()
                self._db_conn = None
                self._db_cursor = None
                self._records.clear()
                self._compound_tree.delete(*self._compound_tree.get_children())
                # Clear record display
                if hasattr(self, '_record_display'):
                    self._record_display.delete(1.0, tk.END)
                self._update_db_status("[No database]")
                print("[DEBUG] Database closed")
            except Exception as e:
                print(f"[ERROR] Failed to close database: {e}")

    def _insert_sdf_to_database(self, mol, idx: int, fields: dict) -> None:
        """Insert SDF record data into database."""
        try:
            # Extract key fields
            name = fields.get("NAME", fields.get("COMPOUND NAME", f"Compound {idx + 1}"))
            formula = fields.get("FORMULA", "")
            try:
                molecular_weight = float(fields.get("MW", 0)) if fields.get("MW") else None
            except (ValueError, TypeError):
                molecular_weight = None
            cas_number = fields.get("CASNO", fields.get("CAS", ""))
            iupac_name = fields.get("IUPAC_NAME", "")
            smiles = fields.get("SMILES", "")
            inchi = fields.get("InChI", "")

            # Insert into compounds table
            self._db_cursor.execute("""
                INSERT INTO compounds (name, formula, molecular_weight, cas_number, iupac_name, smiles, inchi)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (name, formula, molecular_weight, cas_number, iupac_name, smiles, inchi))

            compound_id = self._db_cursor.lastrowid

            # Insert other fields into metadata table
            excluded_fields = {"NAME", "COMPOUND NAME", "FORMULA", "MW", "CASNO", "CAS", "IUPAC_NAME", "SMILES", "InChI"}
            for field_name, field_value in fields.items():
                if field_name not in excluded_fields and field_value:
                    self._db_cursor.execute("""
                        INSERT INTO metadata (compound_id, field_name, field_value)
                        VALUES (?, ?, ?)
                    """, (compound_id, field_name, str(field_value)))

            # Parse and insert mass spectrum peaks if available
            # Check multiple field names for compatibility with different SDF formats
            peaks_field = None
            peaks_candidates = ["Num Peaks", "PEAKS", "MASS SPECTRAL PEAKS", "MASS SPECTRUM",
                              "MS PEAKS", "MS DATA", "peaks", "mass_spectrum"]
            for candidate in peaks_candidates:
                if candidate in fields and fields[candidate]:
                    peaks_field = fields[candidate]
                    break

            if peaks_field:
                try:
                    peaks = self._parse_peaks_from_field(peaks_field)
                    for mz, intensity in peaks:
                        self._db_cursor.execute("""
                            INSERT INTO mass_spectrum (compound_id, mz, intensity)
                            VALUES (?, ?, ?)
                        """, (compound_id, mz, intensity))
                except Exception as e:
                    print(f"[WARNING] Could not parse peaks for compound {idx}: {e}")

            # Store mol reference in mol_data (keep molecule object in memory via _records)
            self._db_cursor.execute("""
                INSERT INTO mol_data (compound_id, mol_reference)
                VALUES (?, ?)
            """, (compound_id, f"mol_{idx}"))

            self._db_conn.commit()
        except Exception as e:
            print(f"[ERROR] Failed to insert record {idx} into database: {e}")
            raise

    def _parse_peaks_from_field(self, peaks_str: str) -> list:
        """Parse peaks string into (m/z, intensity) tuples."""
        peaks = []
        if not peaks_str:
            return peaks

        try:
            # Handle multiple formats: newline-separated, semicolon-separated, or comma-separated
            peaks_str = str(peaks_str).strip()

            # Try newline-separated first (most common in SDF files)
            if '\n' in peaks_str:
                parts = peaks_str.split('\n')
            elif ';' in peaks_str:
                parts = peaks_str.split(';')
            else:
                parts = [peaks_str]

            for part in parts:
                part = part.strip()
                if not part:
                    continue
                # Try space-separated first (most common)
                if " " in part:
                    mz_str, intensity_str = part.rsplit(" ", 1)
                elif "," in part:
                    mz_str, intensity_str = part.split(",", 1)
                else:
                    continue
                try:
                    mz = float(mz_str.strip())
                    intensity = float(intensity_str.strip())
                    peaks.append((mz, intensity))
                except ValueError:
                    continue
        except Exception as e:
            print(f"[WARNING] Error parsing peaks: {e}")

        return peaks

    def _undo(self) -> None:
        """Undo last metadata change."""
        if not self._db_conn:
            return

        action = self._undo_redo_stack.undo()
        if action:
            try:
                # Revert to old value in database
                self._db_cursor.execute(
                    "UPDATE metadata SET field_value = ? WHERE compound_id = ? AND field_name = ?",
                    (action['old_value'], action['compound_id'], action['field_name'])
                )
                self._db_conn.commit()
                # Refresh display
                self._refresh_record_display()
            except Exception as e:
                print(f"[ERROR] Undo failed: {e}")

    def _redo(self) -> None:
        """Redo last undone change."""
        if not self._db_conn:
            return

        action = self._undo_redo_stack.redo()
        if action:
            try:
                # Reapply new value to database
                self._db_cursor.execute(
                    "UPDATE metadata SET field_value = ? WHERE compound_id = ? AND field_name = ?",
                    (action['new_value'], action['compound_id'], action['field_name'])
                )
                self._db_conn.commit()
                # Refresh display
                self._refresh_record_display()
            except Exception as e:
                print(f"[ERROR] Redo failed: {e}")

    def _refresh_record_display(self) -> None:
        """Refresh the metadata display for current record."""
        if self._current_idx >= 0 and self._current_idx < len(self._records):
            self._display_record(self._current_idx)

    def _load_sdf(self, path: str) -> None:
        """Parse SDF file and extract records."""
        try:
            print(f"[DEBUG] Loading SDF: {path}")
            
            if not _HAS_RDKIT:
                print("[ERROR] RDKit not available")
                messagebox.showerror("Error", 
                    "RDKit is required to load SDF files.\n\n"
                    "Go to Packages tab and install 'rdkit'.")
                return

            from rdkit import Chem
            self._records = []
            self._current_idx = 0
            print("[DEBUG] RDKit imported")

            # Initialize database
            print("[DEBUG] Initializing database...")
            db_path = None
            if self._persist_db_var.get() and self._db_path_var.get():
                db_path = self._db_path_var.get()
                print(f"[DEBUG] Using persistent database: {db_path}")
            self._init_database(db_path)
            self._current_query_results = []

            # Try to parse with RDKit
            try:
                print(f"[DEBUG] Parsing SDF file...")
                suppl = Chem.SDMolSupplier(str(path), removeHs=False, sanitize=False)
                print(f"[DEBUG] SDF parsed, {len(suppl) if suppl else 0} molecules found")
            except Exception as parse_err:
                print(f"[ERROR] Parse error: {parse_err}")
                import traceback
                traceback.print_exc()
                messagebox.showerror("Parse Error",
                    f"Could not parse SDF file:\n{str(parse_err)[:200]}")
                return

            if suppl is None or len(suppl) == 0:
                print("[ERROR] SDF empty or unreadable")
                messagebox.showerror("Error",
                    "SDF file is empty or could not be read.")
                return

            # Extract molecules and their properties
            print("[DEBUG] Extracting molecules...")
            for idx, mol in enumerate(suppl):
                try:
                    fields = mol.GetPropsAsDict() if mol else {}
                    # Insert into database
                    self._insert_sdf_to_database(mol, idx, fields)
                    # Keep record in memory for mol object reference
                    record = {
                        "mol": mol,
                        "fields": fields
                    }
                    self._records.append(record)
                except Exception as mol_err:
                    print(f"Warning: Could not process molecule {idx}: {mol_err}")
                    # Still add empty record so indexing works
                    self._records.append({"mol": None, "fields": {}})

            if not self._records:
                print("[ERROR] No valid molecules found")
                messagebox.showerror("Error", "No valid molecules found in SDF.")
                return

            print(f"[DEBUG] Successfully loaded {len(self._records)} records")
            # Populate compound tree
            print("[DEBUG] About to populate compound list...")
            self._populate_compound_list()
            print("[DEBUG] Compound list populated, showing first record...")
            self._show_record(0, highlight_in_tree=True)
            print("[DEBUG] First record shown, updating nav label...")
            self._update_nav_label()
            print("[DEBUG] SDF loaded and displayed - loading complete!")

        except Exception as e:
            print(f"[ERROR] Exception in _load_sdf: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Error", f"Failed to load SDF:\n{str(e)[:300]}")

    def _load_mspec(self, path: str) -> None:
        """Load MSPEC file and insert into database."""
        from ei_fragment_calculator.importers.mspec_parser import parse_mspec_file, parse_retention_index

        try:
            print(f"[DEBUG] Loading MSPEC file: {path}")

            # Ensure database is initialized
            if not self._db_conn:
                self._init_database(db_path=None)

            records = parse_mspec_file(path)
            print(f"[DEBUG] Parsed {len(records)} records from MSPEC file")

            for record in records:
                # Extract main fields
                name = record.get('Name', '')
                formula = record.get('Formula', '')
                mw_str = record.get('MW', '')
                try:
                    mw = float(mw_str) if mw_str else None
                except (ValueError, TypeError):
                    mw = None

                cas = record.get('CAS#', '')

                # Insert into compounds table
                self._db_cursor.execute("""
                    INSERT INTO compounds (name, formula, molecular_weight, cas_number)
                    VALUES (?, ?, ?, ?)
                """, (name, formula, mw, cas))

                compound_id = self._db_cursor.lastrowid
                print(f"[DEBUG] Inserted compound {compound_id}: {name}")

                # Insert RI data if available
                if 'Retention_index' in record:
                    ri_dict = record['Retention_index']
                    for gc_column, (ri_val, deviation, data_points) in ri_dict.items():
                        self._db_cursor.execute("""
                            INSERT INTO retention_indices (compound_id, gc_column, ri_value, deviation, data_points)
                            VALUES (?, ?, ?, ?, ?)
                        """, (compound_id, gc_column, ri_val, deviation, data_points))
                    print(f"[DEBUG]   Inserted {len(ri_dict)} RI data entries")

                # Insert peaks
                peaks = record.get('peaks', [])
                for mz, intensity in peaks:
                    self._db_cursor.execute("""
                        INSERT INTO mass_spectrum (compound_id, mz, intensity, base_peak)
                        VALUES (?, ?, ?, ?)
                    """, (compound_id, mz, intensity, 0))
                print(f"[DEBUG]   Inserted {len(peaks)} peaks")

                # Insert other fields into metadata
                excluded = {'Name', 'Formula', 'MW', 'CAS#', 'Retention_index', 'Num Peaks', 'peaks', 'InChIKey'}
                for key, value in record.items():
                    if key not in excluded:
                        if isinstance(value, list):  # Handle Synon, etc.
                            for v in value:
                                if v:  # Skip empty values
                                    self._db_cursor.execute("""
                                        INSERT INTO metadata (compound_id, field_name, field_value)
                                        VALUES (?, ?, ?)
                                    """, (compound_id, key, str(v)))
                        elif value:  # Skip empty values
                            self._db_cursor.execute("""
                                INSERT INTO metadata (compound_id, field_name, field_value)
                                VALUES (?, ?, ?)
                            """, (compound_id, key, str(value)))

            self._db_conn.commit()
            print(f"[DEBUG] MSPEC file loaded and committed")

            # Store file path and populate UI
            self._sdf_path.set(path)
            self._records = list(range(len(records)))
            self._current_idx = 0
            self._populate_compound_list()
            # Update spectrum analyzer with records
            if self._spectrum_tab:
                self._spectrum_tab.set_records(records)
            self._show_record(0, highlight_in_tree=True)
            self._update_nav_label()
            print("[DEBUG] MSPEC loaded and displayed - loading complete!")
            messagebox.showinfo("Success", f"Loaded {len(records)} compounds from MSPEC file")

        except Exception as e:
            print(f"[ERROR] Exception in _load_mspec: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Error", f"Failed to load MSPEC:\n{str(e)[:300]}")

    def _populate_compound_list(self) -> None:
        """Populate the compound list with all records from database."""
        print("[DEBUG] _populate_compound_list called")
        if not self._compound_tree:
            print("[ERROR] _compound_tree is None!")
            return

        print(f"[DEBUG] _compound_tree exists: {self._compound_tree}")
        try:
            # Clear existing items
            print("[DEBUG] Clearing existing items...")
            for item in self._compound_tree.get_children():
                self._compound_tree.delete(item)
            print("[DEBUG] Cleared existing items")

            # Query database for compounds (or use current query results if filtered)
            if self._current_query_results:
                results = self._current_query_results
            else:
                # Get all compounds from database
                results = self._db_cursor.execute(
                    "SELECT id, name FROM compounds ORDER BY id"
                ).fetchall()

            print(f"[DEBUG] Adding {len(results)} records to tree...")
            for display_idx, (record_id, name) in enumerate(results):
                try:
                    print(f"[DEBUG] Inserting record {record_id}")
                    # Truncate long names
                    name = str(name)[:60] if name else f"Compound {display_idx + 1}"
                    display_text = f"{display_idx + 1}. {name}"
                    print(f"[DEBUG] Inserting with text: {display_text}")
                    # Use record_id for tree item ID (will convert to idx in _on_compound_selected)
                    self._compound_tree.insert("", tk.END, iid=str(record_id), text=display_text)
                    print(f"[DEBUG] Successfully inserted record {record_id}")
                except Exception as e:
                    print(f"Warning: Could not add record {record_id} to list: {e}")
        except Exception as e:
            print(f"Error populating compound list: {e}")

    def _on_compound_selected(self, event) -> None:
        """Handle compound selection from the list."""
        if not self._compound_tree:
            return

        try:
            selection = self._compound_tree.selection()
            if selection:
                # Tree item ID is record_id (1-based), convert to array index (0-based)
                record_id = int(selection[0])
                idx = record_id - 1
                self._show_record(idx)
                self._update_nav_label()
        except (ValueError, IndexError, AttributeError):
            pass

    def _show_record(self, idx: int, highlight_in_tree: bool = False) -> None:
        """Display record at given index.

        Args:
            idx: Record index to display
            highlight_in_tree: If True, highlight this record in the tree. Only set True
                              when initially loading (to avoid infinite loop from tree selection events).
        """
        print(f"[DEBUG] _show_record called with idx={idx}, highlight_in_tree={highlight_in_tree}")
        if not self._records or idx < 0 or idx >= len(self._records):
            print(f"[ERROR] Invalid index: {idx}, records: {len(self._records) if self._records else 0}")
            return

        print(f"[DEBUG] Setting current index to {idx}")
        self._current_idx = idx
        record = self._records[idx]
        mol = record.get("mol")
        fields = record.get("fields", {})
        print(f"[DEBUG] Got record data for index {idx}")

        # Load record data from database
        try:
            record_id = idx + 1  # Database IDs are 1-based
            compound = self._db_cursor.execute(
                "SELECT name, formula, molecular_weight, cas_number, iupac_name, smiles, inchi "
                "FROM compounds WHERE id = ?", (record_id,)
            ).fetchone()

            if compound:
                db_name, db_formula, db_mw, db_cas, db_iupac, db_smiles, db_inchi = compound
                # Load metadata from database
                metadata_rows = self._db_cursor.execute(
                    "SELECT field_name, field_value FROM metadata WHERE compound_id = ? "
                    "ORDER BY field_name", (record_id,)
                ).fetchall()
                db_metadata = {row[0]: row[1] for row in metadata_rows}
                # Merge database data with fields (database takes precedence)
                fields = {**fields, **db_metadata}
                if db_name:
                    fields["NAME"] = db_name
                if db_formula:
                    fields["FORMULA"] = db_formula
                if db_mw:
                    fields["MW"] = db_mw
                if db_cas:
                    fields["CASNO"] = db_cas
                if db_iupac:
                    fields["IUPAC_NAME"] = db_iupac
                if db_smiles:
                    fields["SMILES"] = db_smiles
                if db_inchi:
                    fields["InChI"] = db_inchi
        except Exception as e:
            print(f"[WARNING] Could not load record from database: {e}")

        # Update structure image
        if not self._canvas:
            print("[ERROR] _canvas is None!")
            return

        print("[DEBUG] Canvas exists, updating structure...")

        self._canvas.delete("all")
        if mol and _HAS_RDKIT:
            try:
                from rdkit.Chem import Draw
                from PIL import ImageTk
                img = Draw.MolToImage(mol, size=(300, 300))
                self._photo = ImageTk.PhotoImage(img)
                self._canvas.create_image(150, 150, image=self._photo)
            except ImportError:
                self._canvas.create_text(150, 150, text="PIL/Pillow not installed",
                                        fill="#cc0000", font=("Arial", 9))
            except Exception as e:
                self._canvas.create_text(150, 150, text=f"Render error",
                                        fill="#999999", font=("Arial", 9))
        else:
            text = "No structure" if not mol else "RDKit not available"
            self._canvas.create_text(150, 150, text=text, fill="#999999",
                                    font=("Arial", 10))

        # Update metadata text
        if self._meta_text:
            try:
                self._meta_text.configure(state="normal")
                self._meta_text.delete("1.0", tk.END)

                # Display name and basic info
                name = fields.get("NAME", fields.get("COMPOUND NAME", "Unknown"))
                formula = fields.get("FORMULA", "—")
                mw = fields.get("MW", fields.get("MONOISOTOPIC MW", "—"))

                info = f"Name: {name}\nFormula: {formula}\nMW: {mw}\n\n"
                info += "─" * 40 + "\n\n"

                # Display all metadata fields
                for key in sorted(fields.keys()):
                    val = str(fields[key])[:100]  # Limit display length
                    info += f"{key}: {val}\n"

                self._meta_text.insert("1.0", info)
                self._meta_text.configure(state="disabled")
            except Exception as e:
                print(f"Error updating metadata: {e}")

        # Plot mass spectrum
        if _HAS_MATPLOTLIB and fields:
            self._plot_mass_spectrum(fields)
        elif self._spec_canvas_frame:
            # Show placeholder if matplotlib not available
            for widget in self._spec_canvas_frame.winfo_children():
                widget.destroy()
            msg = "Matplotlib not installed" if not _HAS_MATPLOTLIB else "No mass spectrum data"
            placeholder = ttk.Label(self._spec_canvas_frame, text=msg,
                                   foreground="#999999", font=("Arial", 10))
            placeholder.pack(fill=tk.BOTH, expand=True)

        # Highlight current record in compound list (only when initially loading)
        # This prevents infinite loops from tree selection events
        if highlight_in_tree and self._compound_tree:
            try:
                # Tree item ID is record_id (1-based), convert from array index
                record_id = str(idx + 1)
                self._compound_tree.selection_set(record_id)
                self._compound_tree.see(record_id)
            except Exception as e:
                print(f"Warning: Could not highlight compound {idx}: {e}")

        # Update info label
        if self._info_label:
            try:
                self._info_label.config(
                    text=f"Record {idx + 1} of {len(self._records)}")
            except Exception as e:
                print(f"Error updating info label: {e}")

        # Enable edit buttons
        if self._edit_metadata_btn:
            self._edit_metadata_btn.config(state=tk.NORMAL)
        if self._edit_spectrum_btn:
            self._edit_spectrum_btn.config(state=tk.NORMAL)

    def _plot_mass_spectrum(self, fields: dict) -> None:
        """Plot mass spectral peaks if available."""
        # Clear previous canvas
        for widget in self._spec_canvas_frame.winfo_children():
            widget.destroy()

        # Try to find mass spectral peaks in various field names
        peaks_data = None
        peaks_candidates = ["MASS SPECTRAL PEAKS", "MASS SPECTRUM", "PEAKS", "MS PEAKS"]
        
        for candidate in peaks_candidates:
            for key in fields.keys():
                if candidate.lower() in key.lower():
                    peaks_data = fields[key]
                    break
            if peaks_data:
                break

        if not peaks_data or not _HAS_MATPLOTLIB:
            # Show placeholder if no data or matplotlib not available
            msg = "No mass spectrum data" if not peaks_data else "Matplotlib not installed"
            placeholder = ttk.Label(self._spec_canvas_frame, text=msg,
                                   foreground="#999999", font=("Arial", 10))
            placeholder.pack(fill=tk.BOTH, expand=True)
            return

        try:
            # Parse peaks data
            mz_values, intensity_values = self._parse_peaks(peaks_data)

            if not mz_values:
                placeholder = ttk.Label(self._spec_canvas_frame, text="Could not parse peaks",
                                       foreground="#999999", font=("Arial", 10))
                placeholder.pack(fill=tk.BOTH, expand=True)
                return

            # Create matplotlib figure
            fig = Figure(figsize=(12, 3), dpi=100)
            ax = fig.add_subplot(111)

            # Plot as bar chart with thinner peaks
            ax.bar(mz_values, intensity_values, width=0.3, color="#0078D4", alpha=0.7, edgecolor="#0055AA", linewidth=0.5)
            ax.set_xlabel("m/z", fontsize=10)
            ax.set_ylabel("Intensity", fontsize=10)
            ax.set_title("Mass Spectrum", fontsize=11, fontweight="bold")
            ax.grid(axis="y", alpha=0.3)
            fig.tight_layout()

            # Embed in tkinter
            canvas = FigureCanvasTkAgg(fig, master=self._spec_canvas_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        except Exception as e:
            error_label = ttk.Label(self._spec_canvas_frame,
                                   text=f"Error plotting spectrum: {str(e)[:50]}",
                                   foreground="#cc0000", font=("Arial", 9))
            error_label.pack(fill=tk.BOTH, expand=True)

    def _parse_peaks(self, peaks_str: str) -> tuple:
        """
        Parse mass spectral peaks from various formats.
        Common formats:
          - "50 287; 51 144; 52 9" (semicolon-separated m/z intensity pairs)
          - "50 287\n51 144\n52 9" (newline-separated)
          - Space-separated list of alternating m/z and intensity values
        """
        mz_values = []
        intensity_values = []

        try:
            # Remove extra whitespace and newlines
            peaks_str = str(peaks_str).strip()

            # Try semicolon-separated format
            if ";" in peaks_str:
                pairs = peaks_str.split(";")
                for pair in pairs:
                    parts = pair.strip().split()
                    if len(parts) >= 2:
                        try:
                            mz = float(parts[0])
                            intensity = float(parts[1])
                            mz_values.append(mz)
                            intensity_values.append(intensity)
                        except ValueError:
                            continue

            # Try newline-separated format
            elif "\n" in peaks_str:
                lines = peaks_str.split("\n")
                for line in lines:
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        try:
                            mz = float(parts[0])
                            intensity = float(parts[1])
                            mz_values.append(mz)
                            intensity_values.append(intensity)
                        except ValueError:
                            continue

            # Try space-separated format (alternating m/z intensity)
            else:
                parts = peaks_str.split()
                for i in range(0, len(parts) - 1, 2):
                    try:
                        mz = float(parts[i])
                        intensity = float(parts[i + 1])
                        mz_values.append(mz)
                        intensity_values.append(intensity)
                    except (ValueError, IndexError):
                        continue

        except Exception:
            pass

        return mz_values, intensity_values

    def _jump_to_record(self) -> None:
        """Jump to a specific record by index."""
        if not self._records:
            messagebox.showwarning("No Data", "No SDF file loaded.")
            return

        # Create dialog
        dialog = tk.Toplevel(self)
        dialog.title("Jump to Record")
        dialog.geometry("300x120")
        dialog.resizable(False, False)

        ttk.Label(dialog, text="Record number (1 to {0}):".format(len(self._records))).pack(
            pady=10)

        # Spinbox for record selection
        spinbox_var = tk.IntVar(value=self._current_idx + 1)
        spinbox = ttk.Spinbox(dialog, from_=1, to=len(self._records),
                            textvariable=spinbox_var, width=10)
        spinbox.pack(pady=5)
        spinbox.focus()

        def jump():
            try:
                idx = spinbox_var.get() - 1
                if 0 <= idx < len(self._records):
                    self._show_record(idx, highlight_in_tree=True)
                    self._update_nav_label()
                    dialog.destroy()
                else:
                    messagebox.showerror("Invalid", f"Please enter a number between 1 and {len(self._records)}")
            except ValueError:
                messagebox.showerror("Invalid", "Please enter a valid number")

        # Buttons
        btn_fr = ttk.Frame(dialog)
        btn_fr.pack(pady=10)
        ttk.Button(btn_fr, text="Go", command=jump).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_fr, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

        # Allow Enter to jump
        dialog.bind("<Return>", lambda e: jump())

    def _search_compounds(self) -> None:
        """Open search dialog to find compounds by name."""
        if not self._db_conn:
            messagebox.showwarning("No Data", "No SDF file loaded.")
            return

        # Create dialog
        dialog = tk.Toplevel(self)
        dialog.title("Search Compounds")
        dialog.geometry("350x150")
        dialog.resizable(False, False)

        ttk.Label(dialog, text="Search by compound name (case-insensitive):").pack(
            pady=10, padx=10)

        # Search entry
        search_var = tk.StringVar()
        entry = ttk.Entry(dialog, textvariable=search_var, width=40)
        entry.pack(pady=5, padx=10)
        entry.focus()

        result_label = ttk.Label(dialog, text="", foreground="#666666")
        result_label.pack(pady=5)

        def search():
            search_term = search_var.get().strip()
            if not search_term:
                messagebox.showwarning("Empty", "Please enter a search term")
                return

            try:
                # Query database for matching compounds
                query = "SELECT id, name FROM compounds WHERE LOWER(name) LIKE LOWER('%' || ? || '%') ORDER BY id"
                results = self._db_cursor.execute(query, (search_term,)).fetchall()

                if results:
                    self._current_query_results = results
                    total = self._db_cursor.execute("SELECT COUNT(*) FROM compounds").fetchone()[0]
                    result_label.config(
                        text=f"Found {len(results)} of {total} compounds",
                        foreground="#0066cc"
                    )
                    # Update filter label
                    self._filter_label.config(text=f"Filtered: {len(results)} of {total}")
                    # Populate tree with results
                    self._populate_compound_list()
                    # Show first result
                    if results:
                        self._show_record(results[0][0] - 1, highlight_in_tree=True)
                        self._update_nav_label()
                    dialog.destroy()
                else:
                    result_label.config(text="No matches found", foreground="#cc0000")
            except Exception as e:
                messagebox.showerror("Search Error", f"Search failed: {e}")

        # Buttons
        btn_fr = ttk.Frame(dialog)
        btn_fr.pack(pady=10)
        ttk.Button(btn_fr, text="Search", command=search).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_fr, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

        # Allow Enter to search
        dialog.bind("<Return>", lambda e: search())

    def _clear_filter(self) -> None:
        """Clear current filter and show all records."""
        self._current_query_results = []
        self._filter_label.config(text="")
        self._populate_compound_list()
        if self._records:
            self._show_record(0, highlight_in_tree=True)
            self._update_nav_label()

    def _on_search_changed(self, var, index, mode) -> None:
        """Handle real-time search as user types."""
        if not self._db_conn:
            return

        search_term = self._search_var.get().strip()

        if not search_term:
            # Empty search - show all compounds
            self._current_query_results = []
            self._filter_label.config(text="")
            self._search_result_label.config(text="")
            self._populate_compound_list()
            if self._records:
                self._show_record(0, highlight_in_tree=True)
                self._update_nav_label()
            return

        try:
            # Query database for matching compounds
            query = "SELECT id, name FROM compounds WHERE LOWER(name) LIKE LOWER('%' || ? || '%') ORDER BY id"
            results = self._db_cursor.execute(query, (search_term,)).fetchall()

            if results:
                self._current_query_results = results
                total = self._db_cursor.execute("SELECT COUNT(*) FROM compounds").fetchone()[0]
                self._search_result_label.config(
                    text=f"Found {len(results)} of {total}",
                    foreground="#0066cc"
                )
                self._filter_label.config(text=f"Filtered: {len(results)} of {total}")
                # Populate tree with results
                self._populate_compound_list()
                # Show first result
                if results:
                    self._show_record(results[0][0] - 1, highlight_in_tree=True)
                    self._update_nav_label()
            else:
                self._search_result_label.config(text="No matches found", foreground="#cc0000")
                self._current_query_results = []
                self._populate_compound_list()
        except Exception as e:
            self._search_result_label.config(text=f"Error: {str(e)[:20]}", foreground="#cc0000")

    def _enrich_metadata_with_pubchem(self, record_id: int) -> dict:
        """Fetch PubChem data for a compound and return enriched fields."""
        try:
            # Get current compound data
            compound_row = self._db_cursor.execute(
                "SELECT name, formula, cas_number, smiles, inchi FROM compounds WHERE id = ?",
                (record_id,)
            ).fetchone()

            if not compound_row:
                messagebox.showerror("Error", "Compound not found in database")
                return {}

            name, formula, cas_number, smiles, inchi = compound_row

            # Create minimal record for enrichment
            record = {
                "name": name or "",
                "FORMULA": formula or "",
                "CASNO": cas_number or "",
                "SMILES": smiles or "",
                "InChI": inchi or "",
            }

            try:
                from sdf_enricher.enricher import EnrichConfig, enrich_records

                # Enrich with PubChem only
                config = EnrichConfig(pubchem=True, chebi=False, kegg=False, hmdb=False,
                                      calc_exact_mass=False, calc_splash=False, overwrite=False)
                enrich_records([record], config=config, verbose=False)

                # Extract enriched fields (only those that were updated)
                enriched_fields = {}
                for key in ["FORMULA", "CASNO", "SMILES", "InChI", "PUBCHEM_CID",
                            "PUBCHEM_NAME", "PUBCHEM_IUPAC", "PUBCHEM_IUPAC_SYSTEMATIC"]:
                    if key in record and record[key]:
                        enriched_fields[key] = record[key]

                return enriched_fields
            except ImportError:
                messagebox.showwarning("Missing Dependency",
                    "sdf_enricher package not installed.\n"
                    "Install with: pip install sdf-enricher")
                return {}
        except Exception as e:
            messagebox.showerror("Enrichment Error", f"Failed to enrich metadata: {str(e)[:200]}")
            print(f"[ERROR] PubChem enrichment failed: {e}")
            return {}

    def _edit_metadata(self) -> None:
        """Open metadata editor dialog for current record."""
        if not self._records or self._current_idx >= len(self._records):
            messagebox.showwarning("No Record", "Please load an SDF file and select a record first.")
            return

        record_id = self._current_idx + 1

        # Get compound name for title
        try:
            compound_name = self._db_cursor.execute(
                "SELECT name FROM compounds WHERE id = ?", (record_id,)
            ).fetchone()[0]
        except (sqlite3.Error, TypeError, IndexError):
            compound_name = f"Compound {record_id}"

        print(f"[DEBUG] _edit_metadata: current_idx={self._current_idx}, record_id={record_id}, name={compound_name}")

        # Create dialog window
        dialog = tk.Toplevel(self)
        dialog.title(f"Edit Metadata - {compound_name}")
        dialog.geometry("500x400")

        # Load metadata from database (exclude mass spectral data)
        try:
            metadata_rows = self._db_cursor.execute(
                "SELECT field_name, field_value FROM metadata WHERE compound_id = ? AND field_name NOT LIKE '%PEAK%' AND field_name NOT LIKE '%SPECTRUM%' ORDER BY field_name",
                (record_id,)
            ).fetchall()
            print(f"[DEBUG] Retrieved {len(metadata_rows)} metadata rows")
            metadata_dict = {row[0]: row[1] for row in metadata_rows}
            print(f"[DEBUG] metadata_dict has {len(metadata_dict)} entries")

            # Also add main compound fields
            compound_row = self._db_cursor.execute(
                "SELECT name, formula, molecular_weight, cas_number, iupac_name, smiles, inchi FROM compounds WHERE id = ?",
                (record_id,)
            ).fetchone()

            if compound_row:
                metadata_dict.update({
                    "NAME": compound_row[0],
                    "FORMULA": compound_row[1],
                    "MW": compound_row[2],
                    "CASNO": compound_row[3],
                    "IUPAC_NAME": compound_row[4],
                    "SMILES": compound_row[5],
                    "InChI": compound_row[6],
                })
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load metadata: {e}")
            dialog.destroy()
            return

        # Create Treeview for metadata
        ttk.Label(dialog, text="Field Name | Value", font=("Arial", 9, "bold")).pack(
            fill=tk.X, padx=5, pady=(5, 2))

        tree_fr = ttk.Frame(dialog)
        tree_fr.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Scrollbars
        vsb = ttk.Scrollbar(tree_fr, orient=tk.VERTICAL)
        hsb = ttk.Scrollbar(tree_fr, orient=tk.HORIZONTAL)

        meta_tree = ttk.Treeview(tree_fr, columns=("Value",), show="tree headings",
                                 yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.config(command=meta_tree.yview)
        hsb.config(command=meta_tree.xview)

        meta_tree.column("#0", width=150)
        meta_tree.heading("#0", text="Field Name")
        meta_tree.column("Value", width=320)
        meta_tree.heading("Value", text="Value")

        # Populate tree with metadata
        item_map = {}  # Map tree item ID to field name
        print(f"[DEBUG] Populating tree with {len(metadata_dict)} items...")
        for idx, (field_name, field_value) in enumerate(sorted(metadata_dict.items())):
            item_id = meta_tree.insert("", tk.END, text=field_name, values=(field_value,))
            item_map[item_id] = field_name
            print(f"[DEBUG]   Inserted item {idx+1}: {field_name}")
        print(f"[DEBUG] Tree population complete")

        meta_tree.grid(row=0, column=0, sticky=tk.NSEW)
        vsb.grid(row=0, column=1, sticky=tk.NS)
        hsb.grid(row=1, column=0, sticky=tk.EW)
        tree_fr.columnconfigure(0, weight=1)
        tree_fr.rowconfigure(0, weight=1)

        # Track changes
        changes = {"modified": {}, "deleted": set(), "added": {}}

        def on_double_click(event):
            """Edit cell on double-click - inline entry."""
            try:
                if not meta_tree.selection():
                    return

                item = meta_tree.selection()[0]
                if item not in item_map:
                    return

                field_name = item_map[item]
                col = meta_tree.identify_column(event.x)

                if col == "#1":  # Value column (column index 1)
                    current_value = meta_tree.item(item, "values")[0]

                    # Get cell bounding box for positioning
                    bbox = meta_tree.bbox(item, col)
                    if not bbox:
                        return

                    # Create inline entry widget
                    entry = tk.Entry(tree_fr, width=40)
                    entry.insert(0, str(current_value) if current_value else "")

                    # Position entry over the cell
                    entry.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])

                    def save_on_focusout(e=None):
                        try:
                            new_value = entry.get().strip()
                            meta_tree.item(item, values=(new_value,))
                            changes["modified"][field_name] = new_value
                        finally:
                            entry.destroy()

                    def save_on_return(e):
                        save_on_focusout()

                    def on_escape(e):
                        entry.destroy()

                    entry.bind("<Return>", save_on_return)
                    entry.bind("<FocusOut>", save_on_focusout)
                    entry.bind("<Escape>", on_escape)
                    entry.focus()
                    entry.select_range(0, tk.END)

            except Exception as e:
                print(f"[DEBUG] Error in on_double_click: {e}")

        meta_tree.bind("<Double-1>", on_double_click)

        # Buttons
        btn_fr = ttk.Frame(dialog)
        btn_fr.pack(fill=tk.X, padx=5, pady=5)

        # Add field inline frame
        add_fr = ttk.Frame(dialog)
        add_fr.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(add_fr, text="Add Field:", font=("Arial", 9)).pack(side=tk.LEFT, padx=(0, 5))

        new_field_name = tk.StringVar()
        name_entry = ttk.Entry(add_fr, textvariable=new_field_name, width=15)
        name_entry.pack(side=tk.LEFT, padx=(0, 5))

        new_field_value = tk.StringVar()
        value_entry = ttk.Entry(add_fr, textvariable=new_field_value, width=30)
        value_entry.pack(side=tk.LEFT, padx=(0, 5))

        def add_field():
            """Add new metadata field inline."""
            field_name = new_field_name.get().strip()
            field_value = new_field_value.get().strip()
            if not field_name:
                messagebox.showwarning("Empty", "Field name cannot be empty")
                return
            item_id = meta_tree.insert("", tk.END, text=field_name, values=(field_value,))
            item_map[item_id] = field_name
            changes["added"][field_name] = field_value
            new_field_name.set("")
            new_field_value.set("")
            name_entry.focus()

        ttk.Button(add_fr, text="Add", command=add_field).pack(side=tk.LEFT)

        def delete_field():
            """Delete selected field."""
            selection = meta_tree.selection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select a field to delete")
                return
            item = selection[0]
            field_name = item_map[item]
            meta_tree.delete(item)
            del item_map[item]
            if field_name not in changes["added"]:
                changes["deleted"].add(field_name)
            else:
                del changes["added"][field_name]

        def enrich_from_pubchem():
            """Fetch PubChem data and fill empty fields."""
            enriched = self._enrich_metadata_with_pubchem(record_id)
            if not enriched:
                messagebox.showinfo("No Data", "Could not fetch PubChem data (compound might need a formula or SMILES)")
                return

            updated_count = 0
            for field_name, field_value in enriched.items():
                # Find if field exists in tree
                existing_item = None
                for item in item_map:
                    if item_map[item] == field_name:
                        existing_item = item
                        break

                current_val = None
                if existing_item:
                    current_val = meta_tree.item(existing_item, "values")[0]

                # Only fill empty fields
                if not current_val or not str(current_val).strip():
                    if existing_item:
                        meta_tree.item(existing_item, values=(str(field_value),))
                    else:
                        item_id = meta_tree.insert("", tk.END, text=field_name, values=(str(field_value),))
                        item_map[item_id] = field_name
                    changes["modified"][field_name] = str(field_value)
                    updated_count += 1

            messagebox.showinfo("Enrichment Complete",
                f"Filled {updated_count} empty field(s) with PubChem data")

        def save_changes(show_message=True):
            """Save all metadata changes to database."""
            if not changes["modified"] and not changes["added"] and not changes["deleted"]:
                return  # Nothing to save

            try:
                # UPDATE modified fields
                for field_name, value in changes["modified"].items():
                    if field_name in ("NAME", "FORMULA", "MW", "CASNO", "IUPAC_NAME", "SMILES", "InChI"):
                        # Update in compounds table
                        col_map = {
                            "NAME": "name", "FORMULA": "formula", "MW": "molecular_weight",
                            "CASNO": "cas_number", "IUPAC_NAME": "iupac_name",
                            "SMILES": "smiles", "InChI": "inchi"
                        }
                        col_name = col_map.get(field_name)
                        if col_name:
                            self._db_cursor.execute(
                                f"UPDATE compounds SET {col_name} = ? WHERE id = ?",
                                (value, record_id)
                            )
                    else:
                        # Update in metadata table
                        self._db_cursor.execute(
                            "DELETE FROM metadata WHERE compound_id = ? AND field_name = ?",
                            (record_id, field_name)
                        )
                        self._db_cursor.execute(
                            "INSERT INTO metadata (compound_id, field_name, field_value) VALUES (?, ?, ?)",
                            (record_id, field_name, value)
                        )

                # DELETE removed fields
                for field_name in changes["deleted"]:
                    if field_name not in ("NAME", "FORMULA", "MW", "CASNO", "IUPAC_NAME", "SMILES", "InChI"):
                        self._db_cursor.execute(
                            "DELETE FROM metadata WHERE compound_id = ? AND field_name = ?",
                            (record_id, field_name)
                        )

                # INSERT new fields
                for field_name, value in changes["added"].items():
                    if field_name not in ("NAME", "FORMULA", "MW", "CASNO", "IUPAC_NAME", "SMILES", "InChI"):
                        self._db_cursor.execute(
                            "INSERT INTO metadata (compound_id, field_name, field_value) VALUES (?, ?, ?)",
                            (record_id, field_name, value)
                        )

                self._db_conn.commit()
                if show_message:
                    messagebox.showinfo("Success", "Metadata updated successfully")

                # Refresh display
                self._show_record(self._current_idx, highlight_in_tree=False)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save: {e}")

        ttk.Button(btn_fr, text="- Delete Field", command=delete_field).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_fr, text="✦ Enrich with PubChem", command=enrich_from_pubchem).pack(side=tk.LEFT, padx=5)

        def on_close():
            """Auto-save and close dialog."""
            save_changes(show_message=False)
            dialog.destroy()

        ttk.Button(btn_fr, text="Save & Close", command=on_close).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_fr, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)

        # Auto-save on window close
        dialog.protocol("WM_DELETE_WINDOW", on_close)

    def _edit_mass_spectrum(self) -> None:
        """Open mass spectrum editor for current record."""
        if not self._records or self._current_idx >= len(self._records):
            messagebox.showwarning("No Record", "Please load an SDF file and select a record first.")
            return

        record_id = self._current_idx + 1

        # Get compound name for title
        try:
            compound_name = self._db_cursor.execute(
                "SELECT name FROM compounds WHERE id = ?", (record_id,)
            ).fetchone()[0]
        except (sqlite3.Error, TypeError, IndexError):
            compound_name = f"Compound {record_id}"

        print(f"[DEBUG] _edit_mass_spectrum: current_idx={self._current_idx}, record_id={record_id}, name={compound_name}")

        # Create dialog window
        dialog = tk.Toplevel(self)
        dialog.title(f"Edit Spectrum - {compound_name}")
        dialog.geometry("600x500")

        # Load peaks from database
        try:
            peaks_rows = self._db_cursor.execute(
                "SELECT mz, intensity, base_peak FROM mass_spectrum WHERE compound_id = ? ORDER BY mz",
                (record_id,)
            ).fetchall()
            print(f"[DEBUG] Retrieved {len(peaks_rows)} mass spectrum peaks")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load peaks: {e}")
            dialog.destroy()
            return

        # Create Treeview for peaks
        ttk.Label(dialog, text="m/z | Intensity | Base Peak", font=("Arial", 9, "bold")).pack(
            fill=tk.X, padx=5, pady=(5, 2))

        tree_fr = ttk.Frame(dialog)
        tree_fr.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Scrollbars
        vsb = ttk.Scrollbar(tree_fr, orient=tk.VERTICAL)
        hsb = ttk.Scrollbar(tree_fr, orient=tk.HORIZONTAL)

        peaks_tree = ttk.Treeview(tree_fr, columns=("mz", "intensity", "base"),
                                  show="tree headings", height=15,
                                  yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.config(command=peaks_tree.yview)
        hsb.config(command=peaks_tree.xview)

        peaks_tree.column("#0", width=50)
        peaks_tree.heading("#0", text="Index")
        peaks_tree.column("mz", width=150)
        peaks_tree.heading("mz", text="m/z")
        peaks_tree.column("intensity", width=150)
        peaks_tree.heading("intensity", text="Intensity")
        peaks_tree.column("base", width=100)
        peaks_tree.heading("base", text="Base Peak")

        # Populate tree with peaks
        item_map = {}  # Map tree item ID to peak index
        print(f"[DEBUG] Populating peaks tree with {len(peaks_rows)} peaks...")
        for idx, (mz, intensity, base_peak) in enumerate(peaks_rows):
            base_mark = "●" if base_peak else "○"
            item_id = peaks_tree.insert("", tk.END, text=str(idx + 1),
                                       values=(f"{mz:.4f}", f"{intensity:.2f}", base_mark))
            item_map[item_id] = {"idx": idx, "mz": mz, "intensity": intensity, "base": base_peak}
            print(f"[DEBUG]   Inserted peak {idx+1}: m/z={mz:.4f}, intensity={intensity:.2f}")
        print(f"[DEBUG] Peaks tree population complete")

        peaks_tree.grid(row=0, column=0, sticky=tk.NSEW)
        vsb.grid(row=0, column=1, sticky=tk.NS)
        hsb.grid(row=1, column=0, sticky=tk.EW)
        tree_fr.columnconfigure(0, weight=1)
        tree_fr.rowconfigure(0, weight=1)

        # Track changes
        changes = {"modified": {}, "added": [], "deleted": set()}
        sort_state = {"column": "mz", "reverse": False}

        def on_double_click(event):
            """Edit cell on double-click - inline entry."""
            try:
                if not peaks_tree.selection():
                    return
                item = peaks_tree.selection()[0]
                col = peaks_tree.identify_column(event.x)

                if col in ("#1", "#2"):  # m/z or intensity columns
                    peak_info = item_map[item]
                    col_idx = int(col[1:]) - 1
                    col_names = ["mz", "intensity"]
                    col_name = col_names[col_idx]
                    current_value = peaks_tree.item(item, "values")[col_idx]

                    # Get cell bounding box for positioning
                    bbox = peaks_tree.bbox(item, col)
                    if not bbox:
                        return

                    entry = tk.Entry(tree_fr, width=15)
                    entry.insert(0, str(current_value))

                    # Position entry over the cell
                    entry.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])

                    def save_on_focusout(e=None):
                        try:
                            new_val = float(entry.get())
                            if col_name == "mz" and new_val <= 0:
                                messagebox.showerror("Invalid", "m/z must be > 0")
                                return
                            elif col_name == "intensity" and new_val < 0:
                                messagebox.showerror("Invalid", "Intensity cannot be negative")
                                return

                            if col_name == "mz":
                                peak_info["mz"] = new_val
                            else:
                                peak_info["intensity"] = new_val
                            peaks_tree.item(item, values=(f"{peak_info['mz']:.4f}",
                                                         f"{peak_info['intensity']:.2f}",
                                                         "●" if peak_info["base"] else "○"))
                            changes["modified"][item] = peak_info
                        except ValueError:
                            messagebox.showerror("Invalid", "Please enter a valid number")
                        finally:
                            entry.destroy()

                    def save_on_return(e):
                        save_on_focusout()

                    def on_escape(e):
                        entry.destroy()

                    entry.bind("<Return>", save_on_return)
                    entry.bind("<FocusOut>", save_on_focusout)
                    entry.bind("<Escape>", on_escape)
                    entry.focus()
                    entry.select_range(0, tk.END)

                elif col == "#3":  # Base peak column - toggle
                    peak_info = item_map[item]
                    peak_info["base"] = not peak_info["base"]
                    base_mark = "●" if peak_info["base"] else "○"
                    peaks_tree.item(item, values=(f"{peak_info['mz']:.4f}",
                                                 f"{peak_info['intensity']:.2f}", base_mark))
                    changes["modified"][item] = peak_info

            except Exception as e:
                print(f"[DEBUG] Error in on_double_click: {e}")

        peaks_tree.bind("<Double-1>", on_double_click)

        # Sorting
        def sort_by_column(col):
            """Sort tree by column."""
            reverse = sort_state["column"] == col and not sort_state["reverse"]
            sort_state["column"] = col
            sort_state["reverse"] = reverse

            # Get all items with their data
            items = []
            for item_id in peaks_tree.get_children():
                peak_info = item_map[item_id]
                if col == "mz":
                    sort_key = peak_info["mz"]
                else:  # intensity
                    sort_key = peak_info["intensity"]
                items.append((sort_key, item_id, peak_info))

            # Sort and rebuild tree
            items.sort(key=lambda x: x[0], reverse=reverse)
            for idx, (_, item_id, _) in enumerate(items):
                peaks_tree.move(item_id, "", idx)

        peaks_tree.heading("mz", command=lambda: sort_by_column("mz"))
        peaks_tree.heading("intensity", command=lambda: sort_by_column("intensity"))

        # Add peak inline frame
        add_fr = ttk.Frame(dialog)
        add_fr.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(add_fr, text="Add Peak:", font=("Arial", 9)).pack(side=tk.LEFT, padx=(0, 5))

        new_mz = tk.StringVar()
        mz_entry = ttk.Entry(add_fr, textvariable=new_mz, width=12)
        mz_entry.pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(add_fr, text="m/z").pack(side=tk.LEFT, padx=(0, 10))

        new_intensity = tk.StringVar()
        int_entry = ttk.Entry(add_fr, textvariable=new_intensity, width=12)
        int_entry.pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(add_fr, text="Intensity").pack(side=tk.LEFT, padx=(0, 10))

        base_peak_var = tk.BooleanVar()
        base_check = ttk.Checkbutton(add_fr, text="Base Peak", variable=base_peak_var)
        base_check.pack(side=tk.LEFT, padx=(0, 10))

        def add_peak():
            """Add new peak inline."""
            try:
                mz = float(new_mz.get().strip())
                intensity = float(new_intensity.get().strip())
                if mz <= 0:
                    messagebox.showerror("Invalid", "m/z must be > 0")
                    return
                if intensity < 0:
                    messagebox.showerror("Invalid", "Intensity cannot be negative")
                    return

                next_idx = len(peaks_tree.get_children())
                item_id = peaks_tree.insert("", tk.END, text=str(next_idx + 1),
                                           values=(f"{mz:.4f}", f"{intensity:.2f}",
                                                  "●" if base_peak_var.get() else "○"))
                item_map[item_id] = {"idx": next_idx, "mz": mz, "intensity": intensity,
                                    "base": base_peak_var.get()}
                changes["added"].append(item_id)
                new_mz.set("")
                new_intensity.set("")
                base_peak_var.set(False)
                mz_entry.focus()
            except ValueError:
                messagebox.showerror("Invalid", "Please enter valid numbers")

        ttk.Button(add_fr, text="Add", command=add_peak).pack(side=tk.LEFT)

        # Buttons
        btn_fr = ttk.Frame(dialog)
        btn_fr.pack(fill=tk.X, padx=5, pady=5)

        def delete_peak():
            """Delete selected peak."""
            selection = peaks_tree.selection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select a peak to delete")
                return
            item = selection[0]
            peaks_tree.delete(item)
            peak_idx = item_map[item]["idx"]
            changes["deleted"].add(peak_idx)
            del item_map[item]

        def save_changes(show_message=True):
            """Save all changes to database."""
            try:
                # Clear existing peaks for this compound
                self._db_cursor.execute("DELETE FROM mass_spectrum WHERE compound_id = ?", (record_id,))

                # Insert all current peaks
                for item_id in peaks_tree.get_children():
                    peak_info = item_map[item_id]
                    self._db_cursor.execute(
                        "INSERT INTO mass_spectrum (compound_id, mz, intensity, base_peak) "
                        "VALUES (?, ?, ?, ?)",
                        (record_id, peak_info["mz"], peak_info["intensity"],
                         1 if peak_info["base"] else 0)
                    )

                self._db_conn.commit()
                if show_message:
                    messagebox.showinfo("Success", "Mass spectrum updated successfully")

                # Refresh display - replot the mass spectrum
                self._show_record(self._current_idx, highlight_in_tree=False)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save: {e}")

        ttk.Button(btn_fr, text="- Delete Peak", command=delete_peak).pack(side=tk.LEFT, padx=5)

        def on_close():
            """Auto-save and close dialog."""
            save_changes(show_message=False)
            dialog.destroy()

        ttk.Button(btn_fr, text="Save & Close", command=on_close).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_fr, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)

        # Auto-save on window close
        dialog.protocol("WM_DELETE_WINDOW", on_close)

    def _export_structure_image(self) -> None:
        """Export structure image(s) to PNG files."""
        if not self._records:
            messagebox.showwarning("No Data", "No SDF file loaded.")
            return

        if not _HAS_RDKIT:
            messagebox.showerror("Error", "RDKit is required for image export.")
            return

        # Dialog: current or all?
        dialog = tk.Toplevel(self)
        dialog.title("Export Structure Images")
        dialog.geometry("300x150")
        dialog.resizable(False, False)

        scope = tk.StringVar(value="current")
        ttk.Radiobutton(dialog, text="Current record only", variable=scope, value="current").pack(
            pady=5, padx=10, anchor=tk.W)
        ttk.Radiobutton(dialog, text="All records", variable=scope, value="all").pack(
            pady=5, padx=10, anchor=tk.W)
        ttk.Radiobutton(dialog, text="Filtered results", variable=scope, value="filtered").pack(
            pady=5, padx=10, anchor=tk.W)

        def export():
            save_dir = filedialog.askdirectory(title="Select directory for images")
            if not save_dir:
                return

            try:
                from rdkit.Chem import Draw
                from PIL import Image
                count = 0

                if scope.get() == "current":
                    # Export current record
                    mol = self._records[self._current_idx].get("mol")
                    if mol:
                        record_id = self._current_idx + 1
                        compound_name = self._db_cursor.execute(
                            "SELECT name FROM compounds WHERE id = ?", (record_id,)
                        ).fetchone()[0]
                        filename = f"{save_dir}/compound_{record_id:04d}_{compound_name[:30]}.png"
                        img = Draw.MolToImage(mol, size=(800, 600))
                        img.save(filename)
                        count = 1

                else:
                    # Export all or filtered
                    if scope.get() == "filtered" and self._current_query_results:
                        results = self._current_query_results
                    else:
                        results = self._db_cursor.execute(
                            "SELECT id, name FROM compounds ORDER BY id"
                        ).fetchall()

                    for display_idx, (record_id, name) in enumerate(results):
                        mol = self._records[record_id - 1].get("mol")
                        if mol:
                            filename = f"{save_dir}/compound_{record_id:04d}_{name[:30]}.png"
                            img = Draw.MolToImage(mol, size=(800, 600))
                            img.save(filename)
                            count += 1

                messagebox.showinfo("Success", f"Exported {count} structure image(s)")
                dialog.destroy()

            except Exception as e:
                messagebox.showerror("Error", f"Export failed: {e}")

        btn_fr = ttk.Frame(dialog)
        btn_fr.pack(pady=10)
        ttk.Button(btn_fr, text="Export", command=export).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_fr, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

    def _export_csv(self) -> None:
        """Export compound data to CSV file."""
        if not self._records:
            messagebox.showwarning("No Data", "No SDF file loaded.")
            return

        # Dialog: current or all or filtered?
        dialog = tk.Toplevel(self)
        dialog.title("Export to CSV")
        dialog.geometry("300x150")
        dialog.resizable(False, False)

        scope = tk.StringVar(value="all")
        ttk.Radiobutton(dialog, text="Current record only", variable=scope, value="current").pack(
            pady=5, padx=10, anchor=tk.W)
        ttk.Radiobutton(dialog, text="All records", variable=scope, value="all").pack(
            pady=5, padx=10, anchor=tk.W)
        ttk.Radiobutton(dialog, text="Filtered results", variable=scope, value="filtered").pack(
            pady=5, padx=10, anchor=tk.W)

        def export():
            save_path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
            )
            if not save_path:
                return

            try:
                # Determine which records to export
                if scope.get() == "current":
                    record_ids = [self._current_idx + 1]
                elif scope.get() == "filtered" and self._current_query_results:
                    record_ids = [r[0] for r in self._current_query_results]
                else:
                    record_ids = [r[0] for r in self._db_cursor.execute(
                        "SELECT id FROM compounds ORDER BY id"
                    ).fetchall()]

                # Get all field names
                all_fields = {"id", "name", "formula", "molecular_weight", "cas_number", "iupac_name", "smiles", "inchi"}
                for row in self._db_cursor.execute(
                    "SELECT DISTINCT field_name FROM metadata"
                ).fetchall():
                    all_fields.add(row[0])

                field_list = sorted(list(all_fields))

                # Write CSV
                with open(save_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=field_list)
                    writer.writeheader()

                    for record_id in record_ids:
                        row = {"id": record_id}
                        # Get compound fields
                        compound = self._db_cursor.execute(
                            "SELECT name, formula, molecular_weight, cas_number, iupac_name, smiles, inchi "
                            "FROM compounds WHERE id = ?", (record_id,)
                        ).fetchone()
                        if compound:
                            row.update({
                                "name": compound[0],
                                "formula": compound[1],
                                "molecular_weight": compound[2],
                                "cas_number": compound[3],
                                "iupac_name": compound[4],
                                "smiles": compound[5],
                                "inchi": compound[6],
                            })

                        # Get metadata fields
                        metadata = self._db_cursor.execute(
                            "SELECT field_name, field_value FROM metadata WHERE compound_id = ?",
                            (record_id,)
                        ).fetchall()
                        for field_name, field_value in metadata:
                            row[field_name] = field_value

                        writer.writerow(row)

                messagebox.showinfo("Success", f"Exported {len(record_ids)} record(s) to CSV")
                dialog.destroy()

            except Exception as e:
                messagebox.showerror("Error", f"Export failed: {e}")

        btn_fr = ttk.Frame(dialog)
        btn_fr.pack(pady=10)
        ttk.Button(btn_fr, text="Export", command=export).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_fr, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

    def _print_record(self) -> None:
        """Print record(s) to HTML and open in browser."""
        if not self._records:
            messagebox.showwarning("No Data", "No SDF file loaded.")
            return

        # Dialog: current or all?
        dialog = tk.Toplevel(self)
        dialog.title("Print Records")
        dialog.geometry("300x120")
        dialog.resizable(False, False)

        scope = tk.StringVar(value="current")
        ttk.Radiobutton(dialog, text="Current record only", variable=scope, value="current").pack(
            pady=5, padx=10, anchor=tk.W)
        ttk.Radiobutton(dialog, text="All records", variable=scope, value="all").pack(
            pady=5, padx=10, anchor=tk.W)

        def print_records():
            try:
                import webbrowser
                import base64
                from io import BytesIO
                import tempfile

                # Determine which records to print
                if scope.get() == "current":
                    record_ids = [self._current_idx + 1]
                else:
                    record_ids = [r[0] for r in self._db_cursor.execute(
                        "SELECT id FROM compounds ORDER BY id"
                    ).fetchall()]

                html = "<html><head><style>"
                html += "body { font-family: Arial, sans-serif; margin: 20px; }"
                html += "h2 { color: #333; border-bottom: 2px solid #0066cc; padding-bottom: 5px; }"
                html += "table { border-collapse: collapse; width: 100%; margin: 10px 0; }"
                html += "th, td { border: 1px solid #ccc; padding: 8px; text-align: left; }"
                html += "th { background-color: #f0f0f0; }"
                html += ".structure { width: 300px; border: 1px solid #ddd; }"
                html += ".page-break { page-break-after: always; margin: 20px 0; border-top: 2px dashed #ccc; }"
                html += "</style></head><body>"

                for idx, record_id in enumerate(record_ids):
                    if idx > 0:
                        html += "<div class='page-break'></div>"

                    # Get compound data
                    compound = self._db_cursor.execute(
                        "SELECT name, formula, molecular_weight FROM compounds WHERE id = ?",
                        (record_id,)
                    ).fetchone()

                    if compound:
                        html += f"<h2>{compound[0]}</h2>"
                        html += "<table><tr><td>Formula:</td><td>{}</td></tr>".format(compound[1] or "—")
                        html += "<tr><td>MW:</td><td>{}</td></tr></table>".format(compound[2] or "—")

                    # Add structure image if available
                    mol = self._records[record_id - 1].get("mol")
                    if mol and _HAS_RDKIT:
                        try:
                            from rdkit.Chem import Draw
                            img = Draw.MolToImage(mol, size=(300, 300))
                            buffered = BytesIO()
                            img.save(buffered, format="PNG")
                            img_str = base64.b64encode(buffered.getvalue()).decode()
                            html += f"<img class='structure' src='data:image/png;base64,{img_str}'/>"
                        except Exception:
                            pass

                    # Add metadata table
                    metadata = self._db_cursor.execute(
                        "SELECT field_name, field_value FROM metadata WHERE compound_id = ? ORDER BY field_name",
                        (record_id,)
                    ).fetchall()

                    if metadata:
                        html += "<table><tr><th>Field</th><th>Value</th></tr>"
                        for field_name, field_value in metadata:
                            html += f"<tr><td>{field_name}</td><td>{field_value}</td></tr>"
                        html += "</table>"

                html += "</body></html>"

                # Save to temp file and open
                with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as f:
                    f.write(html)
                    temp_path = f.name

                webbrowser.open(f"file://{temp_path}")
                messagebox.showinfo("Success", "Opened in browser for printing")
                dialog.destroy()

            except Exception as e:
                messagebox.showerror("Error", f"Print failed: {e}")

        btn_fr = ttk.Frame(dialog)
        btn_fr.pack(pady=10)
        ttk.Button(btn_fr, text="Print", command=print_records).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_fr, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

    def _prev_record(self) -> None:
        if self._records and self._current_idx > 0:
            self._show_record(self._current_idx - 1)
            self._update_nav_label()

    def _next_record(self) -> None:
        if self._records and self._current_idx < len(self._records) - 1:
            self._show_record(self._current_idx + 1)
            self._update_nav_label()

    def _update_nav_label(self) -> None:
        print("[DEBUG] _update_nav_label called")
        if not self._nav_label:
            print("[ERROR] _nav_label is None!")
            return

        print("[DEBUG] _nav_label exists, updating...")
        try:
            if self._records:
                label_text = f"  |  Record {self._current_idx + 1} / {len(self._records)}"
                print(f"[DEBUG] Setting nav label to: {label_text}")
                self._nav_label.config(text=label_text)
                print("[DEBUG] Nav label updated successfully")
            else:
                print("[DEBUG] No records, clearing nav label")
                self._nav_label.config(text="")
        except Exception as e:
            print(f"[ERROR] Exception in _update_nav_label: {e}")
            import traceback
            traceback.print_exc()


# ===========================================================================
# Tab 5 — Packages
# ===========================================================================

_PKGS: list[tuple] = [
    # (import_name, pip_name, required_for, notes)
    ("sdf_enricher", "sdf-enricher",
     "SDF Enricher tab",
     "Fills missing metadata from PubChem, ChEBI, KEGG, HMDB"),
    ("rdkit",        "rdkit",
     "SDF Viewer tab (structure visualization)",
     "Chemical structure rendering; highly recommended"),
    ("PIL",          "Pillow",
     "SDF Viewer tab (image display)",
     "Required for displaying 2D structure images"),
    ("matplotlib",   "matplotlib",
     "SDF Viewer mass spectra & workflow diagrams",
     "Visualize mass spectral peaks and generate workflow images"),
    ("splashpy",     "splashpy",
     "SPLASH hash calculation",
     "Spectral hash for SDF records; optional"),
    ("pytest",       "pytest",
     "Running the test suite  (dev only)",
     "pip install \"ei-fragment-calculator[dev]\""),
]


class _PackagesTab(ttk.Frame):

    def __init__(self, master: tk.Widget):
        super().__init__(master, padding=10)
        self._build()
        self._refresh()

    def _build(self) -> None:
        ttk.Label(
            self,
            text=(
                "Optional packages extend functionality. "
                "Click Install to add missing packages using pip."
            ),
            foreground="#666666",
        ).pack(anchor=tk.W, pady=(0, 6))

        tv_fr = ttk.Frame(self)
        tv_fr.pack(fill=tk.X, pady=(0, 6))

        cols = ("Package", "Pip name", "Required for", "Status")
        self._tree = ttk.Treeview(tv_fr, columns=cols, show="headings",
                                  height=len(_PKGS) + 1, selectmode="browse")
        for col, w in zip(cols, (120, 130, 250, 90)):
            self._tree.heading(col, text=col)
            self._tree.column(col, width=w, stretch=(col == "Required for"))
        self._tree.pack(fill=tk.X)

        self._tree.tag_configure("ok",      foreground="#007000")
        self._tree.tag_configure("missing", foreground="#cc0000")

        btn_fr = ttk.Frame(self)
        btn_fr.pack(fill=tk.X, pady=(0, 6))
        ttk.Button(btn_fr, text="\u21ba  Refresh",
                   command=self._refresh).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_fr, text="Install selected",
                   command=self._install_selected).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_fr, text="Install ALL missing",
                   style="Accent.TButton",
                   command=self._install_all_missing).pack(side=tk.LEFT)

        log_fr = ttk.LabelFrame(self, text=" pip Output ", padding=4)
        log_fr.pack(fill=tk.BOTH, expand=True)
        self._log = _make_log(log_fr)
        self._log.pack(fill=tk.BOTH, expand=True)

    def _refresh(self) -> None:
        self._tree.delete(*self._tree.get_children())
        for imp, pip_name, purpose, _ in _PKGS:
            installed = importlib.util.find_spec(imp) is not None
            status    = "\u2713 installed" if installed else "\u2717 missing"
            tag       = "ok" if installed else "missing"
            self._tree.insert("", tk.END, iid=imp,
                              values=(imp, pip_name, purpose, status), tags=(tag,))

    def _install_selected(self) -> None:
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("No selection", "Select a package row first.")
            return
        imp = sel[0]
        pkg = next((p for i, p, *_ in _PKGS if i == imp), None)
        if pkg:
            self._install([pkg])

    def _install_all_missing(self) -> None:
        missing = [pip for imp, pip, *_ in _PKGS
                   if importlib.util.find_spec(imp) is None]
        if not missing:
            messagebox.showinfo("All installed", "All optional packages are already installed.")
            return
        self._install(missing)

    def _install(self, packages: list[str]) -> None:
        _clear_log(self._log)
        rd = _Redirector(self._log, self.winfo_toplevel())
        threading.Thread(target=self._pip_worker, args=(packages, rd),
                         daemon=True).start()

    def _pip_worker(self, packages: list[str], rd: _Redirector) -> None:
        old_o, old_e = sys.stdout, sys.stderr
        sys.stdout = rd; sys.stderr = rd
        for pkg in packages:
            print("Installing {}\u2026".format(pkg))
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", pkg],
                    capture_output=True, text=True, timeout=120,
                )
                print(result.stdout or "")
                if result.returncode != 0:
                    print("pip stderr:\n" + result.stderr)
                else:
                    print("\u2713 {} installed successfully.\n".format(pkg))
            except Exception as exc:
                print("ERROR: {}\n".format(exc))
        sys.stdout = old_o; sys.stderr = old_e
        self.winfo_toplevel().after(0, self._refresh)
        self.winfo_toplevel().after(0, rd._append,
                                   "\nDone. You may need to restart the application.\n")


# ===========================================================================
# Tiny widget helpers
# ===========================================================================

def _spin(parent: tk.Widget, var: tk.StringVar,
          from_: float, to: float, increment: float) -> ttk.Spinbox:
    sb = ttk.Spinbox(parent, textvariable=var, width=8,
                     from_=from_, to=to, increment=increment,
                     format="%.4g")
    return sb


class _ToolTip:
    """Simple hover tooltip."""
    def __init__(self, widget: tk.Widget, text: str):
        self._w  = widget
        self._t  = text
        self._tw = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, event=None):
        x = self._w.winfo_rootx() + 20
        y = self._w.winfo_rooty() + self._w.winfo_height() + 4
        self._tw = tw = tk.Toplevel(self._w)
        tw.wm_overrideredirect(True)
        tw.wm_geometry("+{}+{}".format(x, y))
        tk.Label(tw, text=self._t, justify=tk.LEFT,
                 background="#ffffc0", foreground="#000000",
                 relief=tk.SOLID, borderwidth=1,
                 font=("Segoe UI", 8)).pack(ipadx=4, ipady=2)

    def _hide(self, event=None):
        if self._tw:
            self._tw.destroy()
            self._tw = None


def _tooltip(widget: tk.Widget, text: str) -> None:
    _ToolTip(widget, text)


def _tooltip_label(parent: tk.Widget, text: str) -> None:
    lbl = ttk.Label(parent, text="\u24d8", foreground="#666666", cursor="question_arrow")
    lbl.pack(side=tk.LEFT, padx=(2, 12))
    _ToolTip(lbl, text)


# ===========================================================================
# Startup package check
# ===========================================================================

def _startup_check(root: tk.Tk, notebook: ttk.Notebook,
                   banner_var: tk.StringVar) -> None:
    """Run in background; show a banner if any optional package is missing."""
    missing = [pip for imp, pip, *_ in _PKGS
               if importlib.util.find_spec(imp) is None]
    if missing:
        msg = ("Optional package(s) not installed: {}  — "
               "see the  Packages  tab to install.").format(", ".join(missing))
        root.after(0, banner_var.set, msg)


# ===========================================================================
# Undo/Redo Stack
# ===========================================================================

class _UndoRedoStack:
    """Stack-based undo/redo system for metadata changes."""

    def __init__(self, max_size: int = 50):
        self.max_size = max_size
        self.undo_stack = []
        self.redo_stack = []

    def push(self, compound_id: int, field_name: str, old_value: str, new_value: str) -> None:
        """Record a metadata change."""
        action = {
            "compound_id": compound_id,
            "field_name": field_name,
            "old_value": old_value,
            "new_value": new_value
        }
        self.undo_stack.append(action)
        # Trim if exceeds max size
        if len(self.undo_stack) > self.max_size:
            self.undo_stack.pop(0)
        # Clear redo stack on new action
        self.redo_stack.clear()

    def undo(self):
        """Pop from undo stack, push to redo stack."""
        if self.undo_stack:
            action = self.undo_stack.pop()
            self.redo_stack.append(action)
            return action
        return None

    def redo(self):
        """Pop from redo stack, push to undo stack."""
        if self.redo_stack:
            action = self.redo_stack.pop()
            self.undo_stack.append(action)
            return action
        return None

    def can_undo(self) -> bool:
        return len(self.undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self.redo_stack) > 0


# ===========================================================================
# Keyboard Manager
# ===========================================================================

class _KeyboardManager:
    """Centralized keyboard binding handler."""

    def __init__(self, root: tk.Widget, callback_fn):
        """Initialize keyboard manager with root window and callback."""
        self.root = root
        self.callback = callback_fn
        self.bindings = {
            "<Control-l>": "load_file",
            "<Control-e>": "open_enrichment",
            "<Control-t>": "open_element_table",
            "<Control-s>": "save_file",
            "<Control-o>": "open_database",
            "<Control-n>": "new_database",
            "<Control-q>": "quit",
            "<Control-h>": "show_help",
            "<Control-z>": "undo",
            "<Control-y>": "redo",
        }

    def setup_bindings(self) -> None:
        """Register all keyboard bindings."""
        for key, command in self.bindings.items():
            self.root.bind(key, lambda e, cmd=command: self.callback(cmd))


# ===========================================================================
# Status Bar Widget
# ===========================================================================

class _StatusBar(ttk.Frame):
    """Status bar showing database and operation state."""

    def __init__(self, parent):
        super().__init__(parent, relief=tk.SUNKEN, height=25)
        self.pack_propagate(False)

        # Database label
        self._db_label = ttk.Label(self, text="Database: [None]", relief=tk.FLAT)
        self._db_label.pack(side=tk.LEFT, padx=5)

        # Separator
        ttk.Separator(self, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=2)

        # Compound count label
        self._count_label = ttk.Label(self, text="Compounds: 0")
        self._count_label.pack(side=tk.LEFT, padx=5)

        # Separator
        ttk.Separator(self, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=2)

        # Last action label
        self._action_label = ttk.Label(self, text="Ready")
        self._action_label.pack(side=tk.LEFT, padx=5)

        # Separator
        ttk.Separator(self, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=2)

        # Timestamp label
        self._time_label = ttk.Label(self, text="", foreground="#666666")
        self._time_label.pack(side=tk.LEFT, padx=5)

    def set_database(self, db_path: str) -> None:
        """Update database display."""
        if not db_path or db_path == ":memory:":
            self._db_label.config(text="Database: [In-Memory]")
        else:
            from pathlib import Path
            name = Path(db_path).name
            self._db_label.config(text=f"Database: {name}")

    def set_compound_count(self, count: int) -> None:
        """Update compound count display."""
        self._count_label.config(text=f"Compounds: {count}")

    def set_last_action(self, action: str) -> None:
        """Update last action with timestamp."""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._action_label.config(text=action)
        self._time_label.config(text=timestamp)


# ===========================================================================
# Database Manager
# ===========================================================================

class _DatabaseManager:
    """Manage database backup and restore operations."""

    def __init__(self):
        from pathlib import Path
        self.backup_dir = Path.home() / ".ei_fragment_calculator_backups"
        self.backup_dir.mkdir(exist_ok=True)

    def backup(self, db_path: str, custom_dir: str = None) -> str:
        """Create timestamped backup of database."""
        from pathlib import Path
        from datetime import datetime
        import shutil

        source = Path(db_path)
        if not source.exists():
            raise FileNotFoundError(f"Database not found: {db_path}")

        backup_dir = Path(custom_dir) if custom_dir else self.backup_dir
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{source.stem}_backup_{timestamp}.db"
        backup_path = backup_dir / backup_name

        shutil.copy2(source, backup_path)
        return str(backup_path)

    def restore(self, backup_path: str, target_db_path: str) -> None:
        """Restore database from backup."""
        from pathlib import Path
        from datetime import datetime
        import shutil

        backup = Path(backup_path)
        target = Path(target_db_path)

        if not backup.exists():
            raise FileNotFoundError(f"Backup not found: {backup_path}")

        # Create safety backup of current database
        if target.exists():
            safety_backup = target.parent / f"{target.stem}_before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            shutil.copy2(target, safety_backup)

        # Restore from backup
        shutil.copy2(backup, target)

    def list_backups(self, db_name: str):
        """List available backups for a database."""
        backups = list(self.backup_dir.glob(f"{db_name}_backup_*.db"))
        return sorted([str(b) for b in backups], reverse=True)

    def cleanup_old_backups(self, max_count: int = 10):
        """Keep only most recent N backups."""
        all_backups = sorted(
            self.backup_dir.glob("*_backup_*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        for backup in all_backups[max_count:]:
            backup.unlink()


# ===========================================================================
# Batch Import Dialog
# ===========================================================================

class _BatchImportDialog(tk.Toplevel):
    """Modal dialog for batch importing multiple files."""

    def __init__(self, parent, callback_fn):
        super().__init__(parent)
        self.title("Batch Import Files")
        self.geometry("500x400")
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self.callback = callback_fn
        self.files = []
        self.result = None

        # File list frame
        list_frame = ttk.LabelFrame(self, text="Files to Import", padding=5)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Listbox with scrollbar
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.file_list = tk.Listbox(list_frame, yscrollcommand=scrollbar.set)
        self.file_list.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.file_list.yview)

        # Buttons frame
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(btn_frame, text="Add Files", command=self._add_files).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Remove Selected", command=self._remove_selected).pack(side=tk.LEFT, padx=2)

        # Options frame
        opt_frame = ttk.LabelFrame(self, text="Import Mode", padding=5)
        opt_frame.pack(fill=tk.X, padx=5, pady=5)

        self.merge_var = tk.BooleanVar(value=True)
        ttk.Radiobutton(opt_frame, text="Merge with existing compounds", variable=self.merge_var, value=True).pack(anchor=tk.W)
        ttk.Radiobutton(opt_frame, text="Replace all compounds", variable=self.merge_var, value=False).pack(anchor=tk.W)

        # Progress frame
        prog_frame = ttk.Frame(self)
        prog_frame.pack(fill=tk.X, padx=5, pady=5)

        self.progress = ttk.Progressbar(prog_frame, mode='determinate')
        self.progress.pack(fill=tk.X)

        self.status_label = ttk.Label(prog_frame, text="")
        self.status_label.pack(anchor=tk.W)

        # Action buttons
        action_frame = ttk.Frame(self)
        action_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(action_frame, text="Import", command=self._import_files).pack(side=tk.LEFT, padx=2)
        ttk.Button(action_frame, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=2)

    def _add_files(self):
        """Add files to import list."""
        files = filedialog.askopenfilenames(
            title="Select Files to Import",
            filetypes=[
                ("All Supported", ("*.sdf", "*.mspec", "*.msp", "*.csv")),
                ("SDF Files", "*.sdf"),
                ("MSPEC Files", ("*.mspec", "*.msp")),
                ("CSV Files", "*.csv"),
                ("All Files", "*.*"),
            ]
        )
        for f in files:
            if f not in self.files:
                self.files.append(f)
                from pathlib import Path
                self.file_list.insert(tk.END, Path(f).name)

    def _remove_selected(self):
        """Remove selected files from list."""
        selection = self.file_list.curselection()
        for idx in reversed(selection):
            self.file_list.delete(idx)
            if idx < len(self.files):
                self.files.pop(idx)

    def _import_files(self):
        """Start batch import in background thread."""
        if not self.files:
            messagebox.showwarning("No Files", "Please select files to import")
            return

        # Clear if replacing
        if not self.merge_var.get():
            self.callback("clear_database")

        # Run import in thread
        self.progress.config(maximum=len(self.files))
        self._import_worker_thread()

    def _import_worker_thread(self):
        """Background import worker."""
        for i, filepath in enumerate(self.files):
            try:
                self.callback("load_batch_file", filepath)
                self.progress['value'] = i + 1
                self.status_label.config(text=f"Imported {i+1}/{len(self.files)}")
                self.update_idletasks()
            except Exception as e:
                self.status_label.config(text=f"Error: {str(e)}")
                return

        messagebox.showinfo("Complete", f"Successfully imported {len(self.files)} file(s)")
        self.destroy()


# ===========================================================================
# Toolbar Widget
# ===========================================================================

class _ToolBar(ttk.Frame):
    """Horizontal compact toolbar with organized command groups."""

    def __init__(self, master, callback_fn=None):
        super().__init__(master)
        self.callback = callback_fn

        # Configure background
        style = ttk.Style()
        style.configure('Toolbar.TFrame', background='#f0f0f0')
        self.config(style='Toolbar.TFrame')

        # Main toolbar frame
        main_frame = ttk.Frame(self, style='Toolbar.TFrame')
        main_frame.pack(fill=tk.X, padx=2, pady=4)

        # File Operations Group
        self._add_button_group(main_frame, "File", [
            ("Browse", "browse_file", "Browse file (Ctrl+B)"),
            ("Load", "load_file", "Load SDF/MSPEC file (Ctrl+L)"),
            ("Save", "save_file", "Save compounds (Ctrl+S)"),
            ("Clear", "clear_compounds", "Clear all compounds"),
            ("Recent", "show_recent_files", "Show recent files"),
            ("Batch", "batch_import", "Batch import multiple files"),
        ])

        # Separator
        ttk.Separator(main_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)

        # Import/Data Group
        self._add_button_group(main_frame, "Import", [
            ("CSV", "import_csv", "Import compounds from CSV"),
            ("RI/RT", "import_ri_rt", "Import retention indices/times"),
            ("SIM", "import_sim", "Import selected ion monitoring"),
            ("MRM", "import_mrm", "Import multiple reaction monitoring"),
        ])

        # Separator
        ttk.Separator(main_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)

        # Enrichment Group
        self._add_button_group(main_frame, "Enrich", [
            ("Enrichment", "open_enrichment", "Open enrichment controls (Ctrl+E)"),
        ])

        # Separator
        ttk.Separator(main_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)

        # View/Display Group
        self._add_button_group(main_frame, "View", [
            ("Full", "layout_full", "Show all panels"),
            ("Spectrum", "layout_spectrum", "Spectrum view only"),
            ("Metadata", "toggle_metadata", "Toggle metadata panel"),
            ("Refresh", "refresh_view", "Refresh display"),
        ])

        # Separator
        ttk.Separator(main_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=4)

        # Database Group
        self._add_button_group(main_frame, "Database", [
            ("New", "new_database", "Create new database (Ctrl+N)"),
            ("Open", "open_database", "Open existing database (Ctrl+O)"),
            ("In-Memory", "in_memory_db", "Use in-memory database"),
            ("Close", "close_database", "Close database"),
            ("Backup", "backup_database", "Backup current database"),
            ("Restore", "restore_database", "Restore from backup"),
        ])

        # Spacer (stretch remaining space)
        ttk.Frame(main_frame).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Help/Settings (right-aligned)
        self._add_button_group(main_frame, "Settings", [
            ("Preferences", "preferences", "Application preferences"),
        ])

    def _add_button_group(self, parent, label, buttons):
        """Add a group of buttons with optional label and tooltips."""
        group = ttk.Frame(parent)
        group.pack(side=tk.LEFT, padx=2)

        # Group label
        if label:
            lbl = ttk.Label(group, text=label + ":", font=("Segoe UI", 8, "bold"))
            lbl.pack(side=tk.LEFT, padx=(0, 4))

        # Buttons
        for item in buttons:
            if len(item) == 3:
                btn_label, command, tooltip = item
            else:
                btn_label, command = item
                tooltip = None

            btn = ttk.Button(
                group,
                text=btn_label,
                width=8,
                command=lambda cmd=command: self.callback(cmd)
            )
            btn.pack(side=tk.LEFT, padx=1)

            # Add tooltip if provided
            if tooltip:
                _tooltip(btn, tooltip)


# ===========================================================================
# Main application window
# ===========================================================================

def _get_version() -> str:
    try:
        from . import __version__
        return __version__
    except Exception:
        return ""


class EIFragmentApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("EI Fragment Exact-Mass Calculator  v{}".format(_get_version()))
        self.minsize(860, 700)
        self.geometry("1000x800")
        _apply_style()

        self._settings = _Settings()
        self._db_manager = _DatabaseManager()
        self._build()

        # Startup check in background
        banner_var = self._banner_var
        threading.Thread(
            target=_startup_check,
            args=(self, self._nb, banner_var),
            daemon=True,
        ).start()

        # Setup cleanup on window close
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _on_closing(self) -> None:
        """Cleanup resources and close application."""
        try:
            # Close database connection in SDF viewer tab
            if hasattr(self, '_viewer_tab') and self._viewer_tab._db_conn:
                try:
                    self._viewer_tab._db_conn.close()
                except (sqlite3.Error, AttributeError):
                    pass
            # Close matplotlib figures in calc tab
            if hasattr(self, '_calc_tab'):
                self._calc_tab._cleanup_spectrum()
        except Exception:
            pass
        finally:
            self.destroy()

    def _build(self) -> None:
        # ── Menu Bar ──────────────────────────────────────────────────────
        self._menu_bar = tk.Menu(self)
        self.config(menu=self._menu_bar)
        self._adv_menu = tk.Menu(self._menu_bar, tearoff=False)
        self._menu_bar.add_cascade(label="Advanced Settings", menu=self._adv_menu)
        self._adv_menu_visible = False

        # ── Toolbar ───────────────────────────────────────────────────────
        self._ribbon = _ToolBar(self, callback_fn=self._on_ribbon_command)
        self._ribbon.pack(fill=tk.X, padx=2, pady=2)

        # ── Keyboard Manager ──────────────────────────────────────────────
        self._keyboard_manager = _KeyboardManager(self, self._on_ribbon_command)
        self._keyboard_manager.setup_bindings()

        # ── Banner (shown when optional packages are missing) ─────────────
        self._banner_var = tk.StringVar()
        self._banner_bar = tk.Label(
            self, textvariable=self._banner_var,
            background="#FFF4CE", foreground="#5D4037",
            font=("Segoe UI", 9), anchor=tk.W, padx=8, pady=4,
        )
        self._banner_var.trace_add("write", self._toggle_banner)

        # ── Notebook ──────────────────────────────────────────────────────
        self._nb = nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        calc_tab = _CalcTab(nb, self._settings)
        nb.add(calc_tab, text="  Fragment Calculator  ")
        self._calc_tab = calc_tab

        self._enrich_tab = _EnrichTab(tk.Frame(self), self._settings)

        self._viewer_tab = _SDFViewerTab(nb)
        nb.add(self._viewer_tab, text="  Compound Database  ")

        pkg_tab = _PackagesTab(nb)
        nb.add(pkg_tab, text="  Packages  ")

        # ── Status Bar ────────────────────────────────────────────────────
        self._status_bar = _StatusBar(self)
        self._status_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=0, pady=0)

        # ── Initial tab visibility ────────────────────────────────────────
        self._on_tab_changed(None)

    def _on_ribbon_command(self, command: str) -> None:
        """Handle ribbon button clicks."""
        # File operations (HOME tab)
        if command == "browse_file":
            self._browse_compound_file()
        elif command == "load_file":
            self._load_compound_file()
        elif command == "save_file":
            self._save_compound_file()
        elif command == "clear_compounds":
            self._clear_compounds()
        elif command == "show_recent_files":
            self._show_recent_files_menu()
        elif command == "batch_import":
            self._open_batch_import_dialog()

        # Compound operations (HOME tab)
        elif command == "add_compound":
            messagebox.showinfo("Add Compound", "Add compound functionality coming soon.")
        elif command == "edit_compound":
            if hasattr(self._viewer_tab, '_edit_metadata'):
                self._viewer_tab._edit_metadata()
        elif command == "delete_compound":
            messagebox.showinfo("Delete Compound", "Delete compound functionality coming soon.")
        elif command == "duplicate_compound":
            messagebox.showinfo("Duplicate Compound", "Duplicate compound functionality coming soon.")

        # Import operations (DATA tab)
        elif command == "import_csv":
            self._import_csv()
        elif command == "import_ri_rt":
            self._import_ri_rt()
        elif command == "import_sim":
            self._import_sim()
        elif command == "import_mrm":
            self._import_mrm()

        # Enrichment operations (DATA tab)
        elif command == "open_enrichment":
            self._open_enrichment_modal()

        # View operations (VIEW tab)
        elif command == "layout_full":
            messagebox.showinfo("Full View", "Full view layout coming soon.")
        elif command == "layout_spectrum":
            messagebox.showinfo("Spectrum Only", "Spectrum-only layout coming soon.")
        elif command == "toggle_metadata":
            messagebox.showinfo("Toggle Metadata", "Toggle metadata panel functionality coming soon.")
        elif command == "refresh_view":
            self._viewer_tab._populate_compound_list()
        elif command == "zoom_in":
            messagebox.showinfo("Zoom In", "Zoom functionality coming soon.")
        elif command == "zoom_out":
            messagebox.showinfo("Zoom Out", "Zoom functionality coming soon.")
        elif command == "grid_view":
            messagebox.showinfo("Grid View", "Grid view functionality coming soon.")

        # Database operations (SETTINGS tab)
        elif command == "new_database":
            self._db_new_file()
        elif command == "open_database":
            self._db_open_file()
        elif command == "close_database":
            self._db_close()
        elif command == "in_memory_db":
            self._db_new_in_memory()
        elif command == "backup_database":
            self._backup_database()
        elif command == "restore_database":
            self._restore_database()

        # Application settings (SETTINGS tab)
        elif command == "save_defaults":
            self._save_settings_defaults()
        elif command == "preferences":
            messagebox.showinfo("Preferences", "Preferences dialog coming soon.")
        elif command == "database_info":
            messagebox.showinfo("Database Info", "Database info coming soon.")

        # Undo/Redo operations
        elif command == "undo":
            if hasattr(self._viewer_tab, '_undo'):
                self._viewer_tab._undo()
                if hasattr(self, '_status_bar') and self._viewer_tab._undo_redo_stack.can_undo():
                    self._status_bar.set_last_action("Undo performed")
        elif command == "redo":
            if hasattr(self._viewer_tab, '_redo'):
                self._viewer_tab._redo()
                if hasattr(self, '_status_bar') and self._viewer_tab._undo_redo_stack.can_redo():
                    self._status_bar.set_last_action("Redo performed")

        # Navigation and help
        elif command == "open_element_table":
            if hasattr(self._calc_tab, '_open_element_table'):
                self._calc_tab._open_element_table()
        elif command == "show_help":
            messagebox.showinfo("Help", "Help documentation coming soon.")
        elif command == "quit":
            self.quit()

    def _on_tab_changed(self, event) -> None:
        """Handle tab changes to show/hide toolbar and Advanced Settings menu."""
        try:
            current_tab_idx = self._nb.index(self._nb.select())
            current_tab_text = self._nb.tab(current_tab_idx, "text").strip()

            # Show toolbar only for Compound Database and Packages tabs
            if current_tab_text in ["Compound Database", "Packages"]:
                self._ribbon.pack(fill=tk.X, padx=2, pady=2)
            else:
                self._ribbon.pack_forget()

            # Show Advanced Settings menu only for Fragment Calculator tab
            if current_tab_text == "Fragment Calculator":
                if not self._adv_menu_visible:
                    self._populate_adv_menu()
                    self._adv_menu_visible = True
            else:
                if self._adv_menu_visible:
                    self._adv_menu.delete(0, tk.END)
                    self._adv_menu_visible = False
        except Exception:
            pass

    def _populate_adv_menu(self) -> None:
        """Populate the Advanced Settings menu with controls."""
        self._adv_menu.add_command(
            label="Show / Hide Settings Panel",
            command=self._toggle_adv_panel
        )

    def _toggle_adv_panel(self) -> None:
        """Toggle Advanced Settings panel visibility in Fragment Calculator tab."""
        if hasattr(self._calc_tab, '_toggle_advanced'):
            self._calc_tab._toggle_advanced()

    def _open_batch_import_dialog(self) -> None:
        """Open batch import dialog."""
        dialog = _BatchImportDialog(self, self._on_batch_import_command)

    def _on_batch_import_command(self, command: str, *args) -> None:
        """Handle batch import dialog commands."""
        if command == "load_batch_file":
            filepath = args[0] if args else None
            if filepath and hasattr(self._viewer_tab, '_load_file_path'):
                self._viewer_tab._load_file_path(filepath)
        elif command == "clear_database":
            self._clear_compounds()

    def _backup_database(self) -> None:
        """Create backup of current database."""
        from pathlib import Path
        current_db = self._viewer_tab._db_path if hasattr(self._viewer_tab, '_db_path') else None

        if not current_db or current_db == ":memory:":
            messagebox.showinfo("Info", "In-memory databases cannot be backed up")
            return

        try:
            backup_path = self._db_manager.backup(current_db)
            if hasattr(self, '_status_bar'):
                self._status_bar.set_last_action(f"Database backed up")
            messagebox.showinfo("Backup Complete", f"Database backed up to:\n{Path(backup_path).name}")
        except Exception as e:
            messagebox.showerror("Backup Failed", f"Error backing up database:\n{e}")

    def _restore_database(self) -> None:
        """Restore database from backup."""
        from pathlib import Path
        current_db = self._viewer_tab._db_path if hasattr(self._viewer_tab, '_db_path') else None

        if not current_db or current_db == ":memory:":
            messagebox.showinfo("Info", "Cannot restore to in-memory database")
            return

        # Show backup selection dialog
        backup_path = filedialog.askopenfilename(
            title="Select Backup to Restore",
            initialdir=self._db_manager.backup_dir,
            filetypes=[("Database Backups", "*.db"), ("All Files", "*.*")]
        )

        if not backup_path:
            return

        # Confirm restore
        result = messagebox.askyesno(
            "Confirm Restore",
            f"Restore database from backup?\n\nCurrent database will be backed up as safety measure.\n\nBackup: {Path(backup_path).name}"
        )

        if result:
            try:
                self._db_manager.restore(backup_path, current_db)
                if hasattr(self, '_status_bar'):
                    self._status_bar.set_last_action("Database restored from backup")
                messagebox.showinfo("Restore Complete", "Database restored successfully")
            except Exception as e:
                messagebox.showerror("Restore Failed", f"Error restoring database:\n{e}")

    def _toggle_banner(self, *_) -> None:
        if self._banner_var.get():
            self._banner_bar.pack(side=tk.TOP, fill=tk.X, before=self._nb)
        else:
            self._banner_bar.pack_forget()

    # Database menu handlers
    def _db_new_in_memory(self) -> None:
        """Create a new in-memory database."""
        self._viewer_tab._init_database(db_path=None)
        self._viewer_tab._update_db_status("(in-memory database)")
        messagebox.showinfo("Database", "Created new in-memory database")

    def _db_new_file(self) -> None:
        """Create a new persistent database file."""
        file_path = filedialog.asksaveasfilename(
            defaultextension=".db",
            filetypes=[("SQLite Database", "*.db"), ("All files", "*.*")],
            title="Create New Database"
        )
        if file_path:
            self._viewer_tab._init_database(db_path=file_path)
            filename = file_path.split('\\')[-1] if '\\' in file_path else file_path.split('/')[-1]
            self._viewer_tab._update_db_status(f"({filename})")
            messagebox.showinfo("Database", f"Created persistent database at:\n{file_path}")

    def _db_open_file(self) -> None:
        """Open an existing database file."""
        file_path = filedialog.askopenfilename(
            filetypes=[("SQLite Database", "*.db"), ("All files", "*.*")],
            title="Open Existing Database"
        )
        if file_path:
            try:
                self._viewer_tab._init_database(db_path=file_path)
                filename = file_path.split('\\')[-1] if '\\' in file_path else file_path.split('/')[-1]
                self._viewer_tab._update_db_status(f"({filename})")
                messagebox.showinfo("Database", f"Opened database:\n{file_path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open database:\n{e}")

    def _db_close(self) -> None:
        """Close the current database."""
        self._viewer_tab._close_database()
        messagebox.showinfo("Database", "Database closed")

    def _db_save_as(self) -> None:
        """Save current database as a new file."""
        if not self._viewer_tab._db_conn:
            messagebox.showwarning("No Database", "No database is currently open")
            return
        file_path = filedialog.asksaveasfilename(
            defaultextension=".db",
            filetypes=[("SQLite Database", "*.db"), ("All files", "*.*")],
            title="Save Database As"
        )
        if file_path:
            try:
                import shutil
                if hasattr(self._viewer_tab, '_db_path') and self._viewer_tab._db_path:
                    shutil.copy(self._viewer_tab._db_path, file_path)
                else:
                    messagebox.showwarning("In-Memory Database",
                        "Cannot save in-memory database. Use 'Create New Database' first.")
                    return
                filename = file_path.split('\\')[-1] if '\\' in file_path else file_path.split('/')[-1]
                self._viewer_tab._update_db_status(f"({filename})")
                messagebox.showinfo("Success", f"Database saved to:\n{file_path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save database:\n{e}")

    def _open_enrichment_modal(self) -> None:
        """Open Enrichment controls as a modal window."""
        modal = tk.Toplevel(self)
        modal.title("SDF Enrichment")
        modal.geometry("900x600")
        modal.resizable(True, True)
        modal.transient(self)
        modal.grab_set()

        enrich_frame = _EnrichTab(modal, self._settings)
        enrich_frame.pack(fill=tk.BOTH, expand=True)

    # Compound file operations
    def _browse_compound_file(self) -> None:
        """Browse and select a compound file."""
        if hasattr(self._viewer_tab, '_browse_file'):
            self._viewer_tab._browse_file()
        else:
            messagebox.showwarning("Not Available", "File browser not available")

    def _load_compound_file(self) -> None:
        """Load the selected compound file."""
        if hasattr(self._viewer_tab, '_load_file'):
            self._viewer_tab._load_file()
        else:
            messagebox.showwarning("Not Available", "File loader not available")

    def _save_compound_file(self) -> None:
        """Save compounds from database to SDF file."""
        if not self._viewer_tab._db_conn:
            messagebox.showwarning("No Database", "No compounds loaded")
            return
        file_path = filedialog.asksaveasfilename(
            defaultextension=".sdf",
            filetypes=[("SDF Files", "*.sdf"), ("All files", "*.*")],
            title="Save Compounds As"
        )
        if file_path:
            messagebox.showinfo("Saving", "Save functionality coming soon.\n\nUse SDF Enricher tab to export enriched data.")

    def _clear_compounds(self) -> None:
        """Clear all loaded compounds from the database."""
        if not self._viewer_tab._db_conn:
            messagebox.showwarning("No Database", "No database is currently open")
            return
        if messagebox.askyesno("Confirm", "Clear all compounds from database? This cannot be undone."):
            try:
                self._viewer_tab._db_cursor.execute("DELETE FROM mass_spectrum")
                self._viewer_tab._db_cursor.execute("DELETE FROM metadata")
                self._viewer_tab._db_cursor.execute("DELETE FROM compounds")
                self._viewer_tab._db_conn.commit()
                self._viewer_tab._records = []
                self._viewer_tab._current_idx = 0
                self._viewer_tab._populate_compound_list()
                self._viewer_tab._clear_record_display()
                messagebox.showinfo("Success", "All compounds cleared")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to clear compounds:\n{e}")

    def _show_recent_files_menu(self) -> None:
        """Display recent files as a dropdown menu."""
        from pathlib import Path
        menu = tk.Menu(self, tearoff=0)

        recent = self._settings.get_recent_files()
        if recent:
            for filepath in recent:
                name = Path(filepath).name if Path(filepath).exists() else f"{Path(filepath).name} (missing)"
                menu.add_command(
                    label=name,
                    command=lambda f=filepath: self._load_recent_file(f)
                )
            menu.add_separator()

        menu.add_command(label="Clear Recent Files", command=self._settings.clear_recent_files)

        # Show menu at toolbar button position
        try:
            menu.post(self.winfo_pointerx(), self.winfo_pointery())
        except tk.TclError:
            pass

    def _load_recent_file(self, filepath: str) -> None:
        """Load a file from recent files list."""
        from pathlib import Path
        if not Path(filepath).exists():
            messagebox.showerror("File Not Found", f"The file no longer exists:\n{filepath}")
            self._settings.clear_recent_files()
            return

        # Load the file using the viewer tab's file loader
        if hasattr(self._viewer_tab, '_load_file_path'):
            self._viewer_tab._load_file_path(filepath)
        else:
            messagebox.showwarning("Not Available", "File loader not available")

    # Import data operations
    def _import_pubchem(self) -> None:
        """Enrich current compounds from PubChem."""
        if not self._viewer_tab._db_conn:
            messagebox.showwarning("No Database", "No compounds loaded. Load compounds first.")
            return
        messagebox.showinfo("PubChem Enrichment",
            "To enrich your compounds with PubChem data:\n\n"
            "1. Go to the SDF Enricher tab\n"
            "2. Load an SDF file\n"
            "3. Select PubChem as a data source\n"
            "4. Click Enrich\n\n"
            "Then import the enriched data back into the database.")

    def _import_csv(self) -> None:
        """Import compound data from CSV file."""
        file_path = filedialog.askopenfilename(
            filetypes=[("CSV Files", "*.csv"), ("TSV Files", "*.tsv"), ("All files", "*.*")],
            title="Select CSV File to Import"
        )
        if file_path:
            messagebox.showinfo("CSV Import",
                f"Selected: {file_path}\n\n"
                "CSV import functionality coming soon.\n\n"
                "Supported columns:\n"
                "- Name (compound name)\n"
                "- Formula (molecular formula)\n"
                "- MW (molecular weight)\n"
                "- CAS (CAS number)")

    def _import_ri_rt(self) -> None:
        """Import Retention Index/Time data."""
        file_path = filedialog.askopenfilename(
            filetypes=[("CSV Files", "*.csv"), ("TSV Files", "*.tsv"), ("All files", "*.*")],
            title="Select RI/RT Data File"
        )
        if file_path:
            messagebox.showinfo("RI/RT Import",
                f"Selected: {file_path}\n\n"
                "RI/RT data import functionality coming soon.\n\n"
                "Expected format:\n"
                "CompoundName, ColumnType, RI_Value, Deviation\n"
                "Example: Vanillin, StdNP, 1404, 7")

    def _import_sim(self) -> None:
        """Import SIM (Selected Ion Monitoring) information."""
        file_path = filedialog.askopenfilename(
            filetypes=[("CSV Files", "*.csv"), ("Text Files", "*.txt"), ("All files", "*.*")],
            title="Select SIM Data File"
        )
        if file_path:
            messagebox.showinfo("SIM Import",
                f"Selected: {file_path}\n\n"
                "SIM information import coming soon.\n\n"
                "This will import selected ion monitoring transitions\n"
                "and fragment masses from your data file.")

    def _import_mrm(self) -> None:
        """Import MRM (Multiple Reaction Monitoring) information."""
        file_path = filedialog.askopenfilename(
            filetypes=[("CSV Files", "*.csv"), ("Text Files", "*.txt"), ("All files", "*.*")],
            title="Select MRM Data File"
        )
        if file_path:
            messagebox.showinfo("MRM Import",
                f"Selected: {file_path}\n\n"
                "MRM information import coming soon.\n\n"
                "This will import multiple reaction monitoring\n"
                "transitions for mass spec methods.")

    def _save_settings_defaults(self) -> None:
        """Save current settings as defaults."""
        try:
            self._settings.save()
            messagebox.showinfo("Success", "Settings saved as defaults")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings:\n{e}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # Required by PyInstaller on Windows when multiprocessing workers are used
    import multiprocessing
    multiprocessing.freeze_support()
    app = EIFragmentApp()
    app.mainloop()


if __name__ == "__main__":
    main()
