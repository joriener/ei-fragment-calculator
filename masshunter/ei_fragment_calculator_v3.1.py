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
#   v3.2      RDKit setup dialog, reached from a new banner "RDKit..."
#             button. Downloads RDKit.DotNetWrap from nuget.org,
#             extracts the managed assembly plus the natives matching
#             THIS process architecture into a per-user folder needing
#             no elevation, puts them on the process PATH and loads them
#             without a MassHunter restart. Also fixes the assembly name
#             (RDKit2DotNet.dll, not RDKit2DotNetStandard.dll -- the
#             latter does not exist in the package).
#
#   v3.3      Accurate-mass support. A "Mass mode" combo selects unit
#             mass (nominal, the previous and default behaviour) or
#             accurate mass with a ppm or mDa tolerance. In accurate
#             mode assign_peak() enumerates a +/-1 nominal window and
#             keeps only candidates whose electron-corrected exact mass
#             falls inside the tolerance, so the decimals of the
#             measured m/z finally do the discriminating instead of
#             being rounded away. The preview reports the mass error of
#             each assignment in ppm.
#
#   v3.4      Seven defects closed:
#             1 every Spectrum of a compound is converted, not only the
#               first; the XML writer emits one Compound with N Spectrum
#               elements. MSP/SDF get one record per spectrum, suffixed
#               [n/N] when a compound contributed several.
#             2 the written library is re-read and its compound,
#               spectrum and peak counts checked (verify_output_xml).
#             3 RDKit is exercised for real after loading -- benzene is
#               parsed and its atom count checked -- because a managed
#               load says nothing about the 106 native P/Invokes.
#             4 the isotope filter fails open on flat peak lists, where
#               observed ratios are noise (intensity_map_is_flat).
#             5 optional 13C-satellite detection, so a satellite is no
#               longer assigned a fragment formula of its own.
#             6 score_formula profiled: it costs the SAME as
#               apply_all_filters (0.96-1.14x), so Option 3 pre-filter
#               would save <=25%% at best and only by changing results.
#               Closed with data; the safe parts were already in 3.2.
#             7 log box sizes off FORM_HEIGHT; accurate-mass window is
#               configurable; settings written atomically.
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
APP_VERSION = "3.4"
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
FORM_HEIGHT   = 810         # main window height; log box sizes off this

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


def build_banner(form, on_about, on_rdkit=None):
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

    rdk_btn = None
    if on_rdkit is not None:
        rdk_btn = Button()
        rdk_btn.Text      = "RDKit..."
        rdk_btn.Font      = FONT_LABEL
        rdk_btn.Width     = 84
        rdk_btn.Height    = 26
        rdk_btn.Top       = 15
        rdk_btn.FlatStyle = FlatStyle.Flat
        rdk_btn.BackColor = C_BLUE_DK
        rdk_btn.ForeColor = Color.White
        rdk_btn.FlatAppearance.BorderSize = 0
        rdk_btn.FlatAppearance.MouseOverBackColor = Color.FromArgb(0x00, 0x33, 0x55)
        rdk_btn.Cursor    = System.Windows.Forms.Cursors.Hand
        rdk_btn.Click    += on_rdkit
        banner.Controls.Add(rdk_btn)

    # Reposition on resize rather than anchoring: a docked banner is still
    # narrower than the form when its children are added, so an Anchor would
    # snapshot the wrong X and put these buttons off-screen (style guide 6).
    def _pos_help(sender, ev):
        help_btn.Left = banner.Width - help_btn.Width - 14
        if rdk_btn is not None:
            rdk_btn.Left = help_btn.Left - rdk_btn.Width - 8
    banner.Resize += _pos_help
    help_btn.Left  = form.Width - help_btn.Width - 30
    if rdk_btn is not None:
        rdk_btn.Left = help_btn.Left - rdk_btn.Width - 8

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



# =============================================================================
# SECTION 1b: RDKit .NET support -- detection, download, load
# =============================================================================
# The RDKit bond-break filter needs the SWIG-generated .NET wrapper. Getting
# it in place by hand is the single most error-prone step in this tool, for
# three reasons that are easy to get wrong and give no useful error:
#
#   1. THE MANAGED ASSEMBLY IS CALLED RDKit2DotNet.dll.
#      v3.0/v3.1 looked for "RDKit2DotNetStandard.dll", which does not exist
#      in the distributed package at all -- verified against
#      RDKit.DotNetWrap 0.2021094.2, whose only managed assemblies are
#      lib/netstandard2.0/RDKit2DotNet.dll and
#      lib/netcoreapp3.1/RDKit2DotNet.dll.
#
#   2. IT HAS ~106 NATIVE DEPENDENCIES.
#      The managed assembly P/Invokes into boost/RDKit native DLLs shipped
#      under runtimes/win-x86/native/ and runtimes/win-x64/native/. Copying
#      only the managed DLL (for instance into System32) can never work: the
#      first real call fails to resolve its native entry points.
#
#   3. THE ARCHITECTURE MUST MATCH THE HOST PROCESS.
#      MassHunter Library Editor (LibraryEdit.exe, under
#      ...\Workstation\Quant\bin) is a 32-bit PE32 image, so it needs the
#      win-x86 natives. Installing win-x64 raises BadImageFormatException.
#      _rdkit_arch() reads IntPtr.Size at runtime rather than assuming.
#
# The installer below downloads the NuGet package, extracts the managed
# assembly plus the natives for THIS process architecture into a per-user
# folder that needs no elevation, puts the native folder on the process PATH
# so the P/Invokes resolve, and then loads the assembly.

RDKIT_NUGET_ID      = "rdkit.dotnetwrap"
RDKIT_NUGET_VERSION = "0.2021094.2"   # pinned known-good; see _rdkit_latest()
RDKIT_INDEX_URL     = ("https://api.nuget.org/v3-flatcontainer/"
                       "rdkit.dotnetwrap/index.json")
RDKIT_NUPKG_FMT     = ("https://api.nuget.org/v3-flatcontainer/"
                       "rdkit.dotnetwrap/{0}/rdkit.dotnetwrap.{0}.nupkg")
RDKIT_MANAGED_ENTRY = "lib/netstandard2.0/RDKit2DotNet.dll"
RDKIT_MANAGED_NAME  = "RDKit2DotNet.dll"
RDKIT_NUGET_PAGE    = "https://www.nuget.org/packages/RDKit.DotNetWrap"

# Legacy location tried by v3.0/v3.1. Kept only so an existing hand-made
# installation keeps working.
RDKIT_LEGACY_DLL = r"C:\Windows\System32\RDKit2DotNetStandard.dll"

RDKIT_LOADED   = False
RDKIT_PATH     = None     # full path of the assembly actually loaded
RDKIT_STATUS   = "not loaded"
_RdkRWMol      = None     # GraphMolWrap.RWMol class, or None


def _rdkit_arch():
    """"win-x86" or "win-x64" for the CURRENT process, from IntPtr.Size."""
    try:
        from System import IntPtr
        return "win-x64" if IntPtr.Size == 8 else "win-x86"
    except:
        return "win-x86"


def rdkit_install_dir():
    """Per-user install folder -- no elevation needed, unlike System32."""
    appdata = Environment.GetFolderPath(
        Environment.SpecialFolder.ApplicationData)
    return Path.Combine(Path.Combine(appdata, "exactmass_libconv"), "rdkit")


def _rdkit_native_dir(base=None):
    return Path.Combine(base or rdkit_install_dir(), "native")


def _rdkit_add_native_to_path(native_dir):
    """Prepend the native folder to the PROCESS PATH so the managed
    assembly's P/Invokes resolve. Process scope only -- nothing persists
    outside this MassHunter session."""
    try:
        from System import EnvironmentVariableTarget
        cur = Environment.GetEnvironmentVariable("PATH") or ""
        if native_dir.lower() not in cur.lower():
            Environment.SetEnvironmentVariable(
                "PATH", native_dir + ";" + cur,
                EnvironmentVariableTarget.Process)
        return True
    except:
        return False


def try_load_rdkit(dll_path=None, log_fn=None):
    """Attempt to load the RDKit .NET wrapper.

    Tries, in order: the path given, the per-user install folder, then the
    legacy System32 name v3.0 used. Sets the module globals RDKIT_LOADED,
    RDKIT_PATH, RDKIT_STATUS and _RdkRWMol.

    Returns (ok, message). Safe to call repeatedly, so the setup dialog can
    enable the filter without restarting MassHunter.
    """
    global RDKIT_LOADED, RDKIT_PATH, RDKIT_STATUS, _RdkRWMol

    def _log(m):
        if log_fn:
            try:
                log_fn(m)
            except:
                pass

    candidates = []
    if dll_path:
        candidates.append(dll_path)
    candidates.append(Path.Combine(rdkit_install_dir(), RDKIT_MANAGED_NAME))
    candidates.append(RDKIT_LEGACY_DLL)

    last_err = ""
    for cand in candidates:
        try:
            if not File.Exists(cand):
                continue
        except:
            continue
        native = _rdkit_native_dir(Path.GetDirectoryName(cand))
        try:
            if Directory.Exists(native):
                _rdkit_add_native_to_path(native)
        except:
            pass
        try:
            # AddReferenceToFileAndPath loads by full path -- the only
            # reliable method in IronPython for an assembly that is not in
            # the GAC or the application directory.
            clr.AddReferenceToFileAndPath(cand)
            from GraphMolWrap import RWMol as _RW
            _RdkRWMol    = _RW
            RDKIT_LOADED = True
            RDKIT_PATH   = cand
            RDKIT_STATUS = "loaded from " + cand
            _log("[OK] RDKit loaded: " + cand)
            return True, RDKIT_STATUS
        except Exception as ex:
            try:
                last_err = ex.ToString()
            except:
                last_err = str(ex)
            _log("[FAIL] " + cand + "\n       " + last_err)

    RDKIT_LOADED = False
    RDKIT_PATH   = None
    RDKIT_STATUS = ("not found" if not last_err
                    else "found but would not load: " + last_err)
    return False, RDKIT_STATUS


def rdkit_self_test():
    """Actually call RDKit and check the answer (defect 3).

    A successful clr.AddReferenceToFileAndPath() only proves the MANAGED
    assembly resolved. The ~106 native boost/RDKit DLLs are reached by
    P/Invoke on first real use, so a load can succeed and every call still
    throw BadImageFormatException or DllNotFoundException -- which is exactly
    what a wrong-architecture install produces.

    Parses benzene and checks it has six heavy atoms.

    Returns (ok, message).
    """
    if not RDKIT_LOADED or _RdkRWMol is None:
        return False, "RDKit is not loaded"
    try:
        m = None
        try:
            m = _RdkRWMol.MolFromSmiles("c1ccccc1")
        except:
            m = None
        if m is None:
            # Fall back to the molblock path, which is what flt_rdkit uses.
            block = ("benzene\n"
                     "  self-test\n"
                     "\n"
                     "  6  6  0  0  0  0  0  0  0  0999 V2000\n"
                     "    0.0000    0.0000    0.0000 C   0  0\n"
                     "    1.4000    0.0000    0.0000 C   0  0\n"
                     "    2.1000    1.2124    0.0000 C   0  0\n"
                     "    1.4000    2.4249    0.0000 C   0  0\n"
                     "    0.0000    2.4249    0.0000 C   0  0\n"
                     "   -0.7000    1.2124    0.0000 C   0  0\n"
                     "  1  2  2  0\n"
                     "  2  3  1  0\n"
                     "  3  4  2  0\n"
                     "  4  5  1  0\n"
                     "  5  6  2  0\n"
                     "  6  1  1  0\n"
                     "M  END\n")
            m = _RdkRWMol.MolFromMolBlock(block, True, False)
        if m is None:
            return False, ("RDKit loaded but could not parse benzene -- the "
                           "managed assembly works, the chemistry core does "
                           "not. Usually a missing or wrong-architecture "
                           "native set.")
        n = m.getNumAtoms()
        if int(n) != 6:
            return False, ("RDKit parsed benzene but reported {0} atoms, "
                           "expected 6".format(n))
        return True, "RDKit self-test passed: benzene parsed, 6 atoms"
    except Exception as ex:
        try:
            det = ex.ToString()
        except:
            det = str(ex)
        return False, ("RDKit loaded but the first real call failed. That is "
                       "the native-library failure, not a load failure:\n\n"
                       + det)


def _rdkit_latest_version(log_fn=None):
    """Ask nuget.org for the newest version. Falls back to the pinned one.

    The response is a small JSON document; there is no json module in this
    host, so the version list is scanned out of the raw text.
    """
    try:
        _rdkit_enable_tls12()
        from System.Net import WebClient
        wc = WebClient()
        wc.Headers.Add("User-Agent", APP_SLUG + "/" + APP_VERSION)
        txt = wc.DownloadString(RDKIT_INDEX_URL)
        vers = []
        i = txt.find("[")
        if i >= 0:
            for tok in txt[i:].replace("[", "").replace("]", "").split(","):
                t = tok.strip().strip('"').strip()
                if t:
                    vers.append(t)
        if vers:
            return vers[-1]
    except Exception as ex:
        if log_fn:
            log_fn("[warn] could not query nuget.org, using pinned "
                   + RDKIT_NUGET_VERSION)
    return RDKIT_NUGET_VERSION


def _rdkit_enable_tls12():
    """nuget.org requires TLS 1.2. .NET Framework targets below 4.6 default
    ServicePointManager to SSL3 + TLS 1.0, so it must be enabled explicitly.
    Written as a numeric cast because the named Tls12 member does not exist
    if the host compiled against 4.0 -- same approach as the PubChem script.
    """
    try:
        from System.Net import ServicePointManager, SecurityProtocolType
        ServicePointManager.SecurityProtocol = (
            ServicePointManager.SecurityProtocol | SecurityProtocolType(3072))
    except:
        try:
            from System.Net import ServicePointManager
            ServicePointManager.SecurityProtocol = 3072
        except:
            pass


def rdkit_download_and_install(log_fn, version=None):
    """Download the NuGet package and extract what this process needs.

    Returns (ok, managed_dll_path_or_message).
    """
    def _log(m):
        try:
            log_fn(m)
        except:
            pass

    base   = rdkit_install_dir()
    native = _rdkit_native_dir(base)
    arch   = _rdkit_arch()

    try:
        if not Directory.Exists(base):
            Directory.CreateDirectory(base)
        if not Directory.Exists(native):
            Directory.CreateDirectory(native)
    except Exception as ex:
        return False, "Could not create " + base + ": " + str(ex)

    ver = version or _rdkit_latest_version(_log)
    url = RDKIT_NUPKG_FMT.format(ver)
    pkg = Path.Combine(base, "rdkit.dotnetwrap." + ver + ".nupkg")

    _log("Process architecture : " + arch + "  (from IntPtr.Size)")
    _log("Install folder       : " + base)
    _log("Package version      : " + ver)
    _log("")

    # ---- download -------------------------------------------------------
    try:
        if File.Exists(pkg):
            _log("[skip] package already downloaded")
        else:
            _rdkit_enable_tls12()
            from System.Net import WebClient
            wc = WebClient()
            wc.Headers.Add("User-Agent", APP_SLUG + "/" + APP_VERSION)
            _log("Downloading ~27 MB from nuget.org ...")
            wc.DownloadFile(url, pkg)
            _log("[OK] downloaded " + pkg)
    except Exception as ex:
        try:
            det = ex.ToString()
        except:
            det = str(ex)
        return False, ("Download failed.\n\n" + det +
                       "\n\nDownload it manually from\n" +
                       RDKIT_NUGET_PAGE +
                       "\nthen use 'Locate an existing RDKit2DotNet.dll'.")

    # ---- extract --------------------------------------------------------
    try:
        clr.AddReference("System.IO.Compression.FileSystem")
        from System.IO.Compression import ZipFile
    except Exception as ex:
        return False, ("This host cannot open zip archives "
                       "(System.IO.Compression.FileSystem unavailable): "
                       + str(ex) +
                       "\n\nExtract " + pkg + " by hand -- it is a zip file "
                       "-- then use 'Locate an existing RDKit2DotNet.dll'.")

    managed_out = Path.Combine(base, RDKIT_MANAGED_NAME)
    native_pref = "runtimes/" + arch + "/native/"
    n_native = 0
    try:
        z = ZipFile.OpenRead(pkg)
        try:
            for entry in z.Entries:
                name = entry.FullName
                if name == RDKIT_MANAGED_ENTRY:
                    _extract_entry(entry, managed_out)
                    _log("[OK] " + RDKIT_MANAGED_NAME)
                elif (name.startswith(native_pref)
                      and name.lower().endswith(".dll")):
                    leaf = name[len(native_pref):]
                    if leaf and "/" not in leaf:
                        _extract_entry(entry, Path.Combine(native, leaf))
                        n_native += 1
        finally:
            z.Dispose()
    except Exception as ex:
        try:
            det = ex.ToString()
        except:
            det = str(ex)
        return False, "Extraction failed: " + det

    _log("[OK] {0} native DLLs -> {1}".format(n_native, native))
    if not File.Exists(managed_out):
        return False, ("The package did not contain " + RDKIT_MANAGED_ENTRY +
                       ". Its layout may have changed; extract it by hand and "
                       "use 'Locate an existing RDKit2DotNet.dll'.")
    if n_native == 0:
        _log("[warn] no natives extracted for " + arch +
             " -- the filter will load but fail on first use")

    _log("")
    _log("Loading ...")
    ok, msg = try_load_rdkit(managed_out, _log)
    if ok:
        try:
            c = load_config()
            c['rdkit_path'] = managed_out
            save_config(c)
            _log("[OK] path remembered for next start")
        except:
            pass
    return ok, (managed_out if ok else msg)


def _extract_entry(entry, dest):
    """Write one zip entry to dest, overwriting. ExtractToFile's overwrite
    overload is not present on every framework version, so the file is
    removed first."""
    try:
        if File.Exists(dest):
            File.Delete(dest)
    except:
        pass
    from System.IO.Compression import ZipFileExtensions
    try:
        ZipFileExtensions.ExtractToFile(entry, dest, True)
    except:
        # Fall back to a manual stream copy.
        src = entry.Open()
        try:
            out = File.Create(dest)
            try:
                src.CopyTo(out)
            finally:
                out.Close()
        finally:
            src.Close()



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

def intensity_map_is_flat(intensity_map, min_distinct=3,
                          min_ratio=1.5):
    """True when a peak list carries too little intensity contrast
    for isotope ratios to mean anything (defect 4).

    Flat if there are fewer than min_distinct distinct abundances,
    or the largest is less than min_ratio times the smallest
    positive one. Both catch the common cases: every peak set to
    the same value, or a list already reduced to a narrow band.
    """
    if not intensity_map:
        return True
    vals = [v for v in intensity_map.values() if v > 0]
    if not vals:
        return True
    if len(set(vals)) < min_distinct:
        return True
    lo = min(vals)
    hi = max(vals)
    if lo <= 0:
        return False
    return (hi / lo) < min_ratio


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
    if intensity_map_is_flat(intensity_map):
        # Defect 4: no usable contrast, so observed ratios are
        # noise. Fail open rather than reject on bad evidence.
        return 0.0, "flat spectrum -- isotope scoring skipped"
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

# --- Accurate-mass matching (new in v3.3) --------------------------------
# "unit" reproduces v3.0/v3.2 exactly: peaks are rounded to a nominal mass
# and everything after the decimal point is thrown away. "ppm" and "mda"
# instead match a candidate's electron-corrected exact mass against the
# measured m/z, which is the whole point of having accurate-mass spectra.
DEFAULT_MASS_MODE = "unit"      # "unit" | "ppm" | "mda"
DEFAULT_TOL_PPM   = 10.0        # +/- ppm in "ppm" mode
DEFAULT_TOL_MDA   = 5.0         # +/- mDa in "mda" mode

# Nominal masses either side of round(m/z) to enumerate in accurate mode.
# See find_subformulas_window() for why this cannot be 0.
ACCURATE_NOMINAL_WINDOW = 1


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


C13_C12_DELTA = 1.0033548378   # 13C - 12C, CODATA


def is_c13_satellite(t_nom, mz, ab, assigned, mass_mode="unit",
                     mass_tol=0.0, factor=2.5):
    """True when this peak looks like the 13C satellite of an
    already-assigned peak one nominal mass below it (defect 5).

    Peaks above M+1 are dropped elsewhere, but satellites INSIDE a
    spectrum were previously handed to the enumerator and assigned
    a fragment formula of their own, which is chemically wrong: the
    peak is the same ion with a heavy carbon.

    Two tests, both required:
      * the peak below must be assigned and at least as abundant;
      * this peak's abundance relative to it must not exceed the
        theoretical M+1 percentage of that formula times 'factor'.
        A real fragment at this mass is normally far more intense
        than the isotope contribution it would have to hide under.

    In accurate mode the spacing is checked against the true
    13C-12C difference as well, which makes the call unambiguous.

    'assigned' maps nominal m/z -> (formula, abundance, mz).
    """
    prev = assigned.get(t_nom - 1)
    if not prev:
        return False
    p_form, p_ab, p_mz = prev
    if p_ab <= 0 or ab <= 0 or ab > p_ab:
        return False
    if mass_mode in ("ppm", "mda") and mass_tol > 0 and mz and p_mz:
        d = mz - p_mz
        if mass_mode == "ppm":
            lim = abs(mz) * mass_tol / 1.0e6
        else:
            lim = mass_tol / 1000.0
        # Allow a little slack: two independent measurements.
        if abs(d - C13_C12_DELTA) > max(lim * 2.0, 0.003):
            return False
    try:
        m1_theo = calc_m1_pct(p_form)
    except:
        return False
    if m1_theo <= 0:
        return False
    obs_pct = 100.0 * ab / p_ab
    return obs_pct <= (m1_theo * factor)


def find_subformulas_window(parent, center_nom, window,
                            parent_key=None, prep=None):
    """Union of find_subformulas_cached() over center_nom +/- window.

    Accurate-mass matching cannot enumerate at round(m/z) alone. A formula's
    NOMINAL mass and round(its EXACT mass) differ by one whenever the mass
    defect passes 0.5 Da, and that happens well inside the GC-MS range:
    hydrogen contributes +7.8 mDa each, so C50H100 is nominal 700 but exact
    700.78, which rounds to 701; bromine contributes -81.7 mDa each and
    rounds the other way. Both directions occur, so the window is symmetric.

    +/-1 covers organics across this range; raise ACCURATE_NOMINAL_WINDOW
    for very high mass.

    The cached lists are never mutated -- results are copied into a new list.
    """
    out = []
    lo = center_nom - window
    if lo < 0:
        lo = 0
    for n in range(lo, center_nom + window + 1):
        out.extend(find_subformulas_cached(parent, n, parent_key, prep))
    return out


def assign_peak(parent, t_nom, ctx, intensity_map, filter_flags,
                electron_mode, mz=None, mass_mode="unit", mass_tol=0.0):
    """Assign one peak to its best candidate formula.

    Returns (best_formula, exact_mass, n_candidates, mass_error_ppm):
      best_formula    composition dict, or None if the peak is unassigned
      exact_mass      electron-corrected exact mass of the winner, or None
      n_candidates    how many candidates survived filtering (callers use
                      > 1 to count ambiguous assignments)
      mass_error_ppm  calculated minus measured, in ppm; None when no
                      measured m/z was supplied

    Two matching modes:

    "unit" -- the default, and byte-identical to v3.0/v3.2 behaviour.
        Enumerate sub-formulas whose NOMINAL mass equals t_nom, then rank.
        The measured m/z is used only to derive t_nom, so everything after
        the decimal point is discarded.

    "ppm" / "mda" -- accurate mass.
        Enumerate over a +/-ACCURATE_NOMINAL_WINDOW nominal window, then
        keep only candidates whose electron-corrected EXACT mass lies within
        mass_tol of the measured m/z. This is where accurate-mass data pays
        off: at 10 ppm on a 150 Da ion the window is +/-1.5 mDa, which
        usually leaves one formula where nominal matching leaves ten.

        Candidates outside tolerance are rejected outright rather than
        penalised, so the tolerance is the control that matters; within
        tolerance the existing chemistry score decides. Tighten the
        tolerance rather than adding filters if assignments stay ambiguous.

    Peaks above the molecular ion (+1 for the 13C satellite) are rejected,
    as are peaks with no candidate reaching the -0.5 DBE physical limit.
    """
    if t_nom > ctx['parent_nom'] + 1:
        return None, None, 0, None

    accurate = (mass_mode in ("ppm", "mda") and mz is not None
                and mass_tol > 0)

    if not accurate:
        subs  = find_subformulas_cached(
            parent, t_nom, ctx['parent_key'], ctx['prep'])
        # Pre-filter: DBE >= -0.5 (the hard physical limit for all ions).
        valid = [f for f in subs if calc_rdb(f) >= -0.5]
    else:
        subs  = find_subformulas_window(
            parent, t_nom, ACCURATE_NOMINAL_WINDOW,
            ctx['parent_key'], ctx['prep'])
        valid = []
        for f in subs:
            if calc_rdb(f) < -0.5:
                continue
            ion = apply_electron_mode(calc_exact(f), electron_mode)
            if mass_mode == "ppm":
                if mz <= 0:
                    continue
                if abs((ion - mz) / mz * 1.0e6) > mass_tol:
                    continue
            else:                                    # "mda"
                if abs(ion - mz) * 1000.0 > mass_tol:
                    continue
            valid.append(f)

    if not valid:
        return None, None, 0, None

    best = pick_best_v3(
        valid, parent, t_nom, ctx['struct_wl'],
        intensity_map, ctx['ring_count'], filter_flags, ctx['rdkit_frags'])
    if best is None:
        return None, None, len(valid), None

    exact = apply_electron_mode(calc_exact(best), electron_mode)
    err   = None
    if mz is not None and mz > 0:
        err = (exact - mz) / mz * 1.0e6
    return best, exact, len(valid), err

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
                    log_fn, filter_flags, export_flags=None,
                    mass_mode="unit", mass_tol=0.0,
                    skip_c13=False):
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
    total         = 0    # compounds with >=1 spectrum
    n_spectra     = 0    # spectra written (defect 1)
    n_c13         = 0    # 13C satellites skipped (defect 5)
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
        # One record per SPECTRUM (defect 1). Everything above this
        # point is per-compound and stays outside the loop, so the
        # MOL parse, structural whitelist and RDKit fragment set are
        # still built only once per compound.
        _had_any = [False]
        for _si, sp in enumerate(sp_nodes):
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
            _assigned = {}   # nom -> (formula, ab, mz), defect 5

            for pi in range(len(mz_vals)):
                mz    = mz_vals[pi]
                ab    = ab_vals[pi]
                t_nom = int(round(mz))
                if (skip_c13 and is_c13_satellite(
                        t_nom, mz, ab, _assigned, mass_mode, mass_tol)):
                    n_c13 += 1
                    continue
                # Single shared pipeline -- see assign_peak() (Option 6).
                # mz is passed whole: in accurate mode its decimals are
                # what select the formula.
                best, exact, n_valid, m_err = assign_peak(
                    parent, t_nom, ctx, intensity_map,
                    filter_flags, electron_mode, mz, mass_mode, mass_tol)
                if best is None:
                    continue
                if n_valid > 1:
                    ambig += 1
                _assigned[t_nom] = (best, ab, mz)
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
            _had_any[0] = True
            _out_last = out_compounds[-1]
            _out_last['SpecIndex'] = _si
            _out_last['SpecTotal'] = len(sp_nodes)
            _out_last['CidKey']    = cid
            n_spectra += 1

        # One compound, however many spectra it contributed.
        if _had_any[0]:
            total += 1
        if ((ci + 1) % 25) == 0:
            log_fn("[INFO] Processed {0}/{1}...".format(ci + 1, c_count))

    # ------------------------------------------------------------------
    # Summary log
    # ------------------------------------------------------------------
    log_fn("")
    log_fn("[INFO] Summary:")
    log_fn("  Compounds converted:   {0}".format(total))
    log_fn("  Spectra converted:     {0}".format(n_spectra))
    if skip_c13:
        log_fn("  13C satellites skipped: {0}".format(n_c13))
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

    # Records are in compound order, so consecutive entries sharing a
    # CidKey belong to one compound: emit <Compound> once, then one
    # <Spectrum> per record with SpectrumID counting from 1 (defect 1).
    _prev_key = object()
    cid       = 0
    _spec_no  = 0
    for idx, c in enumerate(out_compounds):
        mz  = c["mz"]
        ab  = c["ab"]
        bpi = c["bp_idx"]
        _key = c.get("CidKey", idx)
        _new_compound = (_key != _prev_key)
        if _new_compound:
            _prev_key = _key
            cid      += 1
            _spec_no  = 0
        _spec_no += 1

        if _new_compound:
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
        sb.AppendLine('    <SpectrumID>{0}</SpectrumID>'.format(
            _spec_no))
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

        # Defect 2: prove the file just written is structurally sound.
        try:
            _exp_peaks = sum(len(c["mz"]) for c in out_compounds)
            verify_output_xml(out_path, total, n_spectra, _exp_peaks,
                              log_fn)
        except Exception as _vex:
            log_fn("[VERIFY] the check itself failed: " + str(_vex))
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

def _spec_suffix(c):
    """' [2/3]' when a compound contributed several spectra, so MSP
    and SDF records stay distinguishable. Empty for the common
    single-spectrum case, which keeps existing output unchanged."""
    n = c.get('SpecTotal', 1)
    if not n or n < 2:
        return ''
    return ' [{0}/{1}]'.format(c.get('SpecIndex', 0) + 1, n)


def verify_output_xml(out_path, exp_compounds, exp_spectra,
                      exp_peaks, log_fn):
    """Re-read a written MassHunter library and check it against
    what was meant to be written (defect 2).

    Compares compound count, spectrum count and total peak count,
    and confirms every spectrum's base64 arrays decode to equal,
    non-zero lengths. Returns True when everything matches.

    Deliberately a re-read rather than an in-memory check: it
    exercises the encoder, the XML escaping and the file write --
    exactly the path that had never been validated.
    """
    try:
        raw = File.ReadAllText(out_path, Encoding.UTF8)
        doc = XmlDocument()
        doc.LoadXml(sanitize_xml(raw))
    except Exception as ex:
        log_fn("[VERIFY] could not re-read the output: " + str(ex))
        return False

    got_c = len(xnodes(doc, "Compound"))
    specs = xnodes(doc, "Spectrum")
    got_s = len(specs)
    got_p = 0
    bad   = 0
    for sp in specs:
        mz = decode_doubles(xtext(sp, ["MzValues"]))
        ab = decode_doubles(xtext(sp, ["AbundanceValues"]))
        if len(mz) != len(ab) or not mz:
            bad += 1
        got_p += len(mz)

    ok = (got_c == exp_compounds and got_s == exp_spectra
          and got_p == exp_peaks and bad == 0)
    log_fn("")
    log_fn("[VERIFY] re-read {0}".format(out_path))
    log_fn("  compounds {0} (expected {1}){2}".format(
        got_c, exp_compounds,
        "" if got_c == exp_compounds else "   <-- MISMATCH"))
    log_fn("  spectra   {0} (expected {1}){2}".format(
        got_s, exp_spectra,
        "" if got_s == exp_spectra else "   <-- MISMATCH"))
    log_fn("  peaks     {0} (expected {1}){2}".format(
        got_p, exp_peaks,
        "" if got_p == exp_peaks else "   <-- MISMATCH"))
    if bad:
        log_fn("  {0} spectrum/spectra with empty or mismatched "
               "arrays   <-- MISMATCH".format(bad))
    log_fn("  result: {0}".format("OK" if ok else "PROBLEM"))
    return ok


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
        name = (c.get("Name") or "") + _spec_suffix(c)
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
    """Persist settings dict to the settings file.

    Written to a temp file and moved into place (defect 7), so an
    interrupted write or a second instance cannot leave a
    half-written settings file behind.
    """
    try:
        lines = ["{0}={1}".format(k, v) for k, v in cfg.items()]
        tmp = cfg_path + ".tmp"
        File.WriteAllLines(tmp, lines)
        try:
            if File.Exists(cfg_path):
                File.Delete(cfg_path)
        except:
            pass
        File.Move(tmp, cfg_path)
    except:
        try:
            File.WriteAllLines(cfg_path, lines)
        except:
            pass

cfg      = load_config()
last_dir = [cfg.get('last_dir', "C:\\")]


# ---------------------------------------------------------------------------
# Initial RDKit load attempt (SECTION 1b defines the loader; config is now
# available, so a remembered path can be honoured).
# ---------------------------------------------------------------------------
try:
    try_load_rdkit(cfg.get('rdkit_path', None))
except:
    pass

# Defect 7: let the accurate-mass search window be tuned without
# editing the source. Only worth raising for very high mass.
try:
    _w = int(cfg.get('acc_window', str(ACCURATE_NOMINAL_WINDOW)))
    if 0 <= _w <= 5:
        ACCURATE_NOMINAL_WINDOW = _w
except:
    pass


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

README_HTML = r'''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=1200">
<title>EI Fragment Calculator &mdash; Readme</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Roboto:ital,wght@0,100;0,200;0,300;0,400;0,500;0,700;0,900;1,400&family=Roboto+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>

/* ── CSS CUSTOM PROPERTIES (colour tokens) ───────────────────────────────── */
:root {
  --ag-blue:       #3D4B5A;   /* Quant ribbon slate — header, command surfaces          */
  --ag-blue-dark:  #273645;   /* pressed ribbon state                                    */
  --ag-blue-mid:   #5E7182;   /* selected tab and table divider                          */
  --ag-blue-light: #E9F2F8;   /* selected row and hover background                      */
  --ag-navy:       #273645;   /* dark Quant ribbon surface                               */
  --ag-heading:    #303030;   /* headings, log header bg                                 */
  --ag-text:       #53565A;   /* body text                                               */
  --ag-muted:      #888B8D;   /* secondary text, TOC headings, hint labels               */
  --ag-border:     #D8D8D6;   /* card borders, table cell borders                        */
  --ag-bg:         #FFFFFF;   /* content area background                                 */
  --ag-bg-alt:     #F5F5F5;   /* page/sidebar background                                 */
  --ag-green:      #2E7D32;   /* success badges, OK state                                */
  --ag-orange:     #E87722;   /* warning badges                                          */
  --ag-red:        #C62828;   /* error badges                                            */
}

* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: "Segoe UI", Tahoma, Arial, sans-serif;
  font-size: 13px; line-height: 1.5;
  color: var(--ag-text); background: var(--ag-bg-alt);
}

/* ── STYLE LABEL BAR ─────────────────────────────────────────────────────── */
/* Narrow dark strip at the very top of the page.
   Left: category label (e.g. "Tool Reference · Layout A")
   Right: context label (e.g. "MassHunter GC/MS Acq · Internal Use")
   Change or blank out either label as needed. */
.style-label-bar {
  background: #E7ECF0; height: 28px;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 72px;
}
.label-left  { font-size:10px; font-weight:600; color:var(--ag-heading); text-transform:none; letter-spacing:0; }
.label-right { font-size:10px; color:var(--ag-muted); }

/* ── HEADER — LAYOUT A (Quant slate + logo) ──────────────────────────────── */
/* Use this layout for standard tool documentation. The <img> in
  .doc-header-inner shows the Agilent logo. */
.doc-header {
  position: relative; background: var(--ag-blue);
  padding: 16px 48px 12px; overflow: hidden;
}
.doc-header::before { content: none; }
.doc-header-inner {
  position: relative; display: flex; align-items: center;
  gap: 20px; margin-bottom: 16px;
}
.doc-header img   { height:32px; width:auto; display:block; flex-shrink:0; }
.hdr-divider      { width:1px; height:36px; background:rgba(255,255,255,.3); flex-shrink:0; }
.hdr-title        { font-size:18px; font-weight:400; color:#fff; letter-spacing:0; }
.hdr-sub          { font-size:12px; font-weight:400; color:rgba(255,255,255,.78); margin-top:2px; }
/* Badge: top-right pill — e.g. "Internal Diagnostic Tool" */
.hdr-badge {
  margin-left:auto; background:rgba(255,255,255,.1); border:1px solid rgba(255,255,255,.25);
  color:rgba(255,255,255,.9); font-size:10px; font-weight:600;
  letter-spacing:0; text-transform:none; padding:4px 9px;
  border-radius:0; white-space:nowrap;
}
/* Meta pills: bottom row of header — instrument, platform, version info */
.hdr-meta {
  position:relative; display:flex; gap:8px; flex-wrap:wrap;
  padding-top:14px; border-top:1px solid rgba(255,255,255,.2);
}
.meta-pill {
  font-size:11px; color:rgba(255,255,255,.85); background:transparent;
  padding:2px 10px 2px 0; border-radius:0; border:0;
}
.meta-pill strong { font-weight:600; color:#fff; }

/* ── HEADER — LAYOUT B (deep navy + text wordmark) ───────────────────────── */
/* Use this alternative when you want a darker, launcher-style header
   without the Agilent logo. Replace .doc-header bg + add .hdr-wordmark.
   To use Layout B, change the header bg to var(--ag-navy) and replace
   the <img> element with:
     <div class="hdr-wordmark">MY<span>TOOL</span></div>
*/
.hdr-wordmark       { font-size:28px; font-weight:700; color:#fff; letter-spacing:.04em; }
.hdr-wordmark span  { color:var(--ag-blue); font-weight:300; }

/* ── TWO-COLUMN LAYOUT ───────────────────────────────────────────────────── */
/* 220 px sticky TOC sidebar + fluid content area */
.doc-body {
  display: grid; grid-template-columns: 220px 1fr;
  align-items: start; max-width: 1300px; margin: 0 auto;
}

/* ── TABLE OF CONTENTS SIDEBAR ───────────────────────────────────────────── */
.doc-toc-col {
  align-self: stretch; background: var(--ag-bg-alt);
  border-right: 1px solid var(--ag-border);
}
.doc-toc { position: sticky; top: 0; padding: 28px 18px; }
.toc-heading {
  font-size:10px; font-weight:700; color:var(--ag-muted);
  text-transform:uppercase; letter-spacing:.12em; margin-bottom:12px;
}
.toc-list { list-style:none; }
.toc-list > li { margin-bottom:1px; }
.toc-list > li > a {
  display:block; font-size:13px; color:var(--ag-text);
  text-decoration:none; padding:5px 10px; border-radius:4px;
}
.toc-list > li > a:hover { background:var(--ag-blue-light); color:var(--ag-blue); }
/* Active section highlight — set by JavaScript IntersectionObserver */
.toc-list li.toc-active > a {
  color:var(--ag-blue); font-weight:500; background:var(--ag-blue-light);
}
/* Second-level TOC items (sub-sections) */
.toc-sub { list-style:none; padding-left:14px; margin:2px 0 4px; }
.toc-sub li a {
  display:block; font-size:12px; color:var(--ag-muted);
  text-decoration:none; padding:3px 8px; border-radius:3px;
}
.toc-sub li a:hover { color:var(--ag-blue); background:var(--ag-blue-light); }
/* Horizontal rule between TOC sections */
.toc-divider { height:1px; background:var(--ag-border); margin:10px 0; }

/* ── CONTENT AREA ────────────────────────────────────────────────────────── */
.doc-content { background:var(--ag-bg); padding:28px 40px 48px; min-width:0; }

/* Section heading: thin blue left border, light-weight font */
h2 {
  font-size:16px; font-weight:600; color:var(--ag-heading);
  border-left:3px solid var(--ag-blue-mid); padding-left:10px;
  margin:30px 0 12px; scroll-margin-top:16px;
}
h2:first-of-type { margin-top:0; }
h3 { font-size:13px; font-weight:600; color:var(--ag-heading); margin:18px 0 7px; }
h4 { font-size:13px; font-weight:600; color:var(--ag-heading); margin-bottom:6px; }
p  { margin-bottom:10px; }
ul, ol { margin:6px 0 12px 20px; }
li { margin-bottom:4px; }

/* Inline code */
code {
  font-family:Consolas, monospace; font-size:12px;
  background:var(--ag-bg-alt); color:var(--ag-blue-dark); padding:1px 4px; border-radius:0;
}
/* Code block — dark terminal style */
pre {
  font-family:"Roboto Mono", Consolas, monospace; font-size:12px;
  background:#1B2A3B; color:#B8CAD8;
  padding:16px 20px; border-radius:4px; margin:12px 0 18px;
  overflow-x:auto; line-height:1.7;
}
/* Syntax colour spans inside <pre> */
pre .cm  { color:#7BBCD8; }  /* comment  */
pre .key { color:#50FA7B; }  /* key      */
pre .val { color:#FFB86C; }  /* value    */
pre .str { color:#F1FA8C; }  /* string   */

/* ── TABLE ───────────────────────────────────────────────────────────────── */
table { width:100%; border-collapse:collapse; margin:10px 0 18px; font-size:13px; }
th {
  background:#D4DDE5; color:var(--ag-heading); font-weight:600; text-align:left;
  padding:8px 12px; font-size:12px; letter-spacing:.02em;
  border:1px solid var(--ag-border);
}
td {
  padding:7px 12px; border:1px solid var(--ag-border);
  vertical-align:top; background:var(--ag-bg);
}
tr:nth-child(even) td { background:#F8FAFB; }

/* ── CALLOUT BOXES ───────────────────────────────────────────────────────── */
/* .tip   — blue left border, light blue bg.  Helpful notes, examples.    */
.tip {
  background:var(--ag-blue-light); border-left:4px solid var(--ag-blue);
  padding:10px 14px; border-radius:0; margin:12px 0; font-size:13px;
}
.tip strong { color:var(--ag-blue-dark); }

/* .warn  — amber left border, cream bg.  Warnings, gotchas.              */
.warn {
  background:#FFF8E1; border-left:4px solid #F9A825;
  padding:10px 14px; border-radius:0; margin:12px 0; font-size:13px;
}
.warn strong { color:#7B5800; }

/* .note  — purple left border, lavender bg.  Conceptual notes, caveats.  */
.note {
  background:#F3F0F8; border-left:4px solid #6B3FA0;
  padding:10px 14px; border-radius:0; margin:12px 0; font-size:13px;
}

/* .callout-note — steel left border, pale blue bg.  Neutral reference.   */
.callout-note {
  background:#F0F7FF; border-left:4px solid var(--ag-blue-mid);
  padding:10px 14px; border-radius:0; margin:12px 0; font-size:13px;
}

/* .callout-warn — orange left border, light orange bg.  Stronger warning. */
.callout-warn {
  background:#FFF3E0; border-left:4px solid var(--ag-orange);
  padding:11px 16px; border-radius:0 4px 4px 0; margin:14px 0; font-size:13px;
}
.callout-warn strong { color:#7B4800; }

/* ── NUMBERED STEPS ──────────────────────────────────────────────────────── */
/* Use .step > .step-num + .step-body for procedural instructions.
   step-num: blue circle with number. step-body: prose content. */
.step { display:flex; gap:14px; margin-bottom:12px; align-items:flex-start; }
.step-num {
  min-width:24px; height:24px; background:var(--ag-blue); color:#fff;
  border-radius:0; display:flex; align-items:center; justify-content:center;
  font-size:12px; font-weight:700; flex-shrink:0; margin-top:1px;
}
.step-body { flex:1; padding-top:3px; }

/* ── FEATURE CARDS ───────────────────────────────────────────────────────── */
/* 2-column grid of cards. Each card has a coloured top border, a tag chip,
   an h3 title, and a paragraph. Use at the top of the Overview section. */
.feature-grid { display:grid; grid-template-columns:1fr 1fr; gap:14px; margin:14px 0 20px; }
.feature-card {
  background:var(--ag-bg); border:1px solid var(--ag-border);
  border-top:2px solid var(--ag-blue-mid); border-radius:0; padding:12px 14px;
}
.feature-card .tag {
  display:inline-block; font-size:10px; font-weight:700; text-transform:uppercase;
  letter-spacing:.04em; padding:1px 6px; border-radius:0; margin-bottom:8px;
  background:var(--ag-blue-light); color:var(--ag-blue-mid);
}

/* ── INLINE COLOUR SWATCHES ──────────────────────────────────────────────── */
/* Use .diff-swatch with an inline style="background:#RRGGBB" to show a
   colour chip in legend tables (e.g. diff colour keys). */
.diff-swatch {
  display:inline-block; width:14px; height:14px;
  border-radius:2px; vertical-align:middle; margin-right:5px;
  border:1px solid var(--ag-border);
}

/* ── INLINE BADGES ───────────────────────────────────────────────────────── */
/* Small coloured pill badges for status or category labelling in tables. */
.badge {
  display:inline-block; font-size:10px; font-weight:700; text-transform:uppercase;
  letter-spacing:.04em; padding:2px 6px; border-radius:0; vertical-align:middle;
}
.badge-green  { background:#E8F5E9; color:var(--ag-green);  }
.badge-orange { background:#FFF3E0; color:var(--ag-orange); }
.badge-red    { background:#FFEBEE; color:var(--ag-red);    }

/* ── PAGE FOOTER ─────────────────────────────────────────────────────────── */
/* Dark footer with Agilent logo on the left and a label on the right. */
.page-footer {
  background:#303030; padding:18px 72px;
  display:flex; align-items:center; justify-content:space-between;
}
.page-footer img  { height:26px; width:auto; opacity:.85; }
.footer-right     { font-size:11px; color:rgba(255,255,255,.4); font-weight:300; }

/* ── PRINT ───────────────────────────────────────────────────────────────── */
@media print {
  body { width:100%; }
  .style-label-bar, .doc-toc-col, .page-footer { display:none !important; }
  .doc-body { display:block !important; }
  .doc-content { padding:24px 0 !important; }
}

/* ── COLOUR PALETTE SWATCHES ─────────────────────────────────────────────── */
.swatch-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 10px;
  margin: 14px 0 18px;
}
.swatch-cell {
  border-radius: 4px;
  overflow: hidden;
  border: 1px solid var(--ag-border);
  font-size: 11px;
  font-family: "Roboto Mono", Consolas, monospace;
}
.swatch-color {
  height: 44px;
}
.swatch-label {
  background: var(--ag-bg);
  padding: 5px 8px;
  color: var(--ag-heading);
  font-weight: 500;
  line-height: 1.4;
}
.swatch-label span {
  display: block;
  color: var(--ag-muted);
  font-weight: 400;
}

</style>
</head>
<body>

<div class="doc-header">
  <div class="doc-header-inner">
    <img src="data:image/png;base64,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" alt="Agilent">
    <div class="hdr-divider"></div>
    <div>
      <div class="hdr-title">EI Fragment Calculator</div>
      <div class="hdr-sub">Assigns exact masses to unit-mass EI spectra and writes them back into a MassHunter library</div>
    </div>
    <div class="hdr-badge">Internal Diagnostic Tool</div>
  </div>
  <div class="hdr-meta">
    <span class="meta-pill"><strong>Host:</strong> MassHunter Library Editor</span>
    <span class="meta-pill"><strong>Runtime:</strong> IronPython 2.7.5 &middot; .NET only</span>
    <span class="meta-pill"><strong>Platform:</strong> Windows 10 / 11</span>
    <span class="meta-pill"><strong>Version:</strong> 3.4</span>
  </div>
</div>

<div class="doc-body">
  <div class="doc-toc-col">
    <nav class="doc-toc">
      <div class="toc-heading">Contents</div>
      <ul class="toc-list">
        <li><a href="#what-it-does">What It Does</a></li>
        <li><a href="#how-to-use">How to Use</a></li>
        <div class="toc-divider"></div>
        <li><a href="#mass-mode">Mass Mode</a>
          <ul class="toc-sub">
            <li><a href="#unit-mass">Unit mass</a></li>
            <li><a href="#accurate-mass">Accurate mass</a></li>
          </ul>
        </li>
        <li><a href="#filters">Filters</a></li>
        <li><a href="#fragmentation">Fragmentation Rules</a></li>
        <div class="toc-divider"></div>
        <li><a href="#reading-preview">Reading the Preview</a></li>
        <li><a href="#output">Output</a></li>
        <li><a href="#rdkit">RDKit Setup</a></li>
        <div class="toc-divider"></div>
        <li><a href="#limitations">Notes &amp; Limitations</a></li>
      </ul>
    </nav>
  </div>

  <div class="doc-content">
    <h2 id="what-it-does">What It Does</h2>

    <p>Converts a unit-mass EI spectral library into an exact-mass library.
    For each compound the tool parses the molecular formula and the MOL block,
    builds a structural fragment whitelist, and then <strong>for every
    peak</strong> enumerates every sub-formula of the parent with a matching
    mass, filters out the chemically impossible ones, scores the survivors and
    assigns the best candidate's calculated exact mass.</p>

    <div class="callout-note">The molecular formula acts as an
    <strong>elemental upper bound</strong> &mdash; a fragment can never
    contain an atom the parent does not have. That is what keeps the
    enumeration tractable and the assignment meaningful.</div>

    <div class="feature-grid">
      <div class="feature-card">
        <h3>Unit mass in, exact mass out</h3>
        <p>The tool measures nothing. It assigns the most plausible formula to
        each peak and reports that formula's calculated exact mass. It is not
        a substitute for accurate-mass acquisition.</p>
      </div>
      <div class="feature-card">
        <h3>Ambiguity is real</h3>
        <p>At higher m/z one nominal mass can host many valid sub-formulas.
        The filters and the structural whitelist narrow this; where they
        cannot, the winner is a ranked guess and the preview marks it
        <code>[Nopt]</code>.</p>
      </div>
    </div>

    <h2 id="how-to-use">How to Use</h2>

    <div class="step">
      <div class="step-num">1</div>
      <div class="step-body"><strong>Input XML</strong> &mdash; pick a
      MassHunter library (<code>.mslibrary.xml</code>) whose spectra carry
      unit-mass peaks.</div>
    </div>
    <div class="step">
      <div class="step-num">2</div>
      <div class="step-body"><strong>Output Path</strong> &mdash; the XML is
      written as <code>&lt;base&gt;_exactmass.mslibrary.xml</code>; MSP and
      SDF, if ticked, sit alongside it.</div>
    </div>
    <div class="step">
      <div class="step-num">3</div>
      <div class="step-body"><strong>Electron mode</strong> &mdash;
      <code>remove</code> for EI+ (the detector measures the ion, i.e. neutral
      minus one electron), <code>add</code> for EI&minus;, <code>none</code>
      for no correction.</div>
    </div>
    <div class="step">
      <div class="step-num">4</div>
      <div class="step-body"><strong>Mass mode</strong> and
      <strong>tolerance</strong> &mdash; see below. Leave it on
      <em>Unit mass</em> unless your spectra really carry accurate
      masses.</div>
    </div>
    <div class="step">
      <div class="step-num">5</div>
      <div class="step-body"><strong>Min peaks</strong> &mdash; spectra with
      fewer assigned peaks than this are skipped.</div>
    </div>
    <div class="step">
      <div class="step-num">6</div>
      <div class="step-body">Press <strong>Preview</strong> first. It runs the
      identical assignment pipeline and writes nothing.</div>
    </div>
    <div class="step">
      <div class="step-num">7</div>
      <div class="step-body">Press <strong>Convert</strong> to write the
      ticked formats. The output is then re-read and its structure
      verified.</div>
    </div>

    <div class="tip"><strong>Preview and Convert cannot disagree.</strong>
    Both call one implementation of the pipeline, so what the preview shows is
    what the conversion writes.</div>

    <h2 id="mass-mode">Mass Mode</h2>

    <h3 id="unit-mass">Unit mass</h3>
    <p>Peaks are rounded to a nominal mass and sub-formulas of exactly that
    nominal mass are enumerated. Everything after the decimal point is
    discarded. This is the default and the historical behaviour.</p>

    <h3 id="accurate-mass">Accurate mass</h3>
    <p>Candidates are kept only when their electron-corrected exact mass falls
    within the tolerance of the measured m/z, in <strong>ppm</strong> or
    <strong>mDa</strong>. This is where accurate-mass data pays off: at 10 ppm
    on a 150 Da ion the window is &plusmn;1.5 mDa, which usually leaves a
    single formula.</p>

    <table>
      <tr><th>Parent</th><th>Fragment</th><th>m/z</th>
          <th>Unit mode</th><th>10 ppm</th></tr>
      <tr><td>C<sub>21</sub>H<sub>20</sub>Cl<sub>2</sub>O<sub>3</sub>
          (permethrin)</td><td>C<sub>13</sub>H<sub>9</sub>Cl<sub>2</sub></td>
          <td>235.0076</td><td><span class="badge badge-red">21</span></td>
          <td><span class="badge badge-green">1</span></td></tr>
      <tr><td>C<sub>10</sub>H<sub>8</sub>FeNa<sub>2</sub>O<sub>4</sub></td>
          <td>C<sub>10</sub>H<sub>8</sub>O<sub>4</sub></td><td>192.0417</td>
          <td><span class="badge badge-red">16</span></td>
          <td><span class="badge badge-green">1</span></td></tr>
      <tr><td>C<sub>27</sub>H<sub>46</sub>O (cholesterol)</td>
          <td>C<sub>19</sub>H<sub>27</sub></td><td>255.2107</td>
          <td><span class="badge badge-orange">7</span></td>
          <td><span class="badge badge-green">1</span></td></tr>
      <tr><td>C<sub>8</sub>H<sub>10</sub>N<sub>4</sub>O<sub>2</sub>
          (caffeine)</td><td>C<sub>7</sub>H<sub>7</sub>N<sub>4</sub>O<sub>2</sub></td>
          <td>179.0564</td><td><span class="badge badge-orange">2</span></td>
          <td><span class="badge badge-green">1</span></td></tr>
    </table>

    <div class="note"><strong>Why the search window is &plusmn;1 nominal
    mass.</strong> A formula's nominal mass and <code>round(its exact
    mass)</code> diverge once the mass defect passes 0.5 Da, and that happens
    inside the normal GC-MS range &mdash; hydrogen adds +7.8 mDa each, so
    C<sub>50</sub>H<sub>100</sub> is nominal 700 but exact 700.783, which
    rounds to 701. Bromine (&minus;81.7 mDa each) rounds the other way, so the
    window is symmetric. Enumerating at <code>round(m/z)</code> alone would
    miss those molecular ions outright.</div>

    <div class="tip">Candidates outside the tolerance are
    <strong>rejected</strong>, not penalised, so the tolerance is the control
    that matters. If assignments stay ambiguous, tighten it before reaching
    for more filters.</div>

    <h2 id="filters">Filters</h2>

    <p>Six independently toggleable filters. All on by default except
    RDKit.</p>

    <table>
      <tr><th>Filter</th><th>Rejects</th><th>Basis</th></tr>
      <tr><td>Nitrogen rule</td><td>Odd/even m/z inconsistent with the N+P
          count for the ion type</td><td>McLafferty &amp; Turecek 1993</td></tr>
      <tr><td>HD-check</td><td>DBE/C above 1.0 &mdash; implausibly
          hydrogen-poor fragments</td><td>Pretsch et al. 2009</td></tr>
      <tr><td>Lewis-Senior</td><td>Valence sums that cannot form a connected
          structure</td><td>Senior 1951</td></tr>
      <tr><td>Isotope M+1/M+2</td><td>Formulas whose predicted isotope pattern
          disagrees with the observed spectrum</td><td>Gross 2017</td></tr>
      <tr><td>SMILES ring-count</td><td>Fragments with more rings than the
          parent can supply</td><td>Weininger 1988</td></tr>
      <tr><td>RDKit bond-break</td><td>Heavy-atom formulas unreachable by any
          single bond break</td><td>optional, see RDKit Setup</td></tr>
    </table>

    <div class="warn">The isotope filter is the most powerful of the six on
    halogenated compounds because it uses the spectrum itself &mdash; but it
    needs real intensity contrast. Against a flat or normalised peak list the
    observed ratios are noise, so the filter detects that and stands
    down rather than rejecting good formulas.</div>

    <p>A seventh, separate option &mdash; <strong>Skip 13C
    satellites</strong>, off by default &mdash; suppresses peaks that look
    like the 13C satellite of an assigned peak below them, instead of giving
    them a fragment formula of their own.</p>

    <h2 id="fragmentation">Fragmentation Rules</h2>

    <p>When the library entry carries a MOL block, four rules build a
    whitelist of formulas a real EI fragmentation could produce. A candidate
    matching the whitelist receives the largest single bonus in the scoring
    model.</p>

    <table>
      <tr><th>Rule</th><th>Covers</th></tr>
      <tr><td>Homolytic cleavage</td><td>Every non-ring single bond broken
          &mdash; the general &sigma;-bond case</td></tr>
      <tr><td>&alpha;-cleavage</td><td>C&ndash;C bonds &alpha; to
          N/O/S/halogen; dominant for aldehydes, amines, ethers and
          halides</td></tr>
      <tr><td>McLafferty rearrangement</td><td>&gamma;-H migration to a
          carbonyl via a six-membered transition state</td></tr>
      <tr><td>Retro-Diels-Alder</td><td>Six-membered rings containing C=C
          splitting into diene and dienophile</td></tr>
    </table>

    <h2 id="reading-preview">Reading the Preview</h2>

    <p>One line per assigned peak: nominal m/z, relative intensity, the
    assigned exact mass, the formula, EE or OE, and the neutral loss from the
    molecular ion.</p>

<pre><span class="cm">   m/z   rel%        exact mass   formula      ion  loss</span>
   145  100.0%    145.028204   C7H5O3        EE  -CH3   <span class="cm">*  [tropylium]</span>
   119   42.8%    119.048604   C7H7NO        EE  -CO2   <span class="cm">[3opt]</span>
</pre>

    <table>
      <tr><th>Tag</th><th>Meaning</th></tr>
      <tr><td><code>[Nopt]</code></td><td>N candidates were possible and one
          was chosen</td></tr>
      <tr><td><code>*</code></td><td>The formula matched the structural
          whitelist</td></tr>
      <tr><td><code>[ion]</code></td><td>A hit in the stable-ion library,
          named</td></tr>
      <tr><td><code>+1.83 ppm</code></td><td>Mass error of the assignment,
          accurate mode only</td></tr>
    </table>

    <div class="tip">A high <code>[Nopt]</code> count on a compound is the
    signal to supply a MOL block, enable more filters, or switch to accurate
    mass with a tight tolerance.</div>

    <h2 id="output">Output</h2>

    <table>
      <tr><th>Format</th><th>Notes</th></tr>
      <tr><td>MassHunter XML</td><td>One <code>&lt;Compound&gt;</code> per
          compound, with one <code>&lt;Spectrum&gt;</code> per source
          spectrum</td></tr>
      <tr><td>NIST / AMDIS MSP</td><td>One record per spectrum, suffixed
          <code>[2/3]</code> when a compound contributed several</td></tr>
      <tr><td>MDL SDF</td><td>One record per spectrum, same suffixing</td></tr>
    </table>

    <div class="tip">After the XML is written it is <strong>read back and
    checked</strong> &mdash; compound, spectrum and peak counts against what
    was intended, and that every base64 array pair decodes to equal, non-zero
    lengths. Look for the <code>[VERIFY]</code> block at the end of the
    log.</div>

    <h2 id="rdkit">RDKit Setup</h2>

    <p>The RDKit bond-break filter needs the SWIG-generated RDKit .NET
    wrapper. Click <strong>RDKit&hellip;</strong> in the banner; the setup
    dialog installs it for you, into a per-user folder that needs no
    administrator rights, and enables the filter without restarting
    MassHunter.</p>

    <div class="warn"><strong>Why this needs a helper rather than copying one
    file.</strong> The managed assembly is <code>RDKit2DotNet.dll</code>, not
    the <code>RDKit2DotNetStandard.dll</code> earlier versions looked for
    &mdash; that filename does not exist in the distributed package at all. It
    P/Invokes into about 106 native boost and RDKit DLLs, so the managed DLL
    alone can never work. And the natives must match the host process:
    <code>LibraryEdit.exe</code> is a 32-bit image and needs the
    <code>win-x86</code> set, so installing <code>win-x64</code> raises
    <code>BadImageFormatException</code>.</div>

    <p>After loading, the dialog <strong>calls RDKit for real</strong> &mdash;
    it parses benzene and checks the atom count &mdash; because a successful
    assembly load says nothing about whether the native libraries resolve. If
    the self-test fails the filter is left disabled rather than failing on
    first use.</p>

    <h2 id="limitations">Notes &amp; Limitations</h2>

    <div class="feature-grid">
      <div class="feature-card">
        <h3>Elements</h3>
        <p>30 supported: Al As B Br C Ca Cl Co Cr Cu D F Fe H I K Mg Mn N Na
        Ni O P Pb S Se Si Sn Ti V Zn. Deuterium is a distinct element.</p>
      </div>
      <div class="feature-card">
        <h3>Settings</h3>
        <p>The last folder, min peaks, electron mode, mass mode and
        tolerance, every filter flag and every export flag persist in
        <code>%AppData%\exactmass_libconv\settings.txt</code>.</p>
      </div>
    </div>

    <div class="warn"><strong>Not yet validated end to end.</strong> No
    library has been converted inside a live Library Editor session. The
    chemistry is verified by extracted-function testing &mdash; enumeration
    output identical over 36,506 candidate formulas &mdash; and the output
    verification and RDKit self-test exist to surface a problem at runtime
    rather than hide it. Run <strong>Preview</strong> on a small library and
    compare against a known-good result before trusting a conversion.</div>

    <div class="note"><strong>Locale.</strong> The base64 codecs no longer
    round-trip through a culture-dependent number parse, so output is
    identical on any Windows regional setting. Libraries written by v3.0 or
    earlier <em>on a non-English-locale machine</em> carry corrupted m/z and
    abundance values and should be regenerated.</div>
  </div>
</div>

<div class="page-footer">
  <img src="data:image/png;base64,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" alt="Agilent">
  <span class="footer-right">EI Fragment Calculator &middot; Internal Use Only</span>
</div>


<script>
(function() {
  var tocLinks = document.querySelectorAll('.toc-list a[href^="#"]');
  if (!tocLinks.length) return;
  var sections = [];
  tocLinks.forEach(function(a) {
    var el = document.getElementById(a.getAttribute('href').slice(1));
    if (el) sections.push(el);
  });
  if (!sections.length) return;

  function setActive(id) {
    tocLinks.forEach(function(a) {
      a.parentElement.classList.toggle('toc-active', a.getAttribute('href') === '#' + id);
    });
  }

  function update() {
    // When scrolled to (or near) the bottom, always highlight the last section.
    if (window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 10) {
      setActive(sections[sections.length - 1].id);
      return;
    }
    // Otherwise highlight the last section whose heading has scrolled above
    // 35% of the viewport height.
    var threshold = window.scrollY + window.innerHeight * 0.35;
    var current = sections[0];
    for (var i = 0; i < sections.length; i++) {
      if (sections[i].getBoundingClientRect().top + window.scrollY <= threshold) {
        current = sections[i];
      }
    }
    setActive(current.id);
  }

  window.addEventListener('scroll', update, { passive: true });
  update();
})();
</script>


</body>
</html>
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
# RDKit setup dialog
# =============================================================================

def show_rdkit_setup(owner_form, on_state_change=None):
    """Install or locate the RDKit .NET wrapper, and load it without a
    restart. Reached from the banner "RDKit..." button.

    on_state_change is called after a successful load so the caller can
    enable the RDKit filter checkbox.
    """
    dlg = Form()
    dlg.Text            = "RDKit setup"
    dlg.Size            = Size(760, 560)
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
    ht = Label()
    ht.Text      = "RDKit setup"
    ht.Font      = FONT_BANNER
    ht.ForeColor = Color.White
    ht.BackColor = C_BLUE
    ht.AutoSize  = True
    ht.Location  = Point(16, 16)
    hdr.Controls.Add(ht)

    body = Panel()
    body.Dock      = DockStyle.Fill
    body.BackColor = C_BG
    # Dock BEFORE adding children so Right/Bottom anchors get the real width.
    dlg.Controls.Add(body)

    y = 12

    lbl_status = Label()
    lbl_status.Font      = FONT_LABEL_B
    lbl_status.ForeColor = C_DARK
    lbl_status.Location  = Point(14, y)
    lbl_status.Size      = Size(710, 20)
    body.Controls.Add(lbl_status)
    y += 24

    lbl_arch = Label()
    lbl_arch.Font      = FONT_LABEL
    lbl_arch.ForeColor = C_MUTED
    lbl_arch.Location  = Point(14, y)
    lbl_arch.Size      = Size(710, 34)
    lbl_arch.Text      = (
        "This MassHunter process is {0}, so the {1} native libraries are "
        "required.\nInstall folder: {2}".format(
            "64-bit" if _rdkit_arch() == "win-x64" else "32-bit",
            _rdkit_arch(), rdkit_install_dir()))
    body.Controls.Add(lbl_arch)
    y += 42

    def refresh_status():
        if RDKIT_LOADED:
            lbl_status.ForeColor = Color.FromArgb(0x1B, 0x7F, 0x3B)
            lbl_status.Text = "RDKit is LOADED  --  " + str(RDKIT_PATH)
        else:
            lbl_status.ForeColor = Color.FromArgb(0x8A, 0x1F, 0x1F)
            lbl_status.Text = "RDKit is NOT loaded  --  " + str(RDKIT_STATUS)

    refresh_status()

    # ---- automatic install ---------------------------------------------
    grp_auto = GroupBox()
    grp_auto.Text     = "Option 1 -- download and install automatically"
    grp_auto.Font     = FONT_LABEL_B
    grp_auto.ForeColor = C_DARK
    grp_auto.Location = Point(14, y)
    grp_auto.Size     = Size(714, 96)
    body.Controls.Add(grp_auto)

    lbl_auto = Label()
    lbl_auto.Font      = FONT_LABEL
    lbl_auto.ForeColor = C_BODY
    lbl_auto.Location  = Point(12, 22)
    lbl_auto.Size      = Size(688, 34)
    lbl_auto.Text      = (
        "Downloads RDKit.DotNetWrap from nuget.org (about 27 MB), extracts "
        "the managed assembly\nand the matching native libraries, and loads "
        "it. No administrator rights needed.")
    grp_auto.Controls.Add(lbl_auto)

    btn_auto = Button()
    btn_auto.Text     = "Download and install"
    btn_auto.Location = Point(12, 60)
    btn_auto.Size     = Size(160, 26)
    style_button(btn_auto, primary=True)
    grp_auto.Controls.Add(btn_auto)

    btn_page = Button()
    btn_page.Text     = "Open nuget.org page"
    btn_page.Location = Point(182, 60)
    btn_page.Size     = Size(150, 26)
    style_button(btn_page, primary=False)
    grp_auto.Controls.Add(btn_page)

    y += 104

    # ---- manual path ----------------------------------------------------
    grp_man = GroupBox()
    grp_man.Text      = "Option 2 -- locate an existing RDKit2DotNet.dll"
    grp_man.Font      = FONT_LABEL_B
    grp_man.ForeColor = C_DARK
    grp_man.Location  = Point(14, y)
    grp_man.Size      = Size(714, 96)
    body.Controls.Add(grp_man)

    lbl_man = Label()
    lbl_man.Font      = FONT_LABEL
    lbl_man.ForeColor = C_BODY
    lbl_man.Location  = Point(12, 22)
    lbl_man.Size      = Size(688, 30)
    lbl_man.Text      = (
        "Point at the managed assembly. Its native libraries must sit in a "
        "'native' sub-folder\nbeside it, or already be on the PATH.")
    grp_man.Controls.Add(lbl_man)

    txt_path = TextBox()
    txt_path.Location = Point(12, 58)
    txt_path.Size     = Size(500, 22)
    txt_path.Font     = FONT_LABEL
    try:
        txt_path.Text = load_config().get('rdkit_path', "") or ""
    except:
        txt_path.Text = ""
    grp_man.Controls.Add(txt_path)

    btn_browse = Button()
    btn_browse.Text     = "Browse..."
    btn_browse.Location = Point(520, 57)
    btn_browse.Size     = Size(88, 25)
    style_button(btn_browse, primary=False)
    grp_man.Controls.Add(btn_browse)

    btn_load = Button()
    btn_load.Text     = "Load"
    btn_load.Location = Point(616, 57)
    btn_load.Size     = Size(84, 25)
    style_button(btn_load, primary=False)
    grp_man.Controls.Add(btn_load)

    y += 104

    txt_log = TextBox()
    txt_log.Location   = Point(14, y)
    txt_log.Size       = Size(714, 150)
    txt_log.Font       = FONT_MONO
    txt_log.Multiline  = True
    txt_log.ReadOnly   = True
    txt_log.BackColor  = C_CARD
    txt_log.ForeColor  = C_BODY
    txt_log.ScrollBars = ScrollBars.Both
    txt_log.Anchor     = (AnchorStyles.Top | AnchorStyles.Bottom |
                          AnchorStyles.Left | AnchorStyles.Right)
    body.Controls.Add(txt_log)

    btn_close = Button()
    btn_close.Text     = "Close"
    btn_close.Location = Point(624, y + 158)
    btn_close.Size     = Size(104, 27)
    btn_close.Anchor   = (AnchorStyles.Bottom | AnchorStyles.Right)
    style_button(btn_close, primary=False)
    body.Controls.Add(btn_close)

    def log(msg):
        def _a():
            txt_log.AppendText(str(msg) + "\r\n")
        try:
            if txt_log.InvokeRequired:
                txt_log.BeginInvoke(Action(_a))
            else:
                _a()
        except:
            pass

    def run_self_test():
        """Defect 3: a successful load is not proof. Call RDKit for real."""
        ok, msg = rdkit_self_test()
        log("")
        log(("[SELF-TEST OK] " if ok else "[SELF-TEST FAILED] ") + str(msg))
        return ok

    def finish(ok):
        refresh_status()
        if ok:
            if not run_self_test():
                log("")
                log("The assembly loaded but RDKit does not work, so the")
                log("filter stays disabled -- enabling it would fail on")
                log("first use.")
                globals()['RDKIT_LOADED'] = False
                refresh_status()
                return
        if ok and on_state_change:
            try:
                on_state_change()
            except:
                pass

    def on_auto(sender, args):
        btn_auto.Enabled = False
        btn_auto.Text    = "Working..."
        btn_auto.BackColor = C_BLUE_MUTE
        txt_log.Clear()
        try:
            ok, msg = rdkit_download_and_install(log)
            log("")
            if ok:
                log("RDKit is ready. The RDKit filter checkbox is now "
                    "enabled.")
            else:
                log("FAILED: " + str(msg))
            finish(ok)
        except Exception as ex:
            try:
                log("UNEXPECTED: " + ex.ToString())
            except:
                log("UNEXPECTED: " + str(ex))
        finally:
            btn_auto.Enabled = True
            btn_auto.Text    = "Download and install"
            btn_auto.BackColor = C_BLUE

    def on_page(sender, args):
        try:
            System.Diagnostics.Process.Start(RDKIT_NUGET_PAGE)
        except Exception as ex:
            log("Could not open browser: " + str(ex))

    def on_browse(sender, args):
        d = OpenFileDialog()
        d.Title  = "Select RDKit2DotNet.dll"
        d.Filter = "RDKit managed assembly (RDKit2DotNet.dll)|RDKit2DotNet.dll|Assemblies (*.dll)|*.dll|All (*.*)|*.*"
        # Owned by THIS dialog -- see the 3.1.1 note in the header.
        if d.ShowDialog(dlg) == DialogResult.OK:
            txt_path.Text = d.FileName

    def on_load(sender, args):
        p = txt_path.Text.strip()
        if not p:
            log("Enter or browse to a path first.")
            return
        txt_log.Clear()
        ok, msg = try_load_rdkit(p, log)
        log("")
        log(("OK: " + msg) if ok else ("FAILED: " + msg))
        if ok:
            try:
                c = load_config()
                c['rdkit_path'] = p
                save_config(c)
                log("Path remembered for next start.")
            except:
                pass
        finish(ok)

    btn_auto.Click   += on_auto
    btn_page.Click   += on_page
    btn_browse.Click += on_browse
    btn_load.Click   += on_load
    btn_test = Button()
    btn_test.Text     = "Self-test"
    btn_test.Location = Point(508, y + 158)
    btn_test.Size     = Size(104, 27)
    btn_test.Anchor   = (AnchorStyles.Bottom | AnchorStyles.Right)
    style_button(btn_test, primary=False)
    body.Controls.Add(btn_test)
    btn_test.Click   += lambda s, e: run_self_test()

    btn_close.Click  += lambda s, e: dlg.Close()

    dlg.Controls.Add(hdr)

    log("RDKit is optional. Every other filter works without it.")
    log("")
    log("Why this needs a helper rather than copying one file:")
    log("  * the managed assembly is RDKit2DotNet.dll, not")
    log("    RDKit2DotNetStandard.dll as v3.0/v3.1 assumed;")
    log("  * it P/Invokes into about 106 native boost/RDKit DLLs, so the")
    log("    managed DLL alone can never work;")
    log("  * the natives must match this process ({0}).".format(_rdkit_arch()))
    log("")

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

        # ---- Accurate-mass controls (v3.3) ----
        # Row 3 has free width from x=520, so the rows below keep
        # their existing y positions.
        lbl_mass = Label(Text="Mass mode:", Location=Point(520, y + 4),
                         AutoSize=True, Font=ui_font)
        cmb_mass = ComboBox()
        cmb_mass.Location      = Point(600, y)
        cmb_mass.Size          = Size(170, 24)
        cmb_mass.Font          = ui_font
        cmb_mass.DropDownStyle = ComboBoxStyle.DropDownList
        cmb_mass.Items.Add("Unit mass (nominal)")   # -> "unit"
        cmb_mass.Items.Add("Accurate mass (ppm)")   # -> "ppm"
        cmb_mass.Items.Add("Accurate mass (mDa)")   # -> "mda"
        _saved_mm = cfg.get('mass_mode', DEFAULT_MASS_MODE)
        if _saved_mm == 'ppm':
            cmb_mass.SelectedIndex = 1
        elif _saved_mm == 'mda':
            cmb_mass.SelectedIndex = 2
        else:
            cmb_mass.SelectedIndex = 0

        lbl_tol = Label(Text="Tol:", Location=Point(782, y + 4),
                        AutoSize=True, Font=ui_font)
        nud_tol = NumericUpDown()
        nud_tol.Location      = Point(815, y)
        nud_tol.Size          = Size(80, 24)
        nud_tol.Font          = ui_font
        nud_tol.DecimalPlaces = 2
        nud_tol.Minimum       = 0
        nud_tol.Maximum       = 10000
        nud_tol.Increment     = 1
        try:
            nud_tol.Value = float(cfg.get('mass_tol',
                                          str(DEFAULT_TOL_PPM)))
        except:
            nud_tol.Value = DEFAULT_TOL_PPM

        def _mass_mode_str():
            i = cmb_mass.SelectedIndex
            return "ppm" if i == 1 else ("mda" if i == 2 else "unit")

        def _on_mass_mode(s, e):
            """Grey the tolerance out in unit mode, where it has no
            effect, and relabel it with the active unit."""
            m = _mass_mode_str()
            nud_tol.Enabled = (m != "unit")
            lbl_tol.Text    = "Tol:" if m == "unit" else (
                "ppm:" if m == "ppm" else "mDa:")
        cmb_mass.SelectedIndexChanged += _on_mass_mode
        _on_mass_mode(None, None)
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
                        else "RDKit -- use 'RDKit...' in the banner")
        chk_rdkit    = _mk_chk(rdkit_label, 380, 48, 'flt_rdkit', False)
        chk_c13      = _mk_chk("Skip 13C satellites", 620, 48,
                               'skip_c13', False)
        if not RDKIT_LOADED:
            chk_rdkit.Enabled = False   # greyed out until DLL is present
            chk_rdkit.Checked = False

        def _refresh_rdkit_state():
            """Called by the RDKit setup dialog after a successful load,
            so the filter becomes usable without a restart."""
            try:
                if RDKIT_LOADED:
                    chk_rdkit.Text    = "RDKit (bond-break check)"
                    chk_rdkit.Enabled = True
                else:
                    chk_rdkit.Text    = "RDKit -- use 'RDKit...' in the banner"
                    chk_rdkit.Enabled = False
                    chk_rdkit.Checked = False
            except:
                pass

        def _on_rdkit(s, e):
            show_rdkit_setup(form, _refresh_rdkit_state)

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
            Size=Size(930, FORM_HEIGHT - y - 100),
            Font=mono_font, Multiline=True,
            ScrollBars=ScrollBars.Both, ReadOnly=True,
            Anchor=(AnchorStyles.Top | AnchorStyles.Bottom |
                    AnchorStyles.Left | AnchorStyles.Right))

        # Add all top-level controls to the form.
        for ctrl in [lbl_in, txt_in, btn_in,
                     lbl_out, txt_out, btn_out,
                     lbl_emode, cmb_emode, lbl_min, nud_min, lbl_struct,
                     lbl_mass, cmb_mass, lbl_tol, nud_tol,
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

        def get_skip_c13():
            return bool(chk_c13.Checked)

        def get_mass_settings():
            """Return (mass_mode, tolerance). Tolerance is 0 in unit
            mode so assign_peak() takes the nominal path."""
            m = _mass_mode_str()
            if m == "unit":
                return "unit", 0.0
            try:
                return m, float(str(nud_tol.Value))
            except:
                return m, (DEFAULT_TOL_PPM if m == "ppm"
                           else DEFAULT_TOL_MDA)

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
            """Persist all current GUI settings.

            Merged into what is already stored, so keys this dialog
            does not own -- rdkit_path, written by the RDKit setup
            dialog -- survive. Replacing the dict wholesale used to
            wipe them.
            """
            _merged  = load_config()
            _mm, _mt = get_mass_settings()
            _merged.update({
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
                'mass_mode':     _mm,
                'mass_tol':      str(_mt),
                'skip_c13':      "1" if chk_c13.Checked else "0",
            })
            save_config(_merged)

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
            mass_mode, mass_tol = get_mass_settings()

            log("=== Preview  (electron={0}, min_peaks={1}, mass={2}, tol={3}) ===".format(
                emode, min_pk, mass_mode, mass_tol))
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
                    _p_assigned = {}   # nom -> (formula, ab, mz), defect 5
                    _p_c13      = 0
                    _p_skip_c13 = get_skip_c13()

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

                        if (_p_skip_c13 and is_c13_satellite(
                                t_nom, mz, ab, _p_assigned, mass_mode, mass_tol)):
                            _p_c13  += 1
                            dropped += 1
                            continue
                        best, exact, n_valid, m_err = assign_peak(
                            parent, t_nom, pctx, imap, flt_flgs, emode,
                            mz, mass_mode, mass_tol)
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
                        err_tag = ("" if m_err is None
                                   or mass_mode == "unit"
                                   else "  {0:+.2f} ppm".format(m_err))

                        _p_assigned[t_nom] = (best, ab, mz)
                        assigned += 1
                        log("  {0:>4} {1:>5.1f}%  {2:>12.6f}  {3:<12} "
                            "{4}  -{5}{6}{7}{8}".format(
                            t_nom, rel_pct, exact,
                            formula_str(best), ee_str, loss_s,
                            opt_tag, struct_tag, stable_tag) + err_tag)

                    status = "OK" if assigned >= min_pk else "SKIP"
                    log("  [{0}] {1}/{2} assigned,  {3} dropped,  "
                        "{4} ambiguous{5}".format(
                        status, assigned, len(mz_vals), dropped, ambig,
                        ("  ({0} 13C)".format(_p_c13)
                         if _p_c13 else "")))

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
            mass_mode, mass_tol = get_mass_settings()
            save_current_config()

            try:
                exp_flgs = get_export_flags()
                mass_mode, mass_tol = get_mass_settings()
                n = convert_library(
                    in_path, out_path, min_pk, emode, log, flt_flgs,
                    exp_flgs, mass_mode, mass_tol, get_skip_c13())
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
        form.Controls.Add(build_banner(form, _on_about, _on_rdkit))

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
