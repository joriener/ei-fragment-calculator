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
4. Packages             — check and auto-install optional dependencies

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
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font, messagebox, scrolledtext, ttk

# ---------------------------------------------------------------------------
# Optional enricher
# ---------------------------------------------------------------------------
try:
    import sdf_enricher as _se          # noqa: F401
    _HAS_ENRICHER = True
except ImportError:
    _HAS_ENRICHER = False

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
# Colour palette  (VS Code Dark+ inspired)
# ---------------------------------------------------------------------------
_BG        = "#1e1e1e"
_BG2       = "#252526"
_BG3       = "#2d2d2d"
_FG        = "#d4d4d4"
_FG_DIM    = "#808080"
_FG_BRIGHT = "#ffffff"
_GREEN     = "#4ec994"
_RED       = "#f44747"
_ORANGE    = "#ce9178"
_CYAN      = "#9cdcfe"
_YELLOW    = "#dcdcaa"
_BLUE      = "#569cd6"
_PURPLE    = "#c586c0"
_ACCENT    = "#0e639c"
_ACCENT_H  = "#1177bb"

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
    "workers":         1,
    "last_input_dir":  "",
    "last_output_dir": "",
    # enricher
    "e_no_pubchem":    False,
    "e_no_chebi":      False,
    "e_no_kegg":       False,
    "e_no_hmdb":       False,
    "e_no_exact_mass": False,
    "e_no_splash":     False,
    "e_overwrite":     False,
    "e_delay":         0.5,
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
        bg=_BG, fg=_FG, insertbackground=_FG,
        selectbackground=_ACCENT, selectforeground=_FG_BRIGHT,
        relief=tk.FLAT, borderwidth=0,
    )
    log.tag_configure("ok",      foreground=_GREEN)
    log.tag_configure("fail",    foreground=_RED)
    log.tag_configure("header",  foreground=_CYAN)
    log.tag_configure("mz",      foreground=_YELLOW)
    log.tag_configure("added",   foreground=_GREEN)
    log.tag_configure("warn",    foreground=_ORANGE)
    log.tag_configure("bracket", foreground=_PURPLE)
    return log


def _clear_log(log: scrolledtext.ScrolledText) -> None:
    log.configure(state="normal")
    log.delete("1.0", tk.END)
    log.configure(state="disabled")


def _apply_style() -> None:
    s = ttk.Style()
    try:
        s.theme_use("clam")
    except tk.TclError:
        pass
    s.configure(".",             background=_BG2, foreground=_FG)
    s.configure("TFrame",        background=_BG2)
    s.configure("TLabelframe",   background=_BG2, foreground=_FG,
                relief="groove", borderwidth=1)
    s.configure("TLabelframe.Label", background=_BG2, foreground=_CYAN,
                font=("Segoe UI", 9, "bold"))
    s.configure("TLabel",        background=_BG2, foreground=_FG)
    s.configure("TCheckbutton",  background=_BG2, foreground=_FG,
                indicatorcolor=_BG3)
    s.map("TCheckbutton",        background=[("active", _BG2)])
    s.configure("TRadiobutton",  background=_BG2, foreground=_FG)
    s.map("TRadiobutton",        background=[("active", _BG2)])
    s.configure("TEntry",        fieldbackground=_BG3, foreground=_FG,
                insertcolor=_FG, borderwidth=1)
    s.configure("TSpinbox",      fieldbackground=_BG3, foreground=_FG,
                insertcolor=_FG, arrowcolor=_FG)
    s.configure("TCombobox",     fieldbackground=_BG3, foreground=_FG)
    s.configure("TButton",       background=_BG3, foreground=_FG,
                borderwidth=1, focuscolor="none")
    s.map("TButton",             background=[("active", "#505050"),
                                              ("disabled", "#333")])
    s.configure("Accent.TButton", background=_ACCENT, foreground=_FG_BRIGHT,
                font=("Segoe UI", 9, "bold"), borderwidth=0)
    s.map("Accent.TButton",       background=[("active",   _ACCENT_H),
                                               ("disabled", "#444")])
    s.configure("TNotebook",     background=_BG, tabmargins=[2, 5, 0, 0])
    s.configure("TNotebook.Tab", background=_BG3, foreground=_FG_DIM,
                padding=[14, 5])
    s.map("TNotebook.Tab",       background=[("selected", _BG)],
                                 foreground=[("selected", _FG_BRIGHT)])
    s.configure("Treeview",      background=_BG3, foreground=_FG,
                fieldbackground=_BG3, rowheight=22)
    s.configure("Treeview.Heading", background=_BG2, foreground=_CYAN,
                font=("Segoe UI", 9, "bold"))
    s.map("Treeview",            background=[("selected", _ACCENT)],
                                 foreground=[("selected", _FG_BRIGHT)])
    s.configure("Horizontal.TProgressbar",
                troughcolor=_BG3, background=_ACCENT,
                bordercolor=_BG2, lightcolor=_ACCENT, darkcolor=_ACCENT)
    s.configure("TSeparator",    background="#444")


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
        self._build()
        self._load_settings()

    # ── Build UI ─────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # ── I/O Section ──────────────────────────────────────────────────────
        io = ttk.LabelFrame(self, text=" Files ", padding=8)
        io.pack(fill=tk.X, pady=(0, 6))
        io.columnconfigure(1, weight=1)

        ttk.Label(io, text="Input SDF:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self._in_var = tk.StringVar()
        self._in_var.trace_add("write", self._update_out_sdf)
        ttk.Entry(io, textvariable=self._in_var).grid(
            row=0, column=1, sticky=tk.EW, padx=(6, 4))
        ttk.Button(io, text="Browse…", command=self._browse_in).grid(
            row=0, column=2, padx=(0, 2))

        ttk.Label(io, text="Output SDF:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Entry(io, textvariable=self._out_sdf).grid(
            row=1, column=1, sticky=tk.EW, padx=(6, 4))
        ttk.Button(io, text="Browse…", command=self._browse_out_sdf).grid(
            row=1, column=2, padx=(0, 2))

        ttk.Label(io, text="Log to file:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self._log_file_var = tk.StringVar()
        ttk.Entry(io, textvariable=self._log_file_var).grid(
            row=2, column=1, sticky=tk.EW, padx=(6, 4))
        ttk.Button(io, text="Browse…", command=self._browse_log_file).grid(
            row=2, column=2, padx=(0, 2))
        ttk.Label(io, text="(optional — leave blank to show in window only)",
                  foreground=_FG_DIM).grid(row=2, column=3, padx=6, sticky=tk.W)

        # ── Main Options ─────────────────────────────────────────────────────
        opt = ttk.LabelFrame(self, text=" Main Options ", padding=8)
        opt.pack(fill=tk.X, pady=(0, 6))

        # Row 0 — tolerance + workers
        r0 = ttk.Frame(opt); r0.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(r0, text="Tolerance ±Da:").pack(side=tk.LEFT)
        self._tol = tk.StringVar()
        _spin(r0, self._tol, 0.1, 2.0, 0.1).pack(side=tk.LEFT, padx=(4, 24))

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
            ("add",    "add     (EI −)", "Add m_e — negative-ion EI"),
            ("none",   "none",           "No correction"),
        ]:
            rb = ttk.Radiobutton(r0, text=lbl, variable=self._elec, value=val)
            rb.pack(side=tk.LEFT, padx=4)
            _tooltip(rb, tip)

        # Row 1 — toggles
        r1 = ttk.Frame(opt); r1.pack(fill=tk.X, pady=(0, 4))
        self._best_only  = tk.BooleanVar()
        self._hide_empty = tk.BooleanVar()
        self._show_iso   = tk.BooleanVar()
        self._no_sdf     = tk.BooleanVar()
        for var, lbl, tip in [
            (self._best_only,  "Best-only",
             "Keep only the highest-ranked candidate per peak; drop unmatched peaks"),
            (self._hide_empty, "Hide empty",
             "Do not print peaks that have no matching candidate formula"),
            (self._show_iso,   "Show isotope patterns",
             "Display theoretical M / M+1 / M+2 percentages for every candidate"),
            (self._no_sdf,     "Skip SDF output",
             "Do not write the *-EXACT.sdf output file"),
        ]:
            cb = ttk.Checkbutton(r1, text=lbl, variable=var)
            cb.pack(side=tk.LEFT, padx=(0, 16))
            _tooltip(cb, tip)

        # ── Filter Options ───────────────────────────────────────────────────
        flt = ttk.LabelFrame(self, text=" Algorithm Filters  (all ON by default) ",
                             padding=8)
        flt.pack(fill=tk.X, pady=(0, 6))

        fA = ttk.Frame(flt); fA.pack(fill=tk.X, pady=(0, 4))
        self._no_n  = tk.BooleanVar()
        self._no_hd = tk.BooleanVar()
        self._no_ls = tk.BooleanVar()
        self._no_is = tk.BooleanVar()
        self._no_sm = tk.BooleanVar()
        for var, lbl, tip in [
            (self._no_n,  "Disable Nitrogen Rule",
             "McLafferty: odd nominal m/z ↔ odd N count for even-electron ions"),
            (self._no_hd, "Disable H-Deficiency",
             "Pretsch: reject DBE/C > max_ring_ratio (extraordinarily H-poor)"),
            (self._no_ls, "Disable Lewis / Senior",
             "Senior 1951: valence-sum must be even and ≥ 2×(atoms−1)"),
            (self._no_is, "Disable Isotope Score",
             "Gross: reject if |theo% − obs%| sum exceeds isotope_tolerance pp"),
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
        _tooltip_label(fB, "Max Σ|theo% − obs%| deviation; default 30 pp")

        ttk.Label(fB, text="Max ring ratio  (DBE/C):").pack(side=tk.LEFT)
        self._ring = tk.StringVar()
        _spin(fB, self._ring, 0.1, 2.0, 0.05).pack(side=tk.LEFT, padx=(4, 0))
        _tooltip_label(fB, "H-deficiency upper bound; default 0.5")

        # ── Default management ───────────────────────────────────────────────
        def_fr = ttk.Frame(self)
        def_fr.pack(fill=tk.X, pady=(0, 4))
        ttk.Button(def_fr, text="💾  Save as Default",
                   command=self._save_defaults).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(def_fr, text="↩  Reset to Factory",
                   command=self._reset_defaults).pack(side=tk.LEFT)

        _sep(self)

        # ── Run row ──────────────────────────────────────────────────────────
        run_fr = ttk.Frame(self)
        run_fr.pack(fill=tk.X, pady=(0, 4))
        self._run_btn = ttk.Button(run_fr, text="▶  Run",
                                   style="Accent.TButton", command=self._run)
        self._run_btn.pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(run_fr, text="Clear", command=lambda: _clear_log(self._log)
                   ).pack(side=tk.LEFT, padx=(0, 6))
        self._open_btn = ttk.Button(run_fr, text="📂  Open output folder",
                                    state="disabled", command=self._open_folder)
        self._open_btn.pack(side=tk.LEFT)
        self._status = tk.StringVar(value="Ready.")
        ttk.Label(run_fr, textvariable=self._status, foreground=_FG_DIM
                  ).pack(side=tk.RIGHT)

        self._pb = ttk.Progressbar(self, mode="indeterminate",
                                   style="Horizontal.TProgressbar")
        self._pb.pack(fill=tk.X, pady=(0, 4))

        # ── Log ──────────────────────────────────────────────────────────────
        log_fr = ttk.LabelFrame(self, text=" Output ", padding=4)
        log_fr.pack(fill=tk.BOTH, expand=True)
        self._log = _make_log(log_fr)
        self._log.pack(fill=tk.BOTH, expand=True)

    # ── Settings helpers ─────────────────────────────────────────────────────

    def _load_settings(self) -> None:
        s = self._settings
        self._tol.set(str(s["tolerance"]))
        self._elec.set(s["electron_mode"])
        self._best_only.set(s["best_only"])
        self._hide_empty.set(s["hide_empty"])
        self._show_iso.set(s["show_isotope"])
        self._no_sdf.set(s["no_save_sdf"])
        self._no_n.set(s["no_nitrogen"])
        self._no_hd.set(s["no_hd"])
        self._no_ls.set(s["no_lewis"])
        self._no_is.set(s["no_isotope_score"])
        self._no_sm.set(s["no_smiles"])
        self._iso_tol.set(str(s["isotope_tolerance"]))
        self._ring.set(str(s["max_ring_ratio"]))
        self._workers.set(str(s["workers"]))

    def _save_defaults(self) -> None:
        try:
            s = self._settings
            s["tolerance"]        = float(self._tol.get())
            s["electron_mode"]    = self._elec.get()
            s["best_only"]        = self._best_only.get()
            s["hide_empty"]       = self._hide_empty.get()
            s["show_isotope"]     = self._show_iso.get()
            s["no_save_sdf"]      = self._no_sdf.get()
            s["no_nitrogen"]      = self._no_n.get()
            s["no_hd"]            = self._no_hd.get()
            s["no_lewis"]         = self._no_ls.get()
            s["no_isotope_score"] = self._no_is.get()
            s["no_smiles"]        = self._no_sm.get()
            s["isotope_tolerance"]= float(self._iso_tol.get())
            s["max_ring_ratio"]   = float(self._ring.get())
            s["workers"]          = max(1, int(float(self._workers.get())))
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
            title="Select input SDF file",
            filetypes=[("SDF files", "*.sdf *.SDF"), ("All files", "*.*")],
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
            title="Save exact-mass SDF as…",
            defaultextension=".sdf",
            filetypes=[("SDF files", "*.sdf"), ("All files", "*.*")],
        )
        if path:
            self._out_sdf.set(path)
            self._settings["last_output_dir"] = str(Path(path).parent)

    def _browse_log_file(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save text log as…",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if path:
            self._log_file_var.set(path)

    def _update_out_sdf(self, *_) -> None:
        """Auto-derive output SDF path when input changes (unless user set it)."""
        p = self._in_var.get().strip()
        if p:
            from .sdf_writer import exact_sdf_path
            self._out_sdf.set(exact_sdf_path(p))

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
            messagebox.showwarning("No input file", "Please select an input SDF file.")
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

        argv = [
            sdf,
            "--tolerance",         str(tol),
            "--electron",          self._elec.get(),
            "--isotope-tolerance", str(iso_tol),
            "--max-ring-ratio",    str(ring),
        ]
        if self._best_only.get():  argv.append("--best-only")
        if self._hide_empty.get(): argv.append("--hide-empty")
        if self._show_iso.get():   argv.append("--isotope")
        if self._no_sdf.get():     argv.append("--no-save-sdf")
        if self._no_n.get():       argv.append("--no-nitrogen-rule")
        if self._no_hd.get():      argv.append("--no-hd-check")
        if self._no_ls.get():      argv.append("--no-lewis-senior")
        if self._no_is.get():      argv.append("--no-isotope-score")
        if self._no_sm.get():      argv.append("--no-smiles-constraints")
        argv += ["--workers", str(max(1, int(float(self._workers.get()))))]
        if out_sdf:                argv += ["--output-sdf", out_sdf]
        if log_file:               argv += ["--output", log_file]

        self._run_btn.configure(state="disabled")
        self._open_btn.configure(state="disabled")
        self._status.set("Running…")
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
            foreground=_FG_DIM, wraplength=860, justify=tk.LEFT,
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

        ttk.Button(btn_fr, text="➕  Add Row",    command=self._add_row
                   ).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_fr, text="🗑  Delete Row", command=self._delete_row
                   ).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Button(btn_fr, text="💾  Save to elements.csv",
                   style="Accent.TButton", command=self._save_csv
                   ).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_fr, text="↺  Reload from disk", command=self._load_csv
                   ).pack(side=tk.LEFT)

        self._elem_status = tk.StringVar(value="")
        ttk.Label(btn_fr, textvariable=self._elem_status, foreground=_FG_DIM
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
# Tab 3 — SDF Enricher
# ===========================================================================

class _EnrichTab(ttk.Frame):

    def __init__(self, master: tk.Widget, settings: _Settings):
        super().__init__(master, padding=10)
        self._settings = settings
        self._running  = False
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
        self._overwr = tk.BooleanVar()
        ttk.Checkbutton(rB, text="Overwrite existing values", variable=self._overwr
                        ).pack(side=tk.LEFT, padx=(0, 24))
        ttk.Label(rB, text="API delay (s):").pack(side=tk.LEFT)
        self._delay = tk.StringVar()
        _spin(rB, self._delay, 0.0, 5.0, 0.1).pack(side=tk.LEFT, padx=4)

        def_fr = ttk.Frame(self); def_fr.pack(fill=tk.X, pady=(0, 4))
        ttk.Button(def_fr, text="💾  Save as Default",
                   command=self._save_defaults).pack(side=tk.LEFT, padx=(0, 6))

        _sep(self)

        run_fr = ttk.Frame(self); run_fr.pack(fill=tk.X, pady=(0, 4))
        self._run_btn = ttk.Button(run_fr, text="▶  Enrich",
                                   style="Accent.TButton", command=self._run)
        self._run_btn.pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(run_fr, text="Clear",
                   command=lambda: _clear_log(self._log)).pack(side=tk.LEFT, padx=(0, 6))
        self._open_btn = ttk.Button(run_fr, text="📂  Open output folder",
                                    state="disabled", command=self._open_folder)
        self._open_btn.pack(side=tk.LEFT)
        self._status = tk.StringVar(value="Ready.")
        ttk.Label(run_fr, textvariable=self._status, foreground=_FG_DIM
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
            title="Save enriched SDF as…",
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

        self._run_btn.configure(state="disabled")
        self._open_btn.configure(state="disabled")
        self._status.set("Enriching…")
        self._pb.start(12)
        self._running = True
        _clear_log(self._log)

        rd = _Redirector(self._log, self.winfo_toplevel())
        threading.Thread(target=self._worker, args=(sdf, cfg, out, rd),
                         daemon=True).start()

    def _worker(self, sdf_path: str, cfg: dict, out_path: str | None,
                rd: _Redirector) -> None:
        from sdf_enricher.sdf_io   import read_sdf, write_sdf, enriched_path
        from sdf_enricher.enricher import EnrichConfig, enrich_records
        old_o, old_e = sys.stdout, sys.stderr
        sys.stdout = rd; sys.stderr = rd
        ok = True; final_out = out_path or ""
        try:
            records = read_sdf(sdf_path)
            print("SDF Enricher\n  Input   : {}\n  Records : {}\n".format(
                sdf_path, len(records)))
            enrich_records(records, config=EnrichConfig(**cfg), verbose=True)
            final_out = out_path or enriched_path(sdf_path)
            n = write_sdf(records, final_out)
            print("\nSaved {} record(s) to '{}'.".format(n, final_out))
        except Exception as exc:
            sys.stderr.write("\nERROR: {}\n".format(exc))
            ok = False
        finally:
            sys.stdout = old_o; sys.stderr = old_e
        self.winfo_toplevel().after(0, self._done, ok, final_out)

    def _done(self, ok: bool, out_path: str) -> None:
        self._running = False
        self._pb.stop()
        self._run_btn.configure(state="normal")
        self._status.set("Done." if ok else "Finished with errors.")
        if out_path and Path(out_path).exists():
            self._out_path.set(out_path)
            self._open_btn.configure(state="normal")


# ===========================================================================
# Tab 4 — Packages
# ===========================================================================

_PKGS: list[tuple] = [
    # (import_name, pip_name, required_for, notes)
    ("sdf_enricher", "sdf-enricher",
     "SDF Enricher tab",
     "Fills missing metadata from PubChem, ChEBI, KEGG, HMDB"),
    ("splashpy",     "splashpy",
     "SPLASH hash calculation",
     "Spectral hash for SDF records; optional"),
    ("matplotlib",   "matplotlib",
     "Workflow diagram (scripts/generate_workflow_image.py)",
     "Not needed for fragment calculation"),
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
            foreground=_FG_DIM,
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

        self._tree.tag_configure("ok",      foreground=_GREEN)
        self._tree.tag_configure("missing", foreground=_RED)

        btn_fr = ttk.Frame(self)
        btn_fr.pack(fill=tk.X, pady=(0, 6))
        ttk.Button(btn_fr, text="↺  Refresh",
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
            status    = "✓ installed" if installed else "✗ missing"
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
            print("Installing {}…".format(pkg))
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", pkg],
                    capture_output=True, text=True, timeout=120,
                )
                print(result.stdout or "")
                if result.returncode != 0:
                    print("pip stderr:\n" + result.stderr)
                else:
                    print("✓ {} installed successfully.\n".format(pkg))
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
    lbl = ttk.Label(parent, text="ⓘ", foreground=_FG_DIM, cursor="question_arrow")
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
        self.configure(background=_BG)
        self.minsize(860, 700)
        self.geometry("1000x800")
        _apply_style()

        self._settings = _Settings()
        self._build()

        # Startup check in background
        banner_var = self._banner_var
        threading.Thread(
            target=_startup_check,
            args=(self, self._nb, banner_var),
            daemon=True,
        ).start()

    def _build(self) -> None:
        # ── Banner (shown when optional packages are missing) ─────────────
        self._banner_var = tk.StringVar()
        self._banner_bar = tk.Label(
            self, textvariable=self._banner_var,
            background="#5a3e00", foreground="#ffd27f",
            font=("Segoe UI", 9), anchor=tk.W, padx=8, pady=4,
        )
        self._banner_var.trace_add("write", self._toggle_banner)

        # ── Notebook ──────────────────────────────────────────────────────
        self._nb = nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        calc_tab = _CalcTab(nb, self._settings)
        nb.add(calc_tab, text="  Fragment Calculator  ")

        elem_tab = _ElementTab(nb)
        nb.add(elem_tab, text="  Element Table  ")

        if _HAS_ENRICHER:
            enrich_tab = _EnrichTab(nb, self._settings)
            nb.add(enrich_tab, text="  SDF Enricher  ")
        else:
            ph = ttk.Frame(nb, padding=20)
            ttk.Label(
                ph,
                text=(
                    "The SDF Enricher tab requires the  sdf-enricher  package.\n\n"
                    "Go to the  Packages  tab and click  \"Install ALL missing\"  "
                    "— or run:\n\n"
                    '    pip install "ei-fragment-calculator[enrich]"\n\n'
                    "Then restart this application."
                ),
                font=("Consolas", 10), foreground=_FG_DIM, justify=tk.LEFT,
            ).pack(anchor=tk.NW)
            nb.add(ph, text="  SDF Enricher  ")

        pkg_tab = _PackagesTab(nb)
        nb.add(pkg_tab, text="  Packages  ")

    def _toggle_banner(self, *_) -> None:
        if self._banner_var.get():
            self._banner_bar.pack(side=tk.TOP, fill=tk.X, before=self._nb)
        else:
            self._banner_bar.pack_forget()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    app = EIFragmentApp()
    app.mainloop()


if __name__ == "__main__":
    main()
