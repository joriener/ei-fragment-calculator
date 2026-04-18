"""
cef_visualizer.py
=================
Visualization components for match data and consolidation analysis.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import List, Dict, Optional, Tuple
import math

try:
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    import numpy as np
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


class MatchHeatmapViewer(ttk.Frame):
    """Heat map visualization for compound matches between two CEF files."""

    def __init__(self, master):
        super().__init__(master)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        if not MATPLOTLIB_AVAILABLE:
            ttk.Label(self, text="matplotlib not available for visualization").pack()
            return

        # Toolbar
        toolbar = ttk.Frame(self)
        toolbar.grid(row=0, column=0, sticky=tk.EW, pady=(0, 4))
        toolbar.columnconfigure(1, weight=1)

        ttk.Label(toolbar, text="Confidence threshold:").pack(side=tk.LEFT, padx=(0, 4))
        self._threshold_var = tk.DoubleVar(value=0.5)
        ttk.Scale(toolbar, from_=0.0, to=1.0, variable=self._threshold_var,
                 orient=tk.HORIZONTAL, command=self._on_threshold_changed).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Label(toolbar, textvariable=self._threshold_var, width=6).pack(side=tk.LEFT, padx=4)

        # Canvas for heatmap
        self._figure = Figure(figsize=(10, 6), dpi=80)
        self._canvas = FigureCanvasTkAgg(self._figure, master=self)
        self._canvas.get_tk_widget().grid(row=1, column=0, sticky=tk.NSEW)

        self._match_data = None
        self._compounds_file_a = []
        self._compounds_file_b = []

    def display_matches(self, compounds_a: List[Dict], compounds_b: List[Dict],
                       matches: List[Dict], file_a_name: str = "File A", file_b_name: str = "File B"):
        """Display matches as heatmap."""
        self._compounds_file_a = compounds_a
        self._compounds_file_b = compounds_b
        self._match_data = matches
        self._file_a_name = file_a_name
        self._file_b_name = file_b_name
        self._update_heatmap()

    def _on_threshold_changed(self, value):
        """Handle threshold slider change."""
        self._update_heatmap()

    def _update_heatmap(self):
        """Render the heatmap with current threshold."""
        if not MATPLOTLIB_AVAILABLE or not self._match_data:
            return

        threshold = self._threshold_var.get()

        # Build matrix (compounds_a x compounds_b)
        n_a = len(self._compounds_file_a)
        n_b = len(self._compounds_file_b)

        if n_a == 0 or n_b == 0:
            return

        # Initialize matrix with zeros (no match)
        matrix = np.zeros((n_a, n_b))
        labels = [['' for _ in range(n_b)] for _ in range(n_a)]

        # Fill in matches
        for match in self._match_data:
            if match['confidence'] < threshold:
                continue

            # Find indices
            idx_a = next((i for i, c in enumerate(self._compounds_file_a)
                         if c['id'] == match['compound_id_1']), None)
            idx_b = next((i for i, c in enumerate(self._compounds_file_b)
                         if c['id'] == match['compound_id_2']), None)

            if idx_a is not None and idx_b is not None:
                matrix[idx_a, idx_b] = match['confidence']
                delta_mass = abs(match['mass_1'] - match['mass_2'])
                delta_rt = abs(match['rt_1'] - match['rt_2'])
                labels[idx_a][idx_b] = f"{match['confidence']:.2f}\n(m:{delta_mass:.3f},rt:{delta_rt:.2f})"

        # Render heatmap
        self._figure.clear()
        ax = self._figure.add_subplot(111)

        # Create heatmap
        im = ax.imshow(matrix, cmap='RdYlGn', aspect='auto', vmin=0, vmax=1)

        # Set ticks and labels
        compound_names_a = [c['name'][:20] for c in self._compounds_file_a]
        compound_names_b = [c['name'][:20] for c in self._compounds_file_b]

        ax.set_xticks(range(n_b))
        ax.set_yticks(range(n_a))
        ax.set_xticklabels(compound_names_b, rotation=45, ha='right', fontsize=8)
        ax.set_yticklabels(compound_names_a, fontsize=8)

        ax.set_xlabel(f"{self._file_b_name} Compounds")
        ax.set_ylabel(f"{self._file_a_name} Compounds")
        ax.set_title(f"Match Heatmap (Threshold: {threshold:.2f})")

        # Add colorbar
        cbar = self._figure.colorbar(im, ax=ax)
        cbar.set_label('Confidence')

        # Add text annotations for matches
        for i in range(n_a):
            for j in range(n_b):
                if matrix[i, j] > 0 and labels[i][j]:
                    text = ax.text(j, i, labels[i][j],
                                  ha="center", va="center", color="black", fontsize=6)

        self._figure.tight_layout()
        self._canvas.draw()


class MatchTableViewer(ttk.Frame):
    """Tabular view of match details."""

    def __init__(self, master):
        super().__init__(master)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # Toolbar
        toolbar = ttk.Frame(self)
        toolbar.grid(row=0, column=0, sticky=tk.EW, pady=(0, 4))

        ttk.Label(toolbar, text="Confidence threshold:").pack(side=tk.LEFT, padx=(0, 4))
        self._threshold_var = tk.DoubleVar(value=0.5)
        ttk.Scale(toolbar, from_=0.0, to=1.0, variable=self._threshold_var,
                 orient=tk.HORIZONTAL, command=self._on_threshold_changed).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        # Treeview
        tree_frame = ttk.Frame(self)
        tree_frame.grid(row=1, column=0, sticky=tk.NSEW)
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        columns = ("Name A", "M/Z A", "RT A", "Name B", "M/Z B", "RT B", "dM", "dRT", "Conf")
        self._tree = ttk.Treeview(tree_frame, columns=columns,
                                 show="tree headings", height=25)
        self._tree.column("#0", width=0, stretch=False)
        self._tree.column("Name A", width=100)
        self._tree.column("M/Z A", width=70)
        self._tree.column("RT A", width=60)
        self._tree.column("Name B", width=100)
        self._tree.column("M/Z B", width=70)
        self._tree.column("RT B", width=60)
        self._tree.column("dM", width=50)
        self._tree.column("dRT", width=50)
        self._tree.column("Conf", width=50)

        for col in columns:
            self._tree.heading(col, text=col)

        self._tree.grid(row=0, column=0, sticky=tk.NSEW)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        scrollbar.grid(row=0, column=1, sticky=tk.NS)
        self._tree.config(yscroll=scrollbar.set)

        self._matches = []

    def display_matches(self, matches: List[Dict]):
        """Display match list in table."""
        self._matches = matches
        self._update_table()

    def _on_threshold_changed(self, value):
        """Handle threshold change."""
        self._update_table()

    def _update_table(self):
        """Update table with current threshold."""
        self._tree.delete(*self._tree.get_children())

        threshold = self._threshold_var.get()

        for match in self._matches:
            if match['confidence'] < threshold:
                continue

            self._tree.insert("", tk.END, values=(
                match['name_1'],
                f"{match['mass_1']:.4f}",
                f"{match['rt_1']:.2f}",
                match['name_2'],
                f"{match['mass_2']:.4f}",
                f"{match['rt_2']:.2f}",
                f"{match['delta_mass']:.4f}",
                f"{match['delta_rt']:.3f}",
                f"{match['confidence']:.2f}"
            ))
