"""
spectrum_analyzer.py
====================
Compound browser and annotated mass spectrum viewer.

Features:
- Compound list browser with filtering
- Mass spectrum with formula annotations
- Interactive peak inspector
- Formula assignment from formula_calculator module
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Optional, Any

# Optional matplotlib for spectrum plotting
try:
    import matplotlib
    matplotlib.use('TkAgg')
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    _HAS_MATPLOTLIB = True
except ImportError:
    _HAS_MATPLOTLIB = False
    Figure = None
    FigureCanvasTkAgg = None

# Import formula calculator for mass-to-formula lookup
try:
    from .formula_calculator import find_formulas_at_mass
    from .calculator import exact_mass
    _HAS_FORMULA_CALC = True
except ImportError:
    _HAS_FORMULA_CALC = False


class SpectrumAnalyzerTab(ttk.Frame):
    """Compound browser + annotated mass spectrum viewer."""

    def __init__(self, master: tk.Widget, records: list[dict] = None):
        super().__init__(master, padding=0)
        self._records = records or []
        self._current_idx = 0
        self._selected_peaks = set()  # For highlighting
        self._build()

    def _build(self) -> None:
        """Build the UI layout."""
        # ──────────────────────────────────────────────────────────────
        # Top toolbar
        # ──────────────────────────────────────────────────────────────
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, padx=6, pady=6)

        ttk.Label(toolbar, text="Compounds:").pack(side=tk.LEFT, padx=(0, 6))

        self._search_var = tk.StringVar()
        search_entry = ttk.Entry(toolbar, textvariable=self._search_var, width=20)
        search_entry.pack(side=tk.LEFT, padx=(0, 6))
        search_entry.bind("<KeyRelease>", lambda e: self._update_compound_list())

        ttk.Button(toolbar, text="Clear", width=8,
                   command=self._clear_search).pack(side=tk.LEFT, padx=(0, 6))

        ttk.Button(toolbar, text="Refresh", width=8,
                   command=self._refresh_view).pack(side=tk.LEFT)

        # ──────────────────────────────────────────────────────────────
        # Main content: browser on left, spectrum on right
        # ──────────────────────────────────────────────────────────────
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))

        # ── Left: Compound List ─────────────────────────────────────
        left_frame = ttk.LabelFrame(main_frame, text=" Compound Browser ", padding=6)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 6))
        left_frame.pack_propagate(False)
        left_frame.configure(width=250, height=400)

        # Compound listbox with scrollbar
        scroll = ttk.Scrollbar(left_frame)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._compound_list = tk.Listbox(
            left_frame,
            yscrollcommand=scroll.set,
            height=20,
            font=("Segoe UI", 9),
            selectmode=tk.SINGLE
        )
        self._compound_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._compound_list.bind("<<ListboxSelect>>", self._on_compound_selected)
        scroll.config(command=self._compound_list.yview)

        # ── Right: Spectrum View ────────────────────────────────────
        right_frame = ttk.LabelFrame(main_frame, text=" Mass Spectrum ", padding=6)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Spectrum canvas
        self._spectrum_canvas_frame = ttk.Frame(right_frame)
        self._spectrum_canvas_frame.pack(fill=tk.BOTH, expand=True)

        # Info panel below spectrum
        info_frame = ttk.Frame(right_frame)
        info_frame.pack(fill=tk.X, pady=(6, 0))

        ttk.Label(info_frame, text="Formulas:", font=("Segoe UI", 9, "bold")).pack(
            anchor=tk.W)

        scroll_info = ttk.Scrollbar(info_frame)
        scroll_info.pack(side=tk.RIGHT, fill=tk.Y)

        self._formula_list = tk.Listbox(
            info_frame,
            yscrollcommand=scroll_info.set,
            height=5,
            font=("Courier", 8)
        )
        self._formula_list.pack(fill=tk.BOTH, expand=True)
        scroll_info.config(command=self._formula_list.yview)

        # Populate compound list
        self._update_compound_list()

    def set_records(self, records: list[dict]) -> None:
        """Set compound records and refresh list."""
        self._records = records
        self._current_idx = 0
        self._update_compound_list()

    def _update_compound_list(self) -> None:
        """Update compound list based on search filter."""
        self._compound_list.delete(0, tk.END)

        search_term = self._search_var.get().lower()

        for i, record in enumerate(self._records):
            name = record.get("COMPOUNDNAME", record.get("NAME", f"Record {i+1}"))

            if search_term and search_term not in name.lower():
                continue

            self._compound_list.insert(tk.END, name)

        # Auto-select first if available
        if self._compound_list.size() > 0:
            self._compound_list.selection_set(0)
            self._on_compound_selected()

    def _clear_search(self) -> None:
        """Clear search field."""
        self._search_var.set("")
        self._update_compound_list()

    def _on_compound_selected(self, event=None) -> None:
        """Handle compound selection."""
        selection = self._compound_list.curselection()
        if not selection:
            return

        # Find actual index in records (accounting for search filter)
        search_term = self._search_var.get().lower()
        selected_in_list = selection[0]
        actual_count = 0

        for i, record in enumerate(self._records):
            name = record.get("COMPOUNDNAME", record.get("NAME", f"Record {i+1}"))

            if search_term and search_term not in name.lower():
                continue

            if actual_count == selected_in_list:
                self._current_idx = i
                self._display_spectrum(record)
                return

            actual_count += 1

    def _display_spectrum(self, record: dict) -> None:
        """Display mass spectrum with formula annotations."""
        # Clear previous
        for widget in self._spectrum_canvas_frame.winfo_children():
            widget.destroy()
        self._formula_list.delete(0, tk.END)

        if not _HAS_MATPLOTLIB:
            ttk.Label(self._spectrum_canvas_frame,
                     text="Matplotlib not installed",
                     foreground="#cc0000").pack(fill=tk.BOTH, expand=True)
            return

        # Extract spectrum data
        peaks_data = self._find_peaks_field(record)
        formula_str = record.get("FORMULA", "")

        if not peaks_data:
            ttk.Label(self._spectrum_canvas_frame,
                     text="No mass spectrum data",
                     foreground="#999999").pack(fill=tk.BOTH, expand=True)
            return

        try:
            mz_values, intensity_values = self._parse_peaks(peaks_data)

            if not mz_values:
                ttk.Label(self._spectrum_canvas_frame,
                         text="Could not parse peaks",
                         foreground="#999999").pack(fill=tk.BOTH, expand=True)
                return

            # Get formula annotations
            annotations = {}
            if _HAS_FORMULA_CALC and formula_str:
                annotations = self._get_formula_annotations(
                    mz_values, formula_str)

            # Create figure
            fig = Figure(figsize=(12, 4), dpi=100)
            ax = fig.add_subplot(111)

            # Plot spectrum
            bars = ax.bar(mz_values, intensity_values, width=0.3,
                         color="#0078D4", alpha=0.7, edgecolor="#0055AA",
                         linewidth=0.5)

            # Add formula annotations on top of bars
            for i, (mz, intensity) in enumerate(zip(mz_values, intensity_values)):
                if mz in annotations and annotations[mz]:
                    formula = annotations[mz][0]  # Top formula
                    ax.text(mz, intensity + 2, formula, ha='center', va='bottom',
                           fontsize=8, rotation=0, color="#006600", fontweight="bold")

            ax.set_xlabel("m/z", fontsize=10)
            ax.set_ylabel("Intensity (%)", fontsize=10)
            ax.set_title(f"Mass Spectrum: {record.get('COMPOUNDNAME', 'Unknown')}",
                        fontsize=11, fontweight="bold")
            ax.grid(axis="y", alpha=0.3)
            ax.set_ylim(0, max(intensity_values) * 1.15 if intensity_values else 100)
            fig.tight_layout()

            # Embed in tkinter
            canvas = FigureCanvasTkAgg(fig, master=self._spectrum_canvas_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

            # Display formula list
            self._show_formula_annotations(annotations, mz_values)

        except Exception as e:
            ttk.Label(self._spectrum_canvas_frame,
                     text=f"Error: {str(e)[:60]}",
                     foreground="#cc0000").pack(fill=tk.BOTH, expand=True)

    def _find_peaks_field(self, record: dict) -> Optional[str]:
        """Find mass spectral peaks in record."""
        candidates = ["MASS SPECTRAL PEAKS", "MASS SPECTRUM", "PEAKS",
                     "MS PEAKS", "SPECTRUM"]

        for candidate in candidates:
            for key in record.keys():
                if candidate.lower() in key.lower():
                    return record[key]
        return None

    def _parse_peaks(self, peaks_str: str) -> tuple:
        """Parse mass spectral peaks from various formats."""
        mz_values = []
        intensity_values = []

        try:
            peaks_str = str(peaks_str).strip()

            # Semicolon-separated
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

            # Newline-separated
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

            # Space-separated (alternating m/z intensity)
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

    def _get_formula_annotations(self, mz_values: list,
                                 parent_formula_str: str) -> dict:
        """Get formula annotations for peaks."""
        from .formula import parse_formula

        annotations = {}

        try:
            parent_comp = parse_formula(parent_formula_str)
            if not parent_comp:
                return annotations

            for mz in mz_values:
                # Find formulas at this m/z
                results = find_formulas_at_mass(
                    mz, parent_comp,
                    tolerance=0.5,
                    electron_mode="remove"
                )

                if results:
                    # Store top 3 matches
                    formulas = [r["formula"] for r in results[:3]]
                    annotations[mz] = formulas

        except Exception:
            pass

        return annotations

    def _show_formula_annotations(self, annotations: dict,
                                  mz_values: list) -> None:
        """Display formula annotations in listbox."""
        sorted_mz = sorted(mz_values)

        for mz in sorted_mz:
            if mz in annotations and annotations[mz]:
                formula = annotations[mz][0]
                self._formula_list.insert(
                    tk.END, f"m/z {mz:7.1f}  →  {formula}"
                )

    def _refresh_view(self) -> None:
        """Refresh current view."""
        if self._records and self._current_idx < len(self._records):
            self._display_spectrum(self._records[self._current_idx])


# For standalone testing
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Spectrum Analyzer Test")
    root.geometry("1000x600")

    # Sample test data
    test_records = [
        {
            "COMPOUNDNAME": "Caffeine",
            "FORMULA": "C8H10N4O2",
            "MASS SPECTRAL PEAKS": "50 287; 51 144; 52 9; 77 120; 109 115; 110 999; 111 80"
        },
        {
            "COMPOUNDNAME": "Benzene",
            "FORMULA": "C6H6",
            "MASS SPECTRAL PEAKS": "50 28; 51 44; 52 999; 53 52; 77 999; 78 999"
        }
    ]

    tab = SpectrumAnalyzerTab(root, test_records)
    tab.pack(fill=tk.BOTH, expand=True)

    root.mainloop()
