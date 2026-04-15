@echo off
setlocal EnableDelayedExpansion
title EI Fragment Calculator -- Windows Build

echo.
echo ============================================================
echo  EI Fragment Calculator  --  Standalone Windows Build
echo ============================================================
echo.

REM ── Locate Python ──────────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    pause & exit /b 1
)

REM ── Ensure PyInstaller is available ──────────────────────────
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing PyInstaller...
    python -m pip install pyinstaller --quiet
)

REM ── Clean previous build ─────────────────────────────────────
if exist build\EI-Fragment-Calculator (
    echo [INFO] Removing old build\EI-Fragment-Calculator...
    rmdir /s /q build\EI-Fragment-Calculator
)
if exist dist\EI-Fragment-Calculator (
    echo [INFO] Removing old dist\EI-Fragment-Calculator...
    rmdir /s /q dist\EI-Fragment-Calculator
)

REM ── Install package in editable mode ─────────────────────────
echo [INFO] Installing package...
python -m pip install -e . --quiet
if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause & exit /b 1
)

REM ── Build ────────────────────────────────────────────────────
echo.
echo [INFO] Running PyInstaller...
echo.
python -m PyInstaller build_windows.spec --clean --noconfirm
if errorlevel 1 (
    echo.
    echo [ERROR] PyInstaller build failed.
    pause & exit /b 1
)

echo.
echo ============================================================
echo  Build complete!
echo  Output: dist\EI-Fragment-Calculator\
echo  Run:    dist\EI-Fragment-Calculator\EI-Fragment-Calculator.exe
echo ============================================================
echo.
pause
endlocal
