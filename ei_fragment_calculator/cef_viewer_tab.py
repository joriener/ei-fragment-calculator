"""
cef_viewer_tab.py
=================
CEF Viewer tab for the GUI - primary UI for loading, browsing, and consolidating CEF files.
Integrates with SQLite database and provides analysis tools.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path
from typing import Optional, List, Dict
import threading
import traceback

from .cef_parser import parse_cef, CEFCompound
from .cef_db import CEFDatabase
from .cef_matcher import CEFMatcher, CEFConsolidator, MatchParameters

try:
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


class CEFViewerTab(ttk.Frame):
    """Tab for viewing and analyzing CEF files."""

    def __init__(self, master, settings=None):
        super().__init__(master, padding=10)
        self._settings = settings
        self._running = False
        self._db: Optional[CEFDatabase] = None
        self._current_compound = None
        self._compounds_cache = []
        self._cef_files = []
        self._selected_file_id = None

        self._build_ui()

    def _build_ui(self):
        """Build the tab UI."""
        try:
            self.columnconfigure(0, weight=0)
            self.columnconfigure(1, weight=1)
            self.columnconfigure(2, weight=1)
            self.columnconfigure(3, weight=0)
            self.rowconfigure(1, weight=1)

            # ── Toolbar ──────────────────────────────────────────
            toolbar = ttk.Frame(self)
            toolbar.grid(row=0, column=0, columnspan=4, sticky=tk.EW, pady=(0, 6))
            toolbar.columnconfigure(1, weight=1)

            ttk.Button(toolbar, text="Load CEF", command=self._load_cef).pack(side=tk.LEFT, padx=2)
            ttk.Button(toolbar, text="Clear", command=self._clear_data).pack(side=tk.LEFT, padx=2)
            ttk.Button(toolbar, text="Align", command=self._align).pack(side=tk.LEFT, padx=2)
            ttk.Button(toolbar, text="Export Aligned", command=self._export_aligned).pack(side=tk.LEFT, padx=2)
            ttk.Button(toolbar, text="Consolidate", command=self._consolidate).pack(side=tk.LEFT, padx=2)
            ttk.Button(toolbar, text="Export Consolidated", command=self._export).pack(side=tk.LEFT, padx=2)

            self._status_var = tk.StringVar(value="No database loaded")
            status_label = ttk.Label(toolbar, textvariable=self._status_var, foreground="#666666")
            status_label.pack(side=tk.RIGHT, padx=6)

            # ── Left panel: File & compound list ──────────────────
            left_frame = ttk.LabelFrame(self, text=" CEF Files & Compounds ", padding=4)
            left_frame.grid(row=1, column=0, sticky=tk.NSEW, padx=(0, 6))
            left_frame.rowconfigure(1, weight=1)

            search_frame = ttk.Frame(left_frame)
            search_frame.grid(row=0, column=0, sticky=tk.EW, pady=(0, 4))
            search_frame.columnconfigure(0, weight=1)

            ttk.Label(search_frame, text="File:").pack(side=tk.LEFT, padx=(0, 4))
            self._file_var = tk.StringVar(value="All")
            self._file_combo = ttk.Combobox(search_frame, textvariable=self._file_var,
                                            values=["All"], state="readonly", width=15)
            self._file_combo.pack(side=tk.LEFT, padx=(0, 8))

            # Align parameters - directly in UI
            param_frame = ttk.LabelFrame(left_frame, text="Align Parameters", padding=4)
            param_frame.grid(row=1, column=0, sticky=tk.EW, pady=(0, 4))

            ttk.Label(param_frame, text="Method:").grid(row=0, column=0, sticky=tk.W, padx=2, pady=2)
            self._method_var = tk.StringVar(value="mass_rt")
            method_combo = ttk.Combobox(param_frame, textvariable=self._method_var,
                                       values=["mass_rt", "ppm_rt", "spectral", "ppm_spectral"],
                                       state="readonly", width=12)
            method_combo.grid(row=0, column=1, sticky=tk.EW, padx=2, pady=2)

            ttk.Label(param_frame, text="PPM Tolerance:").grid(row=1, column=0, sticky=tk.W, padx=2, pady=2)
            self._ppm_var = tk.DoubleVar(value=5.0)
            ttk.Spinbox(param_frame, from_=0.1, to=100, textvariable=self._ppm_var, width=8).grid(row=1, column=1, sticky=tk.EW, padx=2, pady=2)

            ttk.Label(param_frame, text="Da Tolerance:").grid(row=2, column=0, sticky=tk.W, padx=2, pady=2)
            self._da_var = tk.DoubleVar(value=0.5)
            ttk.Spinbox(param_frame, from_=0.01, to=5, textvariable=self._da_var, width=8).grid(row=2, column=1, sticky=tk.EW, padx=2, pady=2)

            ttk.Label(param_frame, text="RT Tolerance (min):").grid(row=3, column=0, sticky=tk.W, padx=2, pady=2)
            self._rt_tol_var = tk.DoubleVar(value=0.2)
            ttk.Spinbox(param_frame, from_=0.01, to=5, textvariable=self._rt_tol_var, width=8).grid(row=3, column=1, sticky=tk.EW, padx=2, pady=2)

            ttk.Label(param_frame, text="Spectral Threshold:").grid(row=4, column=0, sticky=tk.W, padx=2, pady=2)
            self._spectral_thresh_var = tk.DoubleVar(value=0.8)
            ttk.Spinbox(param_frame, from_=0.0, to=1.0, increment=0.05, textvariable=self._spectral_thresh_var, width=8).grid(row=4, column=1, sticky=tk.EW, padx=2, pady=2)

            ttk.Label(param_frame, text="Spectral Weight:").grid(row=5, column=0, sticky=tk.W, padx=2, pady=2)
            self._spectral_weight_var = tk.DoubleVar(value=0.4)
            ttk.Spinbox(param_frame, from_=0.0, to=1.0, increment=0.1, textvariable=self._spectral_weight_var, width=8).grid(row=5, column=1, sticky=tk.EW, padx=2, pady=2)

            param_frame.columnconfigure(1, weight=1)

            # Store parameters
            self._match_params = MatchParameters.preset_tof()

            # Compound tree
            tree_frame = ttk.Frame(left_frame)
            tree_frame.grid(row=3, column=0, sticky=tk.NSEW)
            tree_frame.rowconfigure(0, weight=1)
            tree_frame.columnconfigure(0, weight=1)

            self._compound_tree = ttk.Treeview(tree_frame, columns=("Name", "M/Z", "RT", "Area", "Height"), show="tree headings", height=20)
            self._compound_tree.column("#0", width=1, stretch=False)
            self._compound_tree.column("Name", width=180)
            self._compound_tree.column("M/Z", width=70)
            self._compound_tree.column("RT", width=60)
            self._compound_tree.column("Area", width=90)
            self._compound_tree.column("Height", width=90)
            self._compound_tree.heading("#0", text="")
            self._compound_tree.heading("Name", text="Name")
            self._compound_tree.heading("M/Z", text="M/Z")
            self._compound_tree.heading("RT", text="RT")
            self._compound_tree.heading("Area", text="Area")
            self._compound_tree.heading("Height", text="Height")
            self._compound_tree.grid(row=0, column=0, sticky=tk.NSEW)
            self._compound_tree.bind("<<TreeviewSelect>>", self._on_compound_selected)

            scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._compound_tree.yview)
            scrollbar.grid(row=0, column=1, sticky=tk.NS)
            self._compound_tree.config(yscroll=scrollbar.set)

            # ── Middle panel: Mass Spectrum Graph ────────────────
            mid_frame = ttk.LabelFrame(self, text=" Mass Spectrum ", padding=4)
            mid_frame.grid(row=1, column=1, columnspan=2, sticky=tk.NSEW, padx=(0, 6))
            mid_frame.rowconfigure(0, weight=1)
            mid_frame.columnconfigure(0, weight=1)

            if MATPLOTLIB_AVAILABLE:
                self._spectrum_figure = Figure(figsize=(8, 4), dpi=80)
                self._spectrum_canvas = FigureCanvasTkAgg(self._spectrum_figure, master=mid_frame)
                self._spectrum_canvas.get_tk_widget().grid(row=0, column=0, sticky=tk.NSEW)
            else:
                self._spectrum_text = scrolledtext.ScrolledText(mid_frame, height=20, width=60, font=("Courier", 9))
                self._spectrum_text.grid(row=0, column=0, sticky=tk.NSEW)
                self._spectrum_text.config(state=tk.DISABLED)

            # ── Right panel: Metadata + Peaks ────────────────────
            right_frame = ttk.LabelFrame(self, text=" Metadata & Peaks ", padding=4)
            right_frame.grid(row=1, column=3, sticky=tk.NSEW)
            right_frame.rowconfigure(1, weight=1)
            right_frame.rowconfigure(3, weight=1)

            ttk.Label(right_frame, text="No compound selected", foreground="#666666").grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 4))

            # Metadata text
            self._meta_text = scrolledtext.ScrolledText(right_frame, height=10, width=30, font=("Courier", 8))
            self._meta_text.grid(row=1, column=0, columnspan=2, sticky=tk.NSEW, pady=(0, 4))
            self._meta_text.config(state=tk.DISABLED)

            # Peak table
            ttk.Label(right_frame, text="Peaks:", foreground="#333333").grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(0, 2))

            peak_frame = ttk.Frame(right_frame)
            peak_frame.grid(row=3, column=0, columnspan=2, sticky=tk.NSEW)
            peak_frame.rowconfigure(0, weight=1)
            peak_frame.columnconfigure(0, weight=1)

            self._peak_tree = ttk.Treeview(peak_frame, columns=("M/Z", "Intensity", "Charge", "Annotation"),
                                           show="headings", height=8)
            self._peak_tree.column("M/Z", width=60)
            self._peak_tree.column("Intensity", width=65)
            self._peak_tree.column("Charge", width=50)
            self._peak_tree.column("Annotation", width=80)
            self._peak_tree.heading("M/Z", text="M/Z")
            self._peak_tree.heading("Intensity", text="Intensity")
            self._peak_tree.heading("Charge", text="Charge")
            self._peak_tree.heading("Annotation", text="Annotation")
            self._peak_tree.grid(row=0, column=0, sticky=tk.NSEW)

            peak_scroll = ttk.Scrollbar(peak_frame, orient=tk.VERTICAL, command=self._peak_tree.yview)
            peak_scroll.grid(row=0, column=1, sticky=tk.NS)
            self._peak_tree.config(yscroll=peak_scroll.set)

            self._edit_btn = ttk.Button(right_frame, text="Edit", command=self._edit_metadata, state=tk.DISABLED)
            self._edit_btn.grid(row=4, column=0, sticky=tk.EW, pady=(4, 0))
            self._del_btn = ttk.Button(right_frame, text="Delete", command=self._delete_compound, state=tk.DISABLED)
            self._del_btn.grid(row=4, column=1, sticky=tk.EW, pady=(4, 0), padx=(4, 0))

        except Exception as e:
            print(f"Error building CEF viewer UI: {e}")
            traceback.print_exc()

    def _load_cef(self):
        """Load CEF file(s)."""
        files = filedialog.askopenfilenames(
            title="Select CEF files to load",
            filetypes=[("CEF files", "*.cef"), ("All files", "*.*")]
        )
        if not files:
            return

        if not self._db:
            project_dir = Path.cwd()
            self._db = CEFDatabase(project_dir)

        # Show progress dialog
        self._progress_dialog = tk.Toplevel(self.master)
        self._progress_dialog.title("Loading CEF Files")
        self._progress_dialog.geometry("300x100")
        self._progress_dialog.resizable(False, False)

        ttk.Label(self._progress_dialog, text="Loading CEF files...").pack(pady=10)
        self._progress_var = tk.DoubleVar(value=0)
        self._progress_bar = ttk.Progressbar(self._progress_dialog, variable=self._progress_var,
                                            maximum=len(files), mode='determinate')
        self._progress_bar.pack(fill=tk.X, padx=10, pady=5)
        self._status_label = ttk.Label(self._progress_dialog, text="")
        self._status_label.pack(pady=5)

        self._running = True
        threading.Thread(target=self._import_files_threaded, args=(files,), daemon=True).start()

    def _clear_data(self):
        """Clear all loaded CEF files and data."""
        if not self._db:
            messagebox.showinfo("Clear Data", "No data loaded")
            return

        if messagebox.askyesno("Clear Data", "Clear all loaded CEF files and compounds? This cannot be undone."):
            try:
                # Delete the database file
                if self._db.db_path.exists():
                    self._db.db_path.unlink()
                self._db = None
                self._cef_files = []
                self._compounds_cache = []
                self._current_compound = None
                self._compound_tree.delete(*self._compound_tree.get_children())
                self._meta_text.config(state=tk.NORMAL)
                self._meta_text.delete("1.0", tk.END)
                self._meta_text.config(state=tk.DISABLED)
                self._peak_tree.delete(*self._peak_tree.get_children())
                self._status_var.set("All data cleared")
                messagebox.showinfo("Clear Data", "All CEF files and data cleared successfully")
            except Exception as e:
                messagebox.showerror("Clear Error", f"Error clearing data: {e}")

    def _import_files_threaded(self, files):
        """Import CEF files in background thread."""
        try:
            total_imported = 0
            for i, file_path in enumerate(files):
                filename = Path(file_path).name
                self._status_label.config(text=f"Loading {filename}...")
                self._progress_dialog.update()

                compounds = parse_cef(file_path)
                _, imported = self._db.import_compounds(file_path, compounds)
                total_imported += imported

                self._progress_var.set(i + 1)
                self._progress_dialog.update()

            self._status_var.set(f"Imported {total_imported} compounds from {len(files)} file(s)")
            self._progress_dialog.destroy()
            self._refresh_compound_list()
        except Exception as e:
            self._status_var.set(f"Error: {e}")
            messagebox.showerror("Import Error", str(e))
            if hasattr(self, '_progress_dialog'):
                self._progress_dialog.destroy()
        finally:
            self._running = False

    def _refresh_compound_list(self):
        """Refresh the compound tree view with hierarchical file structure."""
        self._compound_tree.delete(*self._compound_tree.get_children())
        if not self._db:
            return

        # Update CEF file list
        self._cef_files = self._db.get_all_cef_files()
        self._compounds_cache = []

        # Build hierarchical tree: File -> Compounds
        for cef_file in self._cef_files:
            file_item = self._compound_tree.insert("", tk.END,
                                                   text=f"{cef_file['filename']} ({cef_file['compound_count']})",
                                                   open=True)

            # Get compounds for this file
            file_compounds = self._db.get_compounds_by_file(cef_file['id'])
            self._compounds_cache.extend(file_compounds)

            for compound in file_compounds:
                # Determine display name: use RT@M/Z for unidentified, molecule name for identified
                is_identified = compound.get('is_identified', False)
                if is_identified:
                    display_name = compound['name']
                else:
                    display_name = f"{compound['rt']:.2f}@{compound['mass']:.4f}"

                # Format area and height for display
                area_str = f"{compound.get('area', 0):.0f}" if compound.get('area') else ""
                height_str = f"{compound.get('height', 0):.0f}" if compound.get('height') else ""

                # Store compound ID as the item ID for later retrieval
                compound_item = self._compound_tree.insert(file_item, tk.END,
                                                           iid=f"compound_{compound['id']}",
                                                           text="",
                                                           values=(
                                                               display_name,
                                                               f"{compound['mass']:.3f}",
                                                               f"{compound['rt']:.2f}",
                                                               area_str,
                                                               height_str
                                                           ))

        # Hide file filtering (less relevant with hierarchical view)
        self._file_var.set("All")

    def _on_compound_selected(self, event):
        """Handle compound selection in tree."""
        selection = self._compound_tree.selection()
        if not selection:
            return

        # Get the selected item ID
        selected_iid = selection[0]
        if not selected_iid.startswith("compound_"):
            # File node selected, not a compound
            return

        # Extract compound ID from iid
        try:
            compound_id = int(selected_iid.replace("compound_", ""))
            compound = self._db.get_compound(compound_id)
            if compound:
                self._display_compound(compound)
        except (ValueError, AttributeError):
            pass

    def _get_current_params(self) -> MatchParameters:
        """Build MatchParameters from current UI values."""
        return MatchParameters(
            method=self._method_var.get(),
            mass_ppm=self._ppm_var.get(),
            mass_da=self._da_var.get(),
            rt_tolerance=self._rt_tol_var.get(),
            spectral_threshold=self._spectral_thresh_var.get(),
            spectral_weight=self._spectral_weight_var.get()
        )

    def _display_compound(self, compound: Dict):
        """Display compound details."""
        self._current_compound = compound

        # Update metadata
        self._meta_text.config(state=tk.NORMAL)
        self._meta_text.delete("1.0", tk.END)
        source_info = ", ".join(compound.get('source_files', [])) or "Unknown"
        is_identified = compound.get('is_identified', False)
        compound_type = "Identified" if is_identified else "Unidentified"
        molecule_info = ""
        if is_identified:
            mol_name = compound.get('molecule_name', '')
            mol_formula = compound.get('molecule_formula', '')
            molecule_info = f"Molecule: {mol_name}\nFormula: {mol_formula}\n"

        meta_str = f"""Type: {compound_type}
Name: {compound['name']}
M/Z: {compound['mass']:.4f}
RT: {compound['rt']:.3f} min
{molecule_info}Algorithm: {compound['algorithm']}
Device: {compound['device_type']}
Polarity: {compound['polarity']}
Consolidated: {compound['is_consolidated']}
From: {source_info}
"""
        self._meta_text.insert(tk.END, meta_str)
        self._meta_text.config(state=tk.DISABLED)

        # Update spectrum graph
        if MATPLOTLIB_AVAILABLE:
            self._spectrum_figure.clear()
            ax = self._spectrum_figure.add_subplot(111)

            peaks = sorted(compound['peaks'], key=lambda p: p['mz'])
            if peaks:
                mz_values = [p['mz'] for p in peaks]
                intensity_values = [p['intensity'] for p in peaks]

                ax.bar(mz_values, intensity_values, width=0.5, color='steelblue', edgecolor='navy', alpha=0.7)
                ax.set_xlabel('m/z', fontsize=10)
                ax.set_ylabel('Intensity', fontsize=10)
                ax.set_title(f"{compound['name']} - Mass Spectrum", fontsize=11)
                ax.grid(axis='y', alpha=0.3)

            self._spectrum_figure.tight_layout()
            self._spectrum_canvas.draw()
        else:
            # Fallback to text if matplotlib not available
            self._spectrum_text.config(state=tk.NORMAL)
            self._spectrum_text.delete("1.0", tk.END)
            spectrum_str = "M/Z\t\tIntensity\tCharge\tAnnotation\n"
            spectrum_str += "─" * 60 + "\n"
            for peak in sorted(compound['peaks'], key=lambda p: p['mz']):
                spectrum_str += f"{peak['mz']:.3f}\t\t{peak['intensity']:.1f}\t{peak['charge']}\t{peak['annotation'] or ''}\n"
            self._spectrum_text.insert(tk.END, spectrum_str)
            self._spectrum_text.config(state=tk.DISABLED)

        # Update peak table
        self._peak_tree.delete(*self._peak_tree.get_children())
        for peak in sorted(compound['peaks'], key=lambda p: p['mz']):
            self._peak_tree.insert("", tk.END, values=(
                f"{peak['mz']:.4f}",
                f"{peak['intensity']:.1f}",
                peak['charge'],
                peak['annotation'] or ''
            ))

        self._edit_btn.config(state=tk.NORMAL)
        self._del_btn.config(state=tk.NORMAL)

    def _edit_metadata(self):
        """Edit compound metadata."""
        if not self._current_compound:
            return
        messagebox.showinfo("Edit Metadata", "Edit dialog coming soon")

    def _delete_compound(self):
        """Delete selected compound."""
        if not self._current_compound or not self._db:
            return
        if messagebox.askyesno("Delete", f"Delete {self._current_compound['name']}?"):
            self._db.delete_compound(self._current_compound['id'])
            self._refresh_compound_list()

    def _identify_duplicates_threaded(self):
        """Identify duplicates in background thread."""
        try:
            params = self._get_current_params()
            self._status_var.set(f"Identifying duplicates ({params.method})...")

            all_compounds = self._db.get_all_compounds()
            groups = CEFConsolidator.identify_duplicate_groups(all_compounds, params)

            if not groups:
                self._status_var.set("No duplicates found")
                messagebox.showinfo("Consolidation", "No duplicate compounds found")
                return

            self._show_consolidation_preview(groups)
        except Exception as e:
            self._status_var.set(f"Error: {e}")
            messagebox.showerror("Consolidation Error", str(e))
        finally:
            self._running = False

    def _show_consolidation_preview(self, groups):
        """Show consolidation preview dialog with confidence filtering."""
        # Create top-level window
        dialog = tk.Toplevel(self.master)
        dialog.title("Consolidation Preview")
        dialog.geometry("600x600")
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)

        # Confidence threshold control
        control_frame = ttk.Frame(dialog)
        control_frame.grid(row=0, column=0, sticky=tk.EW, padx=4, pady=4)

        ttk.Label(control_frame, text="Confidence Threshold:").pack(side=tk.LEFT, padx=(0, 4))
        threshold_var = tk.DoubleVar(value=0.5)
        threshold_slider = ttk.Scale(control_frame, from_=0.0, to=1.0, variable=threshold_var, orient=tk.HORIZONTAL)
        threshold_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        threshold_label = ttk.Label(control_frame, text="0.50", width=5)
        threshold_label.pack(side=tk.LEFT, padx=4)

        info_label = ttk.Label(control_frame, text=f"Found {len(groups)} groups", foreground="#666666")
        info_label.pack(side=tk.LEFT, padx=8)

        # Scrollable frame for groups
        canvas = tk.Canvas(dialog)
        scrollbar = ttk.Scrollbar(dialog, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.config(yscrollcommand=scrollbar.set)
        canvas.grid(row=1, column=0, sticky=tk.NSEW)
        scrollbar.grid(row=1, column=1, sticky=tk.NS)

        def update_display(*args):
            # Clear existing groups
            for widget in scrollable_frame.winfo_children():
                widget.destroy()

            threshold = threshold_var.get()
            threshold_label.config(text=f"{threshold:.2f}")
            filtered_groups = [g for g in groups if g.confidence >= threshold]
            info_label.config(text=f"Showing {len(filtered_groups)}/{len(groups)} groups")

            # Display filtered groups
            for i, group in enumerate(filtered_groups):
                group_frame = ttk.LabelFrame(scrollable_frame, text=f"Group {i+1}: {', '.join(group.names)}", padding=4)
                group_frame.pack(fill=tk.BOTH, padx=4, pady=4)

                ttk.Label(group_frame, text=f"Confidence: {group.confidence:.2f}").pack(anchor=tk.W)
                ttk.Label(group_frame, text=f"Master m/z: {group.master_mass:.4f}, RT: {group.master_rt:.2f}").pack(anchor=tk.W)

                # List compounds
                ttk.Label(group_frame, text="Compounds:").pack(anchor=tk.W, padx=8, pady=(4, 0))
                for name in group.names:
                    ttk.Label(group_frame, text=f"- {name}").pack(anchor=tk.W, padx=16)

            canvas.configure(scrollregion=canvas.bbox("all"))

        threshold_slider.config(command=update_display)
        update_display()  # Initial display

        # Buttons
        button_frame = ttk.Frame(dialog)
        button_frame.grid(row=2, column=0, columnspan=2, sticky=tk.EW, padx=4, pady=4)

        def approve_all():
            threshold = threshold_var.get()
            filtered_groups = [g for g in groups if g.confidence >= threshold]
            for group in filtered_groups:
                self._db.consolidate_group(group.compound_ids, group.suggested_master_name)
            self._refresh_compound_list()
            self._status_var.set(f"Consolidated {len(filtered_groups)} groups")
            dialog.destroy()

        ttk.Button(button_frame, text="Approve All", command=approve_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=2)

    def _consolidate(self):
        """Identify and consolidate duplicates."""
        if not self._db:
            messagebox.showwarning("No Database", "Load CEF files first")
            return

        self._running = True
        threading.Thread(target=self._identify_duplicates_threaded, daemon=True).start()

    def _align(self):
        """Find and display aligned compounds."""
        if not self._db:
            messagebox.showwarning("No Database", "Load CEF files first")
            return

        all_compounds = self._db.get_all_compounds()
        if not all_compounds:
            messagebox.showwarning("No Compounds", "Load CEF files first")
            return

        self._running = True
        threading.Thread(target=self._align_threaded, args=(all_compounds,), daemon=True).start()

    def _align_threaded(self, all_compounds):
        """Find aligned compounds in background thread."""
        try:
            params = self._get_current_params()
            self._status_var.set("Finding aligned compounds...")

            # Run alignment with current parameters
            matches = CEFMatcher.find_all_matches(all_compounds, params)

            if not matches:
                self._status_var.set("No alignments found")
                messagebox.showinfo("Alignment", "No aligned compounds found")
                return

            self._status_var.set(f"Found {len(matches)} alignments")

            # Show alignment table
            dialog = tk.Toplevel(self.master)
            dialog.title(f"Alignment Visualization ({params.method})")
            dialog.geometry("900x600")

            from .cef_visualizer import MatchTableViewer
            viewer = MatchTableViewer(dialog)
            viewer.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

            # Convert Match objects to dicts for viewer
            match_dicts = []
            for match in matches:
                match_dicts.append({
                    'compound_id_1': match.compound_id_1,
                    'compound_id_2': match.compound_id_2,
                    'name_1': match.name_1,
                    'name_2': match.name_2,
                    'mass_1': match.mass_1,
                    'mass_2': match.mass_2,
                    'rt_1': match.rt_1,
                    'rt_2': match.rt_2,
                    'delta_mass': match.delta_mass,
                    'delta_rt': match.delta_rt,
                    'confidence': match.confidence,
                    'spectral_similarity': match.spectral_similarity
                })

            viewer.display_matches(match_dicts)

        except Exception as e:
            self._status_var.set(f"Match error: {e}")
            messagebox.showerror("Match Error", str(e))
        finally:
            self._running = False

    def _export_aligned(self):
        """Export aligned compounds (before consolidation)."""
        if not self._db:
            messagebox.showwarning("No Database", "Load CEF files first")
            return

        output_file = filedialog.asksaveasfilename(
            title="Export aligned compounds",
            filetypes=[("CEF files", "*.cef"), ("CSV files", "*.csv"), ("All files", "*.*")],
            defaultextension=".cef"
        )
        if not output_file:
            return

        self._running = True
        threading.Thread(target=self._export_threaded, args=(output_file, False), daemon=True).start()

    def _export(self):
        """Export consolidated compounds."""
        if not self._db:
            messagebox.showwarning("No Database", "Load CEF files first")
            return

        output_file = filedialog.asksaveasfilename(
            title="Export consolidated compounds",
            filetypes=[("CEF files", "*.cef"), ("CSV files", "*.csv"), ("All files", "*.*")],
            defaultextension=".cef"
        )
        if not output_file:
            return

        self._running = True
        threading.Thread(target=self._export_threaded, args=(output_file, True), daemon=True).start()

    def _export_threaded(self, output_file, consolidated_only=True):
        """Export compounds to CEF or CSV format."""
        try:
            output_path = Path(output_file)
            self._status_var.set("Exporting compounds...")
            all_compounds = self._db.get_all_compounds()

            if not all_compounds:
                messagebox.showwarning("Export", "No compounds to export")
                return

            # Filter by consolidation status if needed
            if consolidated_only:
                compounds_to_export = [c for c in all_compounds if c['is_consolidated']]
                if not compounds_to_export:
                    messagebox.showwarning("Export", "No consolidated compounds to export. Run Consolidate first.")
                    return
            else:
                compounds_to_export = all_compounds

            if output_path.suffix.lower() == '.cef':
                self._export_to_cef(output_path, compounds_to_export)
            else:
                self._export_to_csv(output_path, compounds_to_export)

            export_type = "consolidated" if consolidated_only else "aligned"
            self._status_var.set(f"Exported {len(compounds_to_export)} {export_type} compounds to {output_path.name}")
            messagebox.showinfo("Export Success", f"Exported {len(compounds_to_export)} {export_type} compounds")
        except Exception as e:
            self._status_var.set(f"Export error: {e}")
            messagebox.showerror("Export Error", str(e))
        finally:
            self._running = False

    def _export_to_csv(self, output_path: Path, compounds: list):
        """Export compounds to CSV format."""
        import csv

        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'id', 'name', 'mass', 'rt', 'area', 'height', 'algorithm', 'device_type',
                'polarity', 'is_consolidated', 'peak_count', 'source_files'
            ])
            writer.writeheader()

            for compound in compounds:
                source_files = ', '.join(compound.get('source_files', []))
                writer.writerow({
                    'id': compound['id'],
                    'name': compound['name'],
                    'mass': f"{compound['mass']:.6f}",
                    'rt': f"{compound['rt']:.3f}",
                    'area': f"{compound.get('area', 0):.0f}" if compound.get('area') else '',
                    'height': f"{compound.get('height', 0):.0f}" if compound.get('height') else '',
                    'algorithm': compound['algorithm'] or '',
                    'device_type': compound['device_type'] or '',
                    'polarity': compound['polarity'],
                    'is_consolidated': 'Yes' if compound['is_consolidated'] else 'No',
                    'peak_count': len(compound['peaks']),
                    'source_files': source_files
                })

    def _export_to_cef(self, output_path: Path, compounds: list):
        """Export compounds to CEF format."""
        from .cef_parser import CEFCompound, CEFLocation, CEFSpectrum, CEFPeak, write_cef

        cef_compounds = []
        for compound in compounds:
            location = CEFLocation(
                molecular_mass=compound['mass'],
                retention_time=compound['rt'],
                area=compound.get('area'),
                height=compound.get('height')
            )

            peaks = []
            for peak in compound.get('peaks', []):
                cef_peak = CEFPeak(
                    mz=peak['mz'],
                    intensity=peak['intensity'],
                    charge=peak.get('charge', 1),
                    annotation=peak.get('annotation')
                )
                peaks.append(cef_peak)

            spectrum = CEFSpectrum(
                spectrum_type="MFE",
                polarity=compound['polarity'],
                algorithm=compound.get('algorithm', ''),
                peaks=peaks
            )

            cef_compound = CEFCompound(
                name=compound['name'],
                location=location,
                spectrum=spectrum,
                algorithm=compound.get('algorithm', ''),
                device_type=compound.get('device_type'),
                molecule_name=compound.get('molecule_name'),
                molecule_formula=compound.get('molecule_formula'),
                is_identified=compound.get('is_identified', False),
                original_xml=""
            )
            cef_compounds.append(cef_compound)

        write_cef(output_path, cef_compounds)
