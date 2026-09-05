@echo off
chcp 65001 >nul
title الفحص التشخيصي لمنظومة كشف الاستلال الأكاديمي

set "SCRIPT_DIR=%~dp0"
if exist "%SCRIPT_DIR%Runtime\python.exe" (
    set "PYTHON_EXE=%SCRIPT_DIR%Runtime\python.exe"
) else (
    set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" "%SCRIPT_DIR%Tools\portable_cli.py" check
pause
