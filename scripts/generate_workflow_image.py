"""
generate_workflow_image.py
==========================
Generates a comprehensive workflow diagram PNG for the EI Fragment Calculator.
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
    from matplotlib.lines import Line2D
except ImportError:
    print("matplotlib is required to generate the workflow image.")
    print("Install with:  pip install matplotlib")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
C = {
    "input":     "#1565C0",   # dark blue
    "parse":     "#2E7D32",   # dark green
    "loop":      "#E65100",   # dark orange
    "filter":    "#6A1B9A",   # purple
    "optional":  "#00838F",   # teal
    "output":    "#AD1457",   # pink/red
    "enrich":    "#558B2F",   # olive green
    "note_bg":   "#F5F5F5",
    "note_bd":   "#BDBDBD",
    "arrow":     "#37474F",
    "bg":        "#FFFFFF",
    "title":     "#212121",
    "light_txt": "#FFFFFF",
    "dark_txt":  "#212121",
}

FIG_W, FIG_H = 16, 24


def box(ax, cx, cy, w, h, title, subtitle="", color="#444", radius=0.012,
        alpha=1.0, fontsize_title=9.5, fontsize_sub=7.5):
    """Draw a rounded coloured box with title and optional subtitle."""
    patch = FancyBboxPatch(
        (cx - w / 2, cy - h / 2), w, h,
        boxstyle=f"round,pad={radius}",
        facecolor=color, edgecolor="white",
        linewidth=1.8, zorder=3, alpha=alpha,
        transform=ax.transAxes, clip_on=False,
    )
    ax.add_patch(patch)
    # title
    title_y = cy + (h * 0.15 if subtitle else 0)
    ax.text(cx, title_y, title,
            transform=ax.transAxes, ha="center", va="center",
            fontsize=fontsize_title, fontweight="bold",
            color=C["light_txt"], zorder=4)
    # subtitle
    if subtitle:
        ax.text(cx, cy - h * 0.22, subtitle,
                transform=ax.transAxes, ha="center", va="center",
                fontsize=fontsize_sub, color=C["light_txt"],
                zorder=4, linespacing=1.35)


def note(ax, cx, cy, text, color_bd="#607D8B", width=0.20, height=0.07):
    """Small side annotation box."""
    patch = FancyBboxPatch(
        (cx - width / 2, cy - height / 2), width, height,
        boxstyle="round,pad=0.008",
        facecolor=C["note_bg"], edgecolor=color_bd,
        linewidth=1.2, zorder=3,
        transform=ax.transAxes, clip_on=False,
    )
    ax.add_patch(patch)
    ax.text(cx, cy, text,
            transform=ax.transAxes, ha="center", va="center",
            fontsize=7, color=C["dark_txt"], zorder=4,
            linespacing=1.35, family="monospace")


def arrow(ax, x0, y0, x1, y1, color=None, style="-|>", lw=1.8,
          dashed=False, label=""):
    color = color or C["arrow"]
    ls = (0, (4, 3)) if dashed else "solid"
    ax.annotate("",
                xy=(x1, y1), xytext=(x0, y0),
                xycoords="axes fraction", textcoords="axes fraction",
                arrowprops=dict(arrowstyle=style, color=color, lw=lw,
                                linestyle=ls, mutation_scale=14),
                zorder=2)
    if label:
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        ax.text(mx + 0.01, my, label,
                transform=ax.transAxes, fontsize=7,
                color=color, zorder=5)


def hline(ax, x0, x1, y, color=None, lw=1.4, dashed=False):
    color = color or C["arrow"]
    ls = "--" if dashed else "-"
    ax.plot([x0, x1], [y, y], transform=ax.transAxes,
            color=color, lw=lw, ls=ls, zorder=2)


def vline(ax, x, y0, y1, color=None, lw=1.4, dashed=False):
    color = color or C["arrow"]
    ls = "--" if dashed else "-"
    ax.plot([x, x], [y0, y1], transform=ax.transAxes,
            color=color, lw=lw, ls=ls, zorder=2)


def main():
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    fig.patch.set_facecolor(C["bg"])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    BW = 0.44   # main box width
    BH = 0.052  # main box height
    CX = 0.50   # centre x

    # ── Title ────────────────────────────────────────────────────────────────
    ax.text(CX, 0.975, "EI Fragment Exact-Mass Calculator",
            transform=ax.transAxes, ha="center", va="center",
            fontsize=17, fontweight="bold", color=C["title"])
    ax.text(CX, 0.958, "Processing Pipeline  —  v1.6.3",
            transform=ax.transAxes, ha="center", va="center",
            fontsize=11, color="#666666")

    # ── Block positions (y_centre) ────────────────────────────────────────
    Y = {
        "input":        0.920,
        "parse_sdf":    0.856,
        "parse_formula":0.792,
        "parallel":     0.728,
        "peak_loop":    0.660,
        "enumerate":    0.596,
        "mass_filter":  0.532,
        "dbe_filter":   0.468,
        "adv_filters":  0.404,
        "rank":         0.336,
        "best_only":    0.272,
        "progress":     0.208,
        "write_sdf":    0.148,
        "pubchem":      0.084,
        "output":       0.024,
    }

    # ── Main blocks ───────────────────────────────────────────────────────
    box(ax, CX, Y["input"], BW, BH,
        "INPUT  —  SDF File",
        "Molecular formula  ·  EI spectral peaks (m/z + intensity)",
        color=C["input"])

    box(ax, CX, Y["parse_sdf"], BW, BH,
        "PARSE SDF",
        r"Split on \$\$\$\$  ·  extract <NAME> / <FORMULA> / <MASS SPECTRAL PEAKS>",
        color=C["parse"])

    box(ax, CX, Y["parse_formula"], BW, BH,
        "PARSE FORMULA  +  LOAD ELEMENTS",
        "Summenformel → element:count dict  ·  monoisotopic masses from elements.csv",
        color=C["parse"])

    box(ax, CX, Y["parallel"], BW, BH,
        "PARALLEL WORKER POOL",
        "multiprocessing.Pool  ·  N = CPU cores  ·  one compound per task",
        color=C["loop"])

    box(ax, CX, Y["peak_loop"], BW, BH,
        "FOR EACH NOMINAL m/z PEAK",
        "Iterate over all unit-mass peaks in the EI spectrum",
        color=C["loop"])

    box(ax, CX, Y["enumerate"], BW, BH,
        "ENUMERATE CANDIDATES  (analytical)",
        "Compute max atom counts from parent composition & mass window\n"
        "Cartesian product → exact neutral masses per formula",
        color=C["parse"])

    box(ax, CX, Y["mass_filter"], BW, BH,
        "FILTER 1  —  MASS WINDOW",
        "|ion_mass − nominal_mz| ≤ tolerance (default ±0.5 Da)\n"
        "ion_mass = neutral_mass − mₑ  /  + mₑ  /  = neutral (mode)",
        color=C["filter"])

    box(ax, CX, Y["dbe_filter"], BW, BH,
        "FILTER 2  —  DBE  &  H-DEFICIENCY",
        "DBE = 1 + C − H/2 + N/2 − X/2  ·  must be ≥ 0 and integer or ½-integer\n"
        "H-deficiency:  H ≤ 2C + 2 + N − X  (Bredt / valence plausibility)",
        color=C["filter"])

    box(ax, CX, Y["adv_filters"], BW, BH,
        "FILTERS 3–5  —  ADVANCED CHEMICAL RULES",
        "Nitrogen rule  ·  Lewis & Senior valence-sum  ·  Isotope pattern score\n"
        "(polynomial convolution vs. observed M / M+1 / M+2 intensities)",
        color=C["filter"])

    box(ax, CX, Y["rank"], BW, BH,
        "RANK CANDIDATES",
        "Sort by: filter_passed ▸ |Δmass| ▸ isotope_score",
        color=C["parse"])

    box(ax, CX, Y["best_only"], BW, BH,
        "BEST-ONLY SELECTION  (optional --best-only)",
        "Keep only the top-ranked candidate per peak\n"
        "Peaks with no passing candidate are dropped",
        color=C["optional"])

    box(ax, CX, Y["progress"], BW, BH,
        "PROGRESS REPORTING",
        "[N / total]  printed per compound  ·  GUI progress bar updated",
        color=C["parse"])

    box(ax, CX, Y["write_sdf"], BW, BH,
        "SDF WRITER",
        "Nominal m/z → best exact mass (6 d.p.)  ·  NUM PEAKS updated\n"
        "All other fields & MOL block preserved verbatim",
        color=C["output"])

    box(ax, CX, Y["pubchem"], BW, BH,
        "PUBCHEM STRUCTURE FETCH  (optional --fetch-structures)",
        "CAS / name lookup via PubChem REST API\n"
        "Replaces 'No Structure' MOL block with real 2-D coordinates",
        color=C["enrich"])

    box(ax, CX, Y["output"], BW, BH,
        "OUTPUT",
        "Text report  ·  *-EXACT.sdf  with exact masses & 2-D structures",
        color=C["input"])

    # ── Arrows between main blocks ────────────────────────────────────────
    ys = list(Y.values())
    for i in range(len(ys) - 1):
        y_from = ys[i]   - BH / 2 - 0.003
        y_to   = ys[i+1] + BH / 2 + 0.003
        arrow(ax, CX, y_from, CX, y_to)

    # ── Side note: elements.csv ────────────────────────────────────────────
    NX_L = 0.115
    note(ax, NX_L, Y["parse_formula"],
         "elements.csv\n─────────────\nSymbol · Isotope\nExactMass · Abundance\nValence · 30 elements",
         color_bd=C["parse"], width=0.19, height=0.085)
    # dashed connector
    arrow(ax, NX_L + 0.095, Y["parse_formula"],
          CX - BW / 2, Y["parse_formula"],
          color=C["parse"], style="-", dashed=True)

    # ── Side note: electron mode ───────────────────────────────────────────
    NX_R = 0.885
    note(ax, NX_R, Y["mass_filter"],
         "Electron mode\n─────────────\nremove: M − mₑ (EI+)\nadd:    M + mₑ\nnone:   M\n\nmₑ = 0.000549 Da",
         color_bd=C["filter"], width=0.185, height=0.095)
    arrow(ax, CX + BW / 2, Y["mass_filter"],
          NX_R - 0.0925, Y["mass_filter"],
          color=C["filter"], style="-", dashed=True)

    # ── Side note: isotope detail ──────────────────────────────────────────
    note(ax, NX_L, Y["adv_filters"],
         "Isotope scoring\n─────────────\nPolynomial convolution\nper element × count\nPruned at 0.1 % rel.",
         color_bd=C["optional"], width=0.19, height=0.085)
    arrow(ax, NX_L + 0.095, Y["adv_filters"],
          CX - BW / 2, Y["adv_filters"],
          color=C["optional"], style="-", dashed=True)

    # ── Back-loop arrow: next compound ────────────────────────────────────
    loop_x  = CX + BW / 2 + 0.055
    top_y   = Y["parallel"]  + BH / 2
    bot_y   = Y["progress"]  - BH / 2

    vline(ax, loop_x, bot_y, top_y, color=C["loop"], lw=1.4, dashed=True)
    hline(ax, CX + BW / 2, loop_x, top_y, color=C["loop"], lw=1.4, dashed=True)
    hline(ax, CX + BW / 2, loop_x, bot_y, color=C["loop"], lw=1.4, dashed=True)
    ax.annotate("",
                xy=(CX + BW / 2 + 0.002, top_y),
                xytext=(loop_x, top_y),
                xycoords="axes fraction", textcoords="axes fraction",
                arrowprops=dict(arrowstyle="-|>", color=C["loop"],
                                lw=1.4, mutation_scale=12), zorder=2)
    ax.text(loop_x + 0.008, (top_y + bot_y) / 2,
            "next\ncompound",
            transform=ax.transAxes, fontsize=7, color=C["loop"],
            va="center", style="italic")

    # ── Inner back-loop: next peak ────────────────────────────────────────
    lx2     = CX - BW / 2 - 0.055
    top_y2  = Y["peak_loop"] + BH / 2
    bot_y2  = Y["rank"]      - BH / 2

    vline(ax, lx2, bot_y2, top_y2, color=C["loop"], lw=1.2, dashed=True)
    hline(ax, CX - BW / 2, lx2, top_y2, color=C["loop"], lw=1.2, dashed=True)
    hline(ax, CX - BW / 2, lx2, bot_y2, color=C["loop"], lw=1.2, dashed=True)
    ax.annotate("",
                xy=(CX - BW / 2 - 0.002, top_y2),
                xytext=(lx2, top_y2),
                xycoords="axes fraction", textcoords="axes fraction",
                arrowprops=dict(arrowstyle="-|>", color=C["loop"],
                                lw=1.2, mutation_scale=11), zorder=2)
    ax.text(lx2 - 0.075, (top_y2 + bot_y2) / 2,
            "next\npeak",
            transform=ax.transAxes, fontsize=7, color=C["loop"],
            va="center", style="italic")

    # ── Legend ────────────────────────────────────────────────────────────
    legend_items = [
        mpatches.Patch(color=C["input"],    label="Input / Output"),
        mpatches.Patch(color=C["parse"],    label="Processing step"),
        mpatches.Patch(color=C["loop"],     label="Loop / Parallelism"),
        mpatches.Patch(color=C["filter"],   label="Chemical filter"),
        mpatches.Patch(color=C["optional"], label="Optional step"),
        mpatches.Patch(color=C["enrich"],   label="External enrichment"),
    ]
    ax.legend(handles=legend_items, loc="lower center",
              bbox_to_anchor=(0.5, -0.005),
              ncol=3, fontsize=8.5,
              framealpha=0.95, edgecolor="#CCCCCC")

    # ── Save ──────────────────────────────────────────────────────────────
    out_dir = os.path.join(os.path.dirname(__file__), "..", "docs")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "workflow.png")
    fig.savefig(out_path, dpi=150, bbox_inches="tight",
                facecolor=C["bg"])
    plt.close(fig)
    print("Workflow image saved to:", os.path.abspath(out_path))


if __name__ == "__main__":
    main()
