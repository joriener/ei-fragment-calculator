"""
generate_workflow_image.py
==========================
Generates a workflow diagram PNG for the EI Fragment Calculator.
Run from the project root:
    python scripts/generate_workflow_image.py
Output: docs/workflow.png
"""

import os
import sys

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
except ImportError:
    print("matplotlib is required to generate the workflow image.")
    print("Install with:  pip install matplotlib")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------
FIG_W, FIG_H = 14, 20   # inches
COLORS = {
    "input":     "#2196F3",   # blue
    "process":   "#4CAF50",   # green
    "decision":  "#FF9800",   # orange
    "output":    "#9C27B0",   # purple
    "isotope":   "#00BCD4",   # cyan
    "electron":  "#F44336",   # red
    "arrow":     "#455A64",
    "bg":        "#FAFAFA",
    "text_dark": "#212121",
    "text_light":"#FFFFFF",
}

STEPS = [
    # (label, sublabel, color_key, y_center)
    ("INPUT", "SDF File\n(molecular formula + EI spectral peaks)",
     "input", 0.93),

    ("PARSE SDF", "Extract compound name, formula field,\npeak data field per record",
     "process", 0.80),

    ("PARSE FORMULA", "Decompose Summenformel string\ninto element → count dict\n(loaded from elements.csv)",
     "process", 0.67),

    ("FOR EACH PEAK\n(nominal m/z)", "Iterate over all unit-mass peaks\nin the EI spectrum",
     "decision", 0.54),

    ("ENUMERATE CANDIDATES", "Cartesian product of element counts\n0 … max_parent_count per element\n(mass conservation upper bound)",
     "process", 0.41),

    ("FILTER: MASS WINDOW", "ion_mass = neutral_mass ± m_electron\n|ion_mass − nominal_mz| ≤ tolerance",
     "electron", 0.30),

    ("FILTER: DBE CHECK", "DBE = 1 + C − H/2 + N/2 − halogen/2 …\nReject if DBE < 0 or non-multiple of 0.5",
     "decision", 0.20),

    ("ISOTOPE PATTERN\n(optional --isotope)", "Polynomial convolution of\nper-element isotope distributions\nfrom elements.csv abundances",
     "isotope", 0.11),

    ("OUTPUT", "Ranked candidates per peak:\nformula | neutral mass | ion m/z\nΔmass | DBE | isotope pattern",
     "output", 0.02),
]

ELECTRON_SIDE = {
    "x": 0.78,
    "y": 0.30,
    "text": "Electron mode\n──────────────\nremove: m/z = M − mₑ\nadd:    m/z = M + mₑ\nnone:   m/z = M\n\nmₑ = 0.000549 Da",
}

CSV_SIDE = {
    "x": 0.10,
    "y": 0.67,
    "text": "elements.csv\n──────────────\nSymbol, Isotope\nExactMass\nAbundance\nValence",
}


def draw_box(ax, cx, cy, width, height, label, sublabel, color, radius=0.018):
    """Draw a rounded rectangle with title + subtitle text."""
    x = cx - width / 2
    y = cy - height / 2
    box = FancyBboxPatch(
        (x, y), width, height,
        boxstyle=f"round,pad=0",
        facecolor=color, edgecolor="white",
        linewidth=2, zorder=3,
        transform=ax.transAxes, clip_on=False,
    )
    ax.add_patch(box)

    # Title
    ax.text(cx, cy + height * 0.12, label,
            transform=ax.transAxes,
            ha="center", va="center",
            fontsize=11, fontweight="bold",
            color=COLORS["text_light"], zorder=4)

    # Subtitle
    if sublabel:
        ax.text(cx, cy - height * 0.18, sublabel,
                transform=ax.transAxes,
                ha="center", va="center",
                fontsize=8, color=COLORS["text_light"],
                zorder=4, linespacing=1.4)


def draw_side_note(ax, cx, cy, text, color):
    """Draw a small side annotation box."""
    box = FancyBboxPatch(
        (cx - 0.11, cy - 0.065), 0.22, 0.13,
        boxstyle="round,pad=0",
        facecolor=color, alpha=0.15,
        edgecolor=color, linewidth=1.5,
        transform=ax.transAxes, clip_on=False, zorder=2,
    )
    ax.add_patch(box)
    ax.text(cx, cy, text,
            transform=ax.transAxes,
            ha="center", va="center",
            fontsize=7.5, color=COLORS["text_dark"],
            zorder=3, linespacing=1.4,
            family="monospace")


def main():
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    fig.patch.set_facecolor(COLORS["bg"])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # Title
    ax.text(0.5, 0.975,
            "EI Fragment Exact-Mass Calculator — Workflow",
            transform=ax.transAxes,
            ha="center", va="center",
            fontsize=15, fontweight="bold",
            color=COLORS["text_dark"])

    box_w, box_h = 0.52, 0.085
    cx = 0.5

    # Draw boxes
    for label, sublabel, color_key, y in STEPS:
        draw_box(ax, cx, y, box_w, box_h,
                 label, sublabel, COLORS[color_key])

    # Draw arrows between boxes
    for i in range(len(STEPS) - 1):
        y_top    = STEPS[i][3] - box_h / 2
        y_bottom = STEPS[i + 1][3] + box_h / 2
        ax.annotate(
            "", xy=(cx, y_bottom + 0.002),
            xytext=(cx, y_top - 0.002),
            xycoords="axes fraction", textcoords="axes fraction",
            arrowprops=dict(
                arrowstyle="-|>",
                color=COLORS["arrow"],
                lw=2.0,
                mutation_scale=18,
            ),
            zorder=2,
        )

    # Side notes
    draw_side_note(ax, ELECTRON_SIDE["x"], ELECTRON_SIDE["y"],
                   ELECTRON_SIDE["text"], COLORS["electron"])
    ax.annotate(
        "", xy=(cx + box_w / 2, STEPS[5][3]),
        xytext=(ELECTRON_SIDE["x"] - 0.11, ELECTRON_SIDE["y"]),
        xycoords="axes fraction", textcoords="axes fraction",
        arrowprops=dict(arrowstyle="-", color=COLORS["electron"],
                        lw=1.2, linestyle="dashed"),
        zorder=1,
    )

    draw_side_note(ax, CSV_SIDE["x"], CSV_SIDE["y"],
                   CSV_SIDE["text"], COLORS["input"])
    ax.annotate(
        "", xy=(cx - box_w / 2, STEPS[2][3]),
        xytext=(CSV_SIDE["x"] + 0.11, CSV_SIDE["y"]),
        xycoords="axes fraction", textcoords="axes fraction",
        arrowprops=dict(arrowstyle="-", color=COLORS["input"],
                        lw=1.2, linestyle="dashed"),
        zorder=1,
    )

    # Legend
    legend_items = [
        mpatches.Patch(color=COLORS["input"],    label="Input / Data source"),
        mpatches.Patch(color=COLORS["process"],  label="Processing step"),
        mpatches.Patch(color=COLORS["decision"], label="Loop / Decision"),
        mpatches.Patch(color=COLORS["electron"], label="Electron-mass correction"),
        mpatches.Patch(color=COLORS["isotope"],  label="Isotope pattern (optional)"),
        mpatches.Patch(color=COLORS["output"],   label="Output"),
    ]
    ax.legend(
        handles=legend_items,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.01),
        ncol=3,
        fontsize=8,
        framealpha=0.9,
        edgecolor="#CCCCCC",
    )

    # Save
    out_dir = os.path.join(os.path.dirname(__file__), "..", "docs")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "workflow.png")
    fig.savefig(out_path, dpi=150, bbox_inches="tight",
                facecolor=COLORS["bg"])
    plt.close(fig)
    print(f"Workflow image saved to: {os.path.abspath(out_path)}")


if __name__ == "__main__":
    main()
