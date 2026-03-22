@echo off
setlocal enabledelayedexpansion
title EI Fragment Calculator — Build Windows Installer

echo.
echo ================================================================
echo   EI Fragment Exact-Mass Calculator — Windows Installer Builder
echo ================================================================
echo.

REM ── Must be run from the project root ────────────────────────────────────
if not exist "ei_fragment_gui.spec" (
    echo ERROR: Run this script from the project root directory.
    echo        Expected to find ei_fragment_gui.spec here.
    pause & exit /b 1
)

REM ── 1. Check Python ───────────────────────────────────────────────────────
echo [check] Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH.
    echo        Install Python 3.10+ from https://www.python.org/
    echo        Make sure "Add Python to PATH" is ticked during install.
    pause & exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo         %%v found.
echo.

REM ── 2. Ensure the package itself is installed ────────────────────────────
echo [check] ei-fragment-calculator package...
python -c "import ei_fragment_calculator" >nul 2>&1
if errorlevel 1 (
    echo         Not installed — running: pip install -e .
    pip install -e . --quiet
    if errorlevel 1 (
        echo ERROR: pip install -e . failed.
        pause & exit /b 1
    )
)
echo         OK.
echo.

REM ── 3. Ensure PyInstaller is installed ───────────────────────────────────
echo [check] PyInstaller...
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo         Not found — installing PyInstaller...
    pip install pyinstaller --quiet
    if errorlevel 1 (
        echo ERROR: pip install pyinstaller failed.
        pause & exit /b 1
    )
)
for /f "tokens=*" %%v in ('python -c "import PyInstaller; print(PyInstaller.__version__)" 2^>^&1') do echo         PyInstaller %%v found.
echo.

REM ── 4. Find Inno Setup ───────────────────────────────────────────────────
echo [check] Inno Setup 6...
set "ISCC="
for %%p in (
    "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
    "%ProgramFiles%\Inno Setup 6\ISCC.exe"
    "%ProgramFiles(x86)%\Inno Setup 5\ISCC.exe"
    "%ProgramFiles%\Inno Setup 5\ISCC.exe"
) do (
    if exist %%p (
        set "ISCC=%%p"
        goto :found_iscc
    )
)

echo.
echo ERROR: Inno Setup not found.
echo.
echo        Download and install the free Inno Setup 6 from:
echo        https://jrsoftware.org/isdl.php
echo.
echo        Then re-run this script.
pause & exit /b 1

:found_iscc
echo         Found: !ISCC!
echo.

REM ── 5. Clean previous build ──────────────────────────────────────────────
echo [clean] Removing previous dist\ei-fragment-gui ...
if exist "dist\ei-fragment-gui" (
    rmdir /s /q "dist\ei-fragment-gui"
)
echo         Done.
echo.

REM ── 6. PyInstaller — freeze the application ──────────────────────────────
echo [1/2] Freezing application with PyInstaller...
echo       (this may take 1-3 minutes on first run)
echo.
python -m PyInstaller ei_fragment_gui.spec --noconfirm
if errorlevel 1 (
    echo.
    echo ERROR: PyInstaller failed. See output above for details.
    pause & exit /b 1
)

REM Sanity check — make sure the EXE was actually produced
if not exist "dist\ei-fragment-gui\ei-fragment-gui.exe" (
    echo.
    echo ERROR: dist\ei-fragment-gui\ei-fragment-gui.exe was not created.
    echo        Check the PyInstaller output above for errors.
    pause & exit /b 1
)
echo.
echo         PyInstaller build complete.
echo         Application directory: dist\ei-fragment-gui\
echo.

REM ── 7. Create output directory ────────────────────────────────────────────
if not exist "installer_output" mkdir "installer_output"

REM ── 8. Inno Setup — compile the installer ────────────────────────────────
echo [2/2] Compiling Windows installer with Inno Setup...
echo.

REM Skip the SetupIconFile line if docs\icon.ico does not exist
if not exist "docs\icon.ico" (
    echo         Note: docs\icon.ico not found — using default icon.
    REM Patch the .iss on-the-fly: write a temp version without the icon line
    set "ISS_FILE=installer.iss"
    set "ISS_TMP=installer_noicon.iss"
    python -c "
import re, pathlib
src = pathlib.Path('installer.iss').read_text('utf-8')
src = re.sub(r'(?m)^SetupIconFile=.*\n', '', src)
src = re.sub(r'(?m)^; \^ Remove.*\n', '', src)
pathlib.Path('installer_noicon.iss').write_text(src, 'utf-8')
"
    set "ISS_FILE=installer_noicon.iss"
) else (
    set "ISS_FILE=installer.iss"
)

!ISCC! "!ISS_FILE!"
if errorlevel 1 (
    echo.
    echo ERROR: Inno Setup failed. See output above for details.
    if exist "installer_noicon.iss" del "installer_noicon.iss"
    pause & exit /b 1
)

if exist "installer_noicon.iss" del "installer_noicon.iss"

REM ── 9. Done ───────────────────────────────────────────────────────────────
echo.
echo ================================================================
echo   Build complete!
echo.
echo   Installer : installer_output\EI-Fragment-Calculator-v1.6.3-Setup.exe
echo.
echo   To install: double-click the file above.
echo   To rebuild: run this script again.
echo ================================================================
echo.

REM Open the output folder in Explorer
explorer "installer_output"

pause
endlocal
