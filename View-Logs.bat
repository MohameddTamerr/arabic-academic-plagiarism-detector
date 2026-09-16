@echo off
setlocal EnableExtensions
title Arabic Academic Plagiarism Detector - View Logs

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "PYTHON="
if exist "%ROOT%\Runtime\python.exe" (
    set "PYTHON=%ROOT%\Runtime\python.exe"
) else if not exist "%ROOT%\App" (
    rem Fallback to system Python ONLY in developer/source repository mode
    where python >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON=python"
    )
)

if "%PYTHON%"=="" (
    echo ======================================================================
    echo RUNTIME NOT FOUND
    echo ======================================================================
    echo Python executable was not found in:
    echo   %ROOT%\Runtime\python.exe
    echo.
    echo This portable package requires the bundled Runtime.
    echo System Python fallback is disabled in production portable mode.
    echo ======================================================================
    pause
    exit /b 1
)

set "CLI="
if exist "%ROOT%\Tools\portable_cli.py" (
    set "CLI=%ROOT%\Tools\portable_cli.py"
) else if exist "%ROOT%\tools\portable_cli.py" (
    set "CLI=%ROOT%\tools\portable_cli.py"
)

if "%CLI%"=="" (
    echo ======================================================================
    echo PORTABLE CLI NOT FOUND
    echo ======================================================================
    echo Could not locate portable_cli.py in:
    echo   %ROOT%\Tools\portable_cli.py
    echo ======================================================================
    pause
    exit /b 1
)

cd /d "%ROOT%"
"%PYTHON%" "%CLI%" logs

pause
