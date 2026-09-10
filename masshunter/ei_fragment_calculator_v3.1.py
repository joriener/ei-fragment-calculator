# -*- coding: utf-8 -*-
#=============================================================================
# EI Fragment Calculator   v3.1
# IronPython 2.7.5 / .NET-only -- MassHunter Library Editor Script
#
# Lineage
#   UnitMass_to_ExactMass v1.2   Luca Godina
#   UnitMass_to_ExactMass v3.0   Joerg Riener  (12 -> 30 elements, 6 filters,
#                                4 structural rules, MSP/SDF export)
#   ei_fragment_calculator v3.1  Joerg Riener  (this file)
#
#   Renamed to align with the standalone CPython project of the same name
#   (github.com/joriener/ei-fragment-calculator). This file remains the
#   MassHunter-hosted tool: it is the only one of the two that writes exact
#   masses back into a MassHunter library XML.
#
# v3.1 changes -- performance and structure only. The chemistry (element
# table, filters, structural rules, scoring criteria) is byte-for-byte v3.0.
#
#   Option 1  find_subformulas() rewritten: element counts in a flat list
#             indexed by position instead of a dict keyed by symbol, plus a
#             suffix-mass bound that prunes branches which have already
#             spent too little to reach the target. v3.0 pruned only
#             downward. Per-compound preparation (_prepare_parent) is built
#             once and reused for every peak. Measured 7.2x on the hot path
#             in CPython, output identical.
#
#   Option 2  find_subformulas_cached(): enumeration memoised on
#             (parent formula, target nominal mass). Isomers share a parent
#             formula, so a library with many isomers reuses the same
#             enumeration. Bounded at 200,000 entries.
#
#   Option 3  pick_best_v3(): DBE computed once per candidate and handed to
#             both apply_all_filters() and score_formula(); candidates below
#             the -0.5 DBE floor are dropped before the expensive pass when
#             any possible candidate exists. The paper's aggressive
#             pre-filter (H/C ratio, zero-H, RDB range) is deliberately NOT
#             applied -- those are finite penalties, not floors, so
#             filtering on them would change results. See the docstring.
#
#   Option 4  Everything except the GUI moved to module level. v3.0 held all
#             ~50 functions inside _Run(); IronPython's DLR stores every
#             captured free variable in a generated MutableTuple whose size
#             is limited, and EXIMPORT_SDFMSP hit exactly that limit
#             ("ItemNNN is not defined for type") with a smaller file. Also
#             makes the pure functions testable with an extract-and-run
#             harness and visible to check_shared_blocks.py.
#
#   Option 5  encode_doubles() no longer round-trips through a string.
#             v3.0 called BitConverter.GetBytes(Double.Parse(str(v)));
#             Double.Parse(String) with no IFormatProvider uses
#             CurrentCulture AND NumberStyles.AllowThousands, so wherever
#             '.' is the GROUP separator it silently returned a DIFFERENT
#             number rather than raising (measured on CLR 4.0.30319 under
#             de-DE: "147.08" -> 14708.0). Both codecs now convert whole
#             arrays with one Buffer.BlockCopy and are locale-independent.
#
#   Option 6  build_compound_context() + assign_peak(): the
#             whitelist -> enumerate -> pick pipeline had two independent
#             call sites (convert and preview) that had to be kept in step
#             by hand. Both now call one implementation, so the preview
#             cannot drift from what the conversion writes.
#
#   v3.1.1    Browse and the MessageBoxes were owned by the MassHunter
#             MAIN form. The tool's own form is shown modal over that
#             form, so any child owned by it opens BEHIND the tool and
#             cannot be reached -- Browse appeared to do nothing. All six
#             dialog sites are now owned by the tool's own form. This
#             defect was inherited unchanged from v3.0.
#
#   v3.1.2    Browse buttons and the two path text boxes were off-screen.
#             The v3.1 content Panel was populated BEFORE it was added to
#             the form, so it was still the default 200 px wide and every
#             Right-anchored control recorded a negative right margin --
#             x=850 anchored Top|Right ended up near x=1682. The panel is
#             now docked to the form before any child is added. Same trap
#             the style guide documents for the banner "?" button.
#
#   Style     Agilent WinForms Desktop App Style Guide: 56-px brand banner,
#             version label, banner "?", About dialog with the verbatim
#             disclaimer, embedded readme, embedded multi-resolution icon,
#             module identity constants, palette and typography tokens, and
#             the UIState.SynchronizeInvoke entry point (section 10).
#
# Sections
#   0   Module identity, palette, typography, icon   (style guide 2/3/9/11)
#   1   MassHunter UI helpers
#   2   Physical constants  (30 elements, VALENCE, HILL, COMMON_LOSSES)
#   3   Isotope scoring
#   4   Formula utilities
#   5   Stable ion library
#   6   Post-enumeration filters
#   7   V2000 MOL block parser
#   8   Fragment graph utilities
#   9   Structural fragmentation rules
#  10   Candidate enumeration and scoring
#  10b  Shared assignment pipeline   (Option 6)
#  11   XML / binary I/O helpers
#  12   Library conversion pipeline
#  13   Configuration persistence
#  13b  Readme / About dialog        (style guide 7/8)
#  14   GUI
#=============================================================================
import UIState


# =============================================================================
# .NET assembly references (IronPython 2.7 requires explicit loads)
# =============================================================================
import System
import System.Diagnostics
# ------------------------------------------------------------------
# .NET assembly references (IronPython 2.7 requires explicit loads)
# ------------------------------------------------------------------
import clr
clr.AddReference("System")
clr.AddReference("System.Windows.Forms")
clr.AddReference("System.Drawing")
clr.AddReference("System.Xml")
from System import (Action, Convert, Double, BitConverter,
                    Environment, Array, Byte, Buffer)
from System.IO import Path, Directory, File, MemoryStream
from System.Text import StringBuilder, Encoding
from System.Text import EncoderFallback, DecoderFallback
from System.Text.RegularExpressions import Regex
from System.Drawing import Size, Point, Font, Color, FontStyle, Icon
from System.Xml import XmlDocument
from System.Windows.Forms import (
    Form, Label, TextBox, Button, CheckBox, NumericUpDown,
    ComboBox, ComboBoxStyle, GroupBox,
    OpenFileDialog, SaveFileDialog,
    MessageBox, MessageBoxButtons, MessageBoxIcon,
    ScrollBars, AnchorStyles, DialogResult,
    Panel, DockStyle, FlatStyle, FormBorderStyle, FormStartPosition)


# =============================================================================
# SECTION 0: Module identity, palette, typography, icon
# =============================================================================
# Style guide section 11 -- shown in the banner, title bar and MessageBoxes.
APP_TITLE   = "EI Fragment Calculator"
APP_VERSION = "3.1.2"
APP_SLUG    = "ei_fragment_calculator"

# Style guide section 2 -- canonical palette, built once and reused.
C_BG        = Color.FromArgb(0xEA, 0xEA, 0xEA)
C_BORDER    = Color.FromArgb(0xC8, 0xC8, 0xC6)
C_CARD      = Color.White
C_DISABLED  = Color.FromArgb(0xF5, 0xF5, 0xF5)
C_BODY      = Color.FromArgb(0x53, 0x56, 0x5A)
C_DARK      = Color.FromArgb(0x30, 0x30, 0x30)
C_MUTED     = Color.FromArgb(0x88, 0x8B, 0x8D)
C_BLUE      = Color.FromArgb(0x00, 0x85, 0xD5)
C_BLUE_DK   = Color.FromArgb(0x00, 0x42, 0x6A)
C_BLUE_LT   = Color.FromArgb(0xE5, 0xF4, 0xFC)
C_BLUE_MUTE = Color.FromArgb(0x7B, 0xBC, 0xD8)
C_BLUE_HOV  = Color.FromArgb(0x00, 0x69, 0xA8)
C_HDR_BG    = Color.FromArgb(0xD4, 0xDD, 0xE5)
C_ROW_ALT   = Color.FromArgb(0xF3, 0xF7, 0xFB)

# Style guide section 3 -- typography. FONT_BANNER is deliberately NON-bold.
FONT_BANNER  = Font("Segoe UI", 12.0)
FONT_LABEL   = Font("Segoe UI", 9.0)
FONT_LABEL_B = Font("Segoe UI", 9.0, FontStyle.Bold)
FONT_MONO    = Font("Consolas", 9.0)

BANNER_HEIGHT = 56          # REQUIRED by the style guide -- never smaller

APP_ICON_MARK = "EF"        # white on #0085D5


def style_button(b, primary=False):
    """Style guide section 5 -- primary (filled brand blue) or secondary
    (white with a brand-blue caption and a grey border) action button."""
    b.FlatStyle = FlatStyle.Flat
    b.Font      = FONT_LABEL
    b.Cursor    = System.Windows.Forms.Cursors.Hand
    if primary:
        b.BackColor = C_BLUE
        b.ForeColor = Color.White
        b.FlatAppearance.BorderSize = 0
        b.FlatAppearance.MouseOverBackColor = C_BLUE_HOV
    else:
        b.BackColor = C_CARD
        b.ForeColor = C_BLUE
        b.FlatAppearance.BorderColor = C_BORDER
        b.FlatAppearance.BorderSize  = 1
        b.FlatAppearance.MouseOverBackColor = C_BLUE_LT
    return b


def make_app_icon():
    """Build the embedded icon at runtime -- style guide section 9, so the
    tool stays a single .py with no companion .ico to lose."""
    try:
        raw = Convert.FromBase64String(ICON_B64)
        return Icon(MemoryStream(raw))
    except:
        return None


def apply_icon(form):
    """Call from every form so the icon shows in the title bar, taskbar
    and Alt-Tab."""
    try:
        ic = make_app_icon()
        if ic is not None:
            form.Icon     = ic
            form.ShowIcon = True
    except:
        pass


def build_banner(form, on_about):
    """Style guide section 6 -- the verified 56-px brand banner.

    Two documented WinForms traps are handled here:
      * the "?" is repositioned on banner.Resize, because anchoring alone
        snapshots a wrong X while the docked banner is still narrower than
        the form;
      * the "?" uses C_BLUE_DK, not C_BLUE, or it disappears into the
        banner background.

    Returns the banner Panel. Add it to the form LAST (docking order).
    """
    banner = Panel()
    banner.Dock      = DockStyle.Top
    banner.Height    = BANNER_HEIGHT
    banner.BackColor = C_BLUE

    title = Label()
    title.Text      = APP_TITLE
    title.Font      = FONT_BANNER
    title.ForeColor = Color.White
    title.BackColor = C_BLUE
    title.AutoSize  = True
    title.Location  = Point(16, 16)
    banner.Controls.Add(title)

    ver = Label()
    ver.Text      = "v" + APP_VERSION
    ver.Font      = FONT_LABEL
    ver.ForeColor = Color.White
    ver.BackColor = C_BLUE
    ver.AutoSize  = True
    ver.Location  = Point(215, 21)
    banner.Controls.Add(ver)

    help_btn = Button()
    help_btn.Text      = "?"
    help_btn.Font      = Font("Segoe UI", 11.0, FontStyle.Bold)
    help_btn.Width     = 32
    help_btn.Height    = 28
    help_btn.Top       = 14
    help_btn.FlatStyle = FlatStyle.Flat
    help_btn.BackColor = C_BLUE_DK
    help_btn.ForeColor = Color.White
    help_btn.FlatAppearance.BorderSize = 0
    help_btn.FlatAppearance.MouseOverBackColor = Color.FromArgb(0x00, 0x33, 0x55)
    help_btn.Cursor    = System.Windows.Forms.Cursors.Hand
    help_btn.Click    += on_about
    banner.Controls.Add(help_btn)

    def _pos_help(sender, ev):
        help_btn.Left = banner.Width - help_btn.Width - 14
    banner.Resize += _pos_help
    help_btn.Left  = form.Width - help_btn.Width - 30

    return banner


# Embedded multi-resolution application icon (16/24/32/48/64/128/256 px),
# the mark "EF" in white on brand blue -- style guide section 9.
ICON_B64 = (
    "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"
    "gDABgDABgDABgDABgDABgDABgDABgDABgDABgDABgDABgDABgDABgDABgDABgDABgDAB"
    "gDABgDABgDABgDABgDABgDABgDABgDABgDABgDABgDABgDABgDABgDABgDABgDABgDAB"
    "gDABgDABgDABgDABgDABgDABgDABgDABgDABgDABgDABgDABgDABgDABgDABgDABgDAB"
    "gDABgDABgDABgDABgDABgDABgDABgDABgDABgDABgDABgDABgDABgLDF1APm6suTe+PO"
    "9QvjvPt1fDquvtxb+7nuZzN4AoAwAYAwAYAwAYAwAYAwAYAwAYAwAYAwAYAwfwKuweHf"
    "0/F273DM0dHydOoJ7mfGBGAN9n8vx+N339Zx1EZyP/PlFQDCBADCBADCBADCBADCBADC"
    "BADCBADCBADCBADCBADCBADCBADCBADCBADCBADCBADCBADCBADCBADCBADCBADCBADC"
    "BADCBADCBADCBADCBADCBADCBADCBADCBADCFlMP2AR3b14cq2f3x5xcfvF5HC1XU89g"
    "5gSAMyeQ8+UVAMIEAMIEAMIEAMIEAMIEAMIEAMIEAML8CLQGB0cn482ngzEny9OpF3Ae"
    "CMAa/PhzMp6+/76OozaSQM6XAHDmBHK+fAOAMAGAMAGAMAGAMAGAMAGAMAGAMAGAMAGA"
    "MAGAMAGAMAGAMAGAMAGAMAGAMAGAMAGAMAGAMAGAMAGAMAGAMAGAMAGAMAGAMAGAMAGA"
    "MAGAMAGAMAGAMAGAMAGAMAGAsMXUAzbBrSuL8frh7TF3zz/sj6+Hx1PPYEYEYA2uXdoe"
    "jx7cGHP36uNPAeA/XgEgTAAgTAAgTAAgTAAgTAAgTAAgTAAgTAAgbGvs7K6mHgFMwxMA"
    "hAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkA"
    "hAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkA"
    "hAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkA"
    "hAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkA"
    "hAkAhAkAhAkAhAkAhAkAhAkAhAkAhAkAjK5/SVRd++q+dKkAAAAASUVORK5CYII="
)


# =============================================================================
# SECTION 1: MassHunter UI helpers
# =============================================================================

def _GetOwnerForm():
    """Return the MassHunter main window so dialogs appear centred on it."""
    try:
        return UIState.MainForm._Form
    except:
        pass
    try:
        import clr
        clr.AddReference("System.Windows.Forms")
        from System.Windows.Forms import Application
        if Application.OpenForms and Application.OpenForms.Count > 0:
            return Application.OpenForms[0]
    except:
        pass
    return None


# ------------------------------------------------------------------
# RDKit .NET detection  (GraphMolWrap.dll -- optional)
# ------------------------------------------------------------------
# If the RDKit Windows .NET package is installed and its DLL is on
# the .NET assembly search path, GraphMolWrap is loaded here.
# The flag RDKIT_LOADED controls whether the RDKit filter checkbox
# is enabled and whether flt_rdkit() performs real checks.
#
# Installation:
#   1. Download the RDKit Windows release from
#      https://github.com/rdkit/rdkit/releases
#      (e.g. RDKit_2024_09_3_win64.zip)
#   2. Copy GraphMolWrap.dll (and its companion .dll files) to a
#      directory on the system PATH, or to the MassHunter installation
#      directory, or add its folder to PYTHONPATH / .NET probing paths.
#   3. Restart MassHunter.  The RDKit checkbox will become enabled.
RDKIT_LOADED = False
_RdkRWMol    = None    # GraphMolWrap.RWMol class, or None

try:
    # clr.AddReferenceToFileAndPath() loads by full path -- the only
    # reliable method in IronPython when the DLL is not in the GAC or
    # the MassHunter application directory.
    _rdkit_dll = r"C:\Windows\System32\RDKit2DotNetStandard.dll"
    clr.AddReferenceToFileAndPath(_rdkit_dll)
    from GraphMolWrap import RWMol as _RdkRWMol
    RDKIT_LOADED = True
except:
    pass

# ==================================================================
# SECTION 2: Physical constants
# ==================================================================

# Electron mass (CODATA 2018, Da).  Subtracted for EI+ mode because
# the detector measures the mass of the ion (neutral - one electron).
ELECTRON_MASS = 0.00054857990907

# ELEM maps element symbol -> (nominal_mass, monoisotopic_exact_mass).
# nominal_mass = integer mass of the lowest-mass stable isotope.
# exact_mass   = CODATA monoisotopic mass (Da).
# Source: IUPAC 2016 atomic weights + NIST CODATA 2018.
# 30 elements covering all common EI library compounds.
ELEM = {
    'H':  (1,   1.00782503207),   # hydrogen
    'D':  (2,   2.01410177785),   # deuterium (heavy hydrogen)
    'B':  (11,  11.0093053600),   # boron
    'C':  (12,  12.0000000000),   # carbon  (mass standard)
    'N':  (14,  14.0030740048),   # nitrogen
    'O':  (16,  15.9949146221),   # oxygen
    'F':  (19,  18.9984031630),   # fluorine  (monoisotopic)
    'Na': (23,  22.9897692800),   # sodium    (monoisotopic)
    'Mg': (24,  23.9850417000),   # magnesium
    'Al': (27,  26.9815386300),   # aluminium (monoisotopic)
    'Si': (28,  27.9769265325),   # silicon
    'P':  (31,  30.9737616320),   # phosphorus (monoisotopic)
    'S':  (32,  31.9720710000),   # sulfur
    'Cl': (35,  34.9688527160),   # chlorine
    'K':  (39,  38.9637066800),   # potassium
    'Ca': (40,  39.9625909800),   # calcium
    'Cr': (52,  51.9405062300),   # chromium
    'Mn': (55,  54.9380439100),   # manganese (monoisotopic)
    'Fe': (56,  55.9349363300),   # iron
    'Co': (59,  58.9331942900),   # cobalt    (monoisotopic)
    'Ni': (58,  57.9353424100),   # nickel
    'Cu': (63,  62.9295977200),   # copper
    'Zn': (64,  63.9291420100),   # zinc
    'As': (75,  74.9215945700),   # arsenic   (monoisotopic)
    'Se': (78,  77.9173092800),   # selenium
    'Br': (79,  78.9183371070),   # bromine
    'Sn': (118, 117.9016065700),  # tin
    'I':  (127, 126.9044680000),  # iodine    (monoisotopic)
    'Ti': (48,  47.9479419800),   # titanium
    'V':  (51,  50.9439570400),   # vanadium
    'Pb': (208, 207.9766652100),  # lead
}

# Standard valence for each element.  Used by:
#   - calc_rdb()      (degree-of-unsaturation formula)
#   - is_ee_ion()     (even/odd-electron classification)
#   - lewis_senior()  (valence-sum rules, Senior 1951)
VALENCE = {
    'H':  1, 'D':  1, 'B':  3, 'C':  4, 'N':  3, 'O':  2,
    'F':  1, 'Na': 1, 'Mg': 2, 'Al': 3, 'Si': 4, 'P':  3,
    'S':  2, 'Cl': 1, 'K':  1, 'Ca': 2, 'Cr': 3, 'Mn': 2,
    'Fe': 3, 'Co': 2, 'Ni': 2, 'Cu': 2, 'Zn': 2, 'As': 3,
    'Se': 2, 'Br': 1, 'Sn': 4, 'I':  1, 'Ti': 4, 'V':  5,
    'Pb': 2,
}

# Implicit valence for the MOL-block H-adder in structural rules.
# Only elements that can bear implicit H in organic structures.
IMPLICIT_VALENCE = {
    'C': 4, 'N': 3, 'O': 2, 'S': 2, 'P': 5,
    'F': 1, 'Cl': 1, 'Br': 1, 'I': 1, 'Si': 4, 'B': 3,
}

# Heteroatoms recognised by alpha-cleavage rule.
ALPHA_HETEROATOMS = set(['N', 'O', 'S', 'F', 'Cl', 'Br', 'I', 'P'])

# Hill order: C first, H/D second, then alphabetical.
# Determines the canonical formula string printed in logs and XML.
HILL = [
    'C', 'H', 'D',
    'Al', 'As', 'B', 'Br', 'Ca', 'Cl', 'Co', 'Cr', 'Cu',
    'F', 'Fe', 'I', 'K', 'Mg', 'Mn', 'N', 'Na', 'Ni',
    'O', 'P', 'Pb', 'S', 'Se', 'Si', 'Sn', 'Ti', 'V', 'Zn',
]

# Common neutral losses with associated score bonuses.
# When a candidate's neutral loss matches one of these strings
# (in Hill order), the heuristic score is increased.
# Ref: McLafferty & Turecek, "Interpretation of Mass Spectra", 4th ed.
COMMON_LOSSES = {}
for _ls, _sc in [
    ('H', 20), ('CH3', 30), ('C2H5', 30), ('C3H7', 25), ('OH', 25),
    ('CHO', 28), ('C2H3O', 30), ('CH3O', 25), ('Cl', 25), ('Br', 25),
    ('SH', 25), ('NH2', 20), ('H2O', 30), ('CO', 30), ('CO2', 28),
    ('HCN', 30), ('C2H2', 28), ('C2H4', 25), ('CH2O', 25), ('NO', 22),
    ('NO2', 22), ('NH3', 25), ('CH3OH', 22), ('C2H2O', 25), ('HF', 22),
    ('HCl', 22), ('HBr', 22), ('C3H3', 22), ('C3H5', 22), ('C4H8', 20),
    ('C2H3', 22), ('C2H4O', 22), ('CH2', 15), ('C3H6', 20), ('C4H7', 18),
    ('C2H6', 20)]:
    COMMON_LOSSES[_ls] = _sc

# ==================================================================
# SECTION 3: Isotope scoring
# ==================================================================
# Approximate M+1 contribution per atom (% relative to monoisotopic peak).
# Dominant contributions: 13C (1.10%), 15N (0.37%), 34S (M+2), 37Cl (M+2).
# Ref: Gross, "Mass Spectrometry: A Textbook", 3rd ed. (2017).
M1_PER_ATOM = {
    'C':  1.1034,   # 13C: 1.10%
    'H':  0.0156,   # 2H:  0.016%
    'D':  0.0,      # monoisotopic as D
    'N':  0.3663,   # 15N: 0.37%
    'O':  0.0381,   # 17O: 0.04%
    'F':  0.0,      # 19F monoisotopic
    'Na': 0.0,      # 23Na monoisotopic
    'Mg': 10.00,    # 25Mg: 10.0%
    'Al': 0.0,      # 27Al monoisotopic
    'Si': 5.0632,   # 29Si: 5.06%
    'P':  0.0,      # 31P monoisotopic
    'S':  0.7589,   # 33S: 0.76% (M+1); 34S at M+2 handled separately
    'Cl': 0.0,      # 37Cl at M+2 only
    'K':  0.0,      # minor
    'Ca': 0.0,      # minor
    'Cr': 0.0,
    'Mn': 0.0,      # 55Mn monoisotopic
    'Fe': 6.0,      # 57Fe: 6.0% (approx M+1 due to 57Fe)
    'Co': 0.0,      # 59Co monoisotopic
    'Ni': 0.0,
    'Cu': 0.0,
    'Zn': 0.0,
    'As': 0.0,      # 75As monoisotopic
    'Se': 0.0,      # complex pattern; dominant at M+2/M+4
    'Br': 0.0,      # 81Br at M+2 only
    'Sn': 0.0,      # complex 10-isotope pattern
    'I':  0.0,      # 127I monoisotopic
    'Ti': 0.0,
    'V':  0.0,
    'Pb': 0.0,
    'B':  0.0,
}

# M+2 contribution per atom (% relative to monoisotopic peak).
# Dominant: 37Cl (32.5%), 81Br (97.3%), 34S (4.25%), 18O (0.20%).
M2_PER_ATOM = {
    'O':  0.2045,   # 18O: 0.20%
    'S':  4.2534,   # 34S: 4.25%
    'Si': 3.3549,   # 30Si: 3.36%
    'Cl': 32.50,    # 37Cl: 32.5%
    'Br': 97.28,    # 81Br: 97.3%
    'Se': 112.0,    # combined M+2 from 77Se/78Se/80Se (simplified)
    'Sn': 95.0,     # combined heavy isotopes (simplified)
}

def calc_m1_pct(comp):
    """Return approximate M+1 % relative to monoisotopic peak.
    Based on per-atom isotope contributions (additive approximation).
    Accurate for small molecules; for >30 C atoms use full convolution.
    """
    return sum(M1_PER_ATOM.get(el, 0.0) * cnt
               for el, cnt in comp.items())

def calc_m2_pct(comp, m1_pct):
    """Return approximate M+2 % relative to monoisotopic peak.
    Combines single-atom M+2 contributions (Cl, Br, S, O, Si) with
    the square-correction for multi-atom M+1 accumulation:
        M+2_combined = sum(M2[el]*cnt) + M1%^2/200
    Ref: Gross 2017, section on isotope patterns.
    """
    m2 = sum(M2_PER_ATOM.get(el, 0.0) * cnt
             for el, cnt in comp.items())
    m2 += m1_pct * m1_pct / 200.0   # square correction for 13C accumulation
    return m2

def flt_isotope_score(comp, intensity_map, nom_mz, tol=30.0):
    """Score how well the candidate's theoretical M+1/M+2 pattern
    matches the observed spectrum intensities.

    Returns (score, msg) where score = sum of absolute deviations
    in percentage points. Lower score = better match.
    Candidates with score > tol are marked as filter_failed.

    Parameters
    ----------
    comp          : dict   Candidate formula {symbol: count}.
    intensity_map : dict   {nominal_mz: abundance} for whole compound.
    nom_mz        : int    Nominal m/z of the peak being scored.
    tol           : float  Rejection threshold in pp (default 30).
    """
    mono_obs = intensity_map.get(nom_mz, 0.0)
    if mono_obs <= 0.0:
        # No monoisotopic peak recorded -- skip scoring.
        return 0.0, "no mono peak"
    m1_theo = calc_m1_pct(comp)
    m2_theo = calc_m2_pct(comp, m1_theo)
    # Observed M+1 and M+2 as % of observed monoisotopic intensity.
    m1_obs = 100.0 * intensity_map.get(nom_mz + 1, 0.0) / mono_obs
    m2_obs = 100.0 * intensity_map.get(nom_mz + 2, 0.0) / mono_obs
    d1 = abs(m1_theo - m1_obs)
    d2 = abs(m2_theo - m2_obs)
    score = d1 + d2
    msg = ("M+1 theo={0:.1f}% obs={1:.1f}% d={2:.1f}pp; "
           "M+2 theo={3:.1f}% obs={4:.1f}% d={5:.1f}pp; "
           "total={6:.1f}pp (tol={7:.0f}pp)").format(
        m1_theo, m1_obs, d1,
        m2_theo, m2_obs, d2,
        score, tol)
    return score, msg

# ==================================================================
# SECTION 4: Formula utilities
# ==================================================================

# Compiled regex for parsing Hill-notation formula strings.
formula_re = Regex(r"([A-Z][a-z]?)(\d*)")

def parse_formula(s):
    """Parse a Hill-notation formula string into a composition dict.
    Returns None if the string is empty, malformed, or contains an
    element not present in ELEM (covers all 30 supported elements).
    """
    if not s:
        return None
    result = {}
    matches = formula_re.Matches(s.strip())
    for i in range(matches.Count):
        m = matches[i]
        sym = m.Groups[1].Value
        cnt_s = m.Groups[2].Value
        if not sym:
            continue
        cnt = int(cnt_s) if cnt_s else 1
        # Reject unknown elements immediately so the caller gets None
        # rather than a dict with invalid keys.
        if sym not in ELEM:
            return None
        result[sym] = result.get(sym, 0) + cnt
    return result if result else None

def formula_str(f):
    """Convert a composition dict to a canonical Hill-notation string.
    C and H come first, then all other elements alphabetically.
    Elements with count 0 are omitted.
    """
    if not f:
        return ""
    parts = []
    for sym in HILL:
        if sym in f and f[sym] > 0:
            parts.append(sym + (str(f[sym]) if f[sym] > 1 else ""))
    return "".join(parts)

def calc_nominal(f):
    """Return the nominal (integer) mass of composition f.
    Uses the integer mass of the monoisotopic isotope for each element.
    """
    return sum(ELEM[sym][0] * f[sym] for sym in f if sym in ELEM)

def calc_exact(f):
    """Return the exact monoisotopic mass of composition f (Da).
    Sum of (CODATA monoisotopic mass) * count for each element.
    """
    return sum(ELEM[sym][1] * f[sym] for sym in f if sym in ELEM)

def calc_rdb(f):
    """Return the degree of unsaturation (rings + double bonds, DBE).
    General formula: DBE = 1 + sum((valence - 2) * count) / 2
    For organic elements: DBE = (2C + 2 + N + P - H - D - F - halogens) / 2
    The general form handles all 30 elements via the VALENCE dict.
    Ref: IUPAC rules for degree of unsaturation.
    """
    total = 2.0   # constant +2 in numerator (corresponds to the +1 in DBE)
    for sym, cnt in f.items():
        val = VALENCE.get(sym, 2)   # default: divalent -> no contribution
        total += (val - 2) * cnt
    return total / 2.0

def is_ee_ion(f):
    """Return True for even-electron (EE, closed-shell) ions.
    An ion is EE when 2*DBE is an even integer, which is equivalent to:
    the count of atoms with odd standard valence is even.
    EE ions: protonated molecules, acylium, phenyl, tropylium, etc.
    OE ions: radical cations M+., alpha-cleavage radicals, etc.
    """
    odd_count = sum(
        cnt for sym, cnt in f.items()
        if VALENCE.get(sym, 2) % 2 == 1
    )
    return (odd_count % 2) == 0

def apply_electron_mode(exact_mass, electron_mode):
    """Apply the electron-mass correction to convert neutral exact mass
    to the ion m/z detected by the instrument.
    'remove' : EI+ standard mode -- ion = M - m_e  (default)
    'add'    : EI- negative-ion mode -- ion = M + m_e
    'none'   : no correction
    """
    if electron_mode == "remove":
        return exact_mass - ELECTRON_MASS
    elif electron_mode == "add":
        return exact_mass + ELECTRON_MASS
    return exact_mass   # "none"

# ==================================================================
# SECTION 5: Stable ion library
# ==================================================================
# Well-known, highly-stable EI fragment ions from:
#   McLafferty & Turecek (1993) Interpretation of Mass Spectra
#   Gross (2017) Mass Spectrometry: A Textbook
#   NIST WebBook common fragment tables
#
# Dict maps nominal m/z -> list of (composition_dict, ion_name, ion_type).
# ion_type: "stable_cation" | "common_radical_cation"
#
# When a candidate exactly matches one entry, it receives a +100
# heuristic score bonus (STABLE_ION_BONUS).
STABLE_ION_BONUS = 100

STABLE_IONS = {
    15:  [({'C': 1, 'H': 3}, "CH3+",      "stable_cation")],
    18:  [({'H': 2, 'O': 1}, "H2O+.",      "common_radical_cation")],
    26:  [({'C': 2, 'H': 2}, "C2H2+.",     "common_radical_cation")],
    27:  [({'C': 2, 'H': 3}, "C2H3+",      "stable_cation"),         # vinyl
          ({'H': 1, 'C': 1, 'N': 1}, "HCN+.", "common_radical_cation")],
    28:  [({'C': 1, 'O': 1}, "CO+.",        "common_radical_cation"),
          ({'N': 2},          "N2+.",        "common_radical_cation"),
          ({'C': 2, 'H': 4}, "C2H4+.",      "common_radical_cation")],
    29:  [({'C': 2, 'H': 5}, "C2H5+",      "stable_cation"),         # ethyl
          ({'C': 1, 'H': 1, 'O': 1}, "CHO+", "stable_cation")],      # formyl
    39:  [({'C': 3, 'H': 3}, "C3H3+",      "stable_cation")],        # cyclopropenyl
    41:  [({'C': 3, 'H': 5}, "C3H5+",      "stable_cation")],        # allyl
    43:  [({'C': 2, 'H': 3, 'O': 1}, "C2H3O+", "stable_cation"),     # acetyl
          ({'C': 3, 'H': 7},           "C3H7+",  "stable_cation")],   # propyl
    44:  [({'C': 1, 'O': 2}, "CO2+.",       "common_radical_cation"),
          ({'N': 2, 'O': 1}, "N2O+.",       "common_radical_cation")],
    45:  [({'C': 2, 'H': 5, 'O': 1}, "C2H5O+", "stable_cation")],    # ethoxy
    50:  [({'C': 4, 'H': 2}, "C4H2+.",      "common_radical_cation")],
    51:  [({'C': 4, 'H': 3}, "C4H3+",      "stable_cation")],
    55:  [({'C': 4, 'H': 7}, "C4H7+",      "stable_cation"),
          ({'C': 3, 'H': 3, 'O': 1}, "C3H3O+", "stable_cation")],
    57:  [({'C': 4, 'H': 9}, "C4H9+",      "stable_cation"),         # tert-butyl
          ({'C': 3, 'H': 5, 'O': 1}, "C3H5O+", "stable_cation")],    # acrolein
    58:  [({'C': 3, 'H': 6, 'N': 1}, "C3H6N+", "stable_cation")],   # immonium
    65:  [({'C': 5, 'H': 5}, "C5H5+",      "stable_cation")],        # cyclopentadienyl
    67:  [({'C': 5, 'H': 7}, "C5H7+",      "stable_cation")],
    69:  [({'C': 5, 'H': 9}, "C5H9+",      "stable_cation"),
          ({'C': 4, 'H': 5, 'O': 1}, "C4H5O+", "stable_cation"),
          ({'C': 3, 'H': 5, 'N': 2}, "C3H5N2+", "stable_cation")],
    71:  [({'C': 5, 'H': 11}, "C5H11+",    "stable_cation"),
          ({'C': 4, 'H': 7, 'O': 1}, "C4H7O+", "stable_cation")],
    77:  [({'C': 6, 'H': 5}, "C6H5+",      "stable_cation")],        # phenyl (very common)
    78:  [({'C': 6, 'H': 6}, "C6H6+.",      "common_radical_cation")],# benzene rc
    79:  [({'C': 6, 'H': 7}, "C6H7+",      "stable_cation"),
          ({'P': 1, 'O': 3}, "PO3-",        "stable_cation")],        # phosphonate
    80:  [({'C': 5, 'H': 6, 'N': 1}, "C5H6N+", "stable_cation")],   # pyridinium-like
    81:  [({'C': 6, 'H': 9}, "C6H9+",      "stable_cation"),
          ({'C': 5, 'H': 5, 'O': 1}, "C5H5O+", "stable_cation")],
    83:  [({'C': 6, 'H': 11}, "C6H11+",    "stable_cation")],
    85:  [({'C': 5, 'H': 9, 'O': 1}, "C5H9O+", "stable_cation"),
          ({'C': 6, 'H': 13}, "C6H13+",    "stable_cation")],
    91:  [({'C': 7, 'H': 7}, "C7H7+",      "stable_cation")],        # tropylium (very common)
    92:  [({'C': 7, 'H': 8}, "C7H8+.",      "common_radical_cation")],# toluene rc
    93:  [({'C': 7, 'H': 9}, "C7H9+",      "stable_cation"),
          ({'C': 6, 'H': 5, 'O': 1}, "C6H5O+", "stable_cation")],   # phenoxy
    94:  [({'C': 6, 'H': 6, 'O': 1}, "C6H6O+.", "common_radical_cation")],# phenol rc
    95:  [({'C': 7, 'H': 11}, "C7H11+",    "stable_cation"),
          ({'C': 6, 'H': 7, 'O': 1}, "C6H7O+", "stable_cation")],
    97:  [({'C': 7, 'H': 13}, "C7H13+",    "stable_cation")],
    99:  [({'C': 7, 'H': 15}, "C7H15+",    "stable_cation"),
          ({'C': 6, 'H': 11, 'O': 1}, "C6H11O+", "stable_cation")],
    105: [({'C': 8, 'H': 9},           "C8H9+",  "stable_cation"),
          ({'C': 7, 'H': 5, 'O': 1},  "C7H5O+", "stable_cation")],  # benzoyl
    107: [({'C': 7, 'H': 7, 'O': 1},  "C7H7O+", "stable_cation")],  # methylbenzoyl
    119: [({'C': 9, 'H': 11},          "C9H11+", "stable_cation"),
          ({'C': 8, 'H': 7, 'O': 1},  "C8H7O+", "stable_cation")],
    121: [({'C': 8, 'H': 9, 'O': 1},  "C8H9O+", "stable_cation")],
    149: [({'C': 8, 'H': 5, 'O': 3},  "C8H5O3+", "stable_cation")], # phthalate
}

def lookup_stable_ion(comp, nom_mz):
    """Look up comp in the stable-ion library at nom_mz.
    Returns (ion_name, ion_type) if found, else None.
    Comparison is exact: all element counts must match.
    """
    for lib_comp, name, ion_type in STABLE_IONS.get(nom_mz, []):
        if lib_comp == comp:
            return (name, ion_type)
    return None

# ==================================================================
# SECTION 6: Post-enumeration filters
# ==================================================================
# Each filter returns (passed: bool, message: str).
# Candidates that fail a filter are deprioritised (not discarded),
# so pick_best always returns something even if all candidates fail.

def flt_nitrogen_rule(comp, nom_mz, rdb):
    """Nitrogen rule: odd nominal m/z requires odd N+P count for EE ions.
    For OE (radical) ions the parity is inverted.
    Ref: McLafferty & Turecek (1993) Interpretation of Mass Spectra.
    """
    n_count = comp.get('N', 0) + comp.get('P', 0) + comp.get('As', 0)
    mz_odd  = (nom_mz % 2) == 1
    n_odd   = (n_count % 2) == 1
    # is_ee_ion equivalent without calling the outer function:
    # even-electron when 2*DBE is integer-even, i.e., sum of odd-val atoms is even
    odd_val_count = sum(
        cnt for sym, cnt in comp.items()
        if VALENCE.get(sym, 2) % 2 == 1)
    even_electron = (odd_val_count % 2) == 0
    if even_electron:
        passed = (mz_odd == n_odd)
    else:
        passed = (mz_odd != n_odd)
    if passed:
        return True, ""
    return False, ("N-rule fail: m/z {0} ({1}) N+P={2} ({3}) {4}".format(
        nom_mz,
        "odd" if mz_odd else "even",
        n_count,
        "odd" if n_odd else "even",
        "EE" if even_electron else "OE"))

def flt_hd_check(comp, rdb, max_ratio=1.0):
    """H-deficiency check: reject candidates where DBE/C > max_ratio.
    EI fragment ions rarely have DBE/C > 1.0; values above that suggest
    an implausible hydrogen-poor structure.
    Default max_ratio = 1.0 (retains phenyl C6H5 at 0.83, tropylium at 0.86).
    Ref: Pretsch et al. (2009) Structure Determination of Organic Compounds.
    """
    c_count = comp.get('C', 0)
    if c_count == 0:
        return True, ""   # no C: rule does not apply
    ratio = rdb / c_count
    if ratio <= max_ratio:
        return True, ""
    return False, ("HD-check fail: DBE/C={0:.2f} > {1:.2f} "
                   "(DBE={2:.1f}, C={3})".format(
        ratio, max_ratio, rdb, c_count))

def flt_lewis_senior(comp, rdb):
    """Lewis & Senior valence-sum rules.
    Rule 1: sum of valences must be even for EE (closed-shell) ions.
            For OE (radical) ions this rule is relaxed.
    Rule 2: sum of valences >= 2 * (atom_count - 1).
    Ref: Senior J.K. (1951) Am. J. Math. 73(3):663-689.
    """
    total_valence = 0
    atom_count    = 0
    for el, cnt in comp.items():
        if cnt <= 0:
            continue
        val = VALENCE.get(el, 2)
        total_valence += val * cnt
        atom_count    += cnt
    if atom_count == 0:
        return True, ""
    # Determine if OE (radical) -- odd count of odd-valence atoms.
    odd_val_count = sum(
        cnt for sym, cnt in comp.items()
        if VALENCE.get(sym, 2) % 2 == 1)
    is_radical = (odd_val_count % 2) == 1
    # Rule 1: even valence sum for closed-shell ions only.
    if not is_radical and total_valence % 2 != 0:
        return False, ("Lewis-Senior Rule1: valence_sum={0} odd "
                       "for EE ion".format(total_valence))
    # Rule 2: connectivity constraint.
    min_required = 2 * (atom_count - 1)
    if total_valence < min_required:
        return False, ("Lewis-Senior Rule2: valence_sum={0} < {1} "
                       "({2} atoms)".format(
            total_valence, min_required, atom_count))
    return True, ""

def flt_smiles_constraint(comp, rdb, parent_ring_count):
    """SMILES ring-count bound: a fragment cannot have more rings than
    the parent molecule.  Uses parent ring count from the MOL block.
    Threshold: DBE > parent_ring_count * 2 + 1 triggers rejection.
    Skipped when parent_ring_count is None (no MOL block).
    Ref: Weininger (1988) J. Chem. Inf. Comput. Sci. 28(1):31-36.
    """
    if parent_ring_count is None:
        return True, "no MOL ring data"
    if rdb > parent_ring_count * 2 + 1:
        return False, ("SMILES constraint: DBE={0:.1f} > "
                       "2*rings+1={1} (rings={2})".format(
            rdb, parent_ring_count * 2 + 1, parent_ring_count))
    return True, ""

def flt_rdkit(comp, rdkit_frags=None):
    """RDKit-assisted single-bond fragment feasibility check.

    Requires GraphMolWrap.dll to be loaded (RDKIT_LOADED=True) and
    a precomputed rdkit_frags set produced by get_all_bond_break_formulas().

    The check compares the heavy-atom portion of the candidate formula
    against the set of heavy-atom formulas obtainable by breaking any
    single acyclic bond in the parent structure.  H/D atoms are excluded
    from the comparison because V2000 mol blocks typically encode them
    implicitly; the H-count discrimination is already handled by the
    nitrogen rule and DBE filters.

    Falls through (returns True) when:
      - RDKIT_LOADED is False    (DLL not installed)
      - rdkit_frags is None      (no mol block for this compound)
      - candidate has no carbon  (inorganic / heteroatom-only ions)
    """
    if not RDKIT_LOADED:
        return True, "RDKit not loaded"
    if rdkit_frags is None:
        return True, "no mol block"
    # Build heavy-atom-only formula for comparison.
    heavy = {}
    for el, cnt in comp.items():
        if el not in ('H', 'D'):
            heavy[el] = cnt
    if not heavy:
        return True, "no heavy atoms"
    candidate_h = formula_str(heavy)
    if candidate_h in rdkit_frags:
        return True, ""
    return False, (
        "RDKit: {0} not in single-bond fragment set "
        "({1} frags)".format(candidate_h, len(rdkit_frags)))

def apply_all_filters(comp, nom_mz, rdb, intensity_map,
                      parent_ring_count, flags, rdkit_frags=None):
    """Apply all enabled filters to a candidate formula.

    Parameters
    ----------
    comp              : dict  Candidate composition.
    nom_mz            : int   Nominal m/z of the peak.
    rdb               : float Degree of unsaturation (pre-computed).
    intensity_map     : dict  {nom_mz: abundance} for whole compound.
    parent_ring_count : int|None  Ring count from MOL block.
    flags             : dict  {'nitrogen': bool, 'hd': bool,
                               'lewis': bool, 'isotope': bool,
                               'smiles': bool, 'rdkit': bool}

    Returns
    -------
    (filter_passed: bool, isotope_score: float, detail_str: str)
    """
    passed = True
    iso_score = 0.0
    details = []

    if flags.get('nitrogen', True):
        ok, msg = flt_nitrogen_rule(comp, nom_mz, rdb)
        if not ok:
            passed = False
            details.append(msg)

    if flags.get('hd', True):
        ok, msg = flt_hd_check(comp, rdb, max_ratio=1.0)
        if not ok:
            passed = False
            details.append(msg)

    if flags.get('lewis', True):
        ok, msg = flt_lewis_senior(comp, rdb)
        if not ok:
            passed = False
            details.append(msg)

    if flags.get('isotope', True):
        iso_score, msg = flt_isotope_score(comp, intensity_map,
                                           nom_mz, tol=30.0)
        if iso_score > 30.0:
            passed = False
            details.append(msg)

    if flags.get('smiles', True):
        ok, msg = flt_smiles_constraint(comp, rdb, parent_ring_count)
        if not ok:
            passed = False
            details.append(msg)

    if flags.get('rdkit', False):
        ok, msg = flt_rdkit(comp, rdkit_frags)
        if not ok:
            passed = False
            details.append(msg)

    detail_str = "; ".join(details) if details else "OK"
    return passed, iso_score, detail_str

# ==================================================================
# SECTION 7: V2000 MOL block parser
# ==================================================================

def parse_mol_block(mol_text):
    """Parse a V2000 MDL MOL block.

    Returns a dict:
        atoms       : list of {element: str, index: int}  (0-indexed)
        bonds       : list of {a1: int, a2: int, type: int} (0-indexed)
        adjacency   : dict {atom_idx: [neighbour_idxs]}
        ring_count  : int   number of independent rings (SSSR count)
                      = n_bonds - n_heavy_atoms + 1 (Euler's formula
                      for a single connected planar graph)

    Returns None if the block is missing, malformed, or too short.

    Aromatic bonds (V2000 bond type 4) are stored as-is.
    _add_implicit_h() treats them as 1.5 bond-order for valence calc.
    """
    if not mol_text:
        return None
    mol_text = mol_text.strip()
    if not mol_text:
        return None
    lines = mol_text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    # Lines 0-2: molecule name / program stamp / comment.
    # Line  3  : counts line "aaabbblll..." (fixed-width fields of 3).
    if len(lines) < 4:
        return None
    counts_line = lines[3]
    try:
        n_atoms = int(counts_line[0:3].strip())
        n_bonds = int(counts_line[3:6].strip())
    except:
        return None
    if n_atoms <= 0 or n_atoms > 999:
        return None

    # Atom block: element symbol at columns 31-33 (0-based).
    atoms = []
    for i in range(n_atoms):
        li = 4 + i
        if li >= len(lines):
            return None
        line = lines[li]
        if len(line) < 34:
            return None
        elem = line[31:34].strip()
        if not elem:
            return None
        atoms.append({'element': elem, 'index': i})

    # Bond block: a1(cols 0-2), a2(cols 3-5), type(cols 6-8) -- 1-indexed.
    bonds = []
    adjacency = {}
    for i in range(n_atoms):
        adjacency[i] = []

    for i in range(n_bonds):
        li = 4 + n_atoms + i
        if li >= len(lines):
            break
        line = lines[li]
        if len(line) < 9:
            continue
        try:
            a1    = int(line[0:3].strip()) - 1   # 1-indexed -> 0-indexed
            a2    = int(line[3:6].strip()) - 1
            btype = int(line[6:9].strip())
        except:
            continue
        if a1 < 0 or a2 < 0 or a1 >= n_atoms or a2 >= n_atoms:
            continue
        bonds.append({'a1': a1, 'a2': a2, 'type': btype})
        if a2 not in adjacency[a1]:
            adjacency[a1].append(a2)
        if a1 not in adjacency[a2]:
            adjacency[a2].append(a1)

    # Euler's formula for planar connected graphs:
    #   ring_count = E - V + 1  (1 connected component assumed)
    # Only heavy-atom bonds are counted (no explicit H in 2D SDF).
    ring_count = max(0, n_bonds - n_atoms + 1)

    return {
        'atoms': atoms,
        'bonds': bonds,
        'adjacency': adjacency,
        'ring_count': ring_count,
    }

# ==================================================================
# SECTION 8: Fragment graph utilities
# ==================================================================

def _connected_component(adjacency, start, exclude_edge=None):
    """BFS from 'start', optionally skipping one undirected edge.
    Returns frozenset of all atom indices reachable from start.
    Uses a plain list as a FIFO queue (collections.deque unavailable).
    """
    if exclude_edge is not None:
        ea, eb = exclude_edge[0], exclude_edge[1]
    else:
        ea, eb = -1, -2
    visited = set()
    queue = [start]
    while queue:
        node = queue.pop(0)   # O(n) per pop -- acceptable for <100 atoms
        if node in visited:
            continue
        visited.add(node)
        for nb in adjacency.get(node, []):
            # Skip the excluded edge (undirected: check both directions).
            if (node == ea and nb == eb) or (node == eb and nb == ea):
                continue
            if nb not in visited:
                queue.append(nb)
    return frozenset(visited)

def _atoms_to_comp(atoms, indices):
    """Count element occurrences for a set of atom indices.
    Returns a {element: count} dict (no H -- caller adds implicit H).
    """
    comp = {}
    for i in indices:
        el = atoms[i]['element']
        comp[el] = comp.get(el, 0) + 1
    return comp

def _is_ring_bond(adjacency, a1, a2):
    """Return True when bond (a1, a2) is part of a ring.
    Implemented as: does removing the bond leave a2 still reachable
    from a1?  If yes, there is an alternative path -> ring bond.
    """
    frag = _connected_component(adjacency, a1, exclude_edge=(a1, a2))
    return a2 in frag

def _add_implicit_h(comp, atoms, bonds, frag_indices):
    """Add implicit H to a fragment composition.
    For each heavy atom in frag_indices, the used bond-order within
    the fragment is summed; implicit H fills the remaining valence.
    Aromatic bonds (V2000 type 4) count as 1.5 bond-order.
    Only elements listed in IMPLICIT_VALENCE are considered (organic
    elements that typically carry H in organic structures).
    """
    h_count = 0
    for idx in frag_indices:
        el      = atoms[idx]['element']
        valence = IMPLICIT_VALENCE.get(el, 0)
        if valence == 0:
            continue   # metal or other element -> no implicit H
        used = 0.0
        for b in bonds:
            if ((b['a1'] == idx and b['a2'] in frag_indices) or
                    (b['a2'] == idx and b['a1'] in frag_indices)):
                bt    = b['type']
                used += 1.5 if bt == 4 else bt   # aromatic bond = 1.5
        h_count += max(0, int(round(valence - used)))
    result = dict(comp)
    if h_count:
        result['H'] = result.get('H', 0) + h_count
    return result

def _bond_type_between(bonds, a, b):
    """Return the bond type between atoms a and b (0 if not bonded)."""
    for bnd in bonds:
        if (bnd['a1'] == a and bnd['a2'] == b) or \
                (bnd['a1'] == b and bnd['a2'] == a):
            return bnd['type']
    return 0

# ==================================================================
# SECTION 9: Structural fragmentation rules
# ==================================================================

def _homolytic_cleavages(mol_data):
    """Homolytic (radical) cleavage of every non-ring single bond.
    Both radical fragments are listed.  This covers sigma-bond cleavages
    that are the most common EI fragmentation pathway.
    Returns list of (frag1_formula_str, frag2_formula_str).
    Ref: McLafferty & Turecek (1993) ch. 3.
    """
    atoms     = mol_data['atoms']
    bonds     = mol_data['bonds']
    adjacency = mol_data['adjacency']
    results   = []
    for bond in bonds:
        if bond['type'] != 1:
            continue   # only cleave single bonds
        a1, a2 = bond['a1'], bond['a2']
        if _is_ring_bond(adjacency, a1, a2):
            continue   # ring bonds don't produce separate fragments
        frag1 = _connected_component(adjacency, a1, exclude_edge=(a1, a2))
        frag2 = frozenset(range(len(atoms))) - frag1
        c1 = _add_implicit_h(_atoms_to_comp(atoms, frag1), atoms, bonds, frag1)
        c2 = _add_implicit_h(_atoms_to_comp(atoms, frag2), atoms, bonds, frag2)
        results.append((formula_str(c1), formula_str(c2)))
    return results

def _alpha_cleavages(mol_data):
    """Alpha-cleavage: break the C-C single bond one bond away from a
    heteroatom (N/O/S/halogen).  The charge stays with the heteroatom
    fragment (inductive effect).
    Returns list of formula strings (charged frag then neutral frag
    per cleavage event).
    Ref: McLafferty & Turecek (1993) ch. 4.
    """
    atoms     = mol_data['atoms']
    bonds     = mol_data['bonds']
    adjacency = mol_data['adjacency']
    results   = []
    seen      = set()
    for h_idx, atom in enumerate(atoms):
        if atom['element'] not in ALPHA_HETEROATOMS:
            continue
        for alpha_idx in adjacency.get(h_idx, []):
            for beta_idx in adjacency.get(alpha_idx, []):
                if beta_idx == h_idx:
                    continue
                if _bond_type_between(bonds, alpha_idx, beta_idx) != 1:
                    continue
                if _is_ring_bond(adjacency, alpha_idx, beta_idx):
                    continue
                key = (min(alpha_idx, beta_idx), max(alpha_idx, beta_idx))
                if key in seen:
                    continue
                seen.add(key)
                frag_h = _connected_component(
                    adjacency, h_idx, exclude_edge=(alpha_idx, beta_idx))
                frag_n = frozenset(range(len(atoms))) - frag_h
                c_h = _add_implicit_h(
                    _atoms_to_comp(atoms, frag_h), atoms, bonds, frag_h)
                c_n = _add_implicit_h(
                    _atoms_to_comp(atoms, frag_n), atoms, bonds, frag_n)
                results.append(formula_str(c_h))
                results.append(formula_str(c_n))
    return results

def _mclafferty(mol_data):
    """McLafferty rearrangement at C=O groups.

    Search pattern (numbering from C=O outward):
        O=C - Calpha - Cbeta - Cgamma - H
    The gamma-H migrates via a 6-membered cyclic transition state to
    the carbonyl oxygen; the Calpha-Cbeta bond then cleaves.

    Products:
        Enol cation  (contains the C=O side + migrated H)
        Neutral alkene (Cbeta side, loses H and gains a double bond)

    H-count corrections applied after _add_implicit_h:
        Enol   net  0   (+1 H-migration, -1 new C=C at carbonyl C)
        Neutral net -2  (-1 H-migration, -1 new C=C at Cbeta)

    Implicit-H fallback for PubChem 2D SDF where gamma-H is not
    listed explicitly: valence-minus-used-bonds estimate.

    Returns list of formula strings (enol then neutral per event).
    Ref: McLafferty (1959) Anal. Chem. 31:82.
    """
    atoms   = mol_data['atoms']
    bonds   = mol_data['bonds']
    adjacency = mol_data['adjacency']
    results = []
    seen    = set()

    for bnd in bonds:
        if bnd['type'] != 2:
            continue   # looking for C=O double bonds
        a1, a2 = bnd['a1'], bnd['a2']
        c_idx  = o_idx = None
        if atoms[a1]['element'] == 'C' and atoms[a2]['element'] == 'O':
            c_idx, o_idx = a1, a2
        elif atoms[a1]['element'] == 'O' and atoms[a2]['element'] == 'C':
            c_idx, o_idx = a2, a1
        if c_idx is None:
            continue

        for alpha_idx in adjacency.get(c_idx, []):
            if alpha_idx == o_idx:
                continue
            if _bond_type_between(bonds, c_idx, alpha_idx) != 1:
                continue
            if atoms[alpha_idx]['element'] != 'C':
                continue

            for beta_idx in adjacency.get(alpha_idx, []):
                if beta_idx in (c_idx, o_idx):
                    continue
                if _bond_type_between(bonds, alpha_idx, beta_idx) != 1:
                    continue
                if atoms[beta_idx]['element'] != 'C':
                    continue

                for gamma_idx in adjacency.get(beta_idx, []):
                    if gamma_idx in (alpha_idx, c_idx):
                        continue
                    if _bond_type_between(bonds, beta_idx, gamma_idx) != 1:
                        continue

                    # Check for H at gamma: explicit H neighbours first.
                    h_count = sum(
                        1 for nb in adjacency.get(gamma_idx, [])
                        if atoms[nb]['element'] == 'H')
                    # Fallback to valence-based implicit H (PubChem 2D SDF).
                    if h_count == 0:
                        el_g  = atoms[gamma_idx]['element']
                        val_g = IMPLICIT_VALENCE.get(el_g, 0)
                        if val_g > 0:
                            used_g = sum(
                                (1.5 if b['type'] == 4 else b['type'])
                                for b in bonds
                                if b['a1'] == gamma_idx or
                                   b['a2'] == gamma_idx)
                            h_count = max(0, int(round(val_g - used_g)))
                    if h_count == 0:
                        continue

                    key = (c_idx, alpha_idx, beta_idx)
                    if key in seen:
                        continue
                    seen.add(key)

                    enol_atoms = _connected_component(
                        adjacency, c_idx,
                        exclude_edge=(alpha_idx, beta_idx))
                    neut_atoms = frozenset(range(len(atoms))) - enol_atoms

                    enol_comp = _add_implicit_h(
                        _atoms_to_comp(atoms, enol_atoms),
                        atoms, bonds, enol_atoms)
                    neut_comp = _add_implicit_h(
                        _atoms_to_comp(atoms, neut_atoms),
                        atoms, bonds, neut_atoms)

                    # Double-bond correction (new C=C formed in each product).
                    # Enol net H: +1 (received H) - 1 (new C=C) = 0 correction.
                    # Neutral net H: -1 (lost H) - 1 (new C=C) = -2 correction.
                    neut_comp['H'] = max(0, neut_comp.get('H', 0) - 2)

                    results.append(formula_str(enol_comp))
                    results.append(formula_str(neut_comp))
    return results

def _find_6_membered_rings(adjacency, n_atoms):
    """Find all 6-membered rings by iterative DFS.
    Returns a list of frozensets, each containing 6 atom indices.
    Iterative (not recursive) to avoid Python recursion limits.
    """
    rings      = []
    seen_rings = set()
    for start in range(n_atoms):
        init_vis = set([start])
        # Stack items: (current_node, path_list, visited_set)
        stack = [(start, [start], init_vis)]
        while stack:
            node, path, vis = stack.pop()
            plen = len(path)
            if plen == 6:
                # Check if the ring closes back to 'start'.
                if start in adjacency.get(node, []):
                    r = frozenset(path)
                    if r not in seen_rings:
                        seen_rings.add(r)
                        rings.append(r)
            elif plen < 6:
                for nb in adjacency.get(node, []):
                    if nb in vis:
                        continue
                    new_vis = set(vis)
                    new_vis.add(nb)
                    stack.append((nb, path + [nb], new_vis))
    return rings

def _retro_diels_alder(mol_data):
    """Retro-Diels-Alder fragmentation.
    In 6-membered rings containing a C=C double bond, the two
    flanking C-C single bonds (adjacent to the non-double-bond end)
    are cleaved to give two even-electron fragments.
    Returns list of (frag1_formula_str, frag2_formula_str).
    Ref: Djerassi & Fenselau (1965) J. Am. Chem. Soc. 87:5752.
    """
    atoms     = mol_data['atoms']
    bonds     = mol_data['bonds']
    adjacency = mol_data['adjacency']
    results   = []
    rings     = _find_6_membered_rings(adjacency, len(atoms))

    for ring in rings:
        for bnd in bonds:
            if bnd['type'] != 2:
                continue
            da, db = bnd['a1'], bnd['a2']
            if da not in ring or db not in ring:
                continue
            if atoms[da]['element'] != 'C' or atoms[db]['element'] != 'C':
                continue
            cut_bonds = []
            for b2 in bonds:
                if b2['type'] != 1:
                    continue
                x, y = b2['a1'], b2['a2']
                if x not in ring or y not in ring:
                    continue
                if (x == da and y == db) or (x == db and y == da):
                    continue
                if ((x == da or x == db) and atoms[y]['element'] == 'C') or \
                        ((y == da or y == db) and atoms[x]['element'] == 'C'):
                    cut_bonds.append((x, y))
            if len(cut_bonds) != 2:
                continue
            try:
                frag1 = _connected_component(
                    adjacency, cut_bonds[0][0],
                    exclude_edge=cut_bonds[0])
                frag2 = frozenset(range(len(atoms))) - frag1
                c1 = _add_implicit_h(
                    _atoms_to_comp(atoms, frag1), atoms, bonds, frag1)
                c2 = _add_implicit_h(
                    _atoms_to_comp(atoms, frag2), atoms, bonds, frag2)
                results.append((formula_str(c1), formula_str(c2)))
            except:
                pass
    return results

def build_struct_whitelist(mol_data):
    """Run all four structural fragmentation rules and collect every
    predicted fragment formula into a set.
    Returns None when mol_data is None (no MOL block available).
    The whitelist is used by score_formula() (criterion 12: +200 bonus).
    """
    if mol_data is None:
        return None
    wl = set()
    for f1, f2 in _homolytic_cleavages(mol_data):
        wl.add(f1)
        wl.add(f2)
    for fs in _alpha_cleavages(mol_data):
        wl.add(fs)
    for fs in _mclafferty(mol_data):
        wl.add(fs)
    for f1, f2 in _retro_diels_alder(mol_data):
        wl.add(f1)
        wl.add(f2)
    wl.discard("")   # remove empty strings from failed formula_str() calls
    return wl

def get_all_bond_break_formulas(mol_data):
    """Enumerate every heavy-atom formula obtainable by breaking exactly
    one acyclic bond in the parent structure.

    Uses the adjacency graph from parse_mol_block() and the BFS
    component-finder _connected_component() already present in this
    scope.  H atoms are excluded (V2000 mol blocks encode them
    implicitly; comparison is done on heavy atoms only).

    Returns a frozenset of Hill-order heavy-atom formula strings, or
    None when mol_data is None or the mol block has no atoms.

    Ring bonds are skipped automatically: removing a ring bond keeps
    the molecule connected so frag1 covers all atoms and the bond is
    discarded.  Acyclic bonds always split the molecule into two
    complementary fragments, both of which are added to the set.
    """
    if mol_data is None:
        return None
    atoms   = mol_data['atoms']   # [{'element': str, 'index': int}]
    bonds   = mol_data['bonds']   # [{'a1': int, 'a2': int, 'type': int}]
    adj     = mol_data['adjacency']
    n_atoms = len(atoms)
    if n_atoms == 0:
        return None

    # Build element lookup: atom index -> symbol (heavy atoms only).
    elem_of = {}
    for a in atoms:
        sym = a['element']
        if sym not in ('H', 'D'):
            elem_of[a['index']] = sym

    result = set()
    for bond in bonds:
        a1, a2 = bond['a1'], bond['a2']
        # BFS from a1 without crossing the a1--a2 edge.
        frag1_idxs = _connected_component(
            adj, a1, exclude_edge=(a1, a2))
        if len(frag1_idxs) == n_atoms:
            continue    # ring bond: molecule stays connected

        # Compose the formula for each fragment (heavy atoms only).
        frag1 = {}
        for idx in frag1_idxs:
            el = elem_of.get(idx)
            if el:
                frag1[el] = frag1.get(el, 0) + 1
        fs1 = formula_str(frag1)
        if fs1:
            result.add(fs1)

        frag2 = {}
        for idx in range(n_atoms):
            if idx not in frag1_idxs:
                el = elem_of.get(idx)
                if el:
                    frag2[el] = frag2.get(el, 0) + 1
        fs2 = formula_str(frag2)
        if fs2:
            result.add(fs2)

    return frozenset(result) if result else None

# ==================================================================
# SECTION 10: Candidate enumeration and scoring
# ==================================================================

# Enumeration cache, keyed on (parent formula string, target nominal mass).
# Isomers share a parent formula, so a library with many isomers reuses the
# same enumeration repeatedly (Option 2). Bounded so a pathological library
# cannot grow it without limit.
_SUBFORMULA_CACHE     = {}
_SUBFORMULA_CACHE_MAX = 200000


def _prepare_parent(parent):
    """Per-compound preparation for find_subformulas() (Option 1).

    Returns (syms, noms, maxn, suffix):
      syms[i]   element symbol, sorted by DESCENDING nominal mass
      noms[i]   nominal mass of element i
      maxn[i]   atoms of element i available from the parent
      suffix[i] largest nominal mass still obtainable from elements i..n-1

    Built once per parent formula and reused for every peak, instead of
    being rebuilt on every call as in v3.0.
    """
    elems = []
    for sym in parent:
        if sym not in ELEM:
            continue
        nom, _exact = ELEM[sym]
        cnt = parent[sym]
        if cnt > 0 and nom > 0:
            elems.append((sym, nom, cnt))
    elems.sort(key=lambda x: -x[1])
    syms = [e[0] for e in elems]
    noms = [e[1] for e in elems]
    maxn = [e[2] for e in elems]
    n    = len(elems)
    suffix = [0] * (n + 1)
    for i in range(n - 1, -1, -1):
        suffix[i] = suffix[i + 1] + noms[i] * maxn[i]
    return syms, noms, maxn, suffix


def find_subformulas(parent, target_nom, prep=None):
    """Enumerate all sub-formulas of 'parent' whose nominal mass equals
    'target_nom' exactly.

    Branch-and-bound DFS over elements sorted by decreasing nominal mass.
    Two bounds are applied at every node (Option 1):

      * downward -- at most remaining // nom atoms of this element fit;
      * upward   -- if the largest mass still obtainable from the elements
                    that remain is less than the mass still needed, the
                    branch cannot succeed and is abandoned immediately.
                    v3.0 pruned only downward, so it walked branches that
                    had already spent too little to ever reach the target.

    Element counts are held in a flat list indexed by position rather than
    a dict keyed by symbol, removing a dict read and write from every node
    of the search.

    Output is identical to the v3.0 implementation, verified by sweeping
    every nominal mass of every test parent formula.

    Returns a list of composition dicts (only elements with count > 0).
    """
    if prep is None:
        prep = _prepare_parent(parent)
    syms, noms, maxn, suffix = prep
    n_el    = len(syms)
    results = []
    if n_el == 0 or target_nom < 0:
        return results
    counts = [0] * n_el

    def recurse(idx, remaining):
        if idx == n_el:
            if remaining == 0:
                f = {}
                for i in range(n_el):
                    c = counts[i]
                    if c > 0:
                        f[syms[i]] = c
                if f:
                    results.append(f)
            return
        # Upward bound: is 'remaining' still reachable from here on?
        if suffix[idx] < remaining:
            return
        nom  = noms[idx]
        rest = suffix[idx + 1]
        # Downward bound: how many atoms of this element can fit at all.
        hi = remaining // nom
        if hi > maxn[idx]:
            hi = maxn[idx]
        # Lower bound: enough of this element that the rest can still reach it.
        lo = 0
        if remaining > rest:
            lo = -(-(remaining - rest) // nom)      # ceiling division
        for c in range(lo, hi + 1):
            counts[idx] = c
            recurse(idx + 1, remaining - c * nom)
        counts[idx] = 0

    recurse(0, target_nom)
    return results


def find_subformulas_cached(parent, target_nom, parent_key=None, prep=None):
    """find_subformulas() behind a cache keyed on (parent formula, target
    nominal mass) -- Option 2.

    Within one compound the same target nominal mass rarely recurs, so the
    win is across compounds: isomers share a parent formula and a real
    library has many. A library of entirely unique formulas sees no benefit
    and pays only one dict lookup per peak.

    The cached list and its dicts are shared, not copied. Every caller in
    this tool treats the result as read-only (it is filtered into a new
    list); do not mutate what this returns.
    """
    if parent_key is None:
        parent_key = formula_str(parent)
    key = (parent_key, target_nom)
    hit = _SUBFORMULA_CACHE.get(key)
    if hit is not None:
        return hit
    res = find_subformulas(parent, target_nom, prep)
    if len(_SUBFORMULA_CACHE) < _SUBFORMULA_CACHE_MAX:
        _SUBFORMULA_CACHE[key] = res
    return res

def score_formula(f, parent, target_nom, struct_whitelist=None,
                  rdb=None):
    """Heuristic score for candidate formula f.

    Criteria 1-11 (unchanged from v1.2 / v2.0):
      1. EE/OE preference          (+200 EE / +50 OE)
      2. Neutral loss analysis     (common loss bonus; bad-RDB penalty)
      3. Fragment contains C       (+30)
      4. Heteroatom retention     (+8 per shared het-atom)
      5. RDB in plausible range   (+15 if 0 <= DBE <= 15)
      6. RDB/C ratio check        (penalty if DBE > C+1)
      7. Zero-H penalty           (-150 if C>2 and H=0)
      8. Low H/C penalty          (-50 if H/C < 0.3)
      9. Carbon skeleton bonus    (+10 per C)
     10. H-saturation bonus       (+20/+12/+5 by H/C ratio)
     11. Fragment size bonus      (+0 to +10 by frag/parent ratio)

    Criterion 12 (new in v2.0):
     12. Structural rule match   (+200 if formula in whitelist)

    Stable ion bonus (new in v3.0):
     13. Known stable ion        (+100 from STABLE_IONS table)

    Returns an integer score; lower-scoring candidates are deprioritised
    by pick_best_v3().
    """
    if rdb is None:
        rdb = calc_rdb(f)
    if rdb < -0.5:
        return -1000    # physically impossible: too many H atoms

    sc   = 0
    n_c  = f.get('C', 0)
    n_h  = f.get('H', 0) + f.get('D', 0)

    # 1. Even-electron preference.
    # EI fragmentation strongly favours EE ions (closed-shell cations).
    if is_ee_ion(f):
        sc += 200
    else:
        sc += 50

    # 2. Neutral loss analysis.
    # Compute loss = parent - fragment; penalise implausible losses.
    loss = {}
    for sym in parent:
        l = parent.get(sym, 0) - f.get(sym, 0)
        if l < 0:
            return -1000   # fragment larger than parent -> impossible
        if l > 0:
            loss[sym] = l
    if loss:
        loss_rdb = calc_rdb(loss)
        # Neutral loss with negative DBE is chemically implausible.
        if loss_rdb < -0.5:
            sc -= 300
        # EE fragment should lose a radical (half-integer DBE loss);
        # OE fragment should lose a neutral (integer DBE loss).
        if is_ee_ion(f):
            if loss_rdb == int(loss_rdb):
                sc -= 30    # EE ion but loss is even-electron -- unusual
        else:
            if loss_rdb != int(loss_rdb):
                sc -= 30    # OE ion but loss is odd-electron -- unusual
        loss_c = loss.get('C', 0)
        if loss_c > 0 and loss_rdb > loss_c + 1:
            sc -= 80    # loss with too many rings/double bonds for its C count
        loss_s = formula_str(loss)
        if loss_s in COMMON_LOSSES:
            sc += COMMON_LOSSES[loss_s]   # recognised neutral loss
    else:
        sc += 100   # no loss -> molecular ion M+.

    # 3. Fragment should contain at least one carbon.
    if n_c > 0:
        sc += 30

    # 4. Heteroatom retention.
    # Fragments that keep heteroatoms from the parent are favoured
    # (heteroatom-directed fragmentation is the dominant EI pathway).
    for het in ['N', 'O', 'S', 'Si']:
        if parent.get(het, 0) > 0 and f.get(het, 0) > 0:
            sc += 8

    # 5. RDB in physically plausible range.
    if 0 <= rdb <= 15:
        sc += 15

    # 6. RDB/C ratio sanity check.
    # Extremely H-poor fragments are very rare in EI spectra.
    if n_c > 0 and rdb > n_c + 1:
        sc -= int(100 * (rdb - n_c - 1))

    # 7. Zero-hydrogen penalty.
    # Fragments with C>2 but no H are implausible (except CO2, etc.).
    if n_c > 2 and n_h == 0:
        sc -= 150

    # 8. Low H/C penalty.
    # H/C < 0.3 for large fragments is unusual in EI spectra.
    if n_c > 3 and n_h > 0:
        hc = float(n_h) / n_c
        if hc < 0.3:
            sc -= 50

    # 9. Carbon skeleton size bonus.
    # Larger carbon frameworks are thermodynamically more stable.
    sc += n_c * 10

    # 10. Hydrogen saturation bonus.
    # Well-saturated carbocations (H/C >= 1.5) are stabilised by
    # hyperconjugation and are common EI fragments.
    if n_c > 0:
        hc_ratio = float(n_h) / n_c
        if hc_ratio >= 1.5:
            sc += 20
        elif hc_ratio >= 1.0:
            sc += 12
        elif hc_ratio >= 0.5:
            sc += 5

    # 11. Fragment size bonus.
    # Heavier fragments relative to the parent are more diagnostic
    # and more commonly observed in libraries.
    frag_nom   = calc_nominal(f)
    parent_nom = calc_nominal(parent)
    if parent_nom > 0:
        sc += int(float(frag_nom) / parent_nom * 10)

    # 12. Structural rule match bonus [v2.0].
    # +200 when the formula matches one of the four rule engines.
    if struct_whitelist is not None and formula_str(f) in struct_whitelist:
        sc += 200

    # 13. Stable ion bonus [v3.0].
    # +100 when the formula matches a known stable cation in the library.
    if lookup_stable_ion(f, frag_nom) is not None:
        sc += STABLE_ION_BONUS

    return sc

def pick_best_v3(candidates, parent, target_nom, struct_whitelist,
                 intensity_map, parent_ring_count, filter_flags,
                 rdkit_frags=None):
    """Select the best candidate formula for a peak using a three-tier
    priority scheme:
        Tier 1: candidates that pass all enabled filters (filter_passed=True)
                are preferred over those that fail.
        Tier 2: within each tier, highest heuristic score wins.
        Tier 3: lowest isotope pattern deviation breaks ties.

    Option 3 (cheap pre-filter) is applied conservatively, in the two forms
    that provably cannot change which candidate wins:

      * score_formula() returns a hard floor of -1000 for any candidate with
        DBE < -0.5. Such a candidate can only win if EVERY candidate is in
        that state, so when at least one physically possible candidate
        exists the impossible ones are dropped before the expensive
        apply_all_filters() / score_formula() pass rather than after.
      * DBE is computed once here and handed to both apply_all_filters()
        and score_formula(), instead of each recomputing it.

    The paper's more aggressive pre-filter (RDB range, H/C ratio, zero-H)
    is deliberately NOT applied: those criteria carry finite penalties, not
    floors, so a candidate failing one can still legitimately win. Applying
    them as filters would change results, and score_formula() has not been
    profiled to show the saving is worth it.

    Parameters
    ----------
    candidates        : list of composition dicts from find_subformulas().
    parent            : composition dict for the parent molecule.
    target_nom        : nominal m/z of the peak.
    struct_whitelist  : set of formula strings or None.
    intensity_map     : {nom_mz: abundance} for isotope scoring.
    parent_ring_count : int or None from MOL block.
    filter_flags      : dict of {filter_name: bool}.

    Returns the best composition dict, or None if candidates is empty.
    """
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    # Compute DBE once per candidate and partition on the hard floor.
    rdbs = [calc_rdb(f) for f in candidates]
    possible = [i for i in range(len(candidates)) if rdbs[i] >= -0.5]
    if possible:
        idxs = possible
    else:
        idxs = range(len(candidates))       # all impossible: score them all

    if len(idxs) == 1:
        return candidates[idxs[0]]

    scored = []
    for i in idxs:
        f     = candidates[i]
        rdb   = rdbs[i]
        fp, iso_sc, _ = apply_all_filters(
            f, target_nom, rdb, intensity_map,
            parent_ring_count, filter_flags, rdkit_frags)
        h_sc  = score_formula(f, parent, target_nom, struct_whitelist, rdb)
        # Sort key: (not_passed, -h_score, iso_score)
        # Smaller key -> better candidate.
        scored.append((0 if fp else 1, -h_sc, iso_sc, f))

    scored.sort(key=lambda x: (x[0], x[1], x[2]))
    return scored[0][3]   # return formula dict of best candidate

# ==================================================================
# SECTION 10b: Shared assignment pipeline  (Option 6)
# ==================================================================
# v3.0 ran build_struct_whitelist -> find_subformulas -> pick_best_v3 at
# two separate call sites: once in convert_library() and once in the
# preview handler. The two had to be kept in step by hand or the preview
# would stop predicting what the conversion actually writes. Both now go
# through build_compound_context() and assign_peak(), so there is one
# implementation of the pipeline and the preview cannot drift from the
# conversion.

def build_compound_context(parent, mol, filter_flags):
    """Per-compound preparation shared by the conversion and the preview.

    Parses the MOL block once, builds the structural whitelist, the RDKit
    bond-break fragment set and the enumeration preparation, and caches the
    parent nominal mass and formula key.

    Returns a dict consumed by assign_peak().
    """
    mol_data = parse_mol_block(mol) if mol else None
    ctx = {
        'mol_data':    mol_data,
        'struct_wl':   build_struct_whitelist(mol_data) if mol_data else None,
        'ring_count':  mol_data['ring_count'] if mol_data else None,
        'rdkit_frags': None,
        'prep':        _prepare_parent(parent),
        'parent_key':  formula_str(parent),
        'parent_nom':  calc_nominal(parent),
    }
    if filter_flags.get('rdkit', False) and RDKIT_LOADED and mol_data:
        try:
            ctx['rdkit_frags'] = get_all_bond_break_formulas(mol_data)
        except:
            ctx['rdkit_frags'] = None
    return ctx


def assign_peak(parent, t_nom, ctx, intensity_map, filter_flags,
                electron_mode):
    """Assign one peak to its best candidate formula.

    Returns (best_formula, exact_mass, n_candidates):
      best_formula  composition dict, or None if the peak is unassigned
      exact_mass    electron-corrected exact mass, or None
      n_candidates  how many physically possible candidates were considered
                    (callers use > 1 to count ambiguous assignments)

    Peaks above the molecular ion (+1 for the 13C satellite) are rejected,
    as are peaks with no candidate whose DBE reaches the -0.5 physical
    limit.
    """
    if t_nom > ctx['parent_nom'] + 1:
        return None, None, 0
    subs  = find_subformulas_cached(
        parent, t_nom, ctx['parent_key'], ctx['prep'])
    # Pre-filter: DBE >= -0.5 (the hard physical limit for all ions).
    valid = [f for f in subs if calc_rdb(f) >= -0.5]
    if not valid:
        return None, None, 0
    best = pick_best_v3(
        valid, parent, t_nom, ctx['struct_wl'],
        intensity_map, ctx['ring_count'], filter_flags, ctx['rdkit_frags'])
    if best is None:
        return None, None, len(valid)
    exact = apply_electron_mode(calc_exact(best), electron_mode)
    return best, exact, len(valid)

# ==================================================================
# SECTION 11: XML / binary I/O helpers
# ==================================================================

ws_re = Regex(r"\s+")

def decode_doubles(b64):
    """Decode a base64 string into a Python list of IEEE 754 doubles.
    MassHunter stores m/z and abundance arrays in this format inside
    <MzValues> and <AbundanceValues> XML elements.

    Option 5: the whole byte array is converted with a single
    Buffer.BlockCopy instead of N marshaled BitConverter.ToDouble calls.
    """
    if not b64:
        return []
    clean = ws_re.Replace(b64.strip(), "")
    mod = len(clean) % 4
    if mod:
        clean += "=" * (4 - mod)
    try:
        data = Convert.FromBase64String(clean)
    except:
        return []
    n = data.Length // 8
    if n <= 0:
        return []
    arr = Array.CreateInstance(Double, n)
    Buffer.BlockCopy(data, 0, arr, 0, n * 8)
    return [float(arr[i]) for i in range(n)]

def encode_doubles(vals):
    """Encode a Python list of floats as a base64 IEEE 754 double array.
    Required for writing <MzValues> / <AbundanceValues> in output XML.

    Option 5, and the reason it matters: v3.0 encoded each value with
    BitConverter.GetBytes(Double.Parse(str(v))). Double.Parse(String) with
    no IFormatProvider uses CurrentCulture AND NumberStyles.AllowThousands,
    so on any locale where '.' is the GROUP separator it silently returned
    a DIFFERENT number rather than raising. Measured on CLR 4.0.30319 under
    de-DE: "147.08" -> 14708.0, "42.033826" -> 42033826.0, "1.5" -> 15.0.
    Being culture-dependent it is correct on an en-US machine, which is how
    it passed validation.

    The string round trip was never needed -- the value is already a float.
    The array is now converted in one Buffer.BlockCopy, which is both
    faster and locale-independent by construction.
    """
    n = len(vals)
    if n == 0:
        return ""
    arr = Array.CreateInstance(Double, n)
    for i in range(n):
        arr[i] = float(vals[i])
    data = Array.CreateInstance(Byte, n * 8)
    Buffer.BlockCopy(arr, 0, data, 0, n * 8)
    return Convert.ToBase64String(data)

def xtext(node, names, default=""):
    """Return the inner text of the first matching child element.
    Tries each name in 'names' in order; returns 'default' if none found.
    Uses local-name() XPath to ignore namespace prefixes.
    """
    for n in names:
        try:
            x = node.SelectSingleNode(
                ".//*[local-name()='{0}']".format(n))
            if x is not None:
                t = (x.InnerText or "").strip()
                if t:
                    return t
        except:
            pass
    return default

def xnodes(doc, local_name):
    """Return all nodes with the given local name from document doc."""
    try:
        return doc.SelectNodes(
            "//*[local-name()='{0}']".format(local_name))
    except:
        return None

def xml_esc(s):
    """Escape a string for safe embedding in XML text/attribute content."""
    if s is None:
        return ""
    s = str(s)
    s = s.replace("&", "&amp;")
    s = s.replace("<", "&lt;")
    s = s.replace(">", "&gt;")
    s = s.replace('"',  "&quot;")
    s = s.replace("'",  "&apos;")
    return s

def sanitize_xml(text):
    """Remove non-XML characters from a string.
    XmlDocument.LoadXml() rejects control characters except TAB/LF/CR.
    This filter removes all code points outside the XML 1.0 character set.
    """
    sb = StringBuilder()
    for ch in text:
        cp = ord(ch)
        if (cp == 0x9 or cp == 0xA or cp == 0xD or
                (0x20 <= cp <= 0xD7FF) or
                (0xE000 <= cp <= 0xFFFD)):
            sb.Append(ch)
    return sb.ToString()

# ==================================================================
# SECTION 12: Library conversion pipeline
# ==================================================================

def convert_library(xml_path, out_path, min_peaks, electron_mode,
                    log_fn, filter_flags, export_flags=None):
    """Convert a unit-mass MassHunter library to exact mass.

    For each compound:
      1. Parse the molecular formula and MOL block.
      2. Build the structural fragment whitelist (4 rules).
      3. Build the intensity map for isotope scoring.
      4. For each peak: enumerate sub-formulas, apply all filters,
         score, and select the best formula.
      5. Apply the electron-mass correction.
      6. Write the output XML library.

    Parameters
    ----------
    xml_path      : str   Path to the input .mslibrary.xml file.
    out_path      : str   Path for the output file.
    min_peaks     : int   Minimum assigned peaks; compounds below
                          this threshold are skipped.
    electron_mode : str   'remove' / 'add' / 'none'.
    log_fn        : callable  Logging function (appends to GUI log).
    filter_flags  : dict  {filter_name: bool} from GUI checkboxes.
    """
    log_fn("[INFO] Reading: " + xml_path)
    enc = Encoding.GetEncoding(
        "utf-8",
        EncoderFallback.ReplacementFallback,
        DecoderFallback.ReplacementFallback)
    raw   = File.ReadAllText(xml_path, enc)
    clean = sanitize_xml(raw)
    doc   = XmlDocument()
    doc.LoadXml(clean)

    compounds = xnodes(doc, "Compound")
    spectra   = xnodes(doc, "Spectrum")
    c_count   = compounds.Count if compounds else 0
    s_count   = spectra.Count   if spectra   else 0
    log_fn("[INFO] Compounds: {0},  Spectra: {1}".format(c_count, s_count))

    # Build a map from CompoundID -> list of Spectrum nodes.
    spec_map = {}
    if spectra:
        for sp in spectra:
            cid = xtext(sp, ["CompoundID"])
            if cid not in spec_map:
                spec_map[cid] = []
            spec_map[cid].append(sp)

    from System import DateTime
    now          = DateTime.Now.ToString("o")
    out_compounds = []
    skipped_nf    = 0    # skipped: no/bad formula
    skipped_fp    = 0    # skipped: too few peaks
    total         = 0
    used_struct   = 0    # compounds that had a MOL block

    for ci in range(c_count):
        comp       = compounds[ci]
        cid        = xtext(comp, ["CompoundID"])
        name       = xtext(comp, ["CompoundName"])
        cas        = xtext(comp, ["CASNumber"])
        formula_s  = xtext(comp, ["Formula"])
        mw         = xtext(comp, ["MolecularWeight"])
        rt         = xtext(comp, ["RetentionTimeRTL"])
        ri         = xtext(comp, ["RetentionIndex"])
        bp         = xtext(comp, ["BoilingPoint"],     "-300")
        mp         = xtext(comp, ["MeltingPoint"],     "-300")
        mol        = xtext(comp, ["MolFile"])
        desc       = xtext(comp, ["Description"])

        parent = parse_formula(formula_s)
        if parent is None:
            skipped_nf += 1
            log_fn("[SKIP] {0}: {1}".format(
                name, formula_s or "no formula"))
            continue
        # One shared context builder for convert and preview (Option 6).
        ctx        = build_compound_context(parent, mol, filter_flags)
        parent_nom = ctx['parent_nom']
        mol_data   = ctx['mol_data']
        struct_wl  = ctx['struct_wl']
        ring_count = ctx['ring_count']
        if struct_wl is not None:
            used_struct += 1

        # RDKit: parse parent mol block and build bond-break fragment set.
        # get_all_bond_break_formulas() uses our own BFS on mol_data;
        # _RdkRWMol.MolFromMolBlock() provides additional structural
        # validation and a formula cross-check with the library field.
        rdkit_frags = None
        if filter_flags.get('rdkit', False) and RDKIT_LOADED and mol_data:
            try:
                rdkit_mol = _RdkRWMol.MolFromMolBlock(
                    mol + "\n", True, False)   # sanitize=True, removeHs=False
                if rdkit_mol is not None:
                    # Cross-check: atom count from RDKit vs library formula.
                    rdk_heavy = {}
                    for ai in range(rdkit_mol.getNumAtoms()):
                        atom = rdkit_mol.getAtomWithIdx(ai)
                        sym = atom.getSymbol()
                        if sym not in ('H', 'D'):
                            rdk_heavy[sym] = rdk_heavy.get(sym, 0) + 1
                    lib_heavy = {
                        el: cnt for el, cnt in parent.items()
                        if el not in ('H', 'D')}
                    if rdk_heavy != lib_heavy:
                        log_fn(
                            "[WARN] RDKit mol formula mismatch for "
                            "{0}: lib={1} mol={2}".format(
                                name, formula_str(lib_heavy),
                                formula_str(rdk_heavy)))
                # Fragment set already built by build_compound_context().
                rdkit_frags = ctx['rdkit_frags']
            except:
                rdkit_frags = None

        sp_nodes = spec_map.get(cid, [])
        if not sp_nodes:
            log_fn("[SKIP] {0}: no spectrum".format(name))
            continue
        sp      = sp_nodes[0]
        mz_vals = decode_doubles(xtext(sp, ["MzValues"]))
        ab_vals = decode_doubles(xtext(sp, ["AbundanceValues"]))
        if len(mz_vals) == 0 or len(mz_vals) != len(ab_vals):
            log_fn("[SKIP] {0}: bad spectrum".format(name))
            continue

        # Build intensity map for isotope scoring: {nom_mz: max_abundance}.
        intensity_map = {}
        for pi in range(len(mz_vals)):
            nom = int(round(mz_vals[pi]))
            ab  = ab_vals[pi]
            if nom not in intensity_map or ab > intensity_map[nom]:
                intensity_map[nom] = ab

        new_mz   = []
        new_ab   = []
        new_form = []
        ambig    = 0

        for pi in range(len(mz_vals)):
            mz    = mz_vals[pi]
            ab    = ab_vals[pi]
            t_nom = int(round(mz))
            # Single shared pipeline -- see assign_peak() (Option 6).
            best, exact, n_valid = assign_peak(
                parent, t_nom, ctx, intensity_map,
                filter_flags, electron_mode)
            if best is None:
                continue
            if n_valid > 1:
                ambig += 1
            new_mz.append(exact)
            new_ab.append(ab)
            new_form.append(formula_str(best))

        if len(new_mz) < min_peaks:
            skipped_fp += 1
            log_fn("[SKIP] {0}: {1} peaks (need {2})".format(
                name, len(new_mz), min_peaks))
            continue

        # Sort peaks by ascending exact m/z (required by MassHunter).
        combined = sorted(
            zip(new_mz, new_ab, new_form), key=lambda x: x[0])
        new_mz   = [x[0] for x in combined]
        new_ab   = [x[1] for x in combined]
        new_form = [x[2] for x in combined]

        # Normalise abundances to [0, 9999] (MassHunter internal scale).
        max_ab = max(new_ab) if new_ab else 1.0
        if max_ab <= 0:
            max_ab = 1.0
        norm_ab = [(a / max_ab) * 9999.0 for a in new_ab]

        # Find the base peak index (highest normalised abundance).
        bp_idx = 0
        for i in range(len(norm_ab)):
            if norm_ab[i] >= norm_ab[bp_idx]:
                bp_idx = i

        ambi_str   = " ({0} ambig)".format(ambig) if ambig > 0 else ""
        struct_str = " [+struct]" if struct_wl else ""
        log_fn("[OK] {0}: {1}/{2} peaks{3}{4}".format(
            name, len(new_mz), len(mz_vals), ambi_str, struct_str))

        out_compounds.append({
            "Name": name, "CAS": cas, "Formula": formula_s,
            "MW": mw, "RT": rt, "RI": ri, "BP": bp, "MP": mp,
            "MolFile": mol, "Desc": desc,
            "mz": new_mz, "ab": norm_ab,
            "formulas": new_form, "bp_idx": bp_idx,
        })
        total += 1
        if ((ci + 1) % 25) == 0:
            log_fn("[INFO] Processed {0}/{1}...".format(ci + 1, c_count))

    # ------------------------------------------------------------------
    # Summary log
    # ------------------------------------------------------------------
    log_fn("")
    log_fn("[INFO] Summary:")
    log_fn("  Converted:             {0}".format(total))
    log_fn("  With structural rules: {0}".format(used_struct))
    log_fn("  Skipped (formula):     {0}".format(skipped_nf))
    log_fn("  Skipped (peaks):       {0}".format(skipped_fp))

    if total == 0:
        log_fn("[WARN] No compounds converted!")
        return 0

    # ------------------------------------------------------------------
    # Build output XML in MassHunter library format.
    # ------------------------------------------------------------------
    log_fn("")
    log_fn("[INFO] Building XML...")
    sb = StringBuilder()
    sb.AppendLine('<?xml version="1.0" encoding="utf-8"?>')
    sb.AppendLine(
        '<LibraryDataSet SchemaVersion="2" '
        'xmlns="Quantitation.LibraryDatabase">')
    sb.AppendLine('  <Library>')
    sb.AppendLine('    <LibraryID>1</LibraryID>')
    sb.AppendLine('    <AccurateMass>true</AccurateMass>')
    sb.AppendLine(
        '    <CreationDateTime>{0}</CreationDateTime>'.format(now))
    sb.AppendLine(
        '    <LastEditDateTime>{0}</LastEditDateTime>'.format(now))
    sb.AppendLine('  </Library>')

    for idx, c in enumerate(out_compounds):
        cid = idx + 1
        mz  = c["mz"]
        ab  = c["ab"]
        bpi = c["bp_idx"]

        sb.AppendLine('  <Compound>')
        sb.AppendLine('    <LibraryID>1</LibraryID>')
        sb.AppendLine('    <CompoundID>{0}</CompoundID>'.format(cid))
        sb.AppendLine('    <BoilingPoint>{0}</BoilingPoint>'.format(
            c.get("BP", "-300")))
        if c.get("CAS"):
            sb.AppendLine('    <CASNumber>{0}</CASNumber>'.format(
                xml_esc(c["CAS"])))
        sb.AppendLine('    <CompoundName>{0}</CompoundName>'.format(
            xml_esc(c["Name"])))
        if c.get("Formula"):
            sb.AppendLine('    <Formula>{0}</Formula>'.format(
                xml_esc(c["Formula"])))
        sb.AppendLine(
            '    <LastEditDateTime>{0}</LastEditDateTime>'.format(now))
        sb.AppendLine('    <MeltingPoint>{0}</MeltingPoint>'.format(
            c.get("MP", "-300")))
        if c.get("MW"):
            sb.AppendLine(
                '    <MolecularWeight>{0}</MolecularWeight>'.format(c["MW"]))
        if c.get("MolFile"):
            sb.AppendLine('    <MolFile>{0}</MolFile>'.format(
                xml_esc(c["MolFile"])))
        if c.get("RI"):
            sb.AppendLine(
                '    <RetentionIndex>{0}</RetentionIndex>'.format(c["RI"]))
        if c.get("RT"):
            sb.AppendLine(
                '    <RetentionTimeRTL>{0}</RetentionTimeRTL>'.format(c["RT"]))
        sb.AppendLine('  </Compound>')

        mz_b64 = encode_doubles(mz)
        ab_b64 = encode_doubles(ab)
        sb.AppendLine('  <Spectrum>')
        sb.AppendLine('    <LibraryID>1</LibraryID>')
        sb.AppendLine('    <CompoundID>{0}</CompoundID>'.format(cid))
        sb.AppendLine('    <SpectrumID>1</SpectrumID>')
        sb.AppendLine(
            '    <AbundanceValues>{0}</AbundanceValues>'.format(ab_b64))
        sb.AppendLine('    <BasePeakAbundance>9999</BasePeakAbundance>')
        sb.AppendLine('    <BasePeakMZ>{0}</BasePeakMZ>'.format(mz[bpi]))
        sb.AppendLine('    <HighestMz>{0}</HighestMz>'.format(max(mz)))
        sb.AppendLine('    <IonPolarity>Positive</IonPolarity>')
        sb.AppendLine(
            '    <InstrumentType>QuadrupoleTimeOfFlight</InstrumentType>')
        sb.AppendLine(
            '    <LastEditDateTime>{0}</LastEditDateTime>'.format(now))
        sb.AppendLine('    <LowestMz>{0}</LowestMz>'.format(min(mz)))
        sb.AppendLine('    <MzValues>{0}</MzValues>'.format(mz_b64))
        sb.AppendLine(
            '    <NumberOfPeaks>{0}</NumberOfPeaks>'.format(len(mz)))
        sb.AppendLine('    <ScanType>Scan</ScanType>')
        sb.AppendLine('  </Spectrum>')

    sb.AppendLine('</LibraryDataSet>')

    # Derive base path (strip .mslibrary.xml or .xml) for MSP/SDF.
    _base = out_path
    for _e in ['.mslibrary.xml', '.xml']:
        if _base.lower().endswith(_e):
            _base = _base[:-len(_e)]
            break

    # Write XML (always, or when export_flags['xml'] is True).
    if export_flags is None or export_flags.get('xml', True):
        log_fn("[INFO] Writing XML: " + out_path)
        File.WriteAllText(out_path, sb.ToString(), Encoding.UTF8)
        log_fn("[INFO] XML done.  {0} compounds.".format(total))

    # Write MSP (optional).
    if export_flags and export_flags.get('msp', False):
        write_msp(_base + '.msp', out_compounds, log_fn)

    # Write SDF (optional).
    if export_flags and export_flags.get('sdf', False):
        write_sdf(_base + '.sdf', out_compounds, log_fn)

    return total

# ==================================================================
# SECTION 12b: Optional export format writers
# ==================================================================

def write_msp(out_path, compounds, log_fn):
    """Write compounds to NIST MSP format.

    Record layout (one blank line between records):
        Name: <name>
        Formula: <formula>          (if present)
        MW: <nominal_mw>            (if present)
        CAS#: <cas>                 (if present)
        Num Peaks: <n>
        <nom_mz> <intensity>        (0-999 scale, one peak per line)
                                    (blank line terminates record)

    Notes
    -----
    - m/z values are rounded to the nearest integer (nominal mass).
      If two peaks round to the same integer, only the higher-
      abundance one is kept.
    - Intensities are rescaled from the internal 0-9999 range to
      the NIST standard 0-999 range.
    """
    log_fn("[INFO] Writing MSP: " + out_path)
    sb = StringBuilder()
    for c in compounds:
        name = c.get("Name") or ""
        sb.AppendLine("Name: " + name)
        if c.get("Formula"):
            sb.AppendLine("Formula: " + c["Formula"])
        if c.get("MW"):
            sb.AppendLine("MW: " + c["MW"])
        if c.get("CAS"):
            sb.AppendLine("CAS#: " + c["CAS"])
        if c.get("RI"):
            sb.AppendLine("Retention_index: " + c["RI"])
        mz_vals = c["mz"]
        ab_vals = c["ab"]
        # Round exact m/z -> nominal integer; scale 0-9999 -> 0-999.
        # Merge duplicate nominal masses (keep highest abundance).
        peak_map = {}
        for i in range(len(mz_vals)):
            nom = int(round(mz_vals[i]))
            ab  = max(1, int(round(ab_vals[i] / 10.0)))
            if nom not in peak_map or ab > peak_map[nom]:
                peak_map[nom] = ab
        sorted_peaks = sorted(peak_map.items())
        sb.AppendLine("Num Peaks: " + str(len(sorted_peaks)))
        for nom, ab in sorted_peaks:
            sb.AppendLine("{0} {1}".format(nom, ab))
        sb.AppendLine("")   # blank line separates MSP records
    File.WriteAllText(out_path, sb.ToString(), Encoding.UTF8)
    log_fn("[INFO] MSP done.  {0} compounds.".format(len(compounds)))

def write_sdf(out_path, compounds, log_fn):
    """Write compounds to MDL SDF format.

    Each SDF record:
        <V2000 mol block>    (from input MolFile, or empty placeholder)
        >  <COMPOUND_NAME>
        >  <FORMULA>
        >  <CAS>
        >  <MW>
        >  <MASS_SPECTRAL_PEAKS>
            <exact_mz_6dp> <intensity_0-999> <formula_assignment>
        $$$$

    The MASS_SPECTRAL_PEAKS field uses the exact-mass m/z values
    produced by the converter (6 decimal places), so the SDF can be
    loaded by any tool that reads accurate-mass spectra.
    """
    log_fn("[INFO] Writing SDF: " + out_path)
    sb = StringBuilder()
    for c in compounds:
        name     = c.get("Name") or ""
        mol_text = (c.get("MolFile") or "").strip()

        # Write mol block (V2000).
        if mol_text:
            # Normalise line endings then emit each line.
            mol_lines = mol_text.replace(
                "\r\n", "\n").replace("\r", "\n").split("\n")
            for ml in mol_lines:
                sb.AppendLine(ml)
            # Ensure M  END is present (guard against truncated blocks).
            last_content = ""
            for ml in reversed(mol_lines):
                if ml.strip():
                    last_content = ml.strip()
                    break
            if "M  END" not in last_content and "M END" not in last_content:
                sb.AppendLine("M  END")
        else:
            # No structure available: write a minimal empty mol block.
            sb.AppendLine(name[:80] if name else "")
            sb.AppendLine("  ExactMass v3.0")
            sb.AppendLine("")
            sb.AppendLine(
                "  0  0  0  0  0  0  0  0  0  0999 V2000")
            sb.AppendLine("M  END")

        # Data fields.
        sb.AppendLine(">  <COMPOUND_NAME>")
        sb.AppendLine(name)
        sb.AppendLine("")

        if c.get("Formula"):
            sb.AppendLine(">  <FORMULA>")
            sb.AppendLine(c["Formula"])
            sb.AppendLine("")

        if c.get("CAS"):
            sb.AppendLine(">  <CAS>")
            sb.AppendLine(c["CAS"])
            sb.AppendLine("")

        if c.get("MW"):
            sb.AppendLine(">  <MW>")
            sb.AppendLine(c["MW"])
            sb.AppendLine("")

        # Peak assignments: exact m/z, scaled intensity, formula.
        mz_vals   = c["mz"]
        ab_vals   = c["ab"]
        form_list = c.get("formulas", [])
        sb.AppendLine(">  <MASS_SPECTRAL_PEAKS>")
        for i in range(len(mz_vals)):
            ab_sc  = max(1, int(round(ab_vals[i] / 10.0)))
            form_s = form_list[i] if i < len(form_list) else ""
            sb.AppendLine("{0:.6f} {1} {2}".format(
                mz_vals[i], ab_sc, form_s).rstrip())
        sb.AppendLine("")

        sb.AppendLine("$$$$")   # SDF record terminator

    File.WriteAllText(out_path, sb.ToString(), Encoding.UTF8)
    log_fn("[INFO] SDF done.  {0} compounds.".format(len(compounds)))

# ==================================================================
# SECTION 13: Configuration persistence
# ==================================================================
# Settings are stored in a plain "key=value" text file under
# %APPDATA%\exactmass_libconv\settings.txt  (one setting per line).
# Unknown keys are silently ignored for forward compatibility.

def get_cfg_path():
    """Return the path to the settings file, creating the directory."""
    appdata = Environment.GetFolderPath(
        Environment.SpecialFolder.ApplicationData)
    base = Path.Combine(appdata, "exactmass_libconv")
    if not Directory.Exists(base):
        try:
            Directory.CreateDirectory(base)
        except:
            pass
    return Path.Combine(base, "settings.txt")

cfg_path = get_cfg_path()

def load_config():
    """Load saved settings. Returns a dict with sensible defaults."""
    defaults = {
        'last_dir':     "C:\\",
        'electron_mode': "remove",
        'min_peaks':    "3",
        'flt_nitrogen': "1",
        'flt_hd':       "1",
        'flt_lewis':    "1",
        'flt_isotope':  "1",
        'flt_smiles':   "1",
        'flt_rdkit':    "0",
        'export_xml':   "1",
        'export_msp':   "0",
        'export_sdf':   "0",
    }
    try:
        if File.Exists(cfg_path):
            for line in File.ReadAllLines(cfg_path):
                line = line.strip()
                if '=' in line:
                    k, v = line.split('=', 1)
                    defaults[k.strip()] = v.strip()
    except:
        pass
    return defaults

def save_config(cfg):
    """Persist settings dict to the settings file."""
    try:
        lines = ["{0}={1}".format(k, v) for k, v in cfg.items()]
        File.WriteAllLines(cfg_path, lines)
    except:
        pass

cfg      = load_config()
last_dir = [cfg.get('last_dir', "C:\\")]


# =============================================================================
# SECTION 13b: Readme / About dialog   (style guide sections 7 and 8)
# =============================================================================

DISCLAIMER = ("Created by Agilent but not officially tested/supported, this "
              "is a user contributed tool that is as-is with no warranty.")

DESCRIPTION = (
    "Converts a unit-mass EI spectral library into an exact-mass library. "
    "For every peak of every compound it enumerates the sub-formulas of the "
    "parent molecule with matching nominal mass, rejects the chemically "
    "impossible ones with up to six filters, scores the survivors against EI "
    "fragmentation rules and a stable-ion library, and writes the winning "
    "exact mass back out as MassHunter XML, NIST MSP and/or MDL SDF.")

README_HTML = r'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>EI Fragment Calculator v3.1</title>
<style>
 body{font-family:"Segoe UI",sans-serif;background:#EAEAEA;color:#53565A;
      margin:0;padding:0}
 .banner{background:#0085D5;color:#fff;padding:16px 24px;font-size:20px}
 .banner span{font-size:13px;opacity:.85;margin-left:10px}
 .wrap{max-width:900px;margin:0 auto;padding:24px}
 .card{background:#fff;border:1px solid #C8C8C6;padding:18px 22px;
       margin-bottom:18px}
 .warn{background:#FFF6E5;border:1px solid #E8C88A;padding:12px 16px;
       margin-bottom:18px;color:#6B5628}
 h2{color:#303030;font-size:16px;margin:22px 0 8px}
 h3{color:#303030;font-size:13px;margin:16px 0 6px}
 table{border-collapse:collapse;width:100%;margin:8px 0 14px}
 th{background:#D4DDE5;color:#303030;text-align:left;padding:6px 9px;
    font-size:12px}
 td{border-bottom:1px solid #E4E4E2;padding:6px 9px;font-size:12px;
    vertical-align:top}
 code{font-family:Consolas,monospace;background:#F3F7FB;padding:1px 4px}
 .foot{color:#888B8D;font-size:11px;text-align:center;padding:10px 0 26px}
</style></head><body>
<div class="banner">EI Fragment Calculator<span>v3.1</span></div>
<div class="wrap">

<div class="warn"><b>Disclaimer.</b> Created by Agilent but not officially
tested/supported, this is a user contributed tool that is as-is with no
warranty.</div>

<div class="card">
<h2>What it does</h2>
<p>Converts a unit-mass EI spectral library into an exact-mass library. For
each compound the tool parses the molecular formula and the MOL block, builds
a structural fragment whitelist, and then for every peak enumerates all
sub-formulas of the parent with matching nominal mass, filters them, scores
them, and assigns the best candidate.</p>
<p>The molecular formula is an <b>elemental upper bound</b>: a fragment can
never contain an atom the parent does not have. That is what makes the
enumeration tractable and the assignment meaningful.</p>
</div>

<div class="card">
<h2>Workflow</h2>
<table>
<tr><th>Step</th><th>What to do</th></tr>
<tr><td>1</td><td>Pick the <b>Input XML</b> -- a MassHunter library
(<code>.mslibrary.xml</code>) whose spectra carry unit-mass peaks.</td></tr>
<tr><td>2</td><td>Pick an <b>Output Path</b>. The XML is written as
<code>&lt;base&gt;_exactmass.mslibrary.xml</code>; MSP and SDF, if ticked, sit
alongside it.</td></tr>
<tr><td>3</td><td>Choose the <b>Electron mode</b>: <code>remove</code> for
EI+ (the detector measures the ion, i.e. neutral minus one electron),
<code>add</code> for EI-, <code>none</code> for no correction.</td></tr>
<tr><td>4</td><td>Set <b>Min peaks</b> -- spectra with fewer assigned peaks
than this are skipped.</td></tr>
<tr><td>5</td><td>Tick the <b>filters</b> you want. All are on by default
except RDKit.</td></tr>
<tr><td>6</td><td>Press <b>Preview</b> first. It runs the identical
assignment pipeline as Convert and writes nothing.</td></tr>
<tr><td>7</td><td>Press <b>Convert</b> to write the output files.</td></tr>
</table>
</div>

<div class="card">
<h2>The six filters</h2>
<table>
<tr><th>Filter</th><th>Rejects</th><th>Source</th></tr>
<tr><td>Nitrogen rule</td><td>Odd/even m/z inconsistent with the N+P count
for the ion type</td><td>McLafferty &amp; Turecek 1993</td></tr>
<tr><td>HD-check</td><td>DBE/C above 1.0 -- implausibly hydrogen-poor
fragments</td><td>Pretsch et al. 2009</td></tr>
<tr><td>Lewis-Senior</td><td>Valence sums that cannot form a connected
structure</td><td>Senior 1951</td></tr>
<tr><td>Isotope M+1/M+2</td><td>Formulas whose predicted isotope pattern
disagrees with the observed spectrum</td><td>Gross 2017</td></tr>
<tr><td>SMILES ring-count</td><td>Fragments with more rings than the parent
can supply</td><td>Weininger 1988</td></tr>
<tr><td>RDKit bond-break</td><td>Heavy-atom formulas unreachable by any
single bond break</td><td>optional, needs the RDKit .NET assembly</td></tr>
</table>
<p>The isotope filter uses the spectrum itself, so it is the most powerful of
the six on halogenated compounds -- but it needs real intensity contrast to
work.</p>
</div>

<div class="card">
<h2>Structural fragmentation rules</h2>
<p>When the library entry carries a MOL block, four rules build a whitelist of
formulas that a real EI fragmentation could produce. A candidate matching the
whitelist receives the largest single bonus in the scoring model.</p>
<table>
<tr><th>Rule</th><th>Covers</th></tr>
<tr><td>Homolytic cleavage</td><td>Every non-ring single bond broken -- the
general sigma-bond case</td></tr>
<tr><td>Alpha-cleavage</td><td>C-C bonds alpha to N/O/S/halogen; dominant for
aldehydes, amines, ethers and halides</td></tr>
<tr><td>McLafferty rearrangement</td><td>gamma-H migration to a carbonyl via a
six-membered transition state</td></tr>
<tr><td>Retro-Diels-Alder</td><td>Six-membered rings containing C=C splitting
into diene and dienophile</td></tr>
</table>
</div>

<div class="card">
<h2>Reading the preview</h2>
<p>One line per assigned peak: nominal m/z, relative intensity, the assigned
exact mass, the formula, EE or OE, and the neutral loss from the molecular
ion. Tags: <code>[Nopt]</code> means N candidates were possible and one was
chosen; <code>*</code> means the formula matched the structural whitelist;
<code>[ion]</code> names a hit in the stable-ion library.</p>
<p>A high <code>[Nopt]</code> count on a compound is the signal to enable more
filters or to supply a MOL block.</p>
</div>

<div class="card">
<h2>Notes and limits</h2>
<p><b>Unit mass in, exact mass out.</b> The tool does not measure anything --
it assigns the most plausible formula to each nominal peak and reports that
formula's calculated exact mass. It cannot substitute for accurate-mass
acquisition.</p>
<p><b>Ambiguity is real.</b> At higher m/z a nominal mass can host many valid
sub-formulas. The filters and the structural whitelist narrow this, but where
they cannot, the winning candidate is a ranked guess.</p>
<p><b>Elements.</b> 30 supported: Al As B Br C Ca Cl Co Cr Cu D F Fe H I K Mg
Mn N Na Ni O P Pb S Se Si Sn Ti V Zn.</p>
<p><b>Settings</b> (last folder, min peaks, electron mode, all filter flags
and all export flags) persist in
<code>%AppData%\exactmass_libconv\settings.txt</code>.</p>
</div>

<div class="card">
<h2>Relationship to the standalone project</h2>
<p>A separate CPython project, <b>ei-fragment-calculator</b>, shares this
tool's chemistry but runs outside MassHunter with a CLI, a tkinter GUI,
accurate-mass support and a CEF workflow. It does <b>not</b> write MassHunter
library XML. This script is the MassHunter-hosted member of the pair and is
the one to use when the output has to go back into a library.</p>
</div>

<div class="foot">EI Fragment Calculator v3.1 &middot; Internal
user-contributed tooling</div>
</div></body></html>
'''


def _open_readme(sender, args):
    """Style guide section 8 -- write the embedded readme to a temp file and
    hand it to the shell, so the tool stays a single .py."""
    try:
        tmp = Path.Combine(Path.GetTempPath(), APP_SLUG + "_readme.html")
        File.WriteAllText(tmp, README_HTML, Encoding.UTF8)
        System.Diagnostics.Process.Start(tmp)
    except Exception as ex:
        MessageBox.Show(
            "Could not open readme:\n\n" + str(ex), APP_TITLE,
            MessageBoxButtons.OK, MessageBoxIcon.Error)


def show_about(owner_form):
    """Style guide section 7 -- About dialog. Reuses the 56-px banner header
    and carries, in this order: the disclaimer verbatim, a one-paragraph
    description, key/value script info, then View Readme and Close."""
    dlg = Form()
    dlg.Text            = "About " + APP_TITLE
    dlg.Size            = Size(560, 460)
    dlg.BackColor       = C_BG
    dlg.FormBorderStyle = FormBorderStyle.FixedDialog
    dlg.MaximizeBox     = False
    dlg.MinimizeBox     = False
    dlg.StartPosition   = FormStartPosition.CenterParent
    apply_icon(dlg)

    hdr = Panel()
    hdr.Dock      = DockStyle.Top
    hdr.Height    = BANNER_HEIGHT
    hdr.BackColor = C_BLUE
    t = Label()
    t.Text      = APP_TITLE
    t.Font      = FONT_BANNER
    t.ForeColor = Color.White
    t.BackColor = C_BLUE
    t.AutoSize  = True
    t.Location  = Point(16, 16)
    hdr.Controls.Add(t)
    v = Label()
    v.Text      = "v" + APP_VERSION
    v.Font      = FONT_LABEL
    v.ForeColor = Color.White
    v.BackColor = C_BLUE
    v.AutoSize  = True
    v.Location  = Point(215, 21)
    hdr.Controls.Add(v)

    y = 14

    # 1. Disclaimer, verbatim, at the top.
    disc = Label()
    disc.Text      = DISCLAIMER
    disc.Font      = FONT_LABEL_B
    disc.ForeColor = Color.FromArgb(0x6B, 0x56, 0x28)
    disc.BackColor = Color.FromArgb(0xFF, 0xF6, 0xE5)
    disc.Location  = Point(16, y)
    disc.Size      = Size(510, 46)
    y += 56

    # 2. One-paragraph description.
    desc = Label()
    desc.Text      = DESCRIPTION
    desc.Font      = FONT_LABEL
    desc.ForeColor = C_BODY
    desc.Location  = Point(16, y)
    desc.Size      = Size(510, 92)
    y += 100

    # 3. Script info as key/value rows.
    rows = [("Tool name", APP_TITLE),
            ("Version",   APP_VERSION),
            ("Platform",  "MassHunter Library Editor (IronPython 2.7)"),
            ("Author",    "Joerg Riener"),
            ("Lineage",   "UnitMass_to_ExactMass v1.2 (L. Godina) -> v3.0 -> v3.1")]
    info = []
    for k, val in rows:
        kl = Label()
        kl.Text      = k
        kl.Font      = FONT_LABEL_B
        kl.ForeColor = C_DARK
        kl.Location  = Point(16, y)
        kl.Size      = Size(90, 18)
        vl = Label()
        vl.Text      = val
        vl.Font      = FONT_LABEL
        vl.ForeColor = C_BODY
        vl.Location  = Point(112, y)
        vl.Size      = Size(414, 18)
        info.append(kl)
        info.append(vl)
        y += 22

    # 4. View Readme + Close.
    y += 10
    br = Button()
    br.Text     = "View Readme"
    br.Location = Point(16, y)
    br.Size     = Size(120, 28)
    style_button(br, primary=False)
    br.Click   += _open_readme

    bc = Button()
    bc.Text     = "Close"
    bc.Location = Point(420, y)
    bc.Size     = Size(106, 28)
    style_button(bc, primary=True)
    bc.Click   += lambda s, e: dlg.Close()

    for c in [disc, desc] + info + [br, bc]:
        dlg.Controls.Add(c)
    dlg.Controls.Add(hdr)

    if owner_form is not None:
        dlg.ShowDialog(owner_form)
    else:
        dlg.ShowDialog()
    dlg.Dispose()


# =============================================================================
# SECTION 14: GUI
# =============================================================================

def _Run():
    """Build and show the GUI. Everything else now lives at module level
    (Option 4), so this function captures only the widgets it creates.
    """
    try:
        owner = _GetOwnerForm()

        # ==================================================================
        # SECTION 14: GUI
        # ==================================================================
        # Layout (all coordinates in pixels, top-left origin):
        #   Row 1  y= 12  Input file picker
        #   Row 2  y= 47  Output file picker
        #   Row 3  y= 82  Electron mode + Min peaks
        #   Row 4  y=117  Filter GroupBox (6 checkboxes in 2 rows)
        #   Row 5  y=205  Action buttons
        #   Row 6  y=243  Log text box (fills remaining space)

        form = Form()
        form.Text      = APP_TITLE + "  v" + APP_VERSION
        form.Size      = Size(960, 810)   # +56 for the brand banner
        form.BackColor = C_BG
        apply_icon(form)

        # All absolutely-positioned controls live in a Fill panel so the
        # docked 56-px banner cannot cover them (style guide section 4).
        content = Panel()
        content.Dock      = DockStyle.Fill
        content.BackColor = C_BG

        # ADD THE PANEL TO THE FORM NOW, BEFORE ANY CHILD IS ADDED.
        # WinForms computes an Anchor offset at the moment a child is
        # added, from its parent's CURRENT size. A Panel that is not yet
        # on the form is still the default 200 px wide, so a control at
        # x=850 anchored Top|Right would record a right margin of
        # 200-(850+88) = -738 and get flung off-screen when the panel
        # later fills to ~944 px. Docking it first gives it the real
        # client width, so every Right/Bottom anchor below is correct.
        # This is the same trap the style guide documents for the banner
        # "?" button in section 6.
        form.Controls.Add(content)
        ui_font   = Font("Segoe UI", 9)
        mono_font = Font("Consolas", 8.5)

        # ---- Row 1: Input file ----
        y = 12
        lbl_in = Label(Text="Input XML:", Location=Point(10, y + 3),
                       AutoSize=True, Font=ui_font)
        txt_in = TextBox(Location=Point(95, y), Size=Size(745, 22),
                         Font=ui_font,
                         Anchor=(AnchorStyles.Top | AnchorStyles.Left |
                                 AnchorStyles.Right))
        txt_in.Text = ""
        btn_in = Button(Text="Browse...", Location=Point(850, y - 1),
                        Size=Size(88, 26), Font=ui_font,
                        Anchor=(AnchorStyles.Top | AnchorStyles.Right))

        # ---- Row 2: Output file ----
        y += 35
        lbl_out = Label(Text="Output Path:", Location=Point(10, y + 3),
                        AutoSize=True, Font=ui_font)
        txt_out = TextBox(Location=Point(95, y), Size=Size(745, 22),
                          Font=ui_font,
                          Anchor=(AnchorStyles.Top | AnchorStyles.Left |
                                  AnchorStyles.Right))
        btn_out = Button(Text="Browse...", Location=Point(850, y - 1),
                         Size=Size(88, 26), Font=ui_font,
                         Anchor=(AnchorStyles.Top | AnchorStyles.Right))

        # ---- Row 3: Electron mode + Min peaks ----
        y += 35
        lbl_emode = Label(Text="Electron mode:", Location=Point(10, y + 4),
                          AutoSize=True, Font=ui_font)
        # ComboBox replaces the old "Subtract electron mass" checkbox.
        # Three options map to electron_mode strings used by apply_electron_mode().
        cmb_emode = ComboBox()
        cmb_emode.Location     = Point(110, y)
        cmb_emode.Size         = Size(220, 24)
        cmb_emode.Font         = ui_font
        cmb_emode.DropDownStyle = ComboBoxStyle.DropDownList
        cmb_emode.Items.Add("remove  (EI+, standard)")   # -> "remove"
        cmb_emode.Items.Add("add     (EI-, negative ion)")# -> "add"
        cmb_emode.Items.Add("none    (no correction)")    # -> "none"
        # Restore saved electron mode.
        saved_em = cfg.get('electron_mode', 'remove')
        if saved_em == 'add':
            cmb_emode.SelectedIndex = 1
        elif saved_em == 'none':
            cmb_emode.SelectedIndex = 2
        else:
            cmb_emode.SelectedIndex = 0   # default: remove

        lbl_min = Label(Text="Min peaks:", Location=Point(350, y + 4),
                        AutoSize=True, Font=ui_font)
        nud_min = NumericUpDown()
        nud_min.Location = Point(430, y)
        nud_min.Size     = Size(60, 24)
        nud_min.Font     = ui_font
        nud_min.Minimum  = 1
        nud_min.Maximum  = 100
        try:
            nud_min.Value = int(cfg.get('min_peaks', '3'))
        except:
            nud_min.Value = 3

        lbl_struct = Label(
            Text="[+struct when <MolFile> present]",
            Location=Point(510, y + 4), AutoSize=True, Font=ui_font)

        # ---- Row 4: Filter GroupBox ----
        y += 35
        grp_flt = GroupBox()
        grp_flt.Text     = "Post-enumeration filters"
        grp_flt.Font     = ui_font
        grp_flt.Location = Point(10, y)
        grp_flt.Size     = Size(930, 78)
        grp_flt.Anchor   = (AnchorStyles.Top | AnchorStyles.Left |
                            AnchorStyles.Right)

        def _mk_chk(text, x, fy, saved_key, default_on=True):
            """Helper: create a CheckBox inside the filter GroupBox."""
            chk = CheckBox(Text=text, Location=Point(x, fy),
                           AutoSize=True, Font=ui_font)
            chk.Checked = (cfg.get(saved_key, "1" if default_on else "0") == "1")
            grp_flt.Controls.Add(chk)
            return chk

        # Two rows of three checkboxes each inside the GroupBox.
        chk_nitrogen = _mk_chk("Nitrogen rule",        10,  20, 'flt_nitrogen', True)
        chk_hd       = _mk_chk("HD-check (DBE/C<=1)", 175,  20, 'flt_hd',       True)
        chk_lewis    = _mk_chk("Lewis-Senior",         380,  20, 'flt_lewis',    True)
        chk_isotope  = _mk_chk("Isotope M+1/M+2",      10,  48, 'flt_isotope',  True)
        chk_smiles   = _mk_chk("SMILES ring-count",   175,  48, 'flt_smiles',   True)
        rdkit_label  = ("RDKit (bond-break check)" if RDKIT_LOADED
                        else "RDKit (install RDKit2DotNetStandard.dll)")
        chk_rdkit    = _mk_chk(rdkit_label, 380, 48, 'flt_rdkit', False)
        if not RDKIT_LOADED:
            chk_rdkit.Enabled = False   # greyed out until DLL is present
            chk_rdkit.Checked = False

        # ---- Row 4b: Export format checkboxes ----
        y += 92   # GroupBox height (78) + margin (14)
        lbl_export = Label(Text="Export:", Location=Point(10, y + 5),
                           AutoSize=True, Font=ui_font)
        chk_xml = CheckBox(Text="XML  (MassHunter)",
                           Location=Point(65, y + 2),
                           AutoSize=True, Font=ui_font)
        chk_msp = CheckBox(Text="MSP  (NIST / AMDIS)",
                           Location=Point(245, y + 2),
                           AutoSize=True, Font=ui_font)
        chk_sdf = CheckBox(Text="SDF  (MDL / RDKit)",
                           Location=Point(445, y + 2),
                           AutoSize=True, Font=ui_font)
        chk_xml.Checked = (cfg.get('export_xml', '1') == '1')
        chk_msp.Checked = (cfg.get('export_msp', '0') == '1')
        chk_sdf.Checked = (cfg.get('export_sdf', '0') == '1')

        # ---- Row 5: Action buttons ----
        y += 32
        btn_preview = Button(Text="Preview", Location=Point(10, y),
                             Size=Size(110, 30), Font=ui_font)
        btn_convert = Button(Text="Convert", Location=Point(130, y),
                             Size=Size(110, 30), Font=ui_font)
        btn_quit    = Button(Text="Quit",    Location=Point(850, y),
                             Size=Size(88, 30), Font=ui_font,
                             Anchor=(AnchorStyles.Top | AnchorStyles.Right))

        # ---- Row 6: Log text box ----
        y += 40
        txt_log = TextBox(
            Location=Point(10, y),
            Size=Size(930, 750 - y - 40),
            Font=mono_font, Multiline=True,
            ScrollBars=ScrollBars.Both, ReadOnly=True,
            Anchor=(AnchorStyles.Top | AnchorStyles.Bottom |
                    AnchorStyles.Left | AnchorStyles.Right))

        # Add all top-level controls to the form.
        for ctrl in [lbl_in, txt_in, btn_in,
                     lbl_out, txt_out, btn_out,
                     lbl_emode, cmb_emode, lbl_min, nud_min, lbl_struct,
                     grp_flt,
                     lbl_export, chk_xml, chk_msp, chk_sdf,
                     btn_preview, btn_convert, btn_quit,
                     txt_log]:
            content.Controls.Add(ctrl)

        # ---- Logging helpers ----

        def log(msg):
            """Append a line to the log text box (thread-safe via Invoke)."""
            def _a():
                txt_log.AppendText(str(msg) + "\r\n")
            try:
                if form.InvokeRequired:
                    form.Invoke(Action(_a))
                else:
                    _a()
            except:
                pass

        def clear_log():
            """Clear all text from the log text box."""
            def _a():
                txt_log.Clear()
            try:
                if form.InvokeRequired:
                    form.Invoke(Action(_a))
                else:
                    _a()
            except:
                pass

        # ---- Helper: read GUI state into reusable dicts ----

        def get_electron_mode():
            """Map ComboBox selection index to electron_mode string."""
            idx = cmb_emode.SelectedIndex
            if idx == 1:
                return "add"
            elif idx == 2:
                return "none"
            return "remove"

        def get_filter_flags():
            """Return filter flags dict reflecting current checkbox states."""
            return {
                'nitrogen': bool(chk_nitrogen.Checked),
                'hd':       bool(chk_hd.Checked),
                'lewis':    bool(chk_lewis.Checked),
                'isotope':  bool(chk_isotope.Checked),
                'smiles':   bool(chk_smiles.Checked),
                'rdkit':    False,   # always disabled
            }

        def get_export_flags():
            """Return export format flags dict reflecting current checkbox states."""
            return {
                'xml': bool(chk_xml.Checked),
                'msp': bool(chk_msp.Checked),
                'sdf': bool(chk_sdf.Checked),
            }

        def save_current_config():
            """Persist all current GUI settings."""
            save_config({
                'last_dir':      last_dir[0],
                'electron_mode': get_electron_mode(),
                'min_peaks':     str(int(nud_min.Value)),
                'flt_nitrogen':  "1" if chk_nitrogen.Checked else "0",
                'flt_hd':        "1" if chk_hd.Checked       else "0",
                'flt_lewis':     "1" if chk_lewis.Checked     else "0",
                'flt_isotope':   "1" if chk_isotope.Checked   else "0",
                'flt_smiles':    "1" if chk_smiles.Checked    else "0",
                'flt_rdkit':     "0",
                'export_xml':    "1" if chk_xml.Checked else "0",
                'export_msp':    "1" if chk_msp.Checked else "0",
                'export_sdf':    "1" if chk_sdf.Checked else "0",
            })

        # ---- File browser event handlers ----

        def browse_in(sender, args):
            """Open-file dialog for the input library."""
            dlg = OpenFileDialog()
            dlg.Title  = "Select Unit Mass Library"
            dlg.Filter = ("MassHunter Library (*.mslibrary.xml)|*.mslibrary.xml"
                          "|XML (*.xml)|*.xml|All (*.*)|*.*")
            if Directory.Exists(last_dir[0]):
                dlg.InitialDirectory = last_dir[0]
            # Own the dialog by OUR form, not the MassHunter main form:
            # our form is modal over that one, so a child owned by it
            # would open behind us and be unreachable.
            res = dlg.ShowDialog(form)
            if res != DialogResult.OK:
                return
            txt_in.Text  = dlg.FileName
            last_dir[0]  = Path.GetDirectoryName(dlg.FileName)
            save_current_config()
            # Auto-fill output path if empty.
            if not txt_out.Text.strip():
                base = Path.GetFileNameWithoutExtension(dlg.FileName)
                if base.endswith(".mslibrary"):
                    base = base[:-10]
                txt_out.Text = Path.Combine(
                    Path.GetDirectoryName(dlg.FileName),
                    base + "_exactmass.mslibrary.xml")

        def browse_out(sender, args):
            """Save-file dialog for the output library."""
            dlg = SaveFileDialog()
            dlg.Title      = "Save Exact Mass Library"
            dlg.Filter     = ("MassHunter Library (*.mslibrary.xml)|*.mslibrary.xml"
                              "|XML (*.xml)|*.xml|All (*.*)|*.*")
            dlg.DefaultExt = "mslibrary.xml"
            if Directory.Exists(last_dir[0]):
                dlg.InitialDirectory = last_dir[0]
            # Own the dialog by OUR form, not the MassHunter main form:
            # our form is modal over that one, so a child owned by it
            # would open behind us and be unreachable.
            res = dlg.ShowDialog(form)
            if res != DialogResult.OK:
                return
            txt_out.Text = dlg.FileName

        btn_in.Click  += browse_in
        btn_out.Click += browse_out

        # ---- Preview event handler ----

        def on_preview(sender, args):
            """Show a detailed per-peak log for the first N compounds.
            Useful for verifying assignments before committing to a full convert.
            Annotations:
              *   peak formula is in the structural whitelist
              [N opt]  N candidate formulas existed (ambiguous)
              FILT:    filter flag details (when a filter rejects the winner)
            """
            clear_log()
            in_path = txt_in.Text.strip()
            if not in_path or not File.Exists(in_path):
                MessageBox.Show(
                    form,
                    "Select an input file.", "Missing Input",
                    MessageBoxButtons.OK, MessageBoxIcon.Warning)
                return

            emode    = get_electron_mode()
            min_pk   = int(nud_min.Value)
            flt_flgs = get_filter_flags()

            log("=== Preview v3.0  (mode={0}, min_peaks={1}) ===".format(
                emode, min_pk))
            active = [k for k, v in flt_flgs.items() if v]
            log("    Filters active: {0}".format(
                ", ".join(active) if active else "none"))
            log("")

            try:
                enc = Encoding.GetEncoding(
                    "utf-8",
                    EncoderFallback.ReplacementFallback,
                    DecoderFallback.ReplacementFallback)
                raw   = File.ReadAllText(in_path, enc)
                clean = sanitize_xml(raw)
                doc   = XmlDocument()
                doc.LoadXml(clean)
                compounds = xnodes(doc, "Compound")
                spectra   = xnodes(doc, "Spectrum")
                c_count   = compounds.Count if compounds else 0
                spec_map  = {}
                if spectra:
                    for sp in spectra:
                        cid = xtext(sp, ["CompoundID"])
                        if cid not in spec_map:
                            spec_map[cid] = []
                        spec_map[cid].append(sp)
                log("Compounds in file: {0}".format(c_count))

                for ci in range(c_count):
                    comp      = compounds[ci]
                    cid       = xtext(comp, ["CompoundID"])
                    name      = xtext(comp, ["CompoundName"])
                    formula_s = xtext(comp, ["Formula"])
                    mol       = xtext(comp, ["MolFile"])

                    parent = parse_formula(formula_s)
                    if parent is None:
                        log("")
                        log("[SKIP] {0}: {1}".format(name, formula_s or "no formula"))
                        continue
                    parent_nom   = calc_nominal(parent)
                    parent_exact = calc_exact(parent)
                    parent_ee    = "EE" if is_ee_ion(parent) else "OE"
                    # Same context builder the conversion uses (Option 6).
                    pctx         = build_compound_context(parent, mol, flt_flgs)
                    mol_data     = pctx['mol_data']
                    struct_wl    = pctx['struct_wl']
                    ring_count   = pctx['ring_count']
                    struct_info  = (
                        " [struct:{0}]".format(len(struct_wl))
                        if struct_wl else "")
                    # RDKit bond-break fragment set, already built above.
                    prev_rdkit_frags = pctx['rdkit_frags']

                    sp_nodes = spec_map.get(cid, [])
                    if not sp_nodes:
                        log("")
                        log("[SKIP] {0}: no spectrum".format(name))
                        continue
                    sp      = sp_nodes[0]
                    mz_vals = decode_doubles(xtext(sp, ["MzValues"]))
                    ab_vals = decode_doubles(xtext(sp, ["AbundanceValues"]))
                    if len(mz_vals) != len(ab_vals):
                        continue

                    # Build intensity map for isotope scoring.
                    imap = {}
                    for pi in range(len(mz_vals)):
                        nom = int(round(mz_vals[pi]))
                        ab  = ab_vals[pi]
                        if nom not in imap or ab > imap[nom]:
                            imap[nom] = ab

                    max_ab   = max(ab_vals) if ab_vals else 1.0
                    assigned = 0
                    ambig    = 0
                    dropped  = 0

                    log("")
                    log("--- {0} ({1})  MW={2:.4f}  M+.={3}{4} ---".format(
                        name, formula_s, parent_exact, parent_ee, struct_info))

                    for pi in range(len(mz_vals)):
                        mz    = mz_vals[pi]
                        ab    = ab_vals[pi]
                        t_nom = int(round(mz))
                        if t_nom > parent_nom + 1:
                            dropped += 1
                            continue

                        best, exact, n_valid = assign_peak(
                            parent, t_nom, pctx, imap, flt_flgs, emode)
                        if best is None:
                            dropped += 1
                            continue

                        ee_str  = "EE" if is_ee_ion(best) else "OE"
                        rel_pct = 100.0 * ab / max_ab if max_ab > 0 else 0.0

                        # Neutral loss label.
                        loss = {}
                        for sym in parent:
                            l = parent[sym] - best.get(sym, 0)
                            if l > 0:
                                loss[sym] = l
                        loss_s = formula_str(loss) if loss else "M+."

                        # Annotation tags.
                        opt_tag    = ""
                        if n_valid > 1:
                            ambig += 1
                            opt_tag = " [{0}opt]".format(n_valid)
                        struct_tag = (
                            " *" if struct_wl and formula_str(best) in struct_wl
                            else "")
                        stable_hit = lookup_stable_ion(best, t_nom)
                        stable_tag = (
                            " [{0}]".format(stable_hit[0])
                            if stable_hit else "")

                        assigned += 1
                        log("  {0:>4} {1:>5.1f}%  {2:>12.6f}  {3:<12} "
                            "{4}  -{5}{6}{7}{8}".format(
                            t_nom, rel_pct, exact,
                            formula_str(best), ee_str, loss_s,
                            opt_tag, struct_tag, stable_tag))

                    status = "OK" if assigned >= min_pk else "SKIP"
                    log("  [{0}] {1}/{2} assigned,  {3} dropped,  "
                        "{4} ambiguous".format(
                        status, assigned, len(mz_vals), dropped, ambig))

            except Exception as e:
                log("[ERROR] " + str(e))

            log("")
            log("=== Preview complete  "
                "(*=struct match  [ion]=stable library) ===")

        # ---- Convert event handler ----

        def on_convert(sender, args):
            """Run the full conversion and write the output library."""
            clear_log()
            in_path  = txt_in.Text.strip()
            out_path = txt_out.Text.strip()
            if not in_path or not File.Exists(in_path):
                MessageBox.Show(
                    form,
                    "Select an input file.", "Missing Input",
                    MessageBoxButtons.OK, MessageBoxIcon.Warning)
                return
            if not out_path:
                MessageBox.Show(
                    form,
                    "Select an output file.", "Missing Output",
                    MessageBoxButtons.OK, MessageBoxIcon.Warning)
                return

            emode    = get_electron_mode()
            min_pk   = int(nud_min.Value)
            flt_flgs = get_filter_flags()
            save_current_config()

            try:
                exp_flgs = get_export_flags()
                n = convert_library(
                    in_path, out_path, min_pk, emode, log, flt_flgs,
                    exp_flgs)
                if n > 0:
                    # Build a list of output files for the completion dialog.
                    _base = out_path
                    for _e in ['.mslibrary.xml', '.xml']:
                        if _base.lower().endswith(_e):
                            _base = _base[:-len(_e)]
                            break
                    out_files = []
                    if exp_flgs.get('xml', True):
                        out_files.append("XML:  " + out_path)
                    if exp_flgs.get('msp'):
                        out_files.append("MSP:  " + _base + '.msp')
                    if exp_flgs.get('sdf'):
                        out_files.append("SDF:  " + _base + '.sdf')
                    files_str = "\n".join(out_files) if out_files else out_path
                    MessageBox.Show(
                        form,
                        ("Conversion complete!\n\n"
                         "Compounds: {0}\n"
                         "Electron mode: {1}\n\n"
                         "{2}\n\n"
                         "Open XML in Library Editor to verify.").format(
                            n, emode, files_str),
                        "Done",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Information)
            except Exception as e:
                log("[ERROR] " + str(e))

        btn_preview.Click += on_preview
        btn_convert.Click += on_convert
        btn_quit.Click    += lambda s, e: form.Close()

        # Style-guide furniture: content first, banner LAST (docking order).
        def _on_about(s, e):
            show_about(form)

        style_button(btn_preview, primary=False)
        style_button(btn_convert, primary=True)
        style_button(btn_quit,    primary=False)
        style_button(btn_in,      primary=False)
        style_button(btn_out,     primary=False)
        txt_log.BackColor = C_CARD
        txt_log.ForeColor = C_BODY

        # content was docked before its children (see above); the
        # banner goes on LAST so it claims the top edge first and the
        # Fill panel shrinks to what is left (style guide section 4).
        form.Controls.Add(build_banner(form, _on_about))

        # Show the form (modal relative to MassHunter main window).
        if owner is not None:
            form.ShowDialog(owner)
        else:
            form.ShowDialog()

    except Exception as ex:
        # Top-level exception handler: show a message box even if the GUI
        # failed to construct, so the user gets actionable feedback.
        try:
            import clr
            clr.AddReference("System.Windows.Forms")
            from System.Windows.Forms import (
                MessageBox, MessageBoxButtons, MessageBoxIcon)
            try:
                d = ex.ToString()
            except:
                d = str(ex)
            MessageBox.Show(
                "Script failed:\n\n" + d, "Error",
                MessageBoxButtons.OK, MessageBoxIcon.Error)
        except:
            pass


# =============================================================================
# Entry point   (style guide section 10)
# =============================================================================
# MassHunter Library Editor executes module-level code when it loads a
# script, and may call it off the UI thread. Marshal onto the UI thread so
# form.ShowDialog() is always called from the right one.

def _Start():
    """Called by the invocation block below (and optionally by MassHunter)."""
    _Run()


try:
    if UIState.SynchronizeInvoke.InvokeRequired:
        UIState.SynchronizeInvoke.Invoke(Action(_Start), None)
    else:
        _Start()
except:
    # Fall back to the owner-form marshalling used by v3.0 if
    # UIState.SynchronizeInvoke is not exposed by this host.
    try:
        o = _GetOwnerForm()
        if o is not None and o.InvokeRequired:
            o.BeginInvoke(Action(_Start))
        else:
            _Start()
    except:
        _Start()
