# EI Fragment Calculator — v3.2

| | |
|---|---|
| **Platform** | MassHunter Library Editor — IronPython 2.7.5, .NET-only, with a WinForms UI |
| **File** | `ei_fragment_calculator_v3.1.py` (`APP_VERSION = "3.2"`) |
| **Repo path** | `masshunter/ei_fragment_calculator_v3.1.py` |
| **Install folder** | `<MassHunter>\Scripts\LibraryEdit\` |
| **Settings file** | `%AppData%\exactmass_libconv\settings.txt` |
| **Lineage** | `UnitMass_to_ExactMass_v1.2` (Luca Godina) → `v3.0` (Joerg Riener) → `v3.1` → `v3.1.1` → `v3.1.2` → `v3.2` |

> **The filename does not carry the patch level.** The file stays
> `ei_fragment_calculator_v3.1.py`; the build is identified by `APP_VERSION`
> in the source and by the version shown in the banner. **Check the banner
> reads v3.2** — anything lower is an older copy.

### Fixed in 3.1.2 — the Browse buttons were off-screen

This is the defect behind "there is no Browse button". In 3.1 and 3.1.1 the
**Input XML** and **Output Path** rows, their **Browse** buttons, the filter
group and the log were all positioned off the right edge of the window.

v3.1 introduced a `content` panel to sit below the new 56-px banner, but
populated it **before** adding it to the form. WinForms fixes a control's
`Anchor` offset at the moment it is added, from its parent's *current* size —
and a `Panel` not yet on a form is still the default **200 px** wide. A Browse
button at `x=850` with `Anchor = Top | Right` therefore recorded a right
margin of `200 − (850+88) = −738 px`, and when the panel later filled to
~944 px that margin flung it to roughly `x = 1682`. The panel is now docked to
the form before any child is added, so the margin is a correct `+6 px`.

This is the same trap the style guide documents for the banner `?` button
(§6) — it applies to *any* right- or bottom-anchored control added to a parent
that has not been sized yet.

### New in 3.2 — RDKit installable from the GUI

A banner **RDKit…** button opens a setup dialog that downloads and
installs the RDKit .NET wrapper, or loads one you already have, and
enables the filter without restarting MassHunter. It also corrects the
assembly name v3.0/v3.1 looked for, which did not exist. See §2.

### Fixed in 3.1.1 — dialog ownership

Both file dialogs and all four MessageBoxes were owned by the *MassHunter main
form*, but the tool's own form is shown modal over that form — so a child
window owned by it was pushed **behind** the tool and could not be reached.
All six dialog sites are now owned by the tool's own form. **This defect was
inherited unchanged from v3.0.**

> `<MassHunter>` in the paths below stands for your MassHunter installation
> root -- often on the `D:` drive, sometimes `C:`. Substitute the real path
> for your workstation.

> **Renamed in v3.1.** This is the former *Unit Mass to Exact Mass Library
> Converter*, renamed to align with the standalone CPython project
> `github.com/joriener/ei-fragment-calculator`. The two share the chemistry
> but not the host: **this file is the only one of the pair that writes exact
> masses back into a MassHunter library XML.** See
> `ei-fragment-calculator_vs_UnitMass_ComparisonTable.md`.

---

## 1. Purpose

Converts a unit-mass EI spectral library into an exact-mass library.

For each compound the tool parses the molecular formula and the MOL block,
builds a structural fragment whitelist, and then **for every peak** enumerates
all sub-formulas of the parent with matching nominal mass, filters out the
chemically impossible ones, scores the survivors, and assigns the best
candidate's calculated exact mass.

The molecular formula acts as an **elemental upper bound** — a fragment can
never contain an atom the parent does not have. That is what makes the
enumeration tractable.

Output can be written as MassHunter XML, NIST/AMDIS MSP, and/or MDL SDF, in
any combination.

> **Unit mass in, exact mass out.** The tool does not measure anything. It
> assigns the most plausible formula to each nominal peak and reports that
> formula's calculated exact mass. It is not a substitute for accurate-mass
> acquisition, and at higher m/z a nominal mass can host many valid
> sub-formulas. Where the filters and the structural whitelist cannot
> discriminate, the winning candidate is a ranked guess — the preview marks
> these with `[Nopt]`.

---

## 2. Requirements and dependencies

### Required

| Dependency | How to get it |
|---|---|
| MassHunter Library Editor (`LibraryEdit.exe`) | Part of the MassHunter installation |
| IronPython 2.7.5 host | Built into Library Editor — nothing to install |
| .NET Framework (WinForms, `System.Xml`, `System.Drawing`) | Part of Windows / the MassHunter installation |
| A unit-mass library XML to convert | Your input |

No third-party Python packages, and no Python standard library — the
MassHunter IronPython host does not ship one. Everything is plain Python plus
.NET types reached through `clr`.

### Optional — RDKit .NET, installed from the GUI (new in 3.2)

The **RDKit (bond-break check)** filter needs the SWIG-generated RDKit .NET
wrapper. The other five filters work without it.

**Click `RDKit…` in the banner.** The setup dialog installs it for you:

| Option | What it does |
|---|---|
| **1 — Download and install** | Fetches `RDKit.DotNetWrap` from nuget.org (~27 MB), extracts the managed assembly and the natives matching **this** process, puts them on the process PATH, and loads them |
| **2 — Locate an existing `RDKit2DotNet.dll`** | Browse to an assembly you already have and load it |
| **Open nuget.org page** | Fallback if the download is blocked |

The dialog reports the process architecture, the install folder, and a log of
what happened. On success the filter checkbox becomes usable **without
restarting MassHunter**, and the path is remembered for next start
(`rdkit_path` in the settings file).

Install target is `%AppData%\exactmass_libconv\rdkit\` — a per-user folder, so
**no administrator rights are needed**.

```powershell
Get-ChildItem "$env:AppData\exactmass_libconv\rdkit" -Recurse | Measure-Object -Property Length -Sum
```

#### Why this needs a helper rather than copying one file

Three things make manual installation fail silently, all verified against
`RDKit.DotNetWrap 0.2021094.2`:

1. **The managed assembly is `RDKit2DotNet.dll`.** v3.0 and v3.1 looked for
   `C:\Windows\System32\RDKit2DotNetStandard.dll` — **that filename does not
   exist in the package at all.** Its only managed assemblies are
   `lib/netstandard2.0/RDKit2DotNet.dll` and
   `lib/netcoreapp3.1/RDKit2DotNet.dll`.
2. **It has ~106 native dependencies.** The managed assembly P/Invokes into
   boost and RDKit native DLLs under `runtimes/<arch>/native/`. Copying only
   the managed DLL can never work — the first real call fails to resolve.
3. **The architecture must match the host process.** `LibraryEdit.exe`
   (`...\Workstation\Quant\bin`) is a **32-bit PE32** image, so it needs the
   `win-x86` natives; the `win-x64` set raises `BadImageFormatException`.
   `_rdkit_arch()` reads `IntPtr.Size` at runtime rather than assuming, so it
   stays correct on a 64-bit host.

The legacy `System32\RDKit2DotNetStandard.dll` path is still tried last, so an
existing hand-made installation keeps working.

> **Unverified.** The download, extraction and load path has **not** been
> executed inside MassHunter. What *is* verified: the nuget.org URLs resolve,
> the package layout is as described (1 managed assembly + 106 natives per
> architecture, confirmed by scanning the real 27 MB package), the
> entry-matching logic selects exactly those files, and
> `System.IO.Compression.FileSystem` is present on this workstation
> (.NET Framework 4.8.1). What is **not** verified: whether IronPython 2.7 can
> load a `netstandard2.0` assembly in this host, and whether the native
> P/Invokes resolve once loaded. If it fails, the dialog log shows the real
> exception — send it over.

---

## 3. Installation

1. Copy the script into the Library Editor scripts folder:

   ```powershell
   Copy-Item ".\masshunter\ei_fragment_calculator_v3.1.py" -Destination "<MassHunter>\Scripts\LibraryEdit\" -Force
   ```

2. Restart MassHunter Library Editor.

3. Launch the tool from Library Editor's script menu.

The tool is a **single `.py`** — the icon and readme are embedded, so there
are no companion files to lose.

Verify what is installed, and inspect or reset persisted settings:

```powershell
Get-ChildItem "<MassHunter>\Scripts\LibraryEdit\*.py" | Select-Object Name, Length, LastWriteTime
Get-Content "$env:AppData\exactmass_libconv\settings.txt"
Remove-Item "$env:AppData\exactmass_libconv\settings.txt"
```

---

## 4. Parameters in the dialog

### Files

| Control | Meaning |
|---|---|
| **Input XML** | Source unit-mass library. **Browse…** to select |
| **Output Path** | Destination base path. XML is written as `<base>_exactmass.mslibrary.xml`; MSP and SDF sit alongside |

### Conversion settings

| Control | Options / default | Meaning |
|---|---|---|
| **Electron mode** | **`remove (EI+, standard)`** / `add (EI-, negative ion)` / `none (no correction)` | The detector measures the ion, i.e. neutral − one electron, so `remove` is the standard EI+ choice |
| **Min peaks** | `3` (range 1–100) | Spectra with fewer assigned peaks are skipped |

### Post-enumeration filters

Six independently toggleable filters. All on by default except RDKit.

| Filter | Default | Rejects | Basis |
|---|---|---|---|
| **Nitrogen rule** | on | Odd/even m/z inconsistent with the N+P count for the ion type | McLafferty & Turecek 1993 |
| **HD-check (DBE/C<=1)** | on | DBE/C above 1.0 — implausibly hydrogen-poor fragments | Pretsch et al. 2009 |
| **Lewis-Senior** | on | Valence sums that cannot form a connected structure | Senior 1951 |
| **Isotope M+1/M+2** | on | Formulas whose predicted isotope pattern disagrees with the observed spectrum | Gross 2017 |
| **SMILES ring-count** | on | Fragments with more rings than the parent can supply | Weininger 1988 |
| **RDKit (bond-break check)** | off | Heavy-atom formulas unreachable by any single bond break | install it from the banner **RDKit…** button (§2) |

The isotope filter is the most powerful of the six on halogenated compounds
because it uses the spectrum itself — but it needs real intensity contrast.
Structural fragmentation is applied additionally when the compound has a
`<MolFile>`, shown in the dialog as `[+struct when <MolFile> present]`.

### Export formats

| Checkbox | Format |
|---|---|
| **XML (MassHunter)** | `.mslibrary.xml` |
| **MSP (NIST / AMDIS)** | `.msp` |
| **SDF (MDL / RDKit)** | `.sdf` |

### Actions

| Button | Meaning |
|---|---|
| **Preview** | Runs the identical assignment pipeline and writes nothing |
| **Convert** | Runs the conversion and writes the ticked formats |
| **Quit** | Closes the tool |
| **RDKit…** (banner) | RDKit setup: download and install, or locate an existing assembly (§2) |
| **?** (banner) | About dialog → **View Readme** for the full embedded guide |

> **Preview and Convert cannot disagree.** As of v3.1 both call one
> implementation of the pipeline (`build_compound_context` → `assign_peak`).
> In v3.0 they were two independent call sites that had to be kept in step by
> hand.

### Reading the preview

One line per assigned peak: nominal m/z, relative intensity, assigned exact
mass, formula, EE or OE, and the neutral loss from the molecular ion. Tags:

| Tag | Meaning |
|---|---|
| `[Nopt]` | N candidates were possible and one was chosen |
| `*` | The formula matched the structural whitelist |
| `[ion]` | A hit in the stable-ion library, named |

A high `[Nopt]` count is the signal to enable more filters or supply a MOL
block.

---

## 5. Key configuration in the source

| Item | Location | Notes |
|---|---|---|
| `APP_TITLE` / `APP_VERSION` / `APP_SLUG` | Section 0 | `"EI Fragment Calculator"` / `"3.1"` / `"ei_fragment_calculator"`. `APP_SLUG` sets the settings folder and the readme temp-file prefix |
| Palette `C_*` and fonts `FONT_*` | Section 0 | Agilent WinForms style-guide tokens |
| `BANNER_HEIGHT` | Section 0 | `56` — required by the style guide, never smaller |
| `ICON_B64` | Section 0 | Embedded multi-resolution icon (16–256 px), mark `EF` in white on `#0085D5` |
| `ELEM` | Section 2 | Element table: symbol → (nominal mass, monoisotopic exact mass). 30 elements: Al As B Br C Ca Cl Co Cr Cu D F Fe H I K Mg Mn N Na Ni O P Pb S Se Si Sn Ti V Zn. Sources: IUPAC 2016 + NIST CODATA 2018 |
| `ELECTRON_MASS` | Section 2 | `0.00054857990907` Da (CODATA 2018) |
| `VALENCE`, `IMPLICIT_VALENCE`, `HILL`, `COMMON_LOSSES` | Section 2 | Valence tables, Hill ordering, 36 common neutral losses |
| `STABLE_IONS` / `STABLE_ION_BONUS` | Section 5 | 40+ known stable EI cations; a match adds +100 |
| `M1_PER_ATOM` / `M2_PER_ATOM` | Section 3 | Per-atom isotope contributions |
| `_SUBFORMULA_CACHE_MAX` | Section 10 | `200000` — upper bound on the enumeration cache |
| `_rdkit_dll` | Section 0/1 | Full path to the RDKit .NET assembly |
| Settings persistence | Section 13 | `%AppData%\exactmass_libconv\settings.txt`, one setting per line. Last folder, min peaks, electron mode, all six filter flags and all three export flags persist |

---

## 6. Performance

Enumeration cost is driven by **element diversity, not molecule size** —
every distinct element adds a level to the depth-first search. Halogenated and
heteroatom-rich compounds (pesticides, flame retardants, PFAS) are the
expensive case.

v3.1 rewrote the enumeration inner loop: element counts are held in a flat
list indexed by position rather than a dict keyed by symbol, a suffix-mass
bound prunes branches that have already spent too little to reach the target
(v3.0 pruned only downward), per-compound preparation is built once and reused
for every peak, and results are memoised on (parent formula, target nominal
mass).

Measured in CPython, sweeping every nominal mass from 0 to the parent nominal
mass:

| Parent | Formula | Elements | Candidates | v3.0 | v3.1 | Speedup |
|---|---|---|---|---|---|---|
| Caffeine | `C8H10N4O2` | 4 | 1,484 | 23.9 ms | 2.0 ms | 12.0× |
| Cholesterol | `C27H46O` | 3 | 2,631 | 60.1 ms | 2.5 ms | 23.9× |
| Permethrin | `C21H20Cl2O3` | 4 | 5,543 | 136.7 ms | 6.0 ms | 22.8× |
| Large steroid | `C30H50O2` | 3 | 4,742 | 124.7 ms | 4.6 ms | 26.9× |
| Chlorpyrifos | `C9H11Cl3NO3PS` | 7 | 15,359 | 415.0 ms | 23.1 ms | 17.9× |
| TMS-ether | `C6H18OSi2` | 4 | 797 | 9.9 ms | 1.1 ms | 9.2× |
| Bromo mix | `C4H5BrClFNO2S` | 7 | 2,879 | 80.6 ms | 7.5 ms | 10.8× |
| Metal complex | `C10H8FeNa2O4` | 5 | 2,969 | 75.3 ms | 5.4 ms | 13.9× |
| **Total** | | | **36,506** | **929.0 ms** | **53.5 ms** | **17.4×** |

The enumeration cache adds a further **16.1×** on a batch of 30 isomers
sharing one parent formula (150 peaks each: 92.2 ms → 5.7 ms). The benefit is
entirely a property of your library — a library of unique formulas sees none,
and pays only one dict lookup per peak.

These are CPython figures; IronPython 2.7 is typically 2–5× slower in absolute
terms, but the ratio holds. A halogen-rich library that took an hour under
v3.0 should be minutes under v3.1.

**Output is identical to v3.0.** Verified by sweeping every nominal mass from
0 to the parent nominal mass for 12 parent formulas spanning 3–7 distinct
elements — 36,506 candidate formulas in total, with zero differences, and the
cached wrapper cross-checked against the uncached result.

---

## 7. Verification of the v3.1 refactor

The chemistry was **moved, not rewritten**: whole line ranges were sliced from
v3.0 and dedented, so the element table, filters, structural rules and scoring
criteria are preserved byte-for-byte.

| Check | Result |
|---|---|
| Functions relocated from v3.0 | 46 |
| Byte-identical in v3.1 | 39 |
| Changed | 7 — the six named in the optimization options, plus `recurse` (the inner function of `find_subformulas`) |
| Missing | 0 |
| Chemistry constant blocks compared | `ELEM`, `VALENCE`, `IMPLICIT_VALENCE`, `HILL`, `STABLE_IONS`, `M1_PER_ATOM`, `M2_PER_ATOM`, `ALPHA_HETEROATOMS`, `ELECTRON_MASS`, `STABLE_ION_BONUS` — **all identical** |
| GUI functions compared | 11; 10 byte-identical, only `on_preview` changed (the Option 6 rewire) |
| Enumeration output | Identical over 36,506 candidates (§6) |
| Static name resolution | 158 module-level bindings; **no unresolved global references** in any function after de-nesting |
| Syntax | `ast.parse` clean |
| Live `Double.Parse` calls | **0** (the three remaining mentions are comments describing the bug that was fixed) |

**Partially exercised in a live session.** 3.1 was launched in a real
MassHunter Library Editor session -- that is how the dialog-ownership defect
fixed in 3.1.1 was found. Still not validated: a full conversion against a
real library, and the WinForms layout beyond the file pickers (banner
geometry, About dialog, content-panel offset). Run **Preview** on a small
library first and compare its assignments against a v3.0 preview of the same
file before trusting a conversion.

---

## 8. Structure

v3.0 held its entire program inside one function: `_Run()` spanned 2,538 lines
with roughly 50 nested `def`s. IronPython's DLR stores every free variable a
nested function captures in a generated `MutableTuple` whose size is limited,
and `EXIMPORT_SDFMSP` hit exactly that ceiling — *"ItemNNN is not defined for
type"* — with a smaller file.

v3.1 moves everything except the GUI to module level:

| | v3.0 | v3.1 |
|---|---|---|
| Module-level functions | 3 | 58 |
| Functions nested in `_Run()` | ~50 | 14 (GUI event handlers only) |
| `_Run()` size | 2,538 lines | 553 lines |
| Total | 2,625 lines | 3,432 lines |

Besides removing the load-failure risk, this makes the pure functions testable
with an extract-and-run harness — which is how every number in §6 was
obtained — and visible to `check_shared_blocks.py`.

---

## 9. Operational notes

- **Ambiguity is real** (see §1). Treat `[Nopt]` counts as the quality signal.
- **Supply MOL blocks where you can.** The structural whitelist carries the
  largest single scoring bonus and enables the ring-count and RDKit filters.
- **Filter to what your data supports.** The isotope filter needs intensity
  contrast; the ring-count and RDKit filters need a MOL block.
- **Locale independence.** As of v3.1 the base64 codecs no longer round-trip
  through a culture-dependent `Double.Parse`, so the tool writes identical
  output on any Windows regional setting. Libraries written by v3.0 or earlier
  **on a non-English-locale machine** carry corrupted m/z and abundance values
  and should be regenerated.
- **Preview before Convert**, every time. It is the same pipeline and costs
  only time.
