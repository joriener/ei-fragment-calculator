@echo off
setlocal EnableDelayedExpansion
title EI Fragment Calculator -- Installer

echo.
echo ============================================================
echo  EI Fragment Exact-Mass Calculator  v1.5.0  --  Installer
echo ============================================================
echo.

REM ── 1. Locate Python ──────────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python was not found in PATH.
    echo.
    echo   Please install Python 3.10 or newer:
    echo     https://www.python.org/downloads/
    echo.
    echo   During installation make sure to tick:
    echo     [x] Add Python to PATH
    echo.
    pause
    exit /b 1
)

REM ── 2. Check Python version (need 3.10+) ──────────────────────
for /f "tokens=2 delims= " %%V in ('python --version 2^>^&1') do set PYVER=%%V
echo Python found: %PYVER%

for /f "tokens=1,2 delims=." %%A in ("%PYVER%") do (
    set PY_MAJOR=%%A
    set PY_MINOR=%%B
)

if !PY_MAJOR! LSS 3 (
    echo [ERROR] Python 3.10+ is required.  Found %PYVER%.
    echo   Download: https://www.python.org/downloads/
    pause
    exit /b 1
)
if !PY_MAJOR! EQU 3 if !PY_MINOR! LSS 10 (
    echo [ERROR] Python 3.10+ is required.  Found %PYVER%.
    echo   Download: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [OK] Python version is compatible.

REM ── 3. Ensure pip is available ────────────────────────────────
python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] pip is not available.
    echo   Run:  python -m ensurepip --upgrade
    pause
    exit /b 1
)
echo [OK] pip is available.

REM ── 4. Upgrade pip + setuptools to meet build requirements ────
echo.
echo [Step 1/3]  Upgrading pip and setuptools...
python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
    echo [ERROR] Could not upgrade pip / setuptools.
    pause
    exit /b 1
)
echo [OK] pip and setuptools are up to date.

REM ── 5. Install the package ────────────────────────────────────
echo.
echo [Step 2/3]  Installing ei-fragment-calculator...
cd /d "%~dp0"
python -m pip install -e .
if errorlevel 1 (
    echo.
    echo [ERROR] Installation failed.
    echo   Try running this script as Administrator, or run:
    echo     python -m pip install --user -e .
    pause
    exit /b 1
)
echo [OK] Package installed successfully.

REM ── 6. Verify the entry point is reachable ────────────────────
echo.
echo [Step 3/3]  Verifying installation...
ei-fragment-calc --help >nul 2>&1
if errorlevel 1 (
    echo [WARN] 'ei-fragment-calc' command not found in PATH.
    echo   The package is installed but the Scripts folder may not be in PATH.
    echo   You can still run the tool with:
    echo     python -m ei_fragment_calculator.cli  your_spectra.sdf
    echo.
) else (
    echo [OK] Command 'ei-fragment-calc' is ready.
)

REM ── 7. Summary ────────────────────────────────────────────────
echo.
echo ============================================================
echo  Installation complete!
echo ============================================================
echo.
echo  HOW TO RUN
echo  ----------
echo  Basic (writes Caffeine-EXACT.sdf automatically):
echo    ei-fragment-calc Spectra\Caffeine.sdf
echo.
echo  Best candidate per peak + isotope patterns:
echo    ei-fragment-calc Spectra\Caffeine.sdf --best-only --isotope
echo.
echo  Your own spectra:
echo    ei-fragment-calc path\to\your_spectra.sdf --best-only
echo.
echo  All options:
echo    ei-fragment-calc --help
echo.
echo  Run tests:
echo    python -m pip install -e ".[dev]"
echo    pytest
echo.
pause
endlocal
