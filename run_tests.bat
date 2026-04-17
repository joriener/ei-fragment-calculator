@echo off
cd /d D:\tmp\ei-fragment-calculator
C:\Python\Python311\python.exe -m pytest tests -x -q --tb=short > D:\tmp\ei-fragment-calculator\pytest_result.txt 2>&1
echo Exit code: %ERRORLEVEL% >> D:\tmp\ei-fragment-calculator\pytest_result.txt
