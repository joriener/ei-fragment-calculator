# MassHunter sibling — EI Fragment Calculator v3.4

This folder holds the **MassHunter-hosted** member of the EI Fragment
Calculator family. It is not part of the `ei_fragment_calculator` Python
package and is not installed by `pip`.

| | Python package (repo root) | This folder |
|---|---|---|
| **File** | `ei_fragment_calculator/` | `ei_fragment_calculator_v3.1.py` |
| **Runtime** | CPython ≥ 3.10 | IronPython 2.7.5 (.NET only) |
| **Host** | Standalone — CLI + tkinter GUI | Agilent MassHunter Library Editor |
| **Install** | `pip install -e .` | Copy the single `.py` into `<MassHunter>\Scripts\LibraryEdit\` |
| **Dependencies** | Standard library (optional extras) | None — no Python standard library is available in the host |
| **Input** | SDF, MSP, CEF, NIST | MassHunter library XML |
| **Output** | SDF, MSP | **MassHunter library XML**, SDF, MSP |
| **Mass accuracy** | Nominal **and** accurate-mass (`--ppm`, `--hr`) | Nominal **and** accurate-mass (ppm / mDa, v3.3) |
| **Tests** | `pytest` under `tests/` | Verified by extract-and-run harness (see below) |

## Why both exist

The two share the chemistry — the same 30-element table, the same
nitrogen-rule / HD-check / Lewis-Senior / isotope / ring-count / RDKit
filters, and the same homolytic, α-cleavage, McLafferty and retro-Diels-Alder
fragmentation rules.

They differ in where they can run. **Only this script writes exact masses back
into a MassHunter library**, because only it runs inside the Library Editor
and can reach the library XML. The Python package is the better tool for
everything else: it has a CLI, a weighted confidence model, four additional
filters, accurate-mass support, multiprocessing and a CEF workflow, none of
which the IronPython host can support.

If your output has to end up in a MassHunter library, use this. Otherwise use
the package.

## Lineage

```
UnitMass_to_ExactMass v1.2   Luca Godina
UnitMass_to_ExactMass v3.0   Joerg Riener   12 -> 30 elements, 6 filters,
                                            4 structural rules, MSP/SDF export
ei_fragment_calculator v3.1  Joerg Riener   performance + structure; renamed
```

`ei-fragment-calculator_vs_UnitMass_ComparisonTable.md` in this folder is a
67-row three-way comparison of v1.2, v3.0 and the Python package, including
which of the six optimization options each one implements.

## What v3.1 changed

Performance and structure only. The chemistry is byte-for-byte v3.0.

| | Change |
|---|---|
| Enumeration | Flat count list instead of a symbol-keyed dict, plus a suffix-mass bound that prunes branches which have already spent too little to reach the target. v3.0 pruned only downward. Per-compound preparation is built once and reused for every peak |
| Memoisation | Enumeration cached on (parent formula, target nominal mass); isomers share a parent formula |
| Codecs | `Buffer.BlockCopy` for whole arrays, and the culture-dependent `Double.Parse(str(v))` round trip removed — see the warning below |
| Structure | Everything except the GUI moved to module level: `_Run()` 2,538 → 553 lines, module-level functions 3 → 58 |
| Pipeline | One implementation of whitelist → enumerate → pick, shared by the conversion and the preview, which previously were separate call sites |
| Style | Agilent WinForms style guide: 56-px banner, About dialog, embedded readme and icon |

**Measured** (CPython, sweeping every nominal mass from 0 to the parent
nominal mass): **17.4× faster** overall across 12 parent formulas and 36,506
candidate formulas, with **identical output**. The cache adds a further 16.1×
on 30 isomers sharing one formula. IronPython is slower in absolute terms but
the ratio holds.

> ### Locale warning for libraries written by v3.0 or earlier
>
> Up to and including v3.0, the base64 encoder called
> `BitConverter.GetBytes(Double.Parse(str(v)))`. `Double.Parse(String)` with
> no `IFormatProvider` uses `CurrentCulture` **and**
> `NumberStyles.AllowThousands`, so on any locale where `.` is the *group*
> separator it silently returned a different number rather than raising —
> measured on CLR 4.0.30319 under `de-DE`: `"147.08"` → `14708.0`,
> `"42.033826"` → `42033826.0`.
>
> Being culture-dependent, it was correct on an en-US machine, which is how it
> passed validation. **Any library written by v3.0 or earlier on a
> non-English-locale workstation carries corrupted m/z and abundance values
> and should be regenerated with v3.1.**

## New in 3.4 — seven defects closed

| # | Defect | Fix |
|---|---|---|
| 1 | **Only the first spectrum of a compound was converted.** `spec_map[cid]` collected every `<Spectrum>` node; both call sites then used `sp_nodes[0]` and dropped the rest silently. This is the normal shape of an accurate-mass library — one spectrum per collision energy or polarity — so the loss was large and invisible | Every spectrum is converted. The XML writer emits one `<Compound>` followed by one `<Spectrum>` per record, `SpectrumID` counting from 1. MSP and SDF get one record per spectrum (correct for both formats), name-suffixed `[2/3]` when a compound contributed several. The compound-level work — formula parse, MOL block, structural whitelist, RDKit fragment set — still happens once per compound |
| 2 | **The write path had never been validated.** | `verify_output_xml()` re-reads the file just written and checks compound, spectrum and peak counts against what was intended, and that every base64 array pair decodes to equal non-zero lengths. A mismatch is reported loudly in the log. It is a genuine re-read, so it exercises the encoder, the XML escaping and the file write |
| 3 | **A successful RDKit load proved nothing.** `clr.AddReferenceToFileAndPath()` only resolves the *managed* assembly; the ~106 native DLLs are reached by P/Invoke on first real use, so a load can succeed and every call still throw | `rdkit_self_test()` parses benzene and checks it has six atoms. It runs automatically after any successful load, and has its own **Self-test** button. If the assembly loads but RDKit does not work, the filter is left disabled rather than failing on first use |
| 4 | **The isotope filter rejected good formulas on flat spectra.** It compares observed M+1/M+2 ratios against theory, which needs real intensity contrast; against a normalised or thresholded peak list the ratios are noise | `intensity_map_is_flat()` detects too little contrast (fewer than 3 distinct abundances, or max/min < 1.5) and the filter fails **open**, matching how the tool's other filters behave when their evidence is missing |
| 5 | **13C satellites were assigned fragment formulas.** Peaks above M+1 were dropped, but satellites *inside* a spectrum went to the enumerator and got a formula of their own — chemically wrong, it is the same ion with a heavy carbon | Optional `is_c13_satellite()`, via a **Skip 13C satellites** checkbox (**off** by default, since it changes which peaks get formulas). Requires the peak below to be assigned and at least as abundant, and this peak's relative abundance not to exceed that formula's theoretical M+1 × 2.5. In accurate mode the spacing is also checked against the true 13C−12C difference (1.0033548 Da), which makes the call unambiguous |
| 6 | **Option 3's candidate pre-filter was unmeasured.** | **Profiled, and the premise turned out to be wrong** — see below. Closed with data |
| 7 | Minor: log box sized against a hardcoded 750 on an 810-px form; the accurate-mass window was an unreachable constant; settings were written in place | Log box sizes off `FORM_HEIGHT`; the window is configurable via `acc_window`; `save_config()` writes a temp file and moves it into place, so an interrupted write cannot leave a truncated settings file |

### Defect 6 in detail — why the pre-filter is *not* worth doing

Option 3 proposed applying cheap disqualifiers (RDB range, H/C ratio, zero-H)
before full scoring. The paper said to measure `score_formula` first. Measured,
per candidate:

| Parent | m/z | Candidates | `score_formula` | `apply_all_filters` | ratio |
|---|---|---|---|---|---|
| `C9H11Cl3NO3PS` | 200 | 73 | 8.43 µs | 8.10 µs | 0.96× |
| `C21H20Cl2O3` | 235 | 21 | 6.57 µs | 6.28 µs | 0.96× |
| `C8H10N4O2` | 179 | 2 | 5.63 µs | 6.41 µs | 1.14× |
| `C27H46O` | 255 | 7 | 5.58 µs | 5.77 µs | 1.04× |

**Scoring and filtering cost the same.** Pre-filtering before scoring could
therefore save at most half of half the per-candidate cost — ≲25% — and only
by changing results, because those criteria are finite penalties, not floors.
A candidate failing one can still legitimately win.

There is a better route to the same end, already in place: **accurate mass**.
The tolerance filter reduces a peak's candidate set to one in the cases
measured (21→1, 16→1), and `pick_best_v3()` returns immediately for a single
candidate — so scoring and filtering are skipped altogether. Tightening the
tolerance beats pre-filtering, and does not change which formula wins.

The safe parts of Option 3 were already implemented in 3.2: DBE computed once
and shared between the two passes, and below-floor candidates dropped before
the expensive pass whenever a possible candidate exists.

## New in 3.3 — accurate-mass spectra

Until 3.2 every peak was rounded to a nominal mass and the decimals thrown
away, so an accurate-mass library gained nothing from its own precision. A
**Mass mode** control on row 3 now selects how peaks are matched:

| Mass mode | Behaviour |
|---|---|
| **Unit mass (nominal)** — default | Enumerate sub-formulas whose *nominal* mass equals `round(m/z)`. Byte-identical to v3.0/v3.2 |
| **Accurate mass (ppm)** | Keep only candidates whose electron-corrected *exact* mass is within *N* ppm of the measured m/z. Default 10 ppm |
| **Accurate mass (mDa)** | Same, with an absolute tolerance in mDa. Default 5 mDa |

The tolerance box is greyed out in unit mode and relabels itself `ppm:` or
`mDa:`. Both settings persist, and the preview reports the mass error of every
assignment in ppm, e.g. `  -1.83 ppm`.

Candidates outside tolerance are **rejected**, not penalised — so the
tolerance is the control that matters. Within tolerance the existing chemistry
score decides. If assignments stay ambiguous, tighten the tolerance before
reaching for more filters.

### What it buys you — measured

Simulated measurements at the true exact mass, counting candidates that
survive selection:

| Parent | Fragment | m/z | Unit mode | 10 ppm | 5 mDa |
|---|---|---|---|---|---|
| `C8H10N4O2` (caffeine) | `C7H7N4O2` | 179.0564 | 2 | **1** | 1 |
| `C21H20Cl2O3` (permethrin) | `C13H9Cl2` | 235.0076 | **21** | **1** | 1 |
| `C9H11Cl3NO3PS` (chlorpyrifos) | M+ | 348.9257 | 1 | 1 | 1 |
| `C27H46O` (cholesterol) | `C19H27` | 255.2107 | 7 | **1** | 1 |
| `C6H18OSi2` (TMS ether) | `C5H15OSi2` | 147.0656 | 2 | **1** | 1 |
| `C10H8FeNa2O4` | `C10H8O4` | 192.0417 | **16** | **1** | 1 |

The true formula was retained in every accurate-mode result. Permethrin's
fragment goes from 21 plausible formulas to one; the metal complex from 16 to
one. That is the ambiguity the `[Nopt]` tag reports in unit mode.

### Why the search window is ±1 nominal mass

Accurate mode cannot enumerate at `round(m/z)` alone. A formula's *nominal*
mass and `round(its exact mass)` diverge once the mass defect passes 0.5 Da,
and that happens inside the normal GC-MS range — hydrogen adds +7.8 mDa each:

```
C50H100   nominal 700   exact 700.783   round(exact) = 701   offset +1
C40H82    nominal 562   exact 562.642   round(exact) = 563   offset +1
```

Verified: the `C50H100` molecular ion **is** found with the ±1 window and is
**not** found when enumerating at `round(m/z)` only. Bromine (−81.7 mDa each)
rounds the other way, so the window is symmetric. Raise
`ACCURATE_NOMINAL_WINDOW` for very high mass.

## New in 3.2 -- RDKit installable from the GUI

A banner **RDKit...** button opens a setup dialog that either downloads and
installs the RDKit .NET wrapper, or loads one you already have, and enables
the filter **without restarting MassHunter**.

| Option | What it does |
|---|---|
| Download and install | Fetches `RDKit.DotNetWrap` from nuget.org (~27 MB), extracts the managed assembly and the natives matching *this* process, puts them on the process PATH, loads them |
| Locate an existing `RDKit2DotNet.dll` | Browse and load |
| Open nuget.org page | Fallback if the download is blocked |

Install target is `%AppData%\exactmass_libconv
dkit\` -- per-user, so **no
administrator rights**. The path is remembered for next start.

### Why a helper, not a file copy

Verified against `RDKit.DotNetWrap 0.2021094.2`:

1. **The managed assembly is `RDKit2DotNet.dll`.** v3.0/v3.1 looked for
   `RDKit2DotNetStandard.dll`, which **does not exist in the package**.
2. **~106 native dependencies.** It P/Invokes into boost/RDKit natives under
   `runtimes/<arch>/native/`; the managed DLL alone can never work.
3. **Architecture must match.** `LibraryEdit.exe` is a 32-bit PE32 image, so
   it needs `win-x86`; `win-x64` raises `BadImageFormatException`.
   `_rdkit_arch()` reads `IntPtr.Size` at runtime.

> **Unverified in the host.** The nuget URLs, package layout (1 managed + 106
> natives per arch) and the entry-matching logic were all checked against the
> real 27 MB package, and `System.IO.Compression.FileSystem` is present on
> .NET 4.8.1. Not checked: whether IronPython 2.7 can load a `netstandard2.0`
> assembly here, and whether the native P/Invokes resolve. The dialog log
> surfaces the real exception if not.

## Fixed in 3.1.2 -- the Browse buttons were off-screen

The **Input XML** and **Output Path** rows, their **Browse** buttons, the
filter group and the log were positioned off the right edge of the window in
3.1 and 3.1.1.

v3.1 introduced a `content` panel to sit below the new 56-px banner but
populated it *before* adding it to the form. WinForms fixes a control's
`Anchor` offset when the control is added, from its parent's current size --
and a `Panel` not yet on a form is still the default 200 px wide. A Browse
button at `x=850` anchored `Top | Right` therefore recorded a right margin of
`200 - (850+88) = -738 px`, and when the panel later filled to ~944 px that
margin flung it to roughly `x = 1682`. The panel is now docked before any
child is added, so the margin is a correct `+6 px`.

This is the same trap this guide documents for the banner `?` button -- it
applies to any right- or bottom-anchored control whose parent has not been
sized yet.

**Check the banner reads v3.4.** The filename does not carry the patch
level; `APP_VERSION` and the banner do.

## Fixed in 3.1.1 -- dialog ownership

In 3.1, and in v3.0 before it, the **Input XML** and **Output Path** Browse
buttons appeared to do nothing, and some message boxes never appeared. Both
file dialogs and all four MessageBoxes were owned by the *MassHunter main
form*, but the tool's own form is shown modal over that form -- so a child
window owned by it was pushed **behind** the tool and could not be reached.

All six dialog sites are now owned by the tool's own form, which is the
topmost modal window. This is the same correction `EXIMPORT_SDFMSP` v2.2
applied for its MessageBoxes. The banner shows **v3.1.1** once you have the
fixed build.

## Installation

```powershell
Copy-Item ".\masshunter\ei_fragment_calculator_v3.1.py" -Destination "<MassHunter>\Scripts\LibraryEdit\" -Force
```

Restart MassHunter Library Editor, then launch the tool from its script menu.
The script is deliberately a **single file** — the icon and readme are
embedded, so there is nothing else to copy. Full setup, every dialog
parameter and the configuration constants are documented in
`ei_fragment_calculator_v3.1_Documentation.md`.

## Verification status

The chemistry was moved, not rewritten: line ranges were sliced from v3.0 and
dedented, so 39 of the 46 relocated functions are byte-identical and all ten
chemistry constant blocks (`ELEM`, `VALENCE`, `STABLE_IONS`, the isotope
tables, …) compare equal. Enumeration output was verified identical over
36,506 candidates, and a static name-resolution pass confirms no function lost
a binding when it left the enclosing scope.

**Partially exercised in a live session.** 3.1 was launched in a real
MassHunter Library Editor session, which is how the dialog-ownership defect
above was found and fixed in 3.1.1. A full conversion has **not** yet been
validated against a real library, and the WinForms layout beyond the file
pickers is still visually unchecked.

Run **Preview** on a small library and compare its assignments against a v3.0
preview of the same file before trusting a conversion.

## Licence

MIT, as the rest of the repository. The tool carries the in-house disclaimer
in its About dialog: created by Agilent but not officially tested or
supported; a user-contributed tool, as-is with no warranty.
